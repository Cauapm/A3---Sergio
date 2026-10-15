from collections import deque
from typing import Optional, Protocol, List
from modelos import Cliente, NivelPrioridade


class ProtocoloRepositorio(Protocol):
    """Contrato (DIP) que a Frente 1 cumpre com o Supabase.

    Semântica de registrar_chamada():
        Persiste a transição correspondente a 'cliente foi chamado'.
        O valor exato gravado é decisão da Frente 1, alinhada com o
        schema. O Gerenciador não assume qual é.
    """
    def inserir(self, cliente: Cliente) -> None: ...
    def registrar_chamada(self, cliente_id: str) -> None: ...
    def listar_aguardando(self) -> List[Cliente]: ...


class GerenciadorFilas:
    """Coração do sistema: três deques + escalonamento com pesos 3:2:1.

    Comportamento do ciclo:
        A fila convencional recebe 1 chamada a cada bloco de
        (até 3 super + até 2 padrão). Filas vazias têm seu quantum
        pulado — o ciclo ENCURTA em vez de desperdiçar chamadas.
        Isso garante anti-inanição da fila convencional.

        O que ele NÃO garante: SLA temporal ("ninguém espera X min").

    Ordem de operações (importante):
        - adicionar_cliente(): persiste PRIMEIRO, enfileira depois.
          "Se não está no banco, não está na fila."
        - chamar_proximo(): tira da fila, tenta persistir; se falhar,
          restaura fila E contadores (a tentativa não consome quantum).
    """

    QUANTUM_SUPER = 3
    QUANTUM_PADRAO = 2

    def __init__(self, repositorio: Optional[ProtocoloRepositorio] = None):
        self._fila_super: deque[Cliente] = deque()
        self._fila_padrao: deque[Cliente] = deque()
        self._fila_convencional: deque[Cliente] = deque()

        self._contador_super: int = 0
        self._contador_padrao: int = 0
        self._repositorio = repositorio

    # ------------------------------------------------------------------ #
    def adicionar_cliente(self, cliente: Cliente) -> None:
        """Persiste primeiro, enfileira depois. Se o banco falhar, o
        cliente NÃO entra na fila em memória — evita divergência silenciosa."""
        if self._repositorio is not None:
            self._repositorio.inserir(cliente)

        self._fila_para(cliente.nivel_prioridade).append(cliente)

    def chamar_proximo(self) -> Optional[Cliente]:
        """Retira o próximo cliente elegível e notifica o repositório.
        Se a persistência falhar, restaura fila E contadores — a tentativa
        que falhou não consome posição no ciclo 3:2:1."""
        contador_super_antes = self._contador_super
        contador_padrao_antes = self._contador_padrao

        cliente = self._selecionar_proximo()
        if cliente is None:
            return None

        if self._repositorio is not None:
            try:
                self._repositorio.registrar_chamada(cliente.id)
            except Exception:
                # Restaura o estado exato de antes da seleção.
                # Recuperação LOCAL — não é transação distribuída.
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
    def sincronizar_estado(self) -> None:
        """Repovoa as filas em memória a partir do estado salvo no banco."""
        if self._repositorio is None:
            return
        self._fila_super.clear()
        self._fila_padrao.clear()
        self._fila_convencional.clear()
        for cliente in self._repositorio.listar_aguardando():
            self._fila_para(cliente.nivel_prioridade).append(cliente)

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
    def _fila_para(self, nivel: NivelPrioridade) -> deque:
        """Devolve a fila correta para o nível de prioridade informado."""
        if nivel == NivelPrioridade.SUPER_PRIORIDADE:
            return self._fila_super
        if nivel == NivelPrioridade.PRIORIDADE_PADRAO:
            return self._fila_padrao
        return self._fila_convencional

    def _tem_alguem(self) -> bool:
        """True se houver pelo menos um cliente em qualquer uma das filas."""
        return bool(self._fila_super or self._fila_padrao or self._fila_convencional)

    def _resetar_contadores(self) -> None:
        """Zera os contadores do ciclo (Passo 4 do algoritmo 3:2:1)."""
        self._contador_super = 0
        self._contador_padrao = 0
