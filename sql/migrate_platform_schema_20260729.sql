-- =============================================================================
-- 已有库补齐迁移：对齐 sql/platform.sql（2026-07-29）
-- 参照：sql/当前使用的数据库.sql（现网结构）
--
-- 适用：用旧版 platform.sql 初始化、缺列导致 1054 等错误的环境库
-- 新库请直接用 sql/platform.sql，不必执行本脚本
--
-- 可重复执行：已存在的列/索引/外键/视图/触发器/表会跳过
-- 数值精度：float/double/错误精度 DECIMAL 列升级为 platform.sql 目标类型（与 ORM Numeric 一致）
-- 执行顺序：先跑本脚本 → 再部署识别「临时挂靠」的代码
-- =============================================================================

USE `platform`;

SET NAMES utf8mb4;

-- =============================================================================
-- 0. 执行前诊断（只读，不修改数据）
-- =============================================================================
SELECT '=== 0.1 clients 改名预检 ===' AS section;
SELECT id, company_name
FROM clients
WHERE company_name IN ('默认客户（导入数据）', '临时挂靠');

SELECT '=== 0.2 postback_conversions 重复 transaction_id ===' AS section;
SELECT transaction_id, COUNT(*) AS cnt
FROM postback_conversions
WHERE transaction_id IS NOT NULL AND TRIM(transaction_id) <> ''
GROUP BY transaction_id
HAVING COUNT(*) > 1
LIMIT 20;

SELECT '=== 0.3 postback_conversions 重复 request_id ===' AS section;
SELECT request_id, COUNT(*) AS cnt
FROM postback_conversions
WHERE request_id IS NOT NULL AND TRIM(request_id) <> ''
GROUP BY request_id
HAVING COUNT(*) > 1
LIMIT 20;

SELECT '=== 0.4 postback_conversions 外键孤儿数据 ===' AS section;
SELECT 'offer_id' AS ref_col, COUNT(*) AS orphan_cnt
FROM postback_conversions pc
LEFT JOIN offers o ON pc.offer_id = o.id
WHERE pc.offer_id IS NOT NULL AND o.id IS NULL
UNION ALL
SELECT 'publisher_id', COUNT(*)
FROM postback_conversions pc
LEFT JOIN publishers p ON pc.publisher_id = p.id
WHERE pc.publisher_id IS NOT NULL AND p.id IS NULL
UNION ALL
SELECT 'advertiser_id', COUNT(*)
FROM postback_conversions pc
LEFT JOIN advertisers a ON pc.advertiser_id = a.id
WHERE pc.advertiser_id IS NOT NULL AND a.id IS NULL;

