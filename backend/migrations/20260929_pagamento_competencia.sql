ALTER TABLE pagamento
    ADD COLUMN competencia CHAR(7) NULL
    AFTER mensalidade_id,
    ADD INDEX idx_pagamento_mensalidade_competencia
        (mensalidade_id, competencia, status);
