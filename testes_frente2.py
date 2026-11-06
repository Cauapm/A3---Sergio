import os
import unittest
import pandas as pd

from modelos import Cliente, NivelPrioridade, StatusCliente
from gerenciador_filas import GerenciadorFilas
from extracao import ExtratorFila


class ExtratorFalso:
    """Cumpre o papel do ExtratorFila em memória para testes isolados.
    Fornece DataFrames com a mesma estrutura de colunas do extracao.py."""
    def __init__(self, df: pd.DataFrame = None):
        if df is not None:
            self.df = df
        else:
            self.df = pd.DataFrame([
                {
                    "nome": "Super 1",
                    "cpf": "111.111.111-11",
                    "data_nascimento": "1940-01-01",
                    "nivel_prioridade": 0,
                    "motivo": "Idoso 80+ anos (Lei 13.466/2017)",
                    "status": "aguardando",
                    "data_chegada": "2026-10-09T10:00:00+00:00",
                },
                {
                    "nome": "Padrao 1",
                    "cpf": "222.222.222-22",
                    "data_nascimento": "1970-01-01",
                    "nivel_prioridade": 1,
                    "motivo": "PCD (Lei 10.048/2000)",
                    "status": "aguardando",
                    "data_chegada": "2026-10-09T10:01:00+00:00",
                },
                {
                    "nome": "Convencional 1",
                    "cpf": "333.333.333-33",
                    "data_nascimento": "1995-01-01",
                    "nivel_prioridade": 2,
                    "motivo": "Atendimento Convencional",
                    "status": "aguardando",
                    "data_chegada": "2026-10-09T10:02:00+00:00",
                },
            ])

    def converter_pandas(self) -> pd.DataFrame:
        return self.df.copy()


def _cliente(nome, nivel):
    return Cliente.criar(nome, nivel, "teste")


class TestePrioridadeAbsolutaECiclo21(unittest.TestCase):

    def test_prioridade_absoluta_80_mais_e_ciclo_21(self):
        gerenciador = GerenciadorFilas()
        for i in range(4):
            gerenciador.adicionar_cliente(_cliente(f"S{i}", NivelPrioridade.SUPER_PRIORIDADE))
        for i in range(3):
            gerenciador.adicionar_cliente(_cliente(f"P{i}", NivelPrioridade.PRIORIDADE_PADRAO))
        for i in range(3):
            gerenciador.adicionar_cliente(_cliente(f"C{i}", NivelPrioridade.CONVENCIONAL))

        ordem = [gerenciador.chamar_proximo().nivel_prioridade for _ in range(7)]
        self.assertEqual(ordem, [
            NivelPrioridade.SUPER_PRIORIDADE,
            NivelPrioridade.SUPER_PRIORIDADE,
            NivelPrioridade.SUPER_PRIORIDADE,
            NivelPrioridade.SUPER_PRIORIDADE,
            NivelPrioridade.PRIORIDADE_PADRAO,
            NivelPrioridade.PRIORIDADE_PADRAO,
            NivelPrioridade.CONVENCIONAL,
        ])

    def test_super_nao_altera_contador_do_ciclo_21(self):
        gerenciador = GerenciadorFilas()
        gerenciador.adicionar_cliente(_cliente("P0", NivelPrioridade.PRIORIDADE_PADRAO))
        gerenciador.adicionar_cliente(_cliente("P1", NivelPrioridade.PRIORIDADE_PADRAO))
        gerenciador.adicionar_cliente(_cliente("C0", NivelPrioridade.CONVENCIONAL))

        # Chama o primeiro padrão (contador fica 1/2)
        self.assertEqual(gerenciador.chamar_proximo().nome, "P0")

        # Chega um 80+ no meio do ciclo: deve ser atendido imediatamente sem resetar o ciclo 2:1
        gerenciador.adicionar_cliente(_cliente("S0", NivelPrioridade.SUPER_PRIORIDADE))
        self.assertEqual(gerenciador.chamar_proximo().nome, "S0")

        # Retoma o ciclo 2:1 exatamente de onde parou (P1 e depois C0)
        self.assertEqual(gerenciador.chamar_proximo().nome, "P1")
        self.assertEqual(gerenciador.chamar_proximo().nome, "C0")


