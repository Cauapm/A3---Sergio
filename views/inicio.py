import streamlit as st

from conexao import PRIORIDADES, get_supabase, mensagem_erro

st.title("Fila Bancária")
st.markdown(
    "Organiza o atendimento da agência pelas prioridades legais. Quem tem 80 anos ou mais "
    "é chamado sempre primeiro; entre prioridade padrão e convencional, o sistema chama "
    "**2 prioritários para 1 convencional**, para ninguém ficar esperando para sempre."
)

supabase = get_supabase()
if supabase is None:
    st.error("Defina SUPABASE_URL e SUPABASE_KEY no .env (local) ou em Secrets (Streamlit Cloud).")
    st.stop()

try:
    contagens = {
        nivel: supabase.table("clientes_fila").select("id", count="exact", head=True)
        .eq("status", "aguardando").eq("nivel_prioridade", nivel).execute().count or 0
        for nivel in PRIORIDADES
    }
    chamadas = supabase.table("atendimentos").select("id_chamada", count="exact", head=True).execute().count or 0
except Exception as e:
    st.error(mensagem_erro(e))
    st.stop()

st.subheader("Agora na agência")
cols = st.columns(4)
cols[0].metric("Aguardando", sum(contagens.values()))
for col, (nivel, (nome, _)) in zip(cols[1:], PRIORIDADES.items()):
    col.metric(nome, contagens[nivel])
st.caption(f"{chamadas} {'chamada registrada' if chamadas == 1 else 'chamadas registradas'} nos guichês.")

st.subheader("Ordem de chamada")
c1, c2, c3 = st.columns(3)
with c1, st.container(border=True):
    st.markdown(f"**1. {PRIORIDADES[0][0]}**")
    st.caption(PRIORIDADES[0][1])
    st.write("Passa na frente de todos, por ordem de chegada.")
with c2, st.container(border=True):
    st.markdown(f"**2. {PRIORIDADES[1][0]}**")
    st.caption(PRIORIDADES[1][1])
    st.write("Até 2 chamadas seguidas antes de chamar um convencional.")
with c3, st.container(border=True):
    st.markdown(f"**3. {PRIORIDADES[2][0]}**")
    st.caption(PRIORIDADES[2][1])
    st.write("1 chamada a cada ciclo, garantida mesmo com muitos prioritários.")

st.subheader("Por onde começar")
st.page_link("views/painel.py", label="Abrir o painel de atendimento", icon=":material/confirmation_number:")
st.page_link("views/banco.py", label="Ver e gerenciar os dados de demonstração", icon=":material/database:")
