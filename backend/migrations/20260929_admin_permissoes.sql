CREATE TABLE IF NOT EXISTS admin_permissao (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    usuario_admin_id INT NOT NULL,
    modulo VARCHAR(32) NOT NULL,
    pode_visualizar TINYINT(1) NOT NULL DEFAULT 0,
    pode_editar TINYINT(1) NOT NULL DEFAULT 0,
    UNIQUE KEY uq_admin_permissao_usuario_modulo
        (usuario_admin_id, modulo),
    CONSTRAINT fk_admin_permissao_usuario
        FOREIGN KEY (usuario_admin_id)
        REFERENCES usuario_admin(id)
        ON DELETE CASCADE
) ENGINE=InnoDB;
