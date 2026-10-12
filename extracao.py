import os
from dotenv import load_dotenv
import pandas as pd
pd.set_option('display.max_columns', None)
load_dotenv()

def extrair_url():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    url = f"{supabase_url}/rest/v1/clientes_fila?apikey={supabase_key}"

    return url

def converter_pandas(url):
    df = pd.read_json(url)
    df = df.drop(columns=["id","id_motivo"])
    return df

def starvartion(df):
    df = df.sort_values(by='nivel_prioridade')

if __name__ == "__main__":
    url = extrair_url()
    print(converter_pandas(url))