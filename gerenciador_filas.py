from collections import deque
from datetime import datetime
from typing import Optional, Any
from uuid import uuid4
import pandas as pd

from modelos import Cliente, NivelPrioridade, StatusCliente
from extracao import ExtratorFila


class GerenciadorFilas:
    """Coração do sistema: três deques + escalonamento com pesos 3:2:1.

    Comportamento do ciclo:
        A fila convencional recebe 1 chamada a cada bloco de
        (até 3 super + até 2 padrão). Filas vazias têm seu quantum
        pulado — o ciclo ENCURTA em vez de desperdiçar chamadas.
        Isso garante anti-inanição da fila convencional.

        O que ele NÃO garante: SLA temporal ("ninguém espera X min").

    Ordem de operações:
        - carregar_fila() / sincronizar_estado(): extrai os dados via ExtratorFila
          (do extracao.py) e popula as filas em memória respeitando a ordem
          de chegada (FIFO) e as prioridades legais.
        - chamar_proximo(): retira o próximo cliente elegível de acordo com
          o escalonamento 3:2:1 (Superprioridade : Prioridade Padrão : Convencional).
    """

    QUANTUM_SUPER = 3
    QUANTUM_PADRAO = 2

    def __init__(
        self,
        extrator: Optional[ExtratorFila] = None,
        auto_carregar: bool = False,
        repositorio: Optional[Any] = None,
    ):
        self._fila_super: deque[Cliente] = deque()
        self._fila_padrao: deque[Cliente] = deque()
        self._fila_convencional: deque[Cliente] = deque()

        self._contador_super: int = 0
        self._contador_padrao: int = 0
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
        """Repovoa as filas em memória a partir do extracao.py (compatibilidade)."""
        self.carregar_fila()

    def adicionar_cliente(self, cliente: Cliente) -> None:
        """Adiciona um cliente diretamente à fila de prioridade correspondente."""
        if self._repositorio is not None and hasattr(self._repositorio, "inserir"):
            self._repositorio.inserir(cliente)

        self._fila_para(cliente.nivel_prioridade).append(cliente)

    def chamar_proximo(self) -> Optional[Cliente]:
        """Retira o próximo cliente elegível segundo o ciclo 3:2:1.
        Caso exista um repositório configurado, notifica a chamada com rollback local se falhar."""
        contador_super_antes = self._contador_super
        contador_padrao_antes = self._contador_padrao

        cliente = self._selecionar_proximo()
        if cliente is None:
            return None

        if self._repositorio is not None and hasattr(self._repositorio, "registrar_chamada"):
            try:
                self._repositorio.registrar_chamada(cliente.id)
            except Exception:
                self._contador_super = contador_super_antes
                self._contador_padrao = contador_padrao_antes
                self._fila_para(cliente.nivel_prioridade).appendleft(cliente)
                raise

        return cliente

    def _selecionar_proximo(self) -> Optional[Cliente]:
        """Aplica o ciclo 3:2:1 e devolve o próximo cliente, ou None
        se todas as filas estiverem vazias."""
        if not self._tem_alguem():
            self._resetar_contadores()
            return None

        if self._fila_super and self._contador_super < self.QUANTUM_SUPER:
            cliente = self._fila_super.popleft()
            self._contador_super += 1
            return cliente

        if self._fila_padrao and self._contador_padrao < self.QUANTUM_PADRAO:
            cliente = self._fila_padrao.popleft()
            self._contador_padrao += 1
            return cliente

        if self._fila_convencional:
            cliente = self._fila_convencional.popleft()
            self._resetar_contadores()
            return cliente

        # Nenhuma fila elegível neste instante: reinicia ciclo e tenta de novo.
        self._resetar_contadores()
        return self._selecionar_proximo()

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
        """Retorna o valor atual dos contadores do ciclo 3:2:1."""
        return {"super": self._contador_super, "padrao": self._contador_padrao}

    def fase_atual(self) -> str:
        """Indica em qual etapa do ciclo 3:2:1 estamos — apenas inspeção."""
        if self._contador_super < self.QUANTUM_SUPER:
            return f"super ({self._contador_super}/{self.QUANTUM_SUPER})"
        if self._contador_padrao < self.QUANTUM_PADRAO:
            return f"padrao ({self._contador_padrao}/{self.QUANTUM_PADRAO})"
        return "convencional (próxima chamada)"

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
        return self._fila_convencional

    def _tem_alguem(self) -> bool:
        """True se houver pelo menos um cliente em qualquer uma das filas."""
        return bool(self._fila_super or self._fila_padrao or self._fila_convencional)

    def _resetar_contadores(self) -> None:
        """Zera os contadores do ciclo (Passo 4 do algoritmo 3:2:1)."""
        self._contador_super = 0
        self._contador_padrao = 0


if __name__ == "__main__":
    gerenciador = GerenciadorFilas(auto_carregar=True)
    print("--- Filas Carregadas a partir do extracao.py ---")
    print("Tamanhos das filas:", gerenciador.tamanhos())
    print("Contadores:", gerenciador.estado_contadores())
    print("Fase atual:", gerenciador.fase_atual())

    print("\n--- Simulação de Chamadas (Ciclo 3:2:1) ---")
    for i in range(1, 11):
        cliente = gerenciador.chamar_proximo()
        if not cliente:
            print(f"Chamada {i}: Ninguém na fila.")
            break
        print(f"Chamada {i:02d}: {cliente.nome:<25} | Prioridade: {cliente.nivel_prioridade.name:<18} | Motivo: {cliente.motivo}")

    print("\n--- Estado após chamadas ---")
    print("Tamanhos restantes:", gerenciador.tamanhos())
    print("Contadores atuais:", gerenciador.estado_contadores())
    print("Próxima fase:", gerenciador.fase_atual())
