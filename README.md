# Fila Bancária

Sistema de gerenciamento de filas bancárias com prioridades legais (Leis 13.466/2017, 10.048/2000 e 12.764/2012), prioridade absoluta para 80+ e controle anti-inanição (ciclo 2:1 entre Prioridade Padrão e Convencional) desenvolvido em Python, Streamlit e Supabase (PostgreSQL).

---

## 1. Configuração das Variáveis de Ambiente (.env)

Copie o arquivo de exemplo:
```bash
cp .env.example .env
```

Preencha o `.env` com o endereço do projeto (terminando em `.supabase.co`) e a **chave secreta** do Supabase (*Project Settings → API Keys → Secret keys*, começa com `sb_secret_`):
```env
SUPABASE_URL=https://<seu-projeto>.supabase.co
SUPABASE_KEY=sb_secret_...
```

> A chave secreta ignora o RLS, por isso **nunca** a coloque no README, em commits ou em código que rode no navegador. O Streamlit roda no servidor, então ela fica protegida no `.env` (local) ou em *Secrets* (Streamlit Cloud). Desde a migration `20261107150000_seguranca_e_atendimentos.sql`, a chave pública (`sb_publishable_`) não acessa mais as tabelas da fila.

### Banco de dados
Projeto novo: rode `supabase/setup_supabase.sql` no *SQL Editor* do Supabase.
Projeto já existente: rode só `supabase/migrations/20261107150000_seguranca_e_atendimentos.sql`.

---

## 2. Instalação e Execução

### Instalar dependências
```bash
pip install -r requirements.txt
```

### Gerar dados de teste (Faker)
Para simular clientes na fila com a distribuição estocástica do projeto (15% Superprioridade, 35% Prioridade Padrão, 50% Convencional):
```bash
# Gera 20 clientes por padrão
python gerar_clientes.py

# Ou especifique a quantidade desejada (ex: 50 clientes)
python gerar_clientes.py 50
```

### Iniciar o painel Streamlit
```bash
streamlit run app.py
```

O app tem três páginas no menu lateral:
- **Início** (`views/inicio.py`): resumo da fila e a ordem de chamada.
- **Painel de atendimento** (`views/painel.py` + `views/painel.html`): senha atual, as três filas e indicadores, atualizados a cada 5 s. Depois de clicar em **Iniciar atendimento** e digitar a senha de operador na barra lateral (`DASHBOARD_SENHA` no `.env` ou em *Secrets*), escolha o guichê e use:
  - **Chamar próximo**: aplica a regra (80+ primeiro, depois 2:1), marca o cliente como `em_atendimento` e grava a linha em `atendimentos`.
  - **Finalizar atendimento**: fecha o atendimento aberto do guichê (`data_finalizado`) e marca o cliente como `atendido`.
- **Banco de dados** (`views/banco.py`): mostra as tabelas e permite **gerar clientes de demonstração** e **apagar todos os dados** (com confirmação e senha de operador).

Um guichê só chama o próximo depois de finalizar o atual, e dois guichês não conseguem chamar o mesmo cliente (as funções SQL rodam numa transação).

No **Streamlit Community Cloud**, use `app.py` como *Main file* e cadastre `SUPABASE_URL`, `SUPABASE_KEY` (secreta) e `DASHBOARD_SENHA` em *Secrets*. O painel fica visível para quem tiver o link; só os botões de atendimento exigem a senha.
