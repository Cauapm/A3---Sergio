import streamlit as st

from conexao import get_credential

st.set_page_config(page_title="Fila Bancária", page_icon="🏦", layout="wide")

# Números no mesmo estilo condensado do painel (Archivo, largura 62).
st.html("""<style>
[data-testid="stMetricValue"] { font-variation-settings: 'wdth' 62; font-weight: 800; font-variant-numeric: tabular-nums; }
</style>""")

paginas = st.navigation([
    st.Page("views/inicio.py", title="Início", icon=":material/home:", default=True),
    st.Page("views/painel.py", title="Painel de atendimento", icon=":material/confirmation_number:"),
    st.Page("views/banco.py", title="Banco de dados", icon=":material/database:"),
])

with st.sidebar:
    st.markdown("**Operador**")
    st.text_input("Senha do operador", type="password", key="senha_operador",
                  help="Libera chamar, finalizar, gerar e apagar dados.")
    if not get_credential("DASHBOARD_SENHA"):
        st.caption("Defina DASHBOARD_SENHA no .env ou em Secrets para liberar as ações.")

paginas.run()
