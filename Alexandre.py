from collections import deque


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