class TesteFIFO(unittest.TestCase):

    def test_fifo_convencional(self):
        gerenciador = GerenciadorFilas()
        nomes = ["A", "B", "C", "D", "E"]
        for nome in nomes:
            gerenciador.adicionar_cliente(_cliente(nome, NivelPrioridade.CONVENCIONAL))
        chamados = [gerenciador.chamar_proximo().nome for _ in range(5)]
        self.assertEqual(chamados, nomes)

    def test_fifo_super_e_intercalacao_21(self):
        gerenciador = GerenciadorFilas()
        for nome in ["S1", "S2"]:
            gerenciador.adicionar_cliente(_cliente(nome, NivelPrioridade.SUPER_PRIORIDADE))
        for nome in ["P1", "P2", "P3"]:
            gerenciador.adicionar_cliente(_cliente(nome, NivelPrioridade.PRIORIDADE_PADRAO))
        for nome in ["C1", "C2"]:
            gerenciador.adicionar_cliente(_cliente(nome, NivelPrioridade.CONVENCIONAL))

        ordem = [gerenciador.chamar_proximo().nome for _ in range(5)]
        self.assertEqual(ordem, ["S1", "S2", "P1", "P2", "C1"])


class TesteFilasVazias(unittest.TestCase):

    def test_ciclo_encurta_quando_prioritarias_vazias(self):
        gerenciador = GerenciadorFilas()
        gerenciador.adicionar_cliente(_cliente("S1", NivelPrioridade.SUPER_PRIORIDADE))
        for i in range(5):
            gerenciador.adicionar_cliente(_cliente(f"C{i}", NivelPrioridade.CONVENCIONAL))

        niveis = [gerenciador.chamar_proximo().nivel_prioridade for _ in range(6)]
        self.assertEqual(niveis[0], NivelPrioridade.SUPER_PRIORIDADE)
        self.assertTrue(all(n == NivelPrioridade.CONVENCIONAL for n in niveis[1:]))

    def test_fila_convencional_vazia_nao_quebra(self):
        gerenciador = GerenciadorFilas()
        for i in range(4):
            gerenciador.adicionar_cliente(_cliente(f"S{i}", NivelPrioridade.SUPER_PRIORIDADE))
        for i in range(4):
            gerenciador.adicionar_cliente(_cliente(f"P{i}", NivelPrioridade.PRIORIDADE_PADRAO))

        for _ in range(8):
            self.assertIsNotNone(gerenciador.chamar_proximo())
        self.assertIsNone(gerenciador.chamar_proximo())

    def test_todas_vazias_retorna_none(self):
        self.assertIsNone(GerenciadorFilas().chamar_proximo())


class TesteAntiInanicao(unittest.TestCase):

    def test_anti_inanicao_sob_pico_de_padrao(self):
        gerenciador = GerenciadorFilas()
        for i in range(100):
            gerenciador.adicionar_cliente(_cliente(f"P{i}", NivelPrioridade.PRIORIDADE_PADRAO))
        gerenciador.adicionar_cliente(_cliente("C1", NivelPrioridade.CONVENCIONAL))

        niveis = [gerenciador.chamar_proximo().nivel_prioridade for _ in range(3)]
        self.assertEqual(niveis, [
            NivelPrioridade.PRIORIDADE_PADRAO,
            NivelPrioridade.PRIORIDADE_PADRAO,
            NivelPrioridade.CONVENCIONAL,
        ])


class TesteStatus(unittest.TestCase):

    def test_gerenciador_nao_altera_status(self):
        gerenciador = GerenciadorFilas()
        cliente = _cliente("A", NivelPrioridade.CONVENCIONAL)
        gerenciador.adicionar_cliente(cliente)
        chamado = gerenciador.chamar_proximo()
        self.assertIs(chamado.status, StatusCliente.AGUARDANDO)


