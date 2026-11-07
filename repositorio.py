"""Persistência das chamadas no Supabase.

As regras ficam nas funções SQL chamar_cliente / finalizar_atendimento
(supabase/migrations/20261107150000_seguranca_e_atendimentos.sql), que rodam
numa transação: dois guichês não conseguem chamar o mesmo cliente.
"""


class RepositorioSupabase:
    """Repositório usado pelo GerenciadorFilas (hook registrar_chamada)."""

    def __init__(self, client):
        self._client = client

    def registrar_chamada(self, cliente_id: str, guiche: int = 1) -> dict:
        """Marca o cliente como em_atendimento e grava a linha em atendimentos."""
        res = self._client.rpc(
            "chamar_cliente", {"p_cliente_id": cliente_id, "p_guiche": int(guiche)}
        ).execute()
        return res.data

    def finalizar_atendimento(self, guiche: int) -> dict:
        """Fecha o atendimento aberto do guichê e marca o cliente como atendido."""
        res = self._client.rpc("finalizar_atendimento", {"p_guiche": int(guiche)}).execute()
        return res.data
