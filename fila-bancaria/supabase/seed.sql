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
