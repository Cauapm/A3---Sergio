import pandas as pd
import streamlit as st

from conexao import PRIORIDADES, get_gerenciador, get_supabase, mensagem_erro, operador_autorizado
from gerar_clientes import gerar_cliente

STATUS = {"aguardando": "Aguardando", "em_atendimento": "Em atendimento", "atendido": "Atendido", "cancelado": "Cancelado"}
UUID_NULO = "00000000-0000-0000-0000-000000000000"

st.title("Banco de dados")
st.markdown("Os dados abaixo vêm direto do Supabase. Use esta página para preparar uma demonstração "
            "e para limpar tudo depois.")

supabase = get_supabase()
if supabase is None:
    st.error("Defina SUPABASE_URL e SUPABASE_KEY no .env (local) ou em Secrets (Streamlit Cloud).")
    st.stop()

autorizado = operador_autorizado()

if "aviso_banco" in st.session_state:
    tipo, texto = st.session_state.pop("aviso_banco")
    getattr(st, tipo)(texto)


def gerar(qtd: int):
    if not operador_autorizado():
        st.session_state.aviso_banco = ("error", "Digite a senha do operador na barra lateral.")
        return
    try:
        supabase.table("clientes_fila").insert([gerar_cliente() for _ in range(qtd)]).execute()
        st.session_state.aviso_banco = ("success", f"{qtd} clientes de demonstração entraram na fila.")
    except Exception as e:
        st.session_state.aviso_banco = ("error", mensagem_erro(e))


def apagar_tudo():
    if not operador_autorizado():
        st.session_state.aviso_banco = ("error", "Digite a senha do operador na barra lateral.")
        return
    try:
        # atendimentos saem junto (ON DELETE CASCADE); o filtro é exigido pela API para delete em massa
        supabase.table("clientes_fila").delete().neq("id", UUID_NULO).execute()
        get_gerenciador.clear()  # o ciclo 2:1 recomeça junto com a fila
        st.session_state.confirmar_apagar = False
        st.session_state.aviso_banco = ("success", "Todos os clientes e atendimentos foram apagados.")
    except Exception as e:
        st.session_state.aviso_banco = ("error", mensagem_erro(e))


try:
    clientes = supabase.table("clientes_fila").select(
        "id,nome,cpf,nivel_prioridade,motivo,status,data_chegada"
    ).order("data_chegada").execute().data or []
    atendimentos = supabase.table("atendimentos").select(
        "guiche,data_chamada,data_finalizado,clientes_fila!inner(nome)"
    ).order("data_chamada", desc=True).execute().data or []
except Exception as e:
    st.error(mensagem_erro(e))
    st.stop()

df = pd.DataFrame(clientes, columns=["id", "nome", "cpf", "nivel_prioridade", "motivo", "status", "data_chegada"])

cols = st.columns(4)
cols[0].metric("Clientes cadastrados", len(df))
for col, chave in zip(cols[1:], ["aguardando", "em_atendimento", "atendido"]):
    col.metric(STATUS[chave], int((df["status"] == chave).sum()))

aba_clientes, aba_atendimentos, aba_gerenciar = st.tabs(
    [f"Clientes ({len(df)})", f"Atendimentos ({len(atendimentos)})", "Gerenciar dados"]
)

with aba_clientes:
    if df.empty:
        st.info("Nenhum cliente no banco. Gere clientes de demonstração na aba Gerenciar dados.")
    else:
        tabela = pd.DataFrame({
            "Nome": df["nome"],
            "CPF": df["cpf"].fillna("").str.replace(r"^\d{3}\.\d{3}", "***.***", regex=True),
            "Prioridade": df["nivel_prioridade"].map(lambda n: PRIORIDADES.get(n, ("?",))[0]),
            "Motivo": df["motivo"],
            "Situação": df["status"].map(STATUS),
            "Chegada": pd.to_datetime(df["data_chegada"], utc=True, format="ISO8601").dt.tz_convert("America/Sao_Paulo"),
        })
        st.dataframe(tabela, hide_index=True, width="stretch",
                     column_config={"Chegada": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm")})

with aba_atendimentos:
    if not atendimentos:
        st.info("Nenhum atendimento ainda. Os registros aparecem aqui quando um guichê chama alguém no painel.")
    else:
        fuso = "America/Sao_Paulo"
        tabela = pd.DataFrame({
            "Cliente": [a["clientes_fila"]["nome"] for a in atendimentos],
            "Guichê": [a["guiche"] for a in atendimentos],
            "Chamada": pd.to_datetime([a["data_chamada"] for a in atendimentos], utc=True, format="ISO8601").tz_convert(fuso),
            "Finalizado": pd.to_datetime([a["data_finalizado"] for a in atendimentos], utc=True, format="ISO8601").tz_convert(fuso),
        })
        st.dataframe(tabela, hide_index=True, width="stretch", column_config={
            "Chamada": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
            "Finalizado": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
        })

with aba_gerenciar:
    if not autorizado:
        st.warning("Digite a senha do operador na barra lateral para gerar ou apagar dados.")

    with st.container(border=True):
        st.markdown("**Gerar clientes de demonstração**")
        st.caption("Nomes e CPFs fictícios. Distribuição do projeto: 15% superprioridade, "
                   "35% prioridade padrão e 50% convencional.")
        c1, c2 = st.columns([1, 2], vertical_alignment="bottom")
        qtd = c1.number_input("Quantidade", min_value=1, max_value=200, value=20, step=5)
        c2.button(f"Gerar {qtd} clientes", icon=":material/person_add:", disabled=not autorizado,
                  on_click=gerar, args=(int(qtd),))

    with st.container(border=True):
        st.markdown("**Apagar todos os dados**")
        st.caption(f"Remove os {len(df)} clientes e os {len(atendimentos)} atendimentos. "
                   "Os tipos e motivos de prioridade continuam. Não dá para desfazer.")
        confirmado = st.checkbox("Entendo que todos os clientes e atendimentos serão apagados",
                                 key="confirmar_apagar", disabled=not autorizado)
        st.button("Apagar todos os dados", icon=":material/delete_forever:", type="primary",
                  disabled=not (autorizado and confirmado), on_click=apagar_tudo)
