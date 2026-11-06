# Fila Bancária

Sistema de gerenciamento de filas bancárias com prioridades legais (Leis 13.466/2017, 10.048/2000 e 12.764/2012), controle anti-inanição (Anti-Starvation 3:2:1) desenvolvido em Python, Streamlit e Supabase (PostgreSQL).

---

## 1. Configuração das Variáveis de Ambiente (.env)

Copie o arquivo de exemplo:
```bash
cp .env.example .env
```

Certifique-se de que o seu `.env` possui o endereço de API do Supabase (terminando em `.supabase.co`):
```env
SUPABASE_URL=https://agopdtmcvwqhihofkiyt.supabase.co
SUPABASE_KEY=sb_publishable_4D4yvKbq8cJehPjnY9v7rg_RjnY-dCI
```

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