-- =============================================================================
-- 1. 补缺表（旧本地库可能缺失；现网已有则跳过）
-- =============================================================================
CREATE TABLE IF NOT EXISTS `sensitive_path_probe_logs` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `request_path` VARCHAR(1024) NOT NULL COMMENT '请求路径',
  `method` VARCHAR(16) NULL DEFAULT NULL COMMENT '请求方法',
  `client_ip` VARCHAR(64) NULL DEFAULT NULL COMMENT '客户端IP',
  `user_agent` VARCHAR(512) NULL DEFAULT NULL COMMENT '用户代理',
  `query_string` VARCHAR(2048) NULL DEFAULT NULL COMMENT '查询字符串',
  `matched_rule` VARCHAR(255) NULL DEFAULT NULL COMMENT '命中规则',
  `severity_level` TINYINT NOT NULL DEFAULT 2 COMMENT '预警等级：1低危 2中危 3高危 4危急',
  `action_taken` VARCHAR(64) NULL DEFAULT NULL COMMENT '处置动作：blocked_404/auto_blocked_ip等',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  INDEX `idx_sensitive_probe_created_at` (`created_at`),
  INDEX `idx_sensitive_probe_ip_created` (`client_ip`, `created_at`),
  INDEX `idx_sensitive_probe_severity_created` (`severity_level`, `created_at`),
  INDEX `ix_sensitive_path_probe_logs_method` (`method`),
  INDEX `ix_sensitive_path_probe_logs_client_ip` (`client_ip`),
  INDEX `ix_sensitive_path_probe_logs_matched_rule` (`matched_rule`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='敏感路径探测拦截日志表';

CREATE TABLE IF NOT EXISTS `sensitive_blocked_ips` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `blocked_ip` VARCHAR(64) NOT NULL COMMENT '封禁IP',
  `reason` VARCHAR(255) NULL DEFAULT NULL COMMENT '封禁原因',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE INDEX `blocked_ip` (`blocked_ip`),
  INDEX `idx_sensitive_blocked_ip_active` (`is_active`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='敏感路径防护IP黑名单表';

CREATE TABLE IF NOT EXISTS `cloak_configs` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '配置ID',
  `cloak_name` VARCHAR(100) NOT NULL COMMENT '斗篷名称（如 master）',
  `pixel_id` VARCHAR(50) NOT NULL COMMENT '主像素ID',
  `access_token` VARCHAR(500) NOT NULL COMMENT '主像素Token',
  `backup_pixel_id` VARCHAR(50) NULL DEFAULT NULL COMMENT '备份像素ID',
  `backup_access_token` VARCHAR(500) NULL DEFAULT NULL COMMENT '备份像素Token',
  `report_event` VARCHAR(64) NOT NULL DEFAULT 'ViewContent' COMMENT '斗篷点击与测上报的CAPI event_name',
  `report_value` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT '购物类事件金额',
  `report_currency` VARCHAR(10) NULL DEFAULT 'USD' COMMENT '购物类事件货币',
  `click_report_enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '桥页按钮跳转是否做 Facebook 上报',
  `load_report_enabled` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '桥页加载完成是否做 Facebook 上报',
  `load_report_event` VARCHAR(64) NOT NULL DEFAULT 'PageView' COMMENT '加载完成 CAPI event_name',
  `load_report_value` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT '加载上报为 Purchase 时的金额',
  `load_report_currency` VARCHAR(10) NULL DEFAULT 'USD' COMMENT '加载上报为 Purchase 时的货币',
  `postback_report_enabled` TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'postback 转化是否按斗篷配置做 Facebook 上报（0=保持原逻辑按 payout 发 Purchase）',
  `postback_report_event` VARCHAR(64) NOT NULL DEFAULT 'Purchase' COMMENT 'postback 转化 CAPI event_name',
  `postback_report_value` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT 'postback 为 Purchase 时固定金额；NULL 则用 postback 的 payout',
  `postback_report_currency` VARCHAR(10) NULL DEFAULT 'USD' COMMENT 'postback Purchase 货币',
  `is_enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_cloak_name` (`cloak_name`),
  INDEX `idx_cloak_enabled` (`is_enabled`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='斗篷配置表';

-- =============================================================================
-- 2. 增量结构迁移（存储过程，可重复执行）
-- =============================================================================
DELIMITER ;;

DROP PROCEDURE IF EXISTS `tmp_migrate_platform_schema`;;
CREATE PROCEDURE `tmp_migrate_platform_schema`()
BEGIN
  DECLARE v_dup_txn INT DEFAULT 0;
  DECLARE v_dup_req INT DEFAULT 0;
  DECLARE v_orphan_offer INT DEFAULT 0;
  DECLARE v_orphan_publisher INT DEFAULT 0;
  DECLARE v_orphan_advertiser INT DEFAULT 0;

  -- ---------- scheduled_tasks ----------
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'scheduled_tasks' AND COLUMN_NAME = 'status'
  ) THEN
    ALTER TABLE `scheduled_tasks`
      ADD COLUMN `status` VARCHAR(20) NOT NULL DEFAULT 'idle'
        COMMENT '任务状态 idle/running/success/error'
        AFTER `last_error`;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'scheduled_tasks' AND COLUMN_NAME = 'retry_count'
  ) THEN
    ALTER TABLE `scheduled_tasks`
      ADD COLUMN `retry_count` INT NOT NULL DEFAULT 0
        COMMENT '连续失败重试计数'
        AFTER `status`;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'scheduled_tasks' AND COLUMN_NAME = 'last_success_at'
  ) THEN
    ALTER TABLE `scheduled_tasks`
      ADD COLUMN `last_success_at` DATETIME NULL DEFAULT NULL
        COMMENT '上次成功完成时间'
        AFTER `retry_count`;
  END IF;

  -- 历史数据回填：用 last_finish_time 补 last_success_at
  UPDATE `scheduled_tasks`
  SET `last_success_at` = `last_finish_time`
  WHERE `last_success_at` IS NULL
    AND `last_finish_time` IS NOT NULL
    AND `success_count` > 0;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'scheduled_tasks' AND INDEX_NAME = 'idx_scheduled_task_status'
  ) THEN
    ALTER TABLE `scheduled_tasks` ADD INDEX `idx_scheduled_task_status` (`status`);
  END IF;

  -- ---------- postback_conversions ----------
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'postback_conversions' AND COLUMN_NAME = 'transaction_id'
  ) THEN
    ALTER TABLE `postback_conversions`
      ADD COLUMN `transaction_id` VARCHAR(255) NULL DEFAULT NULL
        COMMENT '上游事务ID（幂等）'
        AFTER `conversion_id`;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'postback_conversions' AND COLUMN_NAME = 'request_id'
  ) THEN
    ALTER TABLE `postback_conversions`
      ADD COLUMN `request_id` VARCHAR(128) NULL DEFAULT NULL
        COMMENT '请求防重放ID'
        AFTER `transaction_id`;
  END IF;

  UPDATE `postback_conversions`
  SET `transaction_id` = NULL
  WHERE `transaction_id` IS NOT NULL AND TRIM(`transaction_id`) = '';

  UPDATE `postback_conversions`
  SET `request_id` = NULL
  WHERE `request_id` IS NOT NULL AND TRIM(`request_id`) = '';

  SELECT COUNT(*) INTO v_dup_txn
  FROM (
    SELECT 1
    FROM `postback_conversions`
    WHERE `transaction_id` IS NOT NULL AND TRIM(`transaction_id`) <> ''
    GROUP BY `transaction_id`
    HAVING COUNT(*) > 1
  ) AS `dup_txn`;

  IF v_dup_txn = 0 AND NOT EXISTS (
    SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'postback_conversions' AND INDEX_NAME = 'uq_postback_transaction_id'
  ) THEN
    ALTER TABLE `postback_conversions` ADD UNIQUE INDEX `uq_postback_transaction_id` (`transaction_id`);
  END IF;

  SELECT COUNT(*) INTO v_dup_req
  FROM (
    SELECT 1
    FROM `postback_conversions`
    WHERE `request_id` IS NOT NULL AND TRIM(`request_id`) <> ''
    GROUP BY `request_id`
    HAVING COUNT(*) > 1
  ) AS `dup_req`;

  IF v_dup_req = 0 AND NOT EXISTS (
    SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'postback_conversions' AND INDEX_NAME = 'uq_postback_request_id'
  ) THEN
    ALTER TABLE `postback_conversions` ADD UNIQUE INDEX `uq_postback_request_id` (`request_id`);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'postback_conversions' AND INDEX_NAME = 'idx_postback_created_at_click_id'
  ) THEN
    ALTER TABLE `postback_conversions` ADD INDEX `idx_postback_created_at_click_id` (`created_at`, `click_id`);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'postback_conversions' AND INDEX_NAME = 'idx_postback_created_at_platform'
  ) THEN
    ALTER TABLE `postback_conversions` ADD INDEX `idx_postback_created_at_platform` (`created_at`, `platform`);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'postback_conversions' AND INDEX_NAME = 'idx_postback_created_at_status'
  ) THEN
    ALTER TABLE `postback_conversions` ADD INDEX `idx_postback_created_at_status` (`created_at`, `conversion_status`);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'postback_conversions' AND INDEX_NAME = 'idx_postback_offer_id'
  ) THEN
    ALTER TABLE `postback_conversions` ADD INDEX `idx_postback_offer_id` (`offer_id`);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'postback_conversions' AND INDEX_NAME = 'idx_postback_publisher_id'
  ) THEN
    ALTER TABLE `postback_conversions` ADD INDEX `idx_postback_publisher_id` (`publisher_id`);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'postback_conversions' AND INDEX_NAME = 'idx_postback_advertiser_id'
  ) THEN
    ALTER TABLE `postback_conversions` ADD INDEX `idx_postback_advertiser_id` (`advertiser_id`);
  END IF;

  SELECT COUNT(*) INTO v_orphan_offer
  FROM `postback_conversions` pc
  LEFT JOIN `offers` o ON pc.`offer_id` = o.`id`
  WHERE pc.`offer_id` IS NOT NULL AND o.`id` IS NULL;

  IF v_orphan_offer = 0 AND NOT EXISTS (
    SELECT 1 FROM information_schema.KEY_COLUMN_USAGE
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'postback_conversions'
      AND COLUMN_NAME = 'offer_id' AND REFERENCED_TABLE_NAME IS NOT NULL
  ) THEN
    ALTER TABLE `postback_conversions`
      ADD CONSTRAINT `postback_conversions_ibfk_offer`
      FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT;
  END IF;

  SELECT COUNT(*) INTO v_orphan_publisher
  FROM `postback_conversions` pc
  LEFT JOIN `publishers` p ON pc.`publisher_id` = p.`id`
  WHERE pc.`publisher_id` IS NOT NULL AND p.`id` IS NULL;

  IF v_orphan_publisher = 0 AND NOT EXISTS (
    SELECT 1 FROM information_schema.KEY_COLUMN_USAGE
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'postback_conversions'
      AND COLUMN_NAME = 'publisher_id' AND REFERENCED_TABLE_NAME IS NOT NULL
  ) THEN
    ALTER TABLE `postback_conversions`
      ADD CONSTRAINT `postback_conversions_ibfk_publisher`
      FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT;
  END IF;

  SELECT COUNT(*) INTO v_orphan_advertiser
  FROM `postback_conversions` pc
  LEFT JOIN `advertisers` a ON pc.`advertiser_id` = a.`id`
  WHERE pc.`advertiser_id` IS NOT NULL AND a.`id` IS NULL;

  IF v_orphan_advertiser = 0 AND NOT EXISTS (
    SELECT 1 FROM information_schema.KEY_COLUMN_USAGE
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'postback_conversions'
      AND COLUMN_NAME = 'advertiser_id' AND REFERENCED_TABLE_NAME IS NOT NULL
  ) THEN
    ALTER TABLE `postback_conversions`
      ADD CONSTRAINT `postback_conversions_ibfk_advertiser`
      FOREIGN KEY (`advertiser_id`) REFERENCES `advertisers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT;
  END IF;

  -- ---------- postback_forward_queue ----------
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'postback_forward_queue' AND COLUMN_NAME = 'publisher_id'
  ) THEN
    ALTER TABLE `postback_forward_queue`
      ADD COLUMN `publisher_id` INT NULL DEFAULT NULL
        COMMENT '渠道ID（渠道级转发时使用）'
        AFTER `product_id`;
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'postback_forward_queue'
      AND COLUMN_NAME = 'product_id' AND IS_NULLABLE = 'NO'
  ) THEN
    ALTER TABLE `postback_forward_queue`
      MODIFY COLUMN `product_id` INT NULL DEFAULT NULL COMMENT '产品ID（产品级转发时使用）';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'postback_forward_queue' AND INDEX_NAME = 'idx_forward_queue_publisher'
  ) THEN
    ALTER TABLE `postback_forward_queue` ADD INDEX `idx_forward_queue_publisher` (`publisher_id`);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.KEY_COLUMN_USAGE
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'postback_forward_queue'
      AND COLUMN_NAME = 'publisher_id' AND REFERENCED_TABLE_NAME IS NOT NULL
  ) THEN
    ALTER TABLE `postback_forward_queue`
      ADD CONSTRAINT `postback_forward_queue_ibfk_publisher`
      FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT;
  END IF;

  -- ---------- user_sessions ----------
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'user_sessions' AND COLUMN_NAME = 'token_type'
  ) THEN
    ALTER TABLE `user_sessions`
      ADD COLUMN `token_type` VARCHAR(16) NOT NULL DEFAULT 'access'
        COMMENT '令牌类型 access/refresh'
        AFTER `token_jti`;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'user_sessions' AND INDEX_NAME = 'ix_user_sessions_token_type'
  ) THEN
    ALTER TABLE `user_sessions` ADD INDEX `ix_user_sessions_token_type` (`token_type`);
  END IF;

  -- ---------- products：补缺 cplpo_deduct_ratio ----------
  IF EXISTS (
    SELECT 1 FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'products'
  ) AND NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'products' AND COLUMN_NAME = 'cplpo_deduct_ratio'
  ) THEN
    ALTER TABLE `products`
      ADD COLUMN `cplpo_deduct_ratio` DECIMAL(12, 4) NOT NULL DEFAULT 0
        COMMENT 'CPL PO减扣比例 '
        AFTER `revenue_deduct_ratio`;
  END IF;

  -- ---------- cloak_configs：旧表补列（表已存在但缺三阶段上报字段时） ----------
  IF EXISTS (
    SELECT 1 FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cloak_configs'
  ) THEN
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cloak_configs' AND COLUMN_NAME = 'click_report_enabled'
    ) THEN
      ALTER TABLE `cloak_configs`
        ADD COLUMN `click_report_enabled` TINYINT(1) NOT NULL DEFAULT 1
          COMMENT '桥页按钮跳转是否做 Facebook 上报'
          AFTER `report_currency`;
    END IF;

    IF NOT EXISTS (
      SELECT 1 FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cloak_configs' AND COLUMN_NAME = 'load_report_enabled'
    ) THEN
      ALTER TABLE `cloak_configs`
        ADD COLUMN `load_report_enabled` TINYINT(1) NOT NULL DEFAULT 0
          COMMENT '桥页加载完成是否做 Facebook 上报'
          AFTER `click_report_enabled`;
    END IF;

    IF NOT EXISTS (
      SELECT 1 FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cloak_configs' AND COLUMN_NAME = 'load_report_event'
    ) THEN
      ALTER TABLE `cloak_configs`
        ADD COLUMN `load_report_event` VARCHAR(64) NOT NULL DEFAULT 'PageView'
          COMMENT '加载完成 CAPI event_name'
          AFTER `load_report_enabled`;
    END IF;

    IF NOT EXISTS (
      SELECT 1 FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cloak_configs' AND COLUMN_NAME = 'load_report_value'
    ) THEN
      ALTER TABLE `cloak_configs`
        ADD COLUMN `load_report_value` DECIMAL(12, 4) NULL DEFAULT NULL
          COMMENT '加载上报为 Purchase 时的金额'
          AFTER `load_report_event`;
    END IF;

    IF NOT EXISTS (
      SELECT 1 FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cloak_configs' AND COLUMN_NAME = 'load_report_currency'
    ) THEN
      ALTER TABLE `cloak_configs`
        ADD COLUMN `load_report_currency` VARCHAR(10) NULL DEFAULT 'USD'
          COMMENT '加载上报为 Purchase 时的货币'
          AFTER `load_report_value`;
    END IF;

    IF NOT EXISTS (
      SELECT 1 FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cloak_configs' AND COLUMN_NAME = 'postback_report_enabled'
    ) THEN
      ALTER TABLE `cloak_configs`
        ADD COLUMN `postback_report_enabled` TINYINT(1) NOT NULL DEFAULT 0
          COMMENT 'postback 转化是否按斗篷配置做 Facebook 上报'
          AFTER `load_report_currency`;
    END IF;

    IF NOT EXISTS (
      SELECT 1 FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cloak_configs' AND COLUMN_NAME = 'postback_report_event'
    ) THEN
      ALTER TABLE `cloak_configs`
        ADD COLUMN `postback_report_event` VARCHAR(64) NOT NULL DEFAULT 'Purchase'
          COMMENT 'postback 转化 CAPI event_name'
          AFTER `postback_report_enabled`;
    END IF;

    IF NOT EXISTS (
      SELECT 1 FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cloak_configs' AND COLUMN_NAME = 'postback_report_value'
    ) THEN
      ALTER TABLE `cloak_configs`
        ADD COLUMN `postback_report_value` DECIMAL(12, 4) NULL DEFAULT NULL
          COMMENT 'postback 为 Purchase 时固定金额；NULL 则用 postback 的 payout'
          AFTER `postback_report_event`;
    END IF;

    IF NOT EXISTS (
      SELECT 1 FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cloak_configs' AND COLUMN_NAME = 'postback_report_currency'
    ) THEN
      ALTER TABLE `cloak_configs`
        ADD COLUMN `postback_report_currency` VARCHAR(10) NULL DEFAULT 'USD'
          COMMENT 'postback Purchase 货币'
          AFTER `postback_report_value`;
    END IF;
  END IF;

  -- ---------- 数值精度升迁（对齐 platform.sql / ORM Numeric） ----------
  -- 规则：float/double 或 DECIMAL 精度/小数位与目标不一致时 MODIFY

  -- products DECIMAL(12,4)
  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'products' AND COLUMN_NAME = 'ecpm_deduct_ratio'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `products`
      MODIFY COLUMN `ecpm_deduct_ratio` DECIMAL(12, 4) NOT NULL DEFAULT 0 COMMENT 'eCPM减扣比例';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'products' AND COLUMN_NAME = 'revenue_deduct_ratio'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `products`
      MODIFY COLUMN `revenue_deduct_ratio` DECIMAL(12, 4) NOT NULL DEFAULT 0 COMMENT '收益减扣比例';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'products' AND COLUMN_NAME = 'cplpo_deduct_ratio'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `products`
      MODIFY COLUMN `cplpo_deduct_ratio` DECIMAL(12, 4) NOT NULL DEFAULT 0 COMMENT 'CPL PO减扣比例 ';
  END IF;

  -- ad_data：比率 DECIMAL(7,4)，金额 DECIMAL(12,4)
  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ad_data' AND COLUMN_NAME = 'coverage_rate'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 7 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `ad_data`
      MODIFY COLUMN `coverage_rate` DECIMAL(7, 4) NOT NULL DEFAULT 0.0000 COMMENT '覆盖率（%）';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ad_data' AND COLUMN_NAME = 'display_rate'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 7 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `ad_data`
      MODIFY COLUMN `display_rate` DECIMAL(7, 4) NOT NULL DEFAULT 0.0000 COMMENT '展示率';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ad_data' AND COLUMN_NAME = 'click_rate'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 7 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `ad_data`
      MODIFY COLUMN `click_rate` DECIMAL(7, 4) NOT NULL DEFAULT 0.0000 COMMENT '点击率';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ad_data' AND COLUMN_NAME = 'viewability_rate'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 7 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `ad_data`
      MODIFY COLUMN `viewability_rate` DECIMAL(7, 4) NOT NULL DEFAULT 0.0000 COMMENT '可见率';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ad_data' AND COLUMN_NAME = 'cpc'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `ad_data`
      MODIFY COLUMN `cpc` DECIMAL(12, 4) NOT NULL DEFAULT 0.0000 COMMENT 'CPC';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ad_data' AND COLUMN_NAME = 'ecpm_before_deduct'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `ad_data`
      MODIFY COLUMN `ecpm_before_deduct` DECIMAL(12, 4) NOT NULL DEFAULT 0.0000 COMMENT 'eCPM未减扣';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ad_data' AND COLUMN_NAME = 'ecpm_after_deduct'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `ad_data`
      MODIFY COLUMN `ecpm_after_deduct` DECIMAL(12, 4) NOT NULL DEFAULT 0.0000 COMMENT 'eCPM已减扣';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ad_data' AND COLUMN_NAME = 'revenue_before_deduct'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `ad_data`
      MODIFY COLUMN `revenue_before_deduct` DECIMAL(12, 4) NOT NULL DEFAULT 0.0000 COMMENT '收益未减扣';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ad_data' AND COLUMN_NAME = 'revenue_after_deduct'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `ad_data`
      MODIFY COLUMN `revenue_after_deduct` DECIMAL(12, 4) NOT NULL DEFAULT 0.0000 COMMENT '收益已减扣';
  END IF;

  -- ad_data_archive（结构与 ad_data 数值列一致）
  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ad_data_archive' AND COLUMN_NAME = 'coverage_rate'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 7 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `ad_data_archive`
      MODIFY COLUMN `coverage_rate` DECIMAL(7, 4) NOT NULL DEFAULT 0.0000 COMMENT '覆盖率（%）';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ad_data_archive' AND COLUMN_NAME = 'display_rate'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 7 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `ad_data_archive`
      MODIFY COLUMN `display_rate` DECIMAL(7, 4) NOT NULL DEFAULT 0.0000 COMMENT '展示率';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ad_data_archive' AND COLUMN_NAME = 'click_rate'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 7 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `ad_data_archive`
      MODIFY COLUMN `click_rate` DECIMAL(7, 4) NOT NULL DEFAULT 0.0000 COMMENT '点击率';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ad_data_archive' AND COLUMN_NAME = 'viewability_rate'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 7 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `ad_data_archive`
      MODIFY COLUMN `viewability_rate` DECIMAL(7, 4) NOT NULL DEFAULT 0.0000 COMMENT '可见率';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ad_data_archive' AND COLUMN_NAME = 'cpc'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `ad_data_archive`
      MODIFY COLUMN `cpc` DECIMAL(12, 4) NOT NULL DEFAULT 0.0000 COMMENT 'CPC';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ad_data_archive' AND COLUMN_NAME = 'ecpm_before_deduct'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `ad_data_archive`
      MODIFY COLUMN `ecpm_before_deduct` DECIMAL(12, 4) NOT NULL DEFAULT 0.0000 COMMENT 'eCPM未减扣';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ad_data_archive' AND COLUMN_NAME = 'ecpm_after_deduct'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `ad_data_archive`
      MODIFY COLUMN `ecpm_after_deduct` DECIMAL(12, 4) NOT NULL DEFAULT 0.0000 COMMENT 'eCPM已减扣';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ad_data_archive' AND COLUMN_NAME = 'revenue_before_deduct'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `ad_data_archive`
      MODIFY COLUMN `revenue_before_deduct` DECIMAL(12, 4) NOT NULL DEFAULT 0.0000 COMMENT '收益未减扣';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ad_data_archive' AND COLUMN_NAME = 'revenue_after_deduct'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `ad_data_archive`
      MODIFY COLUMN `revenue_after_deduct` DECIMAL(12, 4) NOT NULL DEFAULT 0.0000 COMMENT '收益已减扣';
  END IF;

  -- tb_search_data
  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'tb_search_data' AND COLUMN_NAME = 'revenue'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `tb_search_data`
      MODIFY COLUMN `revenue` DECIMAL(12, 4) NOT NULL DEFAULT 0.0000 COMMENT 'REVENUE（扣减后）';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'tb_search_data' AND COLUMN_NAME = 'revenue_before_deduct'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `tb_search_data`
      MODIFY COLUMN `revenue_before_deduct` DECIMAL(12, 4) NOT NULL DEFAULT 0.0000 COMMENT 'REVENUE（扣减前）';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'tb_search_data' AND COLUMN_NAME = 'rpm'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 10 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `tb_search_data`
      MODIFY COLUMN `rpm` DECIMAL(10, 4) NOT NULL DEFAULT 0.0000 COMMENT 'RPM（扣减后）';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'tb_search_data' AND COLUMN_NAME = 'rpm_before_deduct'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 10 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `tb_search_data`
      MODIFY COLUMN `rpm_before_deduct` DECIMAL(10, 4) NOT NULL DEFAULT 0.0000 COMMENT 'RPM（扣减前）';
  END IF;

  -- offers / offer_publisher_assignments DECIMAL(10,2)
  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'offers' AND COLUMN_NAME = 'payout'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 10 OR NUMERIC_SCALE <> 2))
      )
  ) THEN
    ALTER TABLE `offers`
      MODIFY COLUMN `payout` DECIMAL(10, 2) NULL DEFAULT NULL COMMENT '上游支付金额（PO）';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'offers' AND COLUMN_NAME = 'affiliate_payout'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 10 OR NUMERIC_SCALE <> 2))
      )
  ) THEN
    ALTER TABLE `offers`
      MODIFY COLUMN `affiliate_payout` DECIMAL(10, 2) NULL DEFAULT NULL COMMENT '扣价后给渠道的金额（PO扣价后）';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'offer_publisher_assignments' AND COLUMN_NAME = 'affiliate_payout'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 10 OR NUMERIC_SCALE <> 2))
      )
  ) THEN
    ALTER TABLE `offer_publisher_assignments`
      MODIFY COLUMN `affiliate_payout` DECIMAL(10, 2) NULL DEFAULT NULL COMMENT '该渠道的扣价后给渠道的金额（PO扣价后）';
  END IF;

  -- publishers DECIMAL(5,2)
  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'publishers' AND COLUMN_NAME = 'price_discount'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 5 OR NUMERIC_SCALE <> 2))
      )
  ) THEN
    ALTER TABLE `publishers`
      MODIFY COLUMN `price_discount` DECIMAL(5, 2) NULL DEFAULT 0.00 COMMENT '渠道级别的价格扣量比例（0-100）';
  END IF;

  -- postback_conversions / pending_postback_conversions DECIMAL(12,4)
  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'postback_conversions' AND COLUMN_NAME = 'event_value'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `postback_conversions`
      MODIFY COLUMN `event_value` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT '事件价值（购买价格等）';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'postback_conversions' AND COLUMN_NAME = 'original_payout'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `postback_conversions`
      MODIFY COLUMN `original_payout` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT '原始支付金额（PO）';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'postback_conversions' AND COLUMN_NAME = 'payout'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `postback_conversions`
      MODIFY COLUMN `payout` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT '扣后支付金额（PO(扣)）';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'pending_postback_conversions' AND COLUMN_NAME = 'event_value'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `pending_postback_conversions`
      MODIFY COLUMN `event_value` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT '事件价值';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'pending_postback_conversions' AND COLUMN_NAME = 'original_payout'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `pending_postback_conversions`
      MODIFY COLUMN `original_payout` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT '原始支付金额（PO）';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'pending_postback_conversions' AND COLUMN_NAME = 'payout'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `pending_postback_conversions`
      MODIFY COLUMN `payout` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT '扣后支付金额（PO(扣)）';
  END IF;

  -- conversion_deduction DECIMAL(5,4) 比例 / DECIMAL(10,2) 金额
  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'conversion_deduction_configs' AND COLUMN_NAME = 'volume_deduction_ratio'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 5 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `conversion_deduction_configs`
      MODIFY COLUMN `volume_deduction_ratio` DECIMAL(5, 4) NULL DEFAULT 0.0000 COMMENT '按比例扣量比例（0-1）';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'conversion_deduction_configs' AND COLUMN_NAME = 'amount_deduction_ratio'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 5 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `conversion_deduction_configs`
      MODIFY COLUMN `amount_deduction_ratio` DECIMAL(5, 4) NULL DEFAULT 0.0000 COMMENT '按比例扣金额比例（0-1）';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'conversion_deduction_logs' AND COLUMN_NAME = 'original_amount'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 10 OR NUMERIC_SCALE <> 2))
      )
  ) THEN
    ALTER TABLE `conversion_deduction_logs`
      MODIFY COLUMN `original_amount` DECIMAL(10, 2) NOT NULL COMMENT '原始转化金额';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'conversion_deduction_logs' AND COLUMN_NAME = 'deducted_amount'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 10 OR NUMERIC_SCALE <> 2))
      )
  ) THEN
    ALTER TABLE `conversion_deduction_logs`
      MODIFY COLUMN `deducted_amount` DECIMAL(10, 2) NULL DEFAULT 0.00 COMMENT '扣减的转化金额';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'conversion_deduction_logs' AND COLUMN_NAME = 'final_amount'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 10 OR NUMERIC_SCALE <> 2))
      )
  ) THEN
    ALTER TABLE `conversion_deduction_logs`
      MODIFY COLUMN `final_amount` DECIMAL(10, 2) NOT NULL COMMENT '最终转化金额（扣减后）';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'conversion_deduction_logs' AND COLUMN_NAME = 'volume_deduction_ratio'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 5 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `conversion_deduction_logs`
      MODIFY COLUMN `volume_deduction_ratio` DECIMAL(5, 4) NULL DEFAULT NULL COMMENT '使用的扣量比例';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'conversion_deduction_logs' AND COLUMN_NAME = 'amount_deduction_ratio'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 5 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `conversion_deduction_logs`
      MODIFY COLUMN `amount_deduction_ratio` DECIMAL(5, 4) NULL DEFAULT NULL COMMENT '使用的扣金额比例';
  END IF;

  -- third_party_report_logs
  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'third_party_report_logs' AND COLUMN_NAME = 'amount'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `third_party_report_logs`
      MODIFY COLUMN `amount` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT '支付金额';
  END IF;

  -- offer_discounts / 测试表 / 通知阈值 / 斗篷金额 DECIMAL(12,4)
  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'offer_discounts' AND COLUMN_NAME = 'discount_ratio'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `offer_discounts`
      MODIFY COLUMN `discount_ratio` DECIMAL(12, 4) NOT NULL COMMENT '扣量比例（0-100）';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'advertiser_tests' AND COLUMN_NAME = 'price'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `advertiser_tests`
      MODIFY COLUMN `price` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT '价格';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'affiliate_tests' AND COLUMN_NAME = 'price'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `affiliate_tests`
      MODIFY COLUMN `price` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT '价格';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'client_notification_configs' AND COLUMN_NAME = 'high_value_threshold'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `client_notification_configs`
      MODIFY COLUMN `high_value_threshold` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT '高价值阈值';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'product_notification_configs' AND COLUMN_NAME = 'high_value_threshold'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `product_notification_configs`
      MODIFY COLUMN `high_value_threshold` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT '高价值阈值';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cloak_configs' AND COLUMN_NAME = 'report_value'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `cloak_configs`
      MODIFY COLUMN `report_value` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT '购物类事件金额';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cloak_configs' AND COLUMN_NAME = 'load_report_value'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `cloak_configs`
      MODIFY COLUMN `load_report_value` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT '加载上报为 Purchase 时的金额';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cloak_configs' AND COLUMN_NAME = 'postback_report_value'
      AND (
        DATA_TYPE IN ('float', 'double')
        OR (DATA_TYPE = 'decimal' AND (NUMERIC_PRECISION <> 12 OR NUMERIC_SCALE <> 4))
      )
  ) THEN
    ALTER TABLE `cloak_configs`
      MODIFY COLUMN `postback_report_value` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT 'postback 为 Purchase 时固定金额；NULL 则用 postback 的 payout';
  END IF;

  -- ---------- 表注释（与 platform.sql 对齐，不影响运行） ----------
  IF EXISTS (
    SELECT 1 FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'clients'
  ) THEN
    ALTER TABLE `clients` COMMENT = '客户表（下游商户）';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'tb_search_data'
  ) THEN
    ALTER TABLE `tb_search_data` COMMENT = 'TB搜索数据表';
  END IF;

  -- 跳过项提示（不自动处理，避免误伤现网）
  IF v_dup_txn > 0 THEN
    SELECT CONCAT('WARN: 跳过 uq_postback_transaction_id，存在 ', v_dup_txn, ' 组重复 transaction_id') AS migrate_warning;
  END IF;
  IF v_dup_req > 0 THEN
    SELECT CONCAT('WARN: 跳过 uq_postback_request_id，存在 ', v_dup_req, ' 组重复 request_id') AS migrate_warning;
  END IF;
  IF v_orphan_offer > 0 THEN
    SELECT CONCAT('WARN: 跳过 offer_id 外键，存在 ', v_orphan_offer, ' 条孤儿数据') AS migrate_warning;
  END IF;
  IF v_orphan_publisher > 0 THEN
    SELECT CONCAT('WARN: 跳过 publisher_id 外键，存在 ', v_orphan_publisher, ' 条孤儿数据') AS migrate_warning;
  END IF;
  IF v_orphan_advertiser > 0 THEN
    SELECT CONCAT('WARN: 跳过 advertiser_id 外键，存在 ', v_orphan_advertiser, ' 条孤儿数据') AS migrate_warning;
  END IF;
