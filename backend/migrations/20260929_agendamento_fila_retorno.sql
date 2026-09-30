CREATE TABLE IF NOT EXISTS agendamento_fila_retorno (
    agendamento_id INT NOT NULL PRIMARY KEY,
    confirmado_id INT NOT NULL,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_fila_retorno_confirmado (confirmado_id),
    CONSTRAINT fk_fila_retorno_agendamento
        FOREIGN KEY (agendamento_id)
        REFERENCES agendamento(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_fila_retorno_confirmado
        FOREIGN KEY (confirmado_id)
        REFERENCES agendamento(id)
        ON DELETE CASCADE
) ENGINE=InnoDB;
