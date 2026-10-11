import unittest

from modelos import Cliente, NivelPrioridade, StatusCliente
from gerenciador_filas import GerenciadorFilas


class RepositorioFalso:
    """Cumpre o ProtocoloRepositorio em memória, sem Supabase.
    Usado para testar a Frente 2 de forma isolada."""
    def __init__(self):
        self.inseridos = []
        self.chamadas = []
        self.falhar = False

    def inserir(self, cliente):
        if self.falhar:
            raise RuntimeError("banco caiu")
        self.inseridos.append(cliente.id)

    def listar_aguardando(self):
        return []

    def registrar_chamada(self, cid):
        if self.falhar:
            raise RuntimeError("banco caiu")
        self.chamadas.append(cid)


def _cliente(nome, nivel):
    return Cliente.criar(nome, nivel, "teste")


class TesteCiclo321(unittest.TestCase):

    def test_ciclo_321_com_filas_cheias(self):
        gerenciador = GerenciadorFilas()
        for i in range(3):
            gerenciador.adicionar_cliente(_cliente(f"S{i}", NivelPrioridade.SUPER_PRIORIDADE))
        for i in range(3):
            gerenciador.adicionar_cliente(_cliente(f"P{i}", NivelPrioridade.PRIORIDADE_PADRAO))
        for i in range(3):
            gerenciador.adicionar_cliente(_cliente(f"C{i}", NivelPrioridade.CONVENCIONAL))

        ordem = [gerenciador.chamar_proximo().nivel_prioridade for _ in range(6)]
        self.assertEqual(ordem, [
            NivelPrioridade.SUPER_PRIORIDADE,
            NivelPrioridade.SUPER_PRIORIDADE,
            NivelPrioridade.SUPER_PRIORIDADE,
            NivelPrioridade.PRIORIDADE_PADRAO,
            NivelPrioridade.PRIORIDADE_PADRAO,
            NivelPrioridade.CONVENCIONAL,
        ])


class TesteFIFO(unittest.TestCase):

    def test_fifo_convencional(self):
        gerenciador = GerenciadorFilas()
        nomes = ["A", "B", "C", "D", "E"]
        for nome in nomes:
            gerenciador.adicionar_cliente(_cliente(nome, NivelPrioridade.CONVENCIONAL))
        chamados = [gerenciador.chamar_proximo().nome for _ in range(5)]
        self.assertEqual(chamados, nomes)

    def test_fifo_super_com_intercalacao(self):
        gerenciador = GerenciadorFilas()
        for nome in ["S1", "S2", "S3", "S4"]:
            gerenciador.adicionar_cliente(_cliente(nome, NivelPrioridade.SUPER_PRIORIDADE))
        for nome in ["P1", "P2", "P3"]:
            gerenciador.adicionar_cliente(_cliente(nome, NivelPrioridade.PRIORIDADE_PADRAO))

        ordem = [gerenciador.chamar_proximo().nome for _ in range(5)]
        self.assertEqual(ordem, ["S1", "S2", "S3", "P1", "P2"])


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

    def test_anti_inanicao_sob_pico_de_super(self):
        gerenciador = GerenciadorFilas()
        for i in range(100):
            gerenciador.adicionar_cliente(_cliente(f"S{i}", NivelPrioridade.SUPER_PRIORIDADE))
        gerenciador.adicionar_cliente(_cliente("C1", NivelPrioridade.CONVENCIONAL))

        niveis = [gerenciador.chamar_proximo().nivel_prioridade for _ in range(4)]
        self.assertIn(NivelPrioridade.CONVENCIONAL, niveis)


class TesteFalhaRepositorio(unittest.TestCase):

    def test_falha_no_banco_devolve_cliente_a_fila(self):
        repositorio = RepositorioFalso()
        gerenciador = GerenciadorFilas(repositorio=repositorio)
        gerenciador.adicionar_cliente(_cliente("C1", NivelPrioridade.CONVENCIONAL))
        repositorio.falhar = True

        with self.assertRaises(RuntimeError):
            gerenciador.chamar_proximo()

        self.assertEqual(gerenciador.tamanhos()["convencional"], 1)
        self.assertEqual(repositorio.chamadas, [])

    def test_falha_no_banco_nao_consome_quantum(self):
        repositorio = RepositorioFalso()
        gerenciador = GerenciadorFilas(repositorio=repositorio)
        for i in range(3):
            gerenciador.adicionar_cliente(_cliente(f"S{i}", NivelPrioridade.SUPER_PRIORIDADE))

        repositorio.falhar = True
        with self.assertRaises(RuntimeError):
            gerenciador.chamar_proximo()
        repositorio.falhar = False

        self.assertEqual(gerenciador.tamanhos()["super"], 3)
        self.assertEqual(gerenciador.estado_contadores()["super"], 0)

        nomes = [gerenciador.chamar_proximo().nome for _ in range(3)]
        self.assertEqual(nomes, ["S0", "S1", "S2"])

    def test_adicionar_cliente_nao_enfileira_se_banco_falhar(self):
        repositorio = RepositorioFalso()
        gerenciador = GerenciadorFilas(repositorio=repositorio)
        repositorio.falhar = True

        with self.assertRaises(RuntimeError):
            gerenciador.adicionar_cliente(_cliente("X", NivelPrioridade.CONVENCIONAL))

        self.assertEqual(gerenciador.tamanhos()["convencional"], 0)


class TesteStatus(unittest.TestCase):

    def test_gerenciador_nao_altera_status(self):
        gerenciador = GerenciadorFilas()
        cliente = _cliente("A", NivelPrioridade.CONVENCIONAL)
        gerenciador.adicionar_cliente(cliente)
        chamado = gerenciador.chamar_proximo()
        self.assertIs(chamado.status, StatusCliente.AGUARDANDO)


if __name__ == "__main__":
    unittest.main(verbosity=2)
