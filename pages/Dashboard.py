import os
import hmac
import json
import threading
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

from gerenciador_filas import GerenciadorFilas
from modelos import NivelPrioridade
from repositorio import RepositorioSupabase

REFRESH_SEGUNDOS = 5
HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")


@st.cache_resource
def get_supabase_client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        return None
    if "supabase.com/dashboard/project/" in url:
        ref = url.rstrip("/").split("/")[-1]
        url = f"https://{ref}.supabase.co"
    return create_client(url, key)


@st.cache_resource
def get_gerenciador():
    """Um gerenciador por servidor, compartilhado por todos os guichês, para o ciclo 2:1
    valer para a agência inteira. O lock evita duas chamadas ao mesmo tempo.
    shortcut: o ciclo 2:1 fica na memória e recomeça se o app reiniciar; persistir no banco se isso importar."""
    client = get_supabase_client()
    repositorio = RepositorioSupabase(client) if client else None
    return GerenciadorFilas(repositorio=repositorio), threading.Lock()


def calcular_tempo_medio_espera(supabase_client):
    """Média de (chamada no guichê - chegada na fila) dos clientes já chamados, em ms."""
    if not supabase_client:
        return None
    try:
        res = supabase_client.table("atendimentos").select("data_chamada,clientes_fila!inner(data_chegada)").execute()
        esperas = []
        for row in res.data or []:
            try:
                chamada = datetime.fromisoformat(row["data_chamada"].replace("Z", "+00:00"))
                chegada = datetime.fromisoformat(row["clientes_fila"]["data_chegada"].replace("Z", "+00:00"))
                esperas.append((chamada - chegada).total_seconds() * 1000)
            except Exception:
                continue
        return sum(esperas) / len(esperas) if esperas else None
    except Exception:
        return None


def build_payload(sistema_iniciado: bool) -> dict:
    g, lock = get_gerenciador()
    with lock:
        g.sincronizar_estado(preservar_ciclo=True)  # recarrega as filas do Supabase
        tamanhos = g.tamanhos()
        filas_dict = {"super": [], "padrao": [], "conv": []}
        for key, nivel in [("super", NivelPrioridade.SUPER_PRIORIDADE), ("padrao", NivelPrioridade.PRIORIDADE_PADRAO), ("conv", NivelPrioridade.CONVENCIONAL)]:
            for cliente in g._fila_para(nivel):
                filas_dict[key].append({
                    "id": cliente.id,
                    "nome": cliente.nome,
                    "nivel_prioridade": int(cliente.nivel_prioridade),
                    "motivo": cliente.motivo,
                    "data_chegada": cliente.data_chegada.isoformat() if cliente.data_chegada else None,
                    "status": cliente.status.value,
                })
        fase_atual = g.fase_atual()
        contadores = g.estado_contadores()

    supabase_client = get_supabase_client()

    atendimentos_count = 0
    if supabase_client:
        try:
            res = supabase_client.table("atendimentos").select("id_chamada", count="exact", head=True).execute()
            atendimentos_count = res.count or 0
        except Exception:
            pass

    tmed = calcular_tempo_medio_espera(supabase_client)

    senha_atual = None
    if supabase_client:
        try:
            res = supabase_client.table("atendimentos").select("id_chamada,cliente_id,guiche,data_chamada,data_finalizado,clientes_fila!inner(nivel_prioridade,status)").order("data_chamada", desc=True).limit(1).execute()
            if res.data:
                row = res.data[0]
                cliente = row.get("clientes_fila", {})
                senha_atual = {
                    "id": row.get("cliente_id"),
                    "tipo": cliente.get("nivel_prioridade"),
                    "nivel_prioridade": cliente.get("nivel_prioridade"),
                    "guiche": row.get("guiche"),
                    "data_chamada": row.get("data_chamada"),
                    "data_finalizado": row.get("data_finalizado"),
                    "status": cliente.get("status", "aguardando"),
                }
        except Exception:
            pass

    distribuicao = {
        "super": tamanhos["super"],
        "padrao": tamanhos["padrao"],
        "conv": tamanhos["convencional"],
    }

    # Sem data/hora no payload: se nada mudou o HTML fica idêntico e o Streamlit não recarrega o iframe.
    return {
        "systemctl": sistema_iniciado,
        "conexao": supabase_client is not None,
        "total": sum(tamanhos.values()),
        **distribuicao,
        "atend": atendimentos_count,
        "tmed": tmed,
        "senha_atual": senha_atual,
        "filas": filas_dict,
        "distribuicao": distribuicao,
        "fase_atual": fase_atual,
        "contadores": contadores,
    }