END;;

DROP PROCEDURE IF EXISTS `tmp_rename_default_client`;;
CREATE PROCEDURE `tmp_rename_default_client`()
BEGIN
  DECLARE v_old_count INT DEFAULT 0;
  DECLARE v_new_count INT DEFAULT 0;

  SELECT COUNT(*) INTO v_old_count
  FROM `clients`
  WHERE `company_name` = '默认客户（导入数据）';

  SELECT COUNT(*) INTO v_new_count
  FROM `clients`
  WHERE `company_name` = '临时挂靠';

  IF v_old_count > 0 AND v_new_count > 0 THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'clients 同时存在「默认客户（导入数据）」与「临时挂靠」，请先人工合并后再执行';
  ELSEIF v_old_count > 0 THEN
    UPDATE `clients`
    SET `company_name` = '临时挂靠',
        `updated_at` = NOW(6)
    WHERE `company_name` = '默认客户（导入数据）';
    SELECT CONCAT('clients 改名完成，影响行数: ', ROW_COUNT()) AS migrate_result;
  ELSE
    SELECT 'clients 无需改名（旧名不存在）' AS migrate_result;
  END IF;
END;;

DELIMITER ;

CALL `tmp_migrate_platform_schema`();
DROP PROCEDURE IF EXISTS `tmp_migrate_platform_schema`;

