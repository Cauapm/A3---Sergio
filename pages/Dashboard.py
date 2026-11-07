import os
import json
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

from gerenciador_filas import GerenciadorFilas
from modelos import NivelPrioridade

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


def calcular_tempo_medio_espera(supabase_client):
    if not supabase_client:
        return None
    try:
        res = supabase_client.table("atendimentos").select("data_chamada,data_finalizado").not_.is_("data_finalizado", "null").execute()
        if not res.data:
            return None
        total_ms = 0
        count = 0
        for row in res.data:
            try:
                inicio = datetime.fromisoformat(row["data_chamada"].replace("Z", "+00:00"))
                fim = datetime.fromisoformat(row["data_finalizado"].replace("Z", "+00:00"))
                total_ms += (fim - inicio).total_seconds() * 1000
                count += 1
            except Exception:
                continue
        if count == 0:
            return None
        return total_ms / count
    except Exception:
        return None


def build_payload(sistema_iniciado: bool) -> dict:
    g = GerenciadorFilas(auto_carregar=True)  # recarrega as filas do Supabase a cada atualização

    tamanhos = g.tamanhos()
    supabase_client = get_supabase_client()

    total_aguardando = sum(tamanhos.values())
    atendimentos_count = 0
    if supabase_client:
        try:
            res = supabase_client.table("atendimentos").select("id_chamada", count="exact").execute()
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

    distribuicao = {
        "super": tamanhos["super"],
        "padrao": tamanhos["padrao"],
        "conv": tamanhos["convencional"],
    }

    # Sem data/hora no payload: se nada mudou o HTML fica idêntico e o Streamlit não recarrega o iframe.
    return {
        "systemctl": sistema_iniciado,
        "conexao": supabase_client is not None,
        "total": total_aguardando,
        **distribuicao,
        "atend": atendimentos_count,
        "tmed": tmed,
        "senha_atual": senha_atual,
        "filas": filas_dict,
        "distribuicao": distribuicao,
        "fase_atual": g.fase_atual(),
        "contadores": g.estado_contadores(),
    }


def render_html(payload) -> str:
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()
    # "</" escapado para que um nome vindo do banco não feche a tag <script>
    dados = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return html.replace("const DATA = null;", f"const DATA = {dados};", 1)


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

if st.button(
    "Sistema iniciado" if st.session_state.sistema_iniciado else "▶ Iniciar sistema",
    disabled=st.session_state.sistema_iniciado,
):
    st.session_state.sistema_iniciado = True
    st.rerun()

painel()
