import os
from dotenv import load_dotenv
import pandas as pd
pd.set_option('display.max_columns', None)
load_dotenv()

class ExtratorFila:
    """Classe responsável por conectar, extrair e manipular os dados da fila bancária."""

    def __init__(self):
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY")
        self.url = self.gerar_url()
        self.df = None

    def gerar_url(self) -> str:
        """Monta a URL para consumo da API REST do Supabase."""
        return f"{self.supabase_url}/rest/v1/clientes_fila?apikey={self.supabase_key}"

    def converter_pandas(self) -> pd.DataFrame:
        """Extrai os dados da API e converte para DataFrame, removendo colunas desnecessárias."""
        self.df = pd.read_json(self.url)
        self.df = self.df.drop(columns=["id", "id_motivo"], errors="ignore")
        return self.df

    def aplicar_starvation(self):
        self.df = self.df.sort_values(by="nivel_prioridade")
        return self.df


if __name__ == "__main__":
    extrator = ExtratorFila()
    df = extrator.converter_pandas()
    print("--- Dados Brutos (amostra) ---")
    print(df.head())

    print("\n--- Dados Ordenados por Prioridade (amostra) ---")
    df_prioridade = extrator.aplicar_starvation()
    print(df_prioridade.head())