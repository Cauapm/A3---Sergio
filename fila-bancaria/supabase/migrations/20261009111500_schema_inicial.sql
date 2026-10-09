-- SQLBook: Code
-- Status possíveis de cliente na fila
CREATE TYPE status_senha AS ENUM (
    'aguardando',
    'em_atendimento',
    'atendido',
    'cancelado'
);

-- Tipos de prioridade (0 = Superprioridade, 1 = Prioridade Padrão, 2 = Convencional)
CREATE TABLE tipo_prioridade (
    id_prioridade INT PRIMARY KEY,
    nome VARCHAR(30) NOT NULL UNIQUE,
    descricao VARCHAR(255)
);

-- Motivos legais de prioridade (Leis 13.466/2017, 10.048/2000, 12.764/2012)
CREATE TABLE motivo_prioridade (
    id_motivo SERIAL PRIMARY KEY,
    id_prioridade INT NOT NULL REFERENCES tipo_prioridade(id_prioridade),
    descricao VARCHAR(255) NOT NULL UNIQUE
);

-- Tabela principal de clientes na fila 
CREATE TABLE clientes_fila (
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

-- Índice para otimizar a busca ordenada do próximo cliente 
CREATE INDEX idx_proximo_fila
    ON clientes_fila(nivel_prioridade, data_chegada)
    WHERE status = 'aguardando';

-- Tabela de histórico e controle de chamadas no guichê
CREATE TABLE atendimentos (
    id_chamada UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cliente_id UUID NOT NULL REFERENCES clientes_fila(id) ON DELETE CASCADE,
    guiche INT NOT NULL CHECK (guiche > 0),
    data_chamada TIMESTAMPTZ NOT NULL DEFAULT now(),
    data_finalizado TIMESTAMPTZ
);

-- compatibilidade caso alguém referencie nomes no singular
CREATE OR REPLACE VIEW cliente_fila AS SELECT * FROM clientes_fila;
CREATE OR REPLACE VIEW atendimento AS SELECT * FROM atendimentos;

-- Configuração de Row Level Security (RLS) para permitir acesso seguro via cliente Supabase
ALTER TABLE tipo_prioridade ENABLE ROW LEVEL SECURITY;
ALTER TABLE motivo_prioridade ENABLE ROW LEVEL SECURITY;
ALTER TABLE clientes_fila ENABLE ROW LEVEL SECURITY;
ALTER TABLE atendimentos ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Permitir leitura de tipo_prioridade" ON tipo_prioridade FOR SELECT USING (true);
CREATE POLICY "Permitir leitura de motivo_prioridade" ON motivo_prioridade FOR SELECT USING (true);
CREATE POLICY "Permitir todas operacoes em clientes_fila" ON clientes_fila FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Permitir todas operacoes em atendimentos" ON atendimentos FOR ALL USING (true) WITH CHECK (true);
