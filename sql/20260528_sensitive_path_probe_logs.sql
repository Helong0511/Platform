-- 敏感路径拦截日志表
CREATE TABLE IF NOT EXISTS `sensitive_path_probe_logs` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `request_path` VARCHAR(1024) NOT NULL COMMENT '请求路径',
  `method` VARCHAR(16) NULL COMMENT '请求方法',
  `client_ip` VARCHAR(64) NULL COMMENT '客户端IP',
  `user_agent` VARCHAR(512) NULL COMMENT '用户代理',
  `query_string` VARCHAR(2048) NULL COMMENT '查询字符串',
  `matched_rule` VARCHAR(255) NULL COMMENT '命中规则',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  INDEX `idx_sensitive_probe_created_at` (`created_at`),
  INDEX `idx_sensitive_probe_ip_created` (`client_ip`, `created_at`),
  INDEX `ix_sensitive_path_probe_logs_method` (`method`),
  INDEX `ix_sensitive_path_probe_logs_client_ip` (`client_ip`),
  INDEX `ix_sensitive_path_probe_logs_matched_rule` (`matched_rule`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='敏感路径探测拦截日志';

-- 敏感路径黑名单IP表
CREATE TABLE IF NOT EXISTS `sensitive_blocked_ips` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `blocked_ip` VARCHAR(64) NOT NULL COMMENT '封禁IP',
  `reason` VARCHAR(255) NULL COMMENT '封禁原因',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_sensitive_blocked_ips_ip` (`blocked_ip`),
  INDEX `idx_sensitive_blocked_ip_active` (`is_active`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='敏感路径防护IP黑名单';