-- =============================================================================
-- 3. 视图与触发器
-- =============================================================================
DROP VIEW IF EXISTS `scheduler_jobs`;
CREATE ALGORITHM = UNDEFINED SQL SECURITY DEFINER VIEW `scheduler_jobs` AS
SELECT
  `scheduled_tasks`.`id` AS `id`,
  `scheduled_tasks`.`task_name` AS `job_name`,
  `scheduled_tasks`.`last_run_time` AS `last_run`,
  `scheduled_tasks`.`last_success_at` AS `last_success`,
  `scheduled_tasks`.`last_error` AS `last_error`,
  `scheduled_tasks`.`retry_count` AS `retry_count`,
  `scheduled_tasks`.`status` AS `status`,
  `scheduled_tasks`.`is_running` AS `is_running`,
  `scheduled_tasks`.`is_active` AS `is_active`,
  `scheduled_tasks`.`cron_expression` AS `cron_expression`,
  `scheduled_tasks`.`updated_at` AS `updated_at`
FROM `scheduled_tasks`;

DROP TRIGGER IF EXISTS `trg_postback_conversions_empty_ids_bi`;
DELIMITER ;;
CREATE TRIGGER `trg_postback_conversions_empty_ids_bi` BEFORE INSERT ON `postback_conversions` FOR EACH ROW BEGIN
  IF NEW.`transaction_id` IS NOT NULL AND TRIM(NEW.`transaction_id`) = '' THEN
    SET NEW.`transaction_id` = NULL;
  END IF;
  IF NEW.`request_id` IS NOT NULL AND TRIM(NEW.`request_id`) = '' THEN
    SET NEW.`request_id` = NULL;
  END IF;
