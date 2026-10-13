-- Fresh-install baseline: structure only, no customer or admin data.
-- Select the target MySQL database before importing this file.
-- Refresh this snapshot whenever a schema migration is added.

SET FOREIGN_KEY_CHECKS=0;

CREATE TABLE IF NOT EXISTS `admin_permissao` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `usuario_admin_id` int NOT NULL,
  `modulo` varchar(32) NOT NULL,
  `pode_visualizar` tinyint(1) NOT NULL DEFAULT '0',
  `pode_editar` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_admin_permissao_usuario_modulo` (`usuario_admin_id`,`modulo`),
  CONSTRAINT `fk_admin_permissao_usuario` FOREIGN KEY (`usuario_admin_id`) REFERENCES `usuario_admin` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `admin_quadra_permissao` (
  `usuario_admin_id` int NOT NULL,
  `quadra_id` int NOT NULL,
  PRIMARY KEY (`usuario_admin_id`,`quadra_id`),
  KEY `fk_admin_quadra_permissao_quadra` (`quadra_id`),
  CONSTRAINT `fk_admin_quadra_permissao_quadra` FOREIGN KEY (`quadra_id`) REFERENCES `quadra` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_admin_quadra_permissao_usuario` FOREIGN KEY (`usuario_admin_id`) REFERENCES `usuario_admin` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `agendamento` (
  `id` int NOT NULL AUTO_INCREMENT,
  `cliente_id` int NOT NULL,
  `quadra_id` int NOT NULL,
  `data` date NOT NULL,
  `horario` time NOT NULL,
  `status` varchar(50) NOT NULL,
  `valor_hora` decimal(10,2) DEFAULT NULL,
  `taxa_reserva` decimal(10,2) NOT NULL DEFAULT '0.00',
  `valor_restante` decimal(10,2) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_cliente_id` (`cliente_id`),
  KEY `idx_quadra_id` (`quadra_id`),
  CONSTRAINT `agendamento_ibfk_1` FOREIGN KEY (`cliente_id`) REFERENCES `cliente` (`id`),
  CONSTRAINT `agendamento_ibfk_2` FOREIGN KEY (`quadra_id`) REFERENCES `quadra` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `agendamento_fila_retorno` (
  `agendamento_id` int NOT NULL,
  `confirmado_id` int NOT NULL,
  `criado_em` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`agendamento_id`),
  KEY `idx_fila_retorno_confirmado` (`confirmado_id`),
  CONSTRAINT `fk_fila_retorno_agendamento` FOREIGN KEY (`agendamento_id`) REFERENCES `agendamento` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_fila_retorno_confirmado` FOREIGN KEY (`confirmado_id`) REFERENCES `agendamento` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `cliente` (
  `id` int NOT NULL AUTO_INCREMENT,
  `nome` varchar(100) NOT NULL,
  `contato` varchar(20) NOT NULL,
  `garantia_reserva` varchar(20) NOT NULL DEFAULT 'Dispensado',
  `motivo_garantia` text,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `configuracao` (
  `id` int NOT NULL AUTO_INCREMENT,
  `chave` varchar(100) NOT NULL,
  `valor` text,
  `descricao` varchar(255) DEFAULT NULL,
  `tipo` varchar(30) NOT NULL DEFAULT 'texto',
  `editavel` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_configuracao_chave` (`chave`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `historico_status_agendamento` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `agendamento_id` int NOT NULL,
  `status_anterior` varchar(30) NOT NULL,
  `status_novo` varchar(30) NOT NULL,
  `alterado_em` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_historico_agendamento` (`agendamento_id`,`alterado_em`),
  CONSTRAINT `fk_historico_status_agendamento` FOREIGN KEY (`agendamento_id`) REFERENCES `agendamento` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `historico_status_pagamento` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `pagamento_id` bigint NOT NULL,
  `status_anterior` varchar(20) NOT NULL,
  `status_novo` varchar(20) NOT NULL,
  `alterado_em` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_historico_pagamento` (`pagamento_id`,`alterado_em`),
  CONSTRAINT `fk_historico_status_pagamento` FOREIGN KEY (`pagamento_id`) REFERENCES `pagamento` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `mensalidade` (
  `id` int NOT NULL AUTO_INCREMENT,
  `cliente_id` int NOT NULL,
  `quadra_id` int NOT NULL,
  `dia_semana` tinyint NOT NULL,
  `horario` time NOT NULL,
  `valor_mensal` decimal(10,2) NOT NULL,
  `data_inicio` date NOT NULL,
  `data_encerramento` date DEFAULT NULL,
  `status` varchar(20) NOT NULL DEFAULT 'Ativa',
  `observacao` text,
  `criado_em` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_mensalidade_cliente` (`cliente_id`),
  KEY `idx_mensalidade_quadra` (`quadra_id`),
  KEY `idx_mensalidade_disponibilidade` (`quadra_id`,`dia_semana`,`horario`,`status`),
  CONSTRAINT `fk_mensalidade_cliente` FOREIGN KEY (`cliente_id`) REFERENCES `cliente` (`id`),
  CONSTRAINT `fk_mensalidade_quadra` FOREIGN KEY (`quadra_id`) REFERENCES `quadra` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `pagamento` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `cliente_id` int NOT NULL,
  `agendamento_id` int DEFAULT NULL,
  `mensalidade_id` int DEFAULT NULL,
  `competencia` char(7) DEFAULT NULL,
  `tipo` varchar(20) NOT NULL,
  `valor` decimal(10,2) NOT NULL,
  `taxa_reserva` decimal(10,2) NOT NULL DEFAULT '0.00',
  `valor_total` decimal(10,2) NOT NULL,
  `valor_pago` decimal(10,2) NOT NULL DEFAULT '0.00',
  `data_pagamento` date DEFAULT NULL,
  `forma_pagamento` varchar(30) DEFAULT NULL,
  `status` varchar(20) NOT NULL DEFAULT 'Pendente',
  `observacao` text,
  `criado_em` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `atualizado_em` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_pagamento_cliente` (`cliente_id`),
  KEY `idx_pagamento_agendamento` (`agendamento_id`),
  KEY `idx_pagamento_mensalidade` (`mensalidade_id`),
  KEY `idx_pagamento_status_data` (`status`,`data_pagamento`),
  KEY `idx_pagamento_mensalidade_competencia` (`mensalidade_id`,`competencia`,`status`),
  CONSTRAINT `fk_pagamento_agendamento` FOREIGN KEY (`agendamento_id`) REFERENCES `agendamento` (`id`),
  CONSTRAINT `fk_pagamento_cliente` FOREIGN KEY (`cliente_id`) REFERENCES `cliente` (`id`),
  CONSTRAINT `fk_pagamento_mensalidade_operacional` FOREIGN KEY (`mensalidade_id`) REFERENCES `mensalidade` (`id`),
  CONSTRAINT `chk_pagamento_referencia` CHECK ((((`tipo` = _utf8mb4'Reserva') and (`agendamento_id` is not null) and (`mensalidade_id` is null)) or ((`tipo` = _utf8mb4'Mensalidade') and (`mensalidade_id` is not null) and (`agendamento_id` is null)))),
  CONSTRAINT `chk_pagamento_valores` CHECK (((`valor` >= 0) and (`taxa_reserva` >= 0) and (`valor_total` = (`valor` + `taxa_reserva`))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `pagamento_mensalidade` (
  `id` int NOT NULL AUTO_INCREMENT,
  `mensalidade_id` int NOT NULL,
  `competencia` date NOT NULL,
  `valor` decimal(10,2) NOT NULL,
  `data_pagamento` date DEFAULT NULL,
  `status` varchar(20) NOT NULL DEFAULT 'Pendente',
  `forma_pagamento` varchar(50) DEFAULT NULL,
  `observacao` text,
  `criado_em` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_pagamento_competencia` (`mensalidade_id`,`competencia`),
  KEY `idx_pagamento_status` (`status`),
  KEY `idx_pagamento_competencia` (`competencia`),
  CONSTRAINT `fk_pagamento_mensalidade` FOREIGN KEY (`mensalidade_id`) REFERENCES `mensalidade` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `quadra` (
  `id` int NOT NULL AUTO_INCREMENT,
  `nome` varchar(100) NOT NULL,
  `tipo` varchar(100) NOT NULL,
  `valor` decimal(10,2) DEFAULT NULL,
  `medidas` varchar(100) DEFAULT NULL,
  `capacidade` int DEFAULT NULL,
  `descricao` text,
  `imagem` varchar(255) DEFAULT NULL,
  `ativo` tinyint(1) DEFAULT '1',
  `valor_mensal` decimal(10,2) DEFAULT NULL,
  `taxa_reserva` decimal(10,2) NOT NULL DEFAULT '0.00',
  `responsavel_whatsapp` varchar(20) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `sessao_admin` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `usuario_admin_id` int NOT NULL,
  `token_hash` char(64) NOT NULL,
  `criado_em` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `expira_em` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `token_hash` (`token_hash`),
  KEY `idx_sessao_admin_expiracao` (`expira_em`),
  KEY `fk_sessao_admin_usuario` (`usuario_admin_id`),
  CONSTRAINT `fk_sessao_admin_usuario` FOREIGN KEY (`usuario_admin_id`) REFERENCES `usuario_admin` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `usuario_admin` (
  `id` int NOT NULL AUTO_INCREMENT,
  `nome` varchar(100) NOT NULL,
  `usuario` varchar(50) NOT NULL,
  `senha_hash` varchar(255) NOT NULL,
  `nivel` varchar(30) NOT NULL DEFAULT 'admin',
  `ativo` tinyint(1) NOT NULL DEFAULT '1',
  `criado_em` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_usuario_admin` (`usuario`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `pagamento_recebimento` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `pagamento_id` bigint NOT NULL,
  `valor_recebido` decimal(10,2) NOT NULL,
  `data_hora_recebimento` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `usuario_recebedor_id` int DEFAULT NULL,
  `nome_usuario` varchar(100) NOT NULL,
  `metodo_pagamento` varchar(30) NOT NULL,
  `observacoes` text,
  PRIMARY KEY (`id`),
  KEY `idx_pagamento_recebimento_data` (`data_hora_recebimento`),
  KEY `idx_pagamento_recebimento_pagamento` (`pagamento_id`,`data_hora_recebimento`),
  CONSTRAINT `fk_pagamento_recebimento_pagamento`
    FOREIGN KEY (`pagamento_id`) REFERENCES `pagamento` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_pagamento_recebimento_usuario`
    FOREIGN KEY (`usuario_recebedor_id`) REFERENCES `usuario_admin` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

SET FOREIGN_KEY_CHECKS=1;
