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

DO $$ BEGIN
    CREATE POLICY "Permitir todas operacoes em clientes_fila" ON clientes_fila FOR ALL USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE POLICY "Permitir todas operacoes em atendimentos" ON atendimentos FOR ALL USING (true) WITH CHECK (true);
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

