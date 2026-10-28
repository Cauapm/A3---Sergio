from collections import deque
from datetime import datetime
from typing import Any, List, Optional, Protocol
from uuid import uuid4
import pandas as pd

from modelos import Cliente, NivelPrioridade, StatusCliente
from extracao import ExtratorFila


class ProtocoloRepositorio(Protocol):
    def inserir(self, cliente: Cliente) -> None: ...
    def registrar_chamada(self, cliente_id: str) -> None: ...
    def listar_aguardando(self) -> List[Cliente]: ...


def aplicar_starvation(
    fila_super: deque,
    fila_padrao: deque,
    fila_convencional: deque,
    etapa: int,
    contador: int,
    limites: tuple = (2, 1),
):
    """Função de controle anti-starvation (regra de Alexandre.py):
    - Prioridade absoluta para 80+ (fila_super), sem alterar nem reiniciar o ciclo 2:1.
    - Ciclo 2:1 entre Prioridade Padrão e Convencional.

    Retorna:
        (cliente, fila_origem, nova_etapa, novo_contador)
    """
    if not (fila_super or fila_padrao or fila_convencional):
        return None, None, 0, 0

    if fila_super:
        cliente = fila_super.popleft()
        return cliente, fila_super, etapa, contador

    filas_ciclo = (fila_padrao, fila_convencional)
    for _ in range(2):
        fila = filas_ciclo[etapa]
        limite = limites[etapa]
        if contador >= limite or not fila:
            etapa = (etapa + 1) % 2
            contador = 0
            continue

        cliente = fila.popleft()
        contador += 1
        if contador >= limite or not fila:
            etapa = (etapa + 1) % 2
            contador = 0
        return cliente, fila, etapa, contador

    return None, None, etapa, contador


class GerenciadorFilas:
    """Gerenciador de filas estruturado com prioridade absoluta para 80+
    e ciclo anti-starvation 2:1 entre Prioridade Padrão e Convencional,
    integrado aos dados do extracao.py (Supabase)."""

    def __init__(
        self,
        extrator: Optional[ExtratorFila] = None,
        auto_carregar: bool = False,
        repositorio: Optional[Any] = None,
    ):
        self._fila_super: deque[Cliente] = deque()
        self._fila_padrao: deque[Cliente] = deque()
        self._fila_convencional: deque[Cliente] = deque()
        self._etapa = 0
        self._contador = 0
        self._limites = (2, 1)
        self._filas_ciclo = (self._fila_padrao, self._fila_convencional)
        self._extrator = extrator if extrator is not None else ExtratorFila()
        self._repositorio = repositorio

        if repositorio is not None:
            auto_carregar = False

        if auto_carregar:
            self.carregar_fila()

    def _fila_para(self, nivel: NivelPrioridade) -> deque:
        if nivel == NivelPrioridade.SUPER_PRIORIDADE or nivel == 0:
            return self._fila_super
        if nivel == NivelPrioridade.PRIORIDADE_PADRAO or nivel == 1:
            return self._fila_padrao
        if nivel == NivelPrioridade.CONVENCIONAL or nivel == 2:
            return self._fila_convencional
        raise ValueError("Prioridade inválida.")

    def carregar_fila(self, df: Optional[pd.DataFrame] = None) -> None:
        """Carrega e repovoa as filas em memória a partir dos dados do extracao.py."""
        if df is None:
            if self._extrator is None:
                self._extrator = ExtratorFila()
            df = self._extrator.converter_pandas()

        self._fila_super.clear()
        self._fila_padrao.clear()
        self._fila_convencional.clear()
        self._etapa = 0
        self._contador = 0

        if df is None or df.empty:
            return

        if "status" in df.columns:
            df = df[df["status"].astype(str).str.strip().str.lower() == "aguardando"]

        if "data_chegada" in df.columns:
            df = df.sort_values(by="data_chegada")

        for _, row in df.iterrows():
            cliente = self._converter_linha_para_cliente(row)
            self._fila_para(cliente.nivel_prioridade).append(cliente)

    def sincronizar_estado(self) -> None:
        """Repovoa as filas em memória a partir do extracao.py ou repositório."""
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
            self._etapa = 0
            self._contador = 0
            return

        self.carregar_fila()

    def adicionar_cliente(self, cliente: Cliente) -> None:
        fila = self._fila_para(cliente.nivel_prioridade)
        if self._repositorio is not None and hasattr(self._repositorio, "inserir"):
            self._repositorio.inserir(cliente)
        fila.append(cliente)

    def chamar_proximo(self) -> Optional[Cliente]:
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

    def _proximo_do_ciclo(self):
        for _ in range(2):
            fila = self._filas_ciclo[self._etapa]
            limite = self._limites[self._etapa]
            if self._contador >= limite or not fila:
                self._avancar_etapa()
                continue

            cliente = fila.popleft()
            self._contador += 1
            if self._contador >= limite or not fila:
                self._avancar_etapa()
            return cliente, fila
        return None

    def _avancar_etapa(self) -> None:
        self._etapa = (self._etapa + 1) % 2
        self._contador = 0

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

    def tamanhos(self) -> dict:
        return {
            "super": len(self._fila_super),
            "padrao": len(self._fila_padrao),
            "convencional": len(self._fila_convencional),
        }

    def estado_contadores(self) -> dict:
        return {
            "padrao": self._contador if self._etapa == 0 else 2,
            "convencional": self._contador if self._etapa == 1 else 0,
        }

    def fase_atual(self) -> str:
        if self._fila_super:
            return "super (prioridade absoluta)"
        nomes = ("padrao", "convencional")
        return f"{nomes[self._etapa]} ({self._contador}/{self._limites[self._etapa]})"


def prova_funcionamento_padrao() -> None:
    """Função temporária de prova do funcionamento padrão conectada ao Supabase."""
    gerenciador = GerenciadorFilas(auto_carregar=True)
    print("=== [Alexandre.py] Prova de Funcionamento Padrão (80+ Absoluto + Ciclo 2:1) ===")
    print("Tamanhos iniciais das filas:", gerenciador.tamanhos())
    print("Contadores do ciclo 2:1:", gerenciador.estado_contadores())
    print("Fase atual:", gerenciador.fase_atual())

    print("\n--- Simulação de Chamadas (Dados Reais do Supabase) ---")
    for i in range(1, 13):
        cliente = gerenciador.chamar_proximo()
        if not cliente:
            print(f"Chamada {i:02d}: Filas vazias.")
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