END
;;
DELIMITER ;

DROP TRIGGER IF EXISTS `trg_postback_conversions_empty_ids_bu`;
DELIMITER ;;
CREATE TRIGGER `trg_postback_conversions_empty_ids_bu` BEFORE UPDATE ON `postback_conversions` FOR EACH ROW BEGIN
  IF NEW.`transaction_id` IS NOT NULL AND TRIM(NEW.`transaction_id`) = '' THEN
    SET NEW.`transaction_id` = NULL;
  END IF;
  IF NEW.`request_id` IS NOT NULL AND TRIM(NEW.`request_id`) = '' THEN
    SET NEW.`request_id` = NULL;
  END IF;
END
;;
DELIMITER ;

-- =============================================================================
-- 4. clients 改名（先库后代码；与代码「临时挂靠」保持一致）
-- =============================================================================
CALL `tmp_rename_default_client`();
DROP PROCEDURE IF EXISTS `tmp_rename_default_client`;

-- =============================================================================
-- 5. 执行后验收（只读）
-- =============================================================================
SELECT '=== 5.1 关键列 ===' AS section;
SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND (
    (TABLE_NAME = 'scheduled_tasks' AND COLUMN_NAME IN ('status', 'retry_count', 'last_success_at'))
    OR (TABLE_NAME = 'postback_conversions' AND COLUMN_NAME IN ('transaction_id', 'request_id'))
    OR (TABLE_NAME = 'postback_forward_queue' AND COLUMN_NAME IN ('publisher_id', 'product_id'))
    OR (TABLE_NAME = 'user_sessions' AND COLUMN_NAME = 'token_type')
    OR (TABLE_NAME = 'products' AND COLUMN_NAME = 'cplpo_deduct_ratio')
    OR (TABLE_NAME = 'cloak_configs' AND COLUMN_NAME IN (
      'click_report_enabled', 'load_report_enabled', 'postback_report_enabled', 'postback_report_value'
    ))
  )
