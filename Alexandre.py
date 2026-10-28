from collections import deque
from typing import List, Optional, Protocol
from modelos import Cliente, NivelPrioridade


class ProtocoloRepositorio(Protocol):
    def inserir(self, cliente: Cliente) -> None: ...
    def registrar_chamada(self, cliente_id: str) -> None: ...
    def listar_aguardando(self) -> List[Cliente]: ...


class GerenciadorFilas:
    def __init__(self, repositorio: Optional[ProtocoloRepositorio] = None):
        self._fila_super = deque()
        self._fila_padrao = deque()
        self._fila_convencional = deque()
        self._etapa = 0
        self._contador = 0
        self._limites = (2, 1)
        self._filas_ciclo = (self._fila_padrao, self._fila_convencional)
        self._repositorio = repositorio

    def _fila_para(self, nivel: NivelPrioridade) -> deque:
        if nivel == NivelPrioridade.SUPER_PRIORIDADE:
            return self._fila_super
        if nivel == NivelPrioridade.PRIORIDADE_PADRAO:
            return self._fila_padrao
        if nivel == NivelPrioridade.CONVENCIONAL:
            return self._fila_convencional
        raise ValueError('Prioridade inválida.')

    def adicionar_cliente(self, cliente: Cliente) -> None:
        fila = self._fila_para(cliente.nivel_prioridade)
        if self._repositorio is not None:
            self._repositorio.inserir(cliente)
        fila.append(cliente)

    def chamar_proximo(self) -> Optional[Cliente]:
        if not (self._fila_super or self._fila_padrao or self._fila_convencional):
            self._etapa = 0
            self._contador = 0
            return None

        etapa_anterior = self._etapa
        contador_anterior = self._contador

        if self._fila_super:
            fila = self._fila_super
            cliente = fila.popleft()
        else:
            resultado = self._proximo_do_ciclo()
            if resultado is None:
                return None
            cliente, fila = resultado

        if self._repositorio is not None:
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

    def sincronizar_estado(self) -> None:
        if self._repositorio is None:
            return
        clientes = list(self._repositorio.listar_aguardando())
        novas_filas = (deque(), deque(), deque())
        for cliente in clientes:
            indice = int(cliente.nivel_prioridade)
            if indice not in (0, 1, 2):
                raise ValueError('Prioridade inválida.')
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

    def tamanhos(self) -> dict:
        return {'super': len(self._fila_super), 'padrao': len(self._fila_padrao),
                'convencional': len(self._fila_convencional)}

    def estado_contadores(self) -> dict:
        return {'padrao': self._contador if self._etapa == 0 else 2,
                'convencional': self._contador if self._etapa == 1 else 0}

    def fase_atual(self) -> str:
        if self._fila_super:
            return 'super (prioridade absoluta)'
        nomes = ('padrao', 'convencional')
        return f'{nomes[self._etapa]} ({self._contador}/{self._limites[self._etapa]})'