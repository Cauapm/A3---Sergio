-- =====================================================================
-- Segurança + registro de atendimentos
--
-- ANTES de rodar: troque SUPABASE_KEY no .env (e nos Secrets do Streamlit)
-- pela chave SECRETA do projeto (Project Settings > API Keys > sb_secret_...).
-- Depois desta migration a chave pública (sb_publishable_...) não lê nem
-- altera mais nada nas tabelas da fila. O app Streamlit roda no servidor,
-- então a chave secreta nunca chega ao navegador.
-- =====================================================================

-- 1. Fecha as tabelas para a chave pública (anon/authenticated).
--    Sem policy, o RLS nega tudo; a service_role (chave secreta) ignora o RLS.
DROP POLICY IF EXISTS "Permitir todas operacoes em clientes_fila" ON clientes_fila;
DROP POLICY IF EXISTS "Permitir todas operacoes em atendimentos" ON atendimentos;

-- 2. As views de compatibilidade rodavam como o dono (postgres) e furariam o RLS.
ALTER VIEW cliente_fila SET (security_invoker = true);
ALTER VIEW atendimento SET (security_invoker = true);
REVOKE ALL ON cliente_fila, atendimento FROM anon, authenticated;

-- 3. Chamar cliente: marca em_atendimento e grava o atendimento numa só transação.
--    Falha se o cliente já foi chamado (outro guichê) ou se o guichê está ocupado.
CREATE OR REPLACE FUNCTION chamar_cliente(p_cliente_id UUID, p_guiche INT)
RETURNS atendimentos
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
    v_atendimento atendimentos;
BEGIN
    IF EXISTS (SELECT 1 FROM atendimentos WHERE guiche = p_guiche AND data_finalizado IS NULL) THEN
        RAISE EXCEPTION 'O guichê % ainda tem um atendimento em andamento. Finalize-o antes de chamar o próximo.', p_guiche;
    END IF;

    UPDATE clientes_fila SET status = 'em_atendimento'
     WHERE id = p_cliente_id AND status = 'aguardando';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Cliente % não está mais aguardando.', p_cliente_id;
    END IF;

    INSERT INTO atendimentos (cliente_id, guiche)
    VALUES (p_cliente_id, p_guiche)
    RETURNING * INTO v_atendimento;

    RETURN v_atendimento;
END;
$$;

-- 4. Finalizar o atendimento aberto de um guichê: grava data_finalizado e marca atendido.
CREATE OR REPLACE FUNCTION finalizar_atendimento(p_guiche INT)
RETURNS atendimentos
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
    v_atendimento atendimentos;
BEGIN
    UPDATE atendimentos SET data_finalizado = now()
     WHERE id_chamada = (
         SELECT id_chamada FROM atendimentos
          WHERE guiche = p_guiche AND data_finalizado IS NULL
          ORDER BY data_chamada DESC
          LIMIT 1
     )
    RETURNING * INTO v_atendimento;

    IF v_atendimento.id_chamada IS NULL THEN
        RAISE EXCEPTION 'O guichê % não tem atendimento em andamento.', p_guiche;
    END IF;

    UPDATE clientes_fila SET status = 'atendido' WHERE id = v_atendimento.cliente_id;
    RETURN v_atendimento;
END;
$$;

-- 5. Só a chave secreta pode chamar as funções.
REVOKE EXECUTE ON FUNCTION chamar_cliente(UUID, INT) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION finalizar_atendimento(INT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION chamar_cliente(UUID, INT) TO service_role;
GRANT EXECUTE ON FUNCTION finalizar_atendimento(INT) TO service_role;