ORDER BY TABLE_NAME, ORDINAL_POSITION;

SELECT '=== 5.2 clients 挂靠客户 ===' AS section;
SELECT id, company_name, `key`, is_active, updated_at
FROM clients
WHERE company_name IN ('默认客户（导入数据）', '临时挂靠');

SELECT '=== 5.3 补缺表是否存在 ===' AS section;
SELECT TABLE_NAME, TABLE_COMMENT
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('sensitive_path_probe_logs', 'sensitive_blocked_ips', 'cloak_configs')
ORDER BY TABLE_NAME;

SELECT '=== 5.4 数值精度（全量 ORM 对齐字段）===' AS section;
SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE, COLUMN_DEFAULT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND (
    (TABLE_NAME = 'products' AND COLUMN_NAME IN ('ecpm_deduct_ratio', 'revenue_deduct_ratio', 'cplpo_deduct_ratio'))
    OR (TABLE_NAME = 'ad_data' AND COLUMN_NAME IN (
      'coverage_rate', 'display_rate', 'click_rate', 'viewability_rate',
      'cpc', 'ecpm_before_deduct', 'ecpm_after_deduct', 'revenue_before_deduct', 'revenue_after_deduct'
    ))
    OR (TABLE_NAME = 'tb_search_data' AND COLUMN_NAME IN ('revenue', 'rpm', 'revenue_before_deduct', 'rpm_before_deduct'))
    OR (TABLE_NAME = 'offers' AND COLUMN_NAME IN ('payout', 'affiliate_payout'))
    OR (TABLE_NAME = 'offer_publisher_assignments' AND COLUMN_NAME = 'affiliate_payout')
    OR (TABLE_NAME = 'publishers' AND COLUMN_NAME = 'price_discount')
    OR (TABLE_NAME = 'postback_conversions' AND COLUMN_NAME IN ('event_value', 'original_payout', 'payout'))
    OR (TABLE_NAME = 'pending_postback_conversions' AND COLUMN_NAME IN ('event_value', 'original_payout', 'payout'))
    OR (TABLE_NAME = 'conversion_deduction_configs' AND COLUMN_NAME IN ('volume_deduction_ratio', 'amount_deduction_ratio'))
    OR (TABLE_NAME = 'conversion_deduction_logs' AND COLUMN_NAME IN (
      'original_amount', 'deducted_amount', 'final_amount', 'volume_deduction_ratio', 'amount_deduction_ratio'
    ))
    OR (TABLE_NAME = 'third_party_report_logs' AND COLUMN_NAME = 'amount')
    OR (TABLE_NAME = 'offer_discounts' AND COLUMN_NAME = 'discount_ratio')
    OR (TABLE_NAME = 'advertiser_tests' AND COLUMN_NAME = 'price')
    OR (TABLE_NAME = 'affiliate_tests' AND COLUMN_NAME = 'price')
    OR (TABLE_NAME = 'client_notification_configs' AND COLUMN_NAME = 'high_value_threshold')
    OR (TABLE_NAME = 'product_notification_configs' AND COLUMN_NAME = 'high_value_threshold')
    OR (TABLE_NAME = 'cloak_configs' AND COLUMN_NAME IN ('report_value', 'load_report_value', 'postback_report_value'))
  )