class TesteIntegracaoExtracao(unittest.TestCase):
    """Testes de integração entre o ExtratorFila (extracao.py), Alexandre.py e o GerenciadorFilas."""

    def test_carregamento_com_extrator_falso(self):
        extrator = ExtratorFalso()
        gerenciador = GerenciadorFilas(extrator=extrator, auto_carregar=True)

        tamanhos = gerenciador.tamanhos()
        self.assertEqual(tamanhos["super"], 1)
        self.assertEqual(tamanhos["padrao"], 1)
        self.assertEqual(tamanhos["convencional"], 1)

    def test_filtro_status_aguardando(self):
        dados = [
            {"nome": "Aguardando", "cpf": "111", "nivel_prioridade": 0, "motivo": "M", "status": "aguardando", "data_chegada": "2026-10-09T10:00:00"},
            {"nome": "Atendido", "cpf": "222", "nivel_prioridade": 0, "motivo": "M", "status": "atendido", "data_chegada": "2026-10-09T10:01:00"},
            {"nome": "Cancelado", "cpf": "333", "nivel_prioridade": 1, "motivo": "M", "status": "cancelado", "data_chegada": "2026-10-09T10:02:00"},
        ]
        df = pd.DataFrame(dados)
        extrator = ExtratorFalso(df=df)
        gerenciador = GerenciadorFilas(extrator=extrator, auto_carregar=True)

        self.assertEqual(gerenciador.tamanhos()["super"], 1)
        self.assertEqual(gerenciador.tamanhos()["padrao"], 0)
        cliente = gerenciador.chamar_proximo()
        self.assertEqual(cliente.nome, "Aguardando")
        self.assertIsNone(gerenciador.chamar_proximo())

    def test_ordenacao_fifo_por_data_chegada(self):
        dados = [
            {"nome": "Terceiro", "cpf": "333", "nivel_prioridade": 2, "motivo": "C", "status": "aguardando", "data_chegada": "2026-10-09T10:15:00"},
            {"nome": "Primeiro", "cpf": "111", "nivel_prioridade": 2, "motivo": "C", "status": "aguardando", "data_chegada": "2026-10-09T10:05:00"},
            {"nome": "Segundo", "cpf": "222", "nivel_prioridade": 2, "motivo": "C", "status": "aguardando", "data_chegada": "2026-10-09T10:10:00"},
        ]
        extrator = ExtratorFalso(df=pd.DataFrame(dados))
        gerenciador = GerenciadorFilas(extrator=extrator, auto_carregar=True)

        ordem_chamada = [gerenciador.chamar_proximo().nome for _ in range(3)]
        self.assertEqual(ordem_chamada, ["Primeiro", "Segundo", "Terceiro"])

    def test_regra_alexandre_com_dados_extrator(self):
        # 2 super (prioridade absoluta), 3 padrao, 2 convencional (ciclo 2:1)
        dados = []
        for i in range(2):
            dados.append({"nome": f"S{i}", "cpf": f"S{i}", "nivel_prioridade": 0, "motivo": "S", "status": "aguardando", "data_chegada": f"2026-10-09T10:0{i}:00"})
        for i in range(3):
            dados.append({"nome": f"P{i}", "cpf": f"P{i}", "nivel_prioridade": 1, "motivo": "P", "status": "aguardando", "data_chegada": f"2026-10-09T10:1{i}:00"})
        for i in range(2):
            dados.append({"nome": f"C{i}", "cpf": f"C{i}", "nivel_prioridade": 2, "motivo": "C", "status": "aguardando", "data_chegada": f"2026-10-09T10:2{i}:00"})

        extrator = ExtratorFalso(df=pd.DataFrame(dados))
        gerenciador = GerenciadorFilas(extrator=extrator, auto_carregar=True)

        chamados = [gerenciador.chamar_proximo().nome for _ in range(6)]
        self.assertEqual(chamados, ["S0", "S1", "P0", "P1", "C0", "P2"])

    def test_sincronizar_estado_recarrega_dados(self):
        extrator = ExtratorFalso()
        gerenciador = GerenciadorFilas(extrator=extrator, auto_carregar=False)
        self.assertEqual(gerenciador.tamanhos()["super"], 0)

        gerenciador.sincronizar_estado()
        self.assertEqual(gerenciador.tamanhos()["super"], 1)

    def test_extracao_real_supabase(self):
        """Verifica conexão real com o Supabase via ExtratorFila se as variáveis de ambiente existirem."""
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            self.skipTest("SUPABASE_URL ou SUPABASE_KEY não configuradas no .env")

        extrator = ExtratorFila()
        try:
            df = extrator.converter_pandas()
        except Exception as exc:
            self.skipTest(f"Conexão de rede indisponível para o Supabase: {exc}")
        self.assertIsInstance(df, pd.DataFrame)

        gerenciador = GerenciadorFilas(extrator=extrator, auto_carregar=True)
        tamanhos = gerenciador.tamanhos()
        total_fila = sum(tamanhos.values())
        self.assertGreaterEqual(total_fila, 0)

        if total_fila > 0:
            cliente = gerenciador.chamar_proximo()
            self.assertIsInstance(cliente, Cliente)
            self.assertIn(cliente.nivel_prioridade, [
                NivelPrioridade.SUPER_PRIORIDADE,
                NivelPrioridade.PRIORIDADE_PADRAO,
                NivelPrioridade.CONVENCIONAL,
            ])


if __name__ == "__main__":
    unittest.main(verbosity=2)
