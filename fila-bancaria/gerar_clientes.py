import os
import random
from datetime import datetime, timezone
from dotenv import load_dotenv
from faker import Faker
from supabase import create_client

load_dotenv()

fake = Faker("pt_BR")

MOTIVOS_PADRAO = [
    ("Idoso 60-79 anos (Lei 10.048/2000)", 60, 79),
    ("Gestante (Lei 10.048/2000)", 18, 45),
    ("Lactante (Lei 10.048/2000)", 18, 45),
    ("Pessoa com criança de colo (Lei 10.048/2000)", 18, 50),
    ("Pessoa com deficiência - PCD (Lei 10.048/2000)", 18, 70),
    ("Pessoa com obesidade (Lei 10.048/2000)", 18, 70),
    ("Pessoa com Transtorno do Espectro Autista - TEA (Lei 12.764/2012)", 18, 70),
]


def gerar_cliente():
    """Gera dados de um cliente seguindo as probabilidades do item 6 do projeto:

    - 15% Superprioridade (80+ anos)
    - 35% Prioridade Padrão
    - 50% Convencional
    """
    categoria = random.choices([0, 1, 2], weights=[0.15, 0.35, 0.50], k=1)[0]
    nome = fake.name()
    cpf = fake.cpf()

    if categoria == 0:
        # Superprioridade: 80 anos ou mais
        data_nascimento = fake.date_of_birth(minimum_age=80, maximum_age=105)
        motivo = "Idoso 80+ anos (Lei 13.466/2017)"
    elif categoria == 1:
        # Prioridade Padrão
        motivo_escolhido, min_age, max_age = random.choice(MOTIVOS_PADRAO)
        data_nascimento = fake.date_of_birth(minimum_age=min_age, maximum_age=max_age)
        motivo = motivo_escolhido
    else:
        # Convencional: 18 a 59 anos
        data_nascimento = fake.date_of_birth(minimum_age=18, maximum_age=59)
        motivo = "Atendimento Convencional"

    return {
        "nome": nome,
        "cpf": cpf,
        "data_nascimento": data_nascimento.isoformat(),
        "nivel_prioridade": categoria,
        "motivo": motivo,
        "status": "aguardando",
    }


def popular_fila(quantidade=50, batch_size=25):
    """Insere clientes sintéticos na tabela clientes_fila via Supabase SDK."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    if not url or not key:
        print("Erro: SUPABASE_URL e SUPABASE_KEY não configuradas no .env")
        return

    if "supabase.com/dashboard/project/" in url:
        ref = url.rstrip("/").split("/")[-1]
        url = f"https://{ref}.supabase.co"

    client = create_client(url, key)
    print(f"Gerando {quantidade} clientes sintéticos para {url}...")

    clientes = [gerar_cliente() for _ in range(quantidade)]

    # Inserção em lotes
    total_inseridos = 0
    for i in range(0, len(clientes), batch_size):
        lote = clientes[i : i + batch_size]
        res = client.table("clientes_fila").insert(lote).execute()
        total_inseridos += len(res.data)
        print(f"Inseridos {total_inseridos}/{quantidade} clientes...")

    print(f"Concluído com sucesso! {total_inseridos} clientes adicionados à fila.")


if __name__ == "__main__":
    import sys

    qtd = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    popular_fila(quantidade=qtd)

