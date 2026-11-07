-- 1. Status possíveis de cliente na fila
DO $$ BEGIN
    CREATE TYPE status_senha AS ENUM (
        'aguardando',
        'em_atendimento',
        'atendido',
        'cancelado'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 2. Tipos de prioridade (0 = Superprioridade, 1 = Prioridade Padrão, 2 = Convencional)
CREATE TABLE IF NOT EXISTS tipo_prioridade (
    id_prioridade INT PRIMARY KEY,
    nome VARCHAR(30) NOT NULL UNIQUE,
    descricao VARCHAR(255)
);

-- 3. Motivos legais de prioridade 
CREATE TABLE IF NOT EXISTS motivo_prioridade (
    id_motivo SERIAL PRIMARY KEY,
    id_prioridade INT NOT NULL REFERENCES tipo_prioridade(id_prioridade),
    descricao VARCHAR(255) NOT NULL UNIQUE
);

-- 4. Tabela principal de clientes na fila 
CREATE TABLE IF NOT EXISTS clientes_fila (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome VARCHAR(120) NOT NULL,
    cpf VARCHAR(14),
    data_nascimento DATE,
    nivel_prioridade INT NOT NULL REFERENCES tipo_prioridade(id_prioridade),
    motivo VARCHAR(255),
    id_motivo INT REFERENCES motivo_prioridade(id_motivo),
    status status_senha NOT NULL DEFAULT 'aguardando',
    data_chegada TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 5. Índice para otimização da consulta FIFO por nível de prioridade
CREATE INDEX IF NOT EXISTS idx_proximo_fila
    ON clientes_fila(nivel_prioridade, data_chegada)
    WHERE status = 'aguardando';

-- 6. Tabela de histórico de atendimentos no guichê 
CREATE TABLE IF NOT EXISTS atendimentos (
    id_chamada UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cliente_id UUID NOT NULL REFERENCES clientes_fila(id) ON DELETE CASCADE,
    guiche INT NOT NULL CHECK (guiche > 0),
    data_chamada TIMESTAMPTZ NOT NULL DEFAULT now(),
    data_finalizado TIMESTAMPTZ
);

-- 7. Views de compatibilidade caso alguém referencie no singular
CREATE OR REPLACE VIEW cliente_fila AS SELECT * FROM clientes_fila;
CREATE OR REPLACE VIEW atendimento AS SELECT * FROM atendimentos;

-- 8. Configuração de RLS (Row Level Security) para acesso seguro via Supabase
ALTER TABLE tipo_prioridade ENABLE ROW LEVEL SECURITY;
ALTER TABLE motivo_prioridade ENABLE ROW LEVEL SECURITY;
ALTER TABLE clientes_fila ENABLE ROW LEVEL SECURITY;
ALTER TABLE atendimentos ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    CREATE POLICY "Permitir leitura de tipo_prioridade" ON tipo_prioridade FOR SELECT USING (true);
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE POLICY "Permitir leitura de motivo_prioridade" ON motivo_prioridade FOR SELECT USING (true);
EXCEPTION WHEN duplicate_object THEN null; END $$;

-- 9. Carga de Dados Iniciais (Seed)
INSERT INTO tipo_prioridade (id_prioridade, nome, descricao) VALUES
(0, 'Superprioridade', 'Indivíduos com 80 anos ou mais (Lei 13.466/2017)'),
(1, 'Prioridade Padrão', 'Idosos (60-79 anos), gestantes, lactantes, pessoas com crianças de colo, obesos, PCD (Lei 10.048/2000) e Autistas (Lei 12.764/2012)'),
(2, 'Convencional', 'Clientes não enquadrados nas prioridades legais')
ON CONFLICT (id_prioridade) DO NOTHING;

INSERT INTO motivo_prioridade (id_prioridade, descricao) VALUES
(0, 'Idoso 80+ anos (Lei 13.466/2017)'),
(1, 'Idoso 60-79 anos (Lei 10.048/2000)'),
(1, 'Gestante (Lei 10.048/2000)'),
(1, 'Lactante (Lei 10.048/2000)'),
(1, 'Pessoa com criança de colo (Lei 10.048/2000)'),
(1, 'Pessoa com deficiência - PCD (Lei 10.048/2000)'),
(1, 'Pessoa com obesidade (Lei 10.048/2000)'),
(1, 'Pessoa com Transtorno do Espectro Autista - TEA (Lei 12.764/2012)'),
(2, 'Atendimento Convencional')
ON CONFLICT (descricao) DO NOTHING;

-- 10. Segurança + funções de atendimento (igual à migration 20261107150000)
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
