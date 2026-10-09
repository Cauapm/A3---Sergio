import os
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()


def get_credential(name: str):
    val = os.getenv(name)
    if not val:
        try:
            val = st.secrets.get(name)
        except Exception:
            pass
    return val


@st.cache_resource
def get_supabase():
    url = get_credential("SUPABASE_URL")
    key = get_credential("SUPABASE_KEY")
    if not url or not key:
        st.error(
            "Defina SUPABASE_URL e SUPABASE_KEY no arquivo .env (local) "
            "ou nos Secrets do Streamlit Cloud."
        )
        st.stop()
    if "supabase.com/dashboard/project/" in url:
        project_ref = url.rstrip("/").split("/")[-1]
        url = f"https://{project_ref}.supabase.co"
    return create_client(url, key)


st.set_page_config(page_title="Fila Bancária", layout="wide")
st.title("🏦 Sistema de Gerenciamento de Fila Bancária")

supabase = get_supabase()
st.success("✅ Conectado com sucesso ao Supabase.")

try:
    # Verificação rápida das tabelas
    res_tipos = supabase.table("tipo_prioridade").select("*").execute()
    res_fila = supabase.table("clientes_fila").select("id", count="exact").execute()
    total_fila = len(res_fila.data) if res_fila.data else 0

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Categorias Configuradas", len(res_tipos.data))
    with col2:
        st.metric("Clientes Atuais na Fila", total_fila)
except Exception as e:
    st.info(f"Aguardando sincronização do schema no Supabase: {e}")
