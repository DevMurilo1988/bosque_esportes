ALTER TABLE pagamento
    ADD COLUMN valor_pago DECIMAL(10,2) NOT NULL DEFAULT 0
    AFTER valor_total;
