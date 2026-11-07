"""Conexão única com o Supabase e helpers compartilhados pelas páginas do Streamlit."""
import hmac
import os
import threading

import streamlit as st
from dotenv import load_dotenv
from supabase import create_client

from gerenciador_filas import GerenciadorFilas
from repositorio import RepositorioSupabase

load_dotenv()


def get_credential(name: str):
    """Lê do .env (local) ou dos Secrets (Streamlit Cloud). O valor é copiado para
    os.environ porque extracao.py lê direto de lá."""
    val = os.getenv(name)
    if not val:
        try:
            val = st.secrets.get(name)
        except Exception:
            val = None
    if val:
        val = str(val).strip()  # espaço ou quebra de linha colados junto geram "Invalid API key"
        os.environ[name] = val
    return val


@st.cache_resource
def get_supabase():
    url = get_credential("SUPABASE_URL")
    key = get_credential("SUPABASE_KEY")
    if not url or not key:
        return None
    if "supabase.com/dashboard/project/" in url:
        ref = url.rstrip("/").split("/")[-1]
        url = f"https://{ref}.supabase.co"
        os.environ["SUPABASE_URL"] = url
    return create_client(url, key)


@st.cache_resource
def get_gerenciador():
    """Um gerenciador por servidor, compartilhado por todos os guichês, para o ciclo 2:1
    valer para a agência inteira. O lock evita duas chamadas ao mesmo tempo.
    shortcut: o ciclo 2:1 fica na memória e recomeça se o app reiniciar; persistir no banco se isso importar."""
    client = get_supabase()
    repositorio = RepositorioSupabase(client) if client else None
    return GerenciadorFilas(repositorio=repositorio), threading.Lock()


def operador_autorizado() -> bool:
    """Ações que alteram o banco exigem DASHBOARD_SENHA (.env ou Secrets).
    Sem senha configurada, ficam bloqueadas.
    shortcut: uma senha para todos os operadores; trocar por login (st.login) se houver operadores diferentes."""
    senha = get_credential("DASHBOARD_SENHA")
    digitada = st.session_state.get("senha_operador", "")
    return bool(senha) and hmac.compare_digest(digitada.encode(), senha.encode())


def mensagem_erro(e: Exception) -> str:
    """Mensagem do Postgres/Supabase (APIError.message) ou o texto do erro."""
    msg = getattr(e, "message", None) or str(e)
    if "Invalid API key" in msg:
        return ("O Supabase recusou a chave (Invalid API key). Confira se SUPABASE_KEY é a chave "
                "secreta atual (sb_secret_...), copiada inteira, sem espaços.")
    return msg


PRIORIDADES = {
    0: ("Superprioridade", "80 anos ou mais (Lei 13.466/2017)"),
    1: ("Prioridade padrão", "Leis 10.048/2000 e 12.764/2012"),
    2: ("Convencional", "Sem prioridade legal"),
}
