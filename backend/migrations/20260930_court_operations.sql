SET @adicionar_responsavel_sql = IF(
    EXISTS (
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'quadra'
          AND COLUMN_NAME = 'responsavel_whatsapp'
    ),
    'SELECT 1',
    'ALTER TABLE quadra ADD COLUMN responsavel_whatsapp VARCHAR(20) NULL AFTER taxa_reserva'
);
PREPARE adicionar_responsavel_stmt FROM @adicionar_responsavel_sql;
EXECUTE adicionar_responsavel_stmt;
DEALLOCATE PREPARE adicionar_responsavel_stmt;

CREATE TABLE IF NOT EXISTS admin_quadra_permissao (
    usuario_admin_id INT NOT NULL,
    quadra_id INT NOT NULL,
    PRIMARY KEY (usuario_admin_id, quadra_id),
    CONSTRAINT fk_admin_quadra_permissao_usuario
        FOREIGN KEY (usuario_admin_id)
        REFERENCES usuario_admin(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_admin_quadra_permissao_quadra
        FOREIGN KEY (quadra_id)
        REFERENCES quadra(id)
        ON DELETE CASCADE
) ENGINE=InnoDB;

INSERT INTO configuracao (chave, valor, descricao, tipo, editavel)
SELECT 'site_titulo', 'Seu jogo. Seu espaço. Seu momento.',
       'Título principal da página inicial.', 'texto', 1
WHERE NOT EXISTS (
    SELECT 1 FROM configuracao WHERE chave = 'site_titulo'
);

INSERT INTO configuracao (chave, valor, descricao, tipo, editavel)
SELECT 'site_subtitulo',
       'Escolha uma modalidade, confira os horários disponíveis e solicite sua reserva no Bosque Esportes.',
       'Texto de apresentação da página inicial.', 'texto', 1
WHERE NOT EXISTS (
    SELECT 1 FROM configuracao WHERE chave = 'site_subtitulo'
);

INSERT INTO configuracao (chave, valor, descricao, tipo, editavel)
SELECT 'site_sobre',
       'Aqui, cada partida começa com a escolha do espaço e do horário. Consulte as informações da quadra, envie sua solicitação e aguarde o contato da nossa equipe para confirmar os detalhes.',
       'Texto da seção Sobre na página inicial.', 'texto', 1
WHERE NOT EXISTS (
    SELECT 1 FROM configuracao WHERE chave = 'site_sobre'
);

INSERT INTO configuracao (chave, valor, descricao, tipo, editavel)
SELECT 'site_sobre_titulo', 'Um lugar para jogar junto.',
       'Título da seção Sobre na página inicial.', 'texto', 1
WHERE NOT EXISTS (
    SELECT 1 FROM configuracao WHERE chave = 'site_sobre_titulo'
);

INSERT INTO configuracao (chave, valor, descricao, tipo, editavel)
SELECT 'site_estrutura_titulo', 'Quadras para todos os jogos',
       'Título da seção de quadras na página inicial.', 'texto', 1
WHERE NOT EXISTS (
    SELECT 1 FROM configuracao WHERE chave = 'site_estrutura_titulo'
);

INSERT INTO configuracao (chave, valor, descricao, tipo, editavel)
SELECT 'site_estrutura_subtitulo',
       'Selecione a estrutura ideal e consulte os horários e valores antes de enviar sua solicitação.',
       'Texto de apresentação das quadras na página inicial.', 'texto', 1
WHERE NOT EXISTS (
    SELECT 1 FROM configuracao WHERE chave = 'site_estrutura_subtitulo'
);

INSERT INTO configuracao (chave, valor, descricao, tipo, editavel)
SELECT 'site_contato_titulo',
       'Escolha uma quadra e planeje sua próxima partida.',
       'Título da seção de contato na página inicial.', 'texto', 1
WHERE NOT EXISTS (
    SELECT 1 FROM configuracao WHERE chave = 'site_contato_titulo'
);

INSERT INTO configuracao (chave, valor, descricao, tipo, editavel)
SELECT 'site_rodape', 'Esporte, encontro e bem-estar.',
       'Texto do rodapé na página inicial.', 'texto', 1
WHERE NOT EXISTS (
    SELECT 1 FROM configuracao WHERE chave = 'site_rodape'
);

INSERT INTO configuracao (chave, valor, descricao, tipo, editavel)
SELECT 'site_cta', 'Encontrar minha quadra',
       'Texto do botão principal da página inicial.', 'texto', 1
WHERE NOT EXISTS (
    SELECT 1 FROM configuracao WHERE chave = 'site_cta'
);

INSERT INTO configuracao (chave, valor, descricao, tipo, editavel)
SELECT 'site_contato_label', 'VAMOS JOGAR?',
       'Chamada curta da seção de contato na página inicial.', 'texto', 1
WHERE NOT EXISTS (
    SELECT 1 FROM configuracao WHERE chave = 'site_contato_label'
);

INSERT INTO configuracao (chave, valor, descricao, tipo, editavel)
SELECT 'mensagem_reserva',
       'Olá {nome}! Recebemos sua solicitação para {quadra} em {data} às {horario}. A equipe do Bosque Esportes seguirá com o atendimento por aqui.',
       'Mensagem sugerida para iniciar o atendimento pelo WhatsApp.', 'texto', 1
WHERE NOT EXISTS (
    SELECT 1 FROM configuracao WHERE chave = 'mensagem_reserva'
);
