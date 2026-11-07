import json
import os
from datetime import datetime

import streamlit as st

from conexao import get_gerenciador, get_supabase, mensagem_erro, operador_autorizado
from modelos import NivelPrioridade

REFRESH_SEGUNDOS = 5
HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "painel.html")


def calcular_tempo_medio_espera(supabase_client):
    """Média de (chamada no guichê - chegada na fila) dos clientes já chamados, em ms."""
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
    supabase_client = get_supabase()
    g, lock = get_gerenciador()
    with lock:
        g.sincronizar_estado(preservar_ciclo=True)  # recarrega as filas do Supabase
        tamanhos = g.tamanhos()
        filas = {"super": [], "padrao": [], "conv": []}
        for key, nivel in [("super", NivelPrioridade.SUPER_PRIORIDADE), ("padrao", NivelPrioridade.PRIORIDADE_PADRAO), ("conv", NivelPrioridade.CONVENCIONAL)]:
            for cliente in g._fila_para(nivel):
                filas[key].append({
                    "id": cliente.id,
                    "nome": cliente.nome,
                    "nivel_prioridade": int(cliente.nivel_prioridade),
                    "motivo": cliente.motivo,
                    "data_chegada": cliente.data_chegada.isoformat() if cliente.data_chegada else None,
                })
        fase_atual = g.fase_atual()

    atendimentos_count = supabase_client.table("atendimentos").select("id_chamada", count="exact", head=True).execute().count or 0

    senha_atual = None
    res = supabase_client.table("atendimentos").select(
        "cliente_id,guiche,data_chamada,data_finalizado,clientes_fila!inner(nome,motivo,nivel_prioridade,status)"
    ).order("data_chamada", desc=True).limit(1).execute()
    if res.data:
        row = res.data[0]
        cliente = row.get("clientes_fila", {})
        senha_atual = {
            "id": row.get("cliente_id"),
            "nome": cliente.get("nome"),
            "motivo": cliente.get("motivo"),
            "nivel_prioridade": cliente.get("nivel_prioridade"),
            "guiche": row.get("guiche"),
            "data_chamada": row.get("data_chamada"),
            "status": cliente.get("status"),
        }

    # Sem data/hora no payload: se nada mudou o HTML fica idêntico e o Streamlit não recarrega o iframe.
    return {
        "conexao": True,
        "sistema": sistema_iniciado,
        "total": sum(tamanhos.values()),
        "atend": atendimentos_count,
        "tmed": calcular_tempo_medio_espera(supabase_client),
        "senha_atual": senha_atual,
        "filas": filas,
        "fase_atual": fase_atual,
    }


def render_html(payload) -> str:
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()
    # "</" escapado para que um nome vindo do banco não feche a tag <script>
    dados = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return html.replace("const DATA = null;", f"const DATA = {dados};", 1)


def chamar_proximo(guiche: int):
    if not operador_autorizado():
        st.session_state.aviso = ("error", "Digite a senha do operador na barra lateral.")
        return
    g, lock = get_gerenciador()
    try:
        with lock:
            g.sincronizar_estado(preservar_ciclo=True)
            cliente = g.chamar_proximo(guiche)
    except Exception as e:
        st.session_state.aviso = ("error", mensagem_erro(e))
        return
    if cliente is None:
        st.session_state.aviso = ("info", "Ninguém aguardando. Gere clientes de demonstração na página Banco de dados.")
    else:
        st.session_state.aviso = ("success", f"Guichê {guiche} chamou {cliente.nome}.")


def finalizar(guiche: int):
    if not operador_autorizado():
        st.session_state.aviso = ("error", "Digite a senha do operador na barra lateral.")
        return
    g, _ = get_gerenciador()
    try:
        g._repositorio.finalizar_atendimento(guiche)
        st.session_state.aviso = ("success", f"Guichê {guiche} finalizou o atendimento.")
    except Exception as e:
        st.session_state.aviso = ("error", mensagem_erro(e))


@st.fragment(run_every=REFRESH_SEGUNDOS)
def painel():
    erro = None
    try:
        payload = build_payload(st.session_state.sistema_iniciado)
    except Exception as e:
        payload, erro = None, mensagem_erro(e)  # o HTML mostra "Banco desconectado"
    if erro:
        st.error(erro)
    # Dados do banco chegam como JSON escapado e o HTML escapa os textos antes de exibir.
    st.iframe(render_html(payload), height=1060)


if get_supabase() is None:
    st.error("Defina SUPABASE_URL e SUPABASE_KEY no .env (local) ou em Secrets (Streamlit Cloud).")
    st.stop()

st.session_state.setdefault("sistema_iniciado", False)
iniciado = st.session_state.sistema_iniciado
liberado = iniciado and operador_autorizado()

with st.container(border=True):
    c_ini, c_guiche, c_chamar, c_finalizar = st.columns([2, 1, 2, 2], vertical_alignment="bottom")
    with c_ini:
        if st.button("Sistema iniciado" if iniciado else "Iniciar atendimento", icon=":material/play_arrow:",
                     disabled=iniciado, width="stretch"):
            st.session_state.sistema_iniciado = True
            st.rerun()
    with c_guiche:
        guiche = st.number_input("Guichê", min_value=1, max_value=99, value=1, step=1)
    with c_chamar:
        st.button("Chamar próximo", icon=":material/campaign:", type="primary", disabled=not liberado,
                  width="stretch", on_click=chamar_proximo, args=(guiche,))
    with c_finalizar:
        st.button("Finalizar atendimento", icon=":material/check_circle:", disabled=not liberado,
                  width="stretch", on_click=finalizar, args=(guiche,))
    if iniciado and not operador_autorizado():
        st.caption("Digite a senha do operador na barra lateral para chamar e finalizar.")

if "aviso" in st.session_state:
    tipo, texto = st.session_state.pop("aviso")
    getattr(st, tipo)(texto)

painel()
