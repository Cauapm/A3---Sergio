from collections import deque
from datetime import datetime
from typing import Optional, Any
from uuid import uuid4
import pandas as pd

from modelos import Cliente, NivelPrioridade, StatusCliente
from extracao import ExtratorFila
from Alexandre import aplicar_starvation


class GerenciadorFilas:
    """Coração do sistema: três deques + escalonamento com prioridade absoluta
    para 80+ e ciclo anti-inanição 2:1 entre Prioridade Padrão e Convencional
    (utilizando a função aplicar_starvation do Alexandre.py).

    Comportamento do escalonamento:
        - Superprioridade (80+ anos): atendida sempre primeiro com prioridade
          absoluta (FIFO), sem alterar nem reiniciar o contador do ciclo 2:1.
        - Ciclo 2:1 (Padrão : Convencional): quando a fila 80+ está vazia,
          atende até 2 clientes da fila Padrão para 1 da fila Convencional.
          Filas vazias têm sua etapa avançada sem desperdiçar chamadas.

    Ordem de operações:
        - carregar_fila() / sincronizar_estado(): extrai os dados via ExtratorFila
          (do extracao.py) e popula as filas em memória respeitando a ordem
          de chegada (FIFO) e as prioridades legais.
        - chamar_proximo(): aplica aplicar_starvation() (de Alexandre.py)
          para retirar o próximo cliente elegível.
    """

    def __init__(
        self,
        extrator: Optional[ExtratorFila] = None,
        auto_carregar: bool = False,
        repositorio: Optional[Any] = None,
    ):
        self._fila_super: deque[Cliente] = deque()
        self._fila_padrao: deque[Cliente] = deque()
        self._fila_convencional: deque[Cliente] = deque()

        self._etapa: int = 0
        self._contador: int = 0
        self._limites: tuple = (2, 1)
        self._filas_ciclo = (self._fila_padrao, self._fila_convencional)

        self._extrator = extrator if extrator is not None else ExtratorFila()
        self._repositorio = repositorio

        if repositorio is not None:
            auto_carregar = False

        if auto_carregar:
            self.carregar_fila()

    # ------------------------------------------------------------------ #
    def carregar_fila(self, df: Optional[pd.DataFrame] = None) -> None:
        """Carrega e repovoa as filas em memória a partir dos dados do extracao.py."""
        if df is None:
            if self._extrator is None:
                self._extrator = ExtratorFila()
            df = self._extrator.converter_pandas()

        self._fila_super.clear()
        self._fila_padrao.clear()
        self._fila_convencional.clear()
        self._resetar_contadores()

        if df is None or df.empty:
            return

        # Filtra apenas clientes que estão aguardando
        if "status" in df.columns:
            df = df[df["status"].astype(str).str.strip().str.lower() == "aguardando"]

        # Garante a ordem de chegada (FIFO) dentro de cada prioridade
        if "data_chegada" in df.columns:
            df = df.sort_values(by="data_chegada")

        for _, row in df.iterrows():
            cliente = self._converter_linha_para_cliente(row)
            self._fila_para(cliente.nivel_prioridade).append(cliente)

    def sincronizar_estado(self) -> None:
        """Repovoa as filas em memória a partir do extracao.py (ou repositório legado)."""
        if self._repositorio is not None and hasattr(self._repositorio, "listar_aguardando"):
            clientes = list(self._repositorio.listar_aguardando())
            novas_filas = (deque(), deque(), deque())
            for cliente in clientes:
                indice = int(cliente.nivel_prioridade)
                if indice not in (0, 1, 2):
                    raise ValueError("Prioridade inválida.")
                novas_filas[indice].append(cliente)
            self._fila_super.clear()
            self._fila_padrao.clear()
            self._fila_convencional.clear()
            for destino, origem in zip(
                (self._fila_super, self._fila_padrao, self._fila_convencional), novas_filas
            ):
                destino.extend(origem)
            self._resetar_contadores()
            return

        self.carregar_fila()

    def adicionar_cliente(self, cliente: Cliente) -> None:
        """Adiciona um cliente diretamente à fila de prioridade correspondente."""
        fila = self._fila_para(cliente.nivel_prioridade)
        if self._repositorio is not None and hasattr(self._repositorio, "inserir"):
            self._repositorio.inserir(cliente)

        fila.append(cliente)

    def chamar_proximo(self) -> Optional[Cliente]:
        """Retira o próximo cliente elegível aplicando a função aplicar_starvation
        do Alexandre.py (80+ prioridade absoluta + ciclo 2:1).
        Caso exista um repositório configurado, notifica a chamada com rollback local se falhar."""
        etapa_anterior = self._etapa
        contador_anterior = self._contador

        cliente, fila, nova_etapa, novo_contador = aplicar_starvation(
            self._fila_super,
            self._fila_padrao,
            self._fila_convencional,
            self._etapa,
            self._contador,
            self._limites,
        )
        self._etapa = nova_etapa
        self._contador = novo_contador

        if cliente is None:
            return None

        if self._repositorio is not None and hasattr(self._repositorio, "registrar_chamada"):
            try:
                self._repositorio.registrar_chamada(cliente.id)
            except Exception:
                self._etapa = etapa_anterior
                self._contador = contador_anterior
                fila.appendleft(cliente)
                raise

        return cliente

    # ------------------------------------------------------------------ #
    # Introspecção
    # ------------------------------------------------------------------ #
    def tamanhos(self) -> dict:
        """Retorna o tamanho de cada fila — útil para painéis e debug."""
        return {
            "super": len(self._fila_super),
            "padrao": len(self._fila_padrao),
            "convencional": len(self._fila_convencional),
        }

    def estado_contadores(self) -> dict:
        """Retorna o valor atual dos contadores do ciclo 2:1."""
        return {
            "padrao": self._contador if self._etapa == 0 else 2,
            "convencional": self._contador if self._etapa == 1 else 0,
        }

    def fase_atual(self) -> str:
        """Indica em qual etapa estamos (super absoluta ou ciclo 2:1)."""
        if self._fila_super:
            return "super (prioridade absoluta)"
        nomes = ("padrao", "convencional")
        return f"{nomes[self._etapa]} ({self._contador}/{self._limites[self._etapa]})"

    # ------------------------------------------------------------------ #
    # Internos
    # ------------------------------------------------------------------ #
    def _converter_linha_para_cliente(self, row) -> Cliente:
        """Converte uma linha do DataFrame gerado pelo ExtratorFila em objeto Cliente."""
        data_chegada = row.get("data_chegada")
        if isinstance(data_chegada, str):
            try:
                data_chegada = datetime.fromisoformat(data_chegada)
            except Exception:
                data_chegada = datetime.now()
        elif isinstance(data_chegada, pd.Timestamp):
            data_chegada = data_chegada.to_pydatetime()
        elif not isinstance(data_chegada, datetime):
            data_chegada = datetime.now()

        status_val = str(row.get("status", "aguardando")).strip().lower()
        try:
            status_enum = StatusCliente(status_val)
        except ValueError:
            status_enum = StatusCliente.AGUARDANDO

        try:
            nivel = NivelPrioridade(int(row["nivel_prioridade"]))
        except (ValueError, TypeError, KeyError):
            nivel = NivelPrioridade.CONVENCIONAL

        cliente_id = str(row.get("id") or row.get("cpf") or uuid4())

        return Cliente(
            id=cliente_id,
            nome=str(row.get("nome", "Sem Nome")),
            nivel_prioridade=nivel,
            motivo=str(row.get("motivo", "")),
            data_chegada=data_chegada,
            status=status_enum,
        )

    def _fila_para(self, nivel: NivelPrioridade) -> deque:
        """Devolve a fila correta para o nível de prioridade informado."""
        if nivel == NivelPrioridade.SUPER_PRIORIDADE or nivel == 0:
            return self._fila_super
        if nivel == NivelPrioridade.PRIORIDADE_PADRAO or nivel == 1:
            return self._fila_padrao
        if nivel == NivelPrioridade.CONVENCIONAL or nivel == 2:
            return self._fila_convencional
        raise ValueError("Prioridade inválida.")

    def _tem_alguem(self) -> bool:
        """True se houver pelo menos um cliente em qualquer uma das filas."""
        return bool(self._fila_super or self._fila_padrao or self._fila_convencional)

    def _resetar_contadores(self) -> None:
        """Zera a etapa e o contador do ciclo 2:1."""
        self._etapa = 0
        self._contador = 0


