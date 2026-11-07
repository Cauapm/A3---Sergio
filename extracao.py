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
        """Monta a URL da API REST do Supabase (só clientes aguardando, em ordem de chegada)."""
        return f"{self.supabase_url}/rest/v1/clientes_fila?status=eq.aguardando&order=data_chegada.asc"

    def converter_pandas(self) -> pd.DataFrame:
        """Extrai os dados da API e converte para DataFrame.
        A coluna "id" (UUID) é mantida: é ela que a tabela atendimentos referencia."""
        # Chave no header, não na URL, para não aparecer em logs.
        cabecalhos = {"apikey": self.supabase_key, "Authorization": f"Bearer {self.supabase_key}"}
        self.df = pd.read_json(self.url, storage_options=cabecalhos)
        self.df = self.df.drop(columns=["id_motivo"], errors="ignore")
        return self.df

if __name__ == "__main__":
    extrator = ExtratorFila()
    df = extrator.converter_pandas()
    print("--- Dados Brutos (amostra) ---")
    print(df.head(30))