def render_html(payload) -> str:
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()
    # "</" escapado para que um nome vindo do banco não feche a tag <script>
    dados = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return html.replace("const DATA = null;", f"const DATA = {dados};", 1)


def mensagem_erro(e: Exception) -> str:
    """Mensagem do RAISE EXCEPTION do Postgres (APIError.message) ou o texto do erro."""
    return getattr(e, "message", None) or str(e)


def operador_autorizado() -> bool:
    """Chamar/finalizar exigem a senha DASHBOARD_SENHA (.env ou Secrets do Streamlit Cloud).
    Sem senha configurada, os botões ficam bloqueados.
    shortcut: uma senha para todos os operadores e guichê escolhido na tela; trocar por login
    (st.login) com guichê vinculado ao usuário se houver operadores diferentes."""
    senha = os.getenv("DASHBOARD_SENHA")
    digitada = st.session_state.get("senha_operador", "")
    return bool(senha) and hmac.compare_digest(digitada.encode(), senha.encode())


def chamar_proximo(guiche: int):
    if not operador_autorizado():
        st.session_state.aviso = ("error", "Senha de operador incorreta.")
        return
    g, lock = get_gerenciador()
    if g._repositorio is None:
        st.session_state.aviso = ("error", "Supabase não configurado (SUPABASE_URL / SUPABASE_KEY).")
        return
    try:
        with lock:
            g.sincronizar_estado(preservar_ciclo=True)
            cliente = g.chamar_proximo(guiche)
    except Exception as e:
        st.session_state.aviso = ("error", mensagem_erro(e))
        return
    if cliente is None:
        st.session_state.aviso = ("info", "Ninguém aguardando na fila.")
    else:
        st.session_state.aviso = ("success", f"Guichê {guiche}: chamando **{cliente.nome}** ({cliente.motivo or cliente.nivel_prioridade.name}).")


def finalizar(guiche: int):
    if not operador_autorizado():
        st.session_state.aviso = ("error", "Senha de operador incorreta.")
        return
    g, _ = get_gerenciador()
    if g._repositorio is None:
        st.session_state.aviso = ("error", "Supabase não configurado (SUPABASE_URL / SUPABASE_KEY).")
        return
    try:
        g._repositorio.finalizar_atendimento(guiche)
        st.session_state.aviso = ("success", f"Guichê {guiche}: atendimento finalizado.")
    except Exception as e:
        st.session_state.aviso = ("error", mensagem_erro(e))


@st.fragment(run_every=REFRESH_SEGUNDOS)
def painel():
    try:
        payload = build_payload(st.session_state.sistema_iniciado)
    except Exception:
        payload = None  # Supabase fora do ar: o HTML mostra "Banco: Desconectado"
    # Dados do banco chegam como JSON escapado e o HTML escapa nome/motivo antes de exibir.
    st.iframe(render_html(payload), height=1000)


st.set_page_config(page_title="Fila Bancária — Dashboard", layout="wide")
st.session_state.setdefault("sistema_iniciado", False)

iniciado = st.session_state.sistema_iniciado
if not os.getenv("DASHBOARD_SENHA"):
    st.warning("Defina DASHBOARD_SENHA no .env (ou em Secrets no Streamlit Cloud) para liberar os botões de atendimento.")
st.text_input("Senha do operador", type="password", key="senha_operador")
liberado = iniciado and operador_autorizado()
col_ini, col_guiche, col_chamar, col_finalizar = st.columns([2, 1, 2, 2], vertical_alignment="bottom")
with col_ini:
    if st.button("Sistema iniciado" if iniciado else "▶ Iniciar sistema", disabled=iniciado, use_container_width=True):
        st.session_state.sistema_iniciado = True
        st.rerun()
with col_guiche:
    guiche = st.number_input("Guichê", min_value=1, max_value=99, value=1, step=1)
with col_chamar:
    st.button("📣 Chamar próximo", disabled=not liberado, use_container_width=True,
              on_click=chamar_proximo, args=(guiche,))
with col_finalizar:
    st.button("✅ Finalizar atendimento", disabled=not liberado, use_container_width=True,
              on_click=finalizar, args=(guiche,))

if "aviso" in st.session_state:
    tipo, texto = st.session_state.pop("aviso")
    getattr(st, tipo)(texto)

painel()
