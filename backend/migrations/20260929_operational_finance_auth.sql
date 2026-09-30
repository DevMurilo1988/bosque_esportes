CREATE TABLE IF NOT EXISTS sessao_admin (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    usuario_admin_id INT NOT NULL,
    token_hash CHAR(64) NOT NULL UNIQUE,
    criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expira_em DATETIME NOT NULL,
    INDEX idx_sessao_admin_expiracao (expira_em),
    CONSTRAINT fk_sessao_admin_usuario
        FOREIGN KEY (usuario_admin_id)
        REFERENCES usuario_admin(id)
        ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS pagamento (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    cliente_id INT NOT NULL,
    agendamento_id INT NULL,
    mensalidade_id INT NULL,
    tipo VARCHAR(20) NOT NULL,
    valor DECIMAL(10,2) NOT NULL,
    taxa_reserva DECIMAL(10,2) NOT NULL DEFAULT 0,
    valor_total DECIMAL(10,2) NOT NULL,
    data_pagamento DATE NULL,
    forma_pagamento VARCHAR(30) NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Pendente',
    observacao TEXT NULL,
    criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_pagamento_cliente (cliente_id),
    INDEX idx_pagamento_agendamento (agendamento_id),
    INDEX idx_pagamento_mensalidade (mensalidade_id),
    INDEX idx_pagamento_status_data (status, data_pagamento),
    CONSTRAINT fk_pagamento_cliente
        FOREIGN KEY (cliente_id)
        REFERENCES cliente(id),
    CONSTRAINT fk_pagamento_agendamento
        FOREIGN KEY (agendamento_id)
        REFERENCES agendamento(id),
    CONSTRAINT fk_pagamento_mensalidade_operacional
        FOREIGN KEY (mensalidade_id)
        REFERENCES mensalidade(id),
    CONSTRAINT chk_pagamento_referencia
        CHECK (
            (tipo = 'Reserva' AND agendamento_id IS NOT NULL AND mensalidade_id IS NULL)
            OR
            (tipo = 'Mensalidade' AND mensalidade_id IS NOT NULL AND agendamento_id IS NULL)
        ),
    CONSTRAINT chk_pagamento_valores
        CHECK (valor >= 0 AND taxa_reserva >= 0 AND valor_total = valor + taxa_reserva)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS historico_status_agendamento (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    agendamento_id INT NOT NULL,
    status_anterior VARCHAR(30) NOT NULL,
    status_novo VARCHAR(30) NOT NULL,
    alterado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_historico_agendamento (agendamento_id, alterado_em),
    CONSTRAINT fk_historico_status_agendamento
        FOREIGN KEY (agendamento_id)
        REFERENCES agendamento(id)
        ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS historico_status_pagamento (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    pagamento_id BIGINT NOT NULL,
    status_anterior VARCHAR(20) NOT NULL,
    status_novo VARCHAR(20) NOT NULL,
    alterado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_historico_pagamento (pagamento_id, alterado_em),
    CONSTRAINT fk_historico_status_pagamento
        FOREIGN KEY (pagamento_id)
        REFERENCES pagamento(id)
        ON DELETE CASCADE
) ENGINE=InnoDB;
