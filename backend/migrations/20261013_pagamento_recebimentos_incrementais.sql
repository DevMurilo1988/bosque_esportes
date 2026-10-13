CREATE TABLE IF NOT EXISTS pagamento_recebimento (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    pagamento_id BIGINT NOT NULL,
    valor_recebido DECIMAL(10,2) NOT NULL,
    data_hora_recebimento DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario_recebedor_id INT NULL,
    nome_usuario VARCHAR(100) NOT NULL,
    metodo_pagamento VARCHAR(30) NOT NULL,
    observacoes TEXT NULL,
    INDEX idx_pagamento_recebimento_data (data_hora_recebimento),
    INDEX idx_pagamento_recebimento_pagamento
        (pagamento_id, data_hora_recebimento),
    CONSTRAINT fk_pagamento_recebimento_pagamento
        FOREIGN KEY (pagamento_id) REFERENCES pagamento(id) ON DELETE CASCADE,
    CONSTRAINT fk_pagamento_recebimento_usuario
        FOREIGN KEY (usuario_recebedor_id)
        REFERENCES usuario_admin(id) ON DELETE SET NULL
) ENGINE=InnoDB;

INSERT INTO pagamento_recebimento
    (pagamento_id, valor_recebido, data_hora_recebimento,
     nome_usuario, metodo_pagamento, observacoes)
SELECT p.id, p.valor_pago,
       COALESCE(p.data_pagamento, p.criado_em),
       'Registro anterior',
       COALESCE(p.forma_pagamento, 'Outro'),
       'Valor existente consolidado na migração; o histórico anterior não discriminava parcelas.'
FROM pagamento p
WHERE p.valor_pago > 0
  AND NOT EXISTS (
      SELECT 1
      FROM pagamento_recebimento r
      WHERE r.pagamento_id = p.id
        AND r.nome_usuario = 'Registro anterior'
  );