ORDER BY TABLE_NAME, COLUMN_NAME;

SELECT '=== 5.5 数值类型未对齐（应为 DECIMAL 但仍是 float/double 或精度不符）===' AS section;
SELECT c.TABLE_NAME, c.COLUMN_NAME, c.DATA_TYPE, c.NUMERIC_PRECISION, c.NUMERIC_SCALE,
       e.expected_precision, e.expected_scale
FROM information_schema.COLUMNS c
INNER JOIN (
  SELECT 'products' AS tbl, 'ecpm_deduct_ratio' AS col, 12 AS expected_precision, 4 AS expected_scale
  UNION ALL SELECT 'products', 'revenue_deduct_ratio', 12, 4
  UNION ALL SELECT 'products', 'cplpo_deduct_ratio', 12, 4
  UNION ALL SELECT 'ad_data', 'coverage_rate', 7, 4
  UNION ALL SELECT 'ad_data', 'display_rate', 7, 4
  UNION ALL SELECT 'ad_data', 'click_rate', 7, 4
  UNION ALL SELECT 'ad_data', 'viewability_rate', 7, 4
  UNION ALL SELECT 'ad_data', 'cpc', 12, 4
  UNION ALL SELECT 'ad_data', 'ecpm_before_deduct', 12, 4
  UNION ALL SELECT 'ad_data', 'ecpm_after_deduct', 12, 4
  UNION ALL SELECT 'ad_data', 'revenue_before_deduct', 12, 4
  UNION ALL SELECT 'ad_data', 'revenue_after_deduct', 12, 4
  UNION ALL SELECT 'tb_search_data', 'revenue', 12, 4
  UNION ALL SELECT 'tb_search_data', 'rpm', 10, 4
  UNION ALL SELECT 'tb_search_data', 'revenue_before_deduct', 12, 4
  UNION ALL SELECT 'tb_search_data', 'rpm_before_deduct', 10, 4
  UNION ALL SELECT 'offers', 'payout', 10, 2
  UNION ALL SELECT 'offers', 'affiliate_payout', 10, 2
  UNION ALL SELECT 'offer_publisher_assignments', 'affiliate_payout', 10, 2
  UNION ALL SELECT 'publishers', 'price_discount', 5, 2
  UNION ALL SELECT 'postback_conversions', 'event_value', 12, 4
  UNION ALL SELECT 'postback_conversions', 'original_payout', 12, 4
  UNION ALL SELECT 'postback_conversions', 'payout', 12, 4
  UNION ALL SELECT 'pending_postback_conversions', 'event_value', 12, 4
  UNION ALL SELECT 'pending_postback_conversions', 'original_payout', 12, 4
  UNION ALL SELECT 'pending_postback_conversions', 'payout', 12, 4
  UNION ALL SELECT 'conversion_deduction_configs', 'volume_deduction_ratio', 5, 4
  UNION ALL SELECT 'conversion_deduction_configs', 'amount_deduction_ratio', 5, 4
  UNION ALL SELECT 'conversion_deduction_logs', 'original_amount', 10, 2
  UNION ALL SELECT 'conversion_deduction_logs', 'deducted_amount', 10, 2
  UNION ALL SELECT 'conversion_deduction_logs', 'final_amount', 10, 2
  UNION ALL SELECT 'conversion_deduction_logs', 'volume_deduction_ratio', 5, 4
  UNION ALL SELECT 'conversion_deduction_logs', 'amount_deduction_ratio', 5, 4
  UNION ALL SELECT 'third_party_report_logs', 'amount', 12, 4
  UNION ALL SELECT 'offer_discounts', 'discount_ratio', 12, 4
  UNION ALL SELECT 'advertiser_tests', 'price', 12, 4
  UNION ALL SELECT 'affiliate_tests', 'price', 12, 4
  UNION ALL SELECT 'client_notification_configs', 'high_value_threshold', 12, 4
  UNION ALL SELECT 'product_notification_configs', 'high_value_threshold', 12, 4
  UNION ALL SELECT 'cloak_configs', 'report_value', 12, 4
  UNION ALL SELECT 'cloak_configs', 'load_report_value', 12, 4
  UNION ALL SELECT 'cloak_configs', 'postback_report_value', 12, 4
) e ON c.TABLE_NAME = e.tbl AND c.COLUMN_NAME = e.col
WHERE c.TABLE_SCHEMA = DATABASE()
  AND (
    c.DATA_TYPE IN ('float', 'double')
    OR c.DATA_TYPE <> 'decimal'
    OR c.NUMERIC_PRECISION <> e.expected_precision
    OR c.NUMERIC_SCALE <> e.expected_scale
  )
ORDER BY c.TABLE_NAME, c.COLUMN_NAME;