def prova_funcionamento_padrao() -> None:
    """Função temporária de prova do funcionamento padrão conectada ao Supabase."""
    gerenciador = GerenciadorFilas(auto_carregar=True)
    print("--- [gerenciador_filas.py] Filas Carregadas a partir do extracao.py ---")
    print("Tamanhos das filas:", gerenciador.tamanhos())
    print("Contadores (ciclo 2:1):", gerenciador.estado_contadores())
    print("Fase atual:", gerenciador.fase_atual())

    print("\n--- Simulação de Chamadas (80+ Prioridade Absoluta + Ciclo 2:1) ---")
    for i in range(1, 13):
        cliente = gerenciador.chamar_proximo()
        if not cliente:
            print(f"Chamada {i:02d}: Ninguém na fila.")
            break
        print(
            f"Chamada {i:02d}: {cliente.nome:<25} | "
            f"Prioridade: {cliente.nivel_prioridade.name:<18} | "
            f"Motivo: {cliente.motivo}"
        )

    print("\n--- Estado após chamadas ---")
    print("Tamanhos restantes:", gerenciador.tamanhos())
    print("Contadores atuais:", gerenciador.estado_contadores())
    print("Próxima fase:", gerenciador.fase_atual())


if __name__ == "__main__":
    prova_funcionamento_padrao()


if __name__ == "__main__":
    prova_funcionamento_padrao()

