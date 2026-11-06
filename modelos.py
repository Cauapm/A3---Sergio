from dataclasses import dataclass
from datetime import datetime
from enum import Enum, IntEnum
from uuid import uuid4


class NivelPrioridade(IntEnum):
    """Níveis de prioridade legal. IntEnum porque:
      1) O schema do Supabase armazena nivel_prioridade como Int;
      2) A hierarquia é ordinal (permite comparação direta).

    Base legal:
      - SUPER_PRIORIDADE:  Lei 13.466/2017 (80+ anos)
      - PRIORIDADE_PADRAO: Lei 10.048/2000 e Lei 12.764/2012
      - CONVENCIONAL:      sem previsão legal
    """
    SUPER_PRIORIDADE = 0
    PRIORIDADE_PADRAO = 1
    CONVENCIONAL = 2


class StatusCliente(Enum):
    """Status fortemente tipado. Valores casam com a coluna status
    do Supabase. O GerenciadorFilas NÃO altera este campo — apenas
    o carrega e devolve. Transições de status são responsabilidade
    da camada de persistência (Frente 1)."""
    AGUARDANDO = "aguardando"
    ATENDIDO = "atendido"


@dataclass(frozen=True)
class Cliente:
    """Entidade imutável (frozen=True) que representa um cliente
    na fila do banco. Contrato de dados entre todas as camadas."""
    id: str
    nome: str
    nivel_prioridade: NivelPrioridade
    motivo: str
    data_chegada: datetime
    status: StatusCliente = StatusCliente.AGUARDANDO

    @classmethod
    def criar(cls, nome: str, nivel: NivelPrioridade, motivo: str) -> "Cliente":
        """Fábrica simples que gera id e timestamp automaticamente."""
        return cls(
            id=str(uuid4()),
            nome=nome,
            nivel_prioridade=nivel,
            motivo=motivo,
            data_chegada=datetime.now(),
        )
