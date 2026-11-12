-- 第三方 Postback CAPI 事务性 Outbox 扩展（MySQL 8.0.16+）
-- 每个字段和索引均通过 information_schema 检测后再添加；可在任意 DDL 边界中断后安全重跑。
-- 本迁移不连接/执行生产数据库；access_token 等凭据绝不写入 Outbox。

SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'third_party_report_logs'
      AND COLUMN_NAME = 'outbox_enqueued'
      AND COLUMN_TYPE = 'tinyint(1)' AND IS_NULLABLE = 'NO' AND COLUMN_DEFAULT = '0'
);
SET @ddl = IF(
    @has_col = 0,
    'ALTER TABLE third_party_report_logs ADD COLUMN outbox_enqueued TINYINT(1) NOT NULL DEFAULT 0 COMMENT ''是否由转化事务创建的持久化 Outbox 事件'' AFTER amount',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'third_party_report_logs'
      AND COLUMN_NAME = 'short_link_id'
      AND COLUMN_TYPE = 'int' AND IS_NULLABLE = 'YES'
);
SET @ddl = IF(
    @has_col = 0,
    'ALTER TABLE third_party_report_logs ADD COLUMN short_link_id INT NULL COMMENT ''用于恢复像素配置的短链接 ID（非外键，保留删除后的证据）'' AFTER outbox_enqueued',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'third_party_report_logs'
      AND COLUMN_NAME = 'cloak_name'
      AND COLUMN_TYPE = 'varchar(100)' AND IS_NULLABLE = 'YES'
);
SET @ddl = IF(
    @has_col = 0,
    'ALTER TABLE third_party_report_logs ADD COLUMN cloak_name VARCHAR(100) NULL COMMENT ''斗篷配置名称（仅配置引用）'' AFTER short_link_id',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'third_party_report_logs'
      AND COLUMN_NAME = 'short_code'
      AND COLUMN_TYPE = 'varchar(100)' AND IS_NULLABLE = 'YES'
);
SET @ddl = IF(
    @has_col = 0,
    'ALTER TABLE third_party_report_logs ADD COLUMN short_code VARCHAR(100) NULL COMMENT ''短链接短码（仅配置引用）'' AFTER cloak_name',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'third_party_report_logs'
      AND COLUMN_NAME = 'click_time'
      AND COLUMN_TYPE = 'datetime' AND IS_NULLABLE = 'YES'
);
SET @ddl = IF(
    @has_col = 0,
    'ALTER TABLE third_party_report_logs ADD COLUMN click_time DATETIME NULL COMMENT ''点击发生时间，用于稳定构造 Meta event_time/fbc'' AFTER short_code',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'third_party_report_logs'
      AND COLUMN_NAME = 'next_retry_time'
      AND COLUMN_TYPE = 'datetime' AND IS_NULLABLE = 'YES'
);
SET @ddl = IF(
    @has_col = 0,
    'ALTER TABLE third_party_report_logs ADD COLUMN next_retry_time DATETIME NULL COMMENT ''Outbox 下次可重试时间'' AFTER click_time',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- 校验索引完整结构；错误的同名索引不得被当作已完成迁移。
SET @has_index = (
    SELECT COUNT(*)
    FROM (
        SELECT INDEX_NAME
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'third_party_report_logs'
          AND INDEX_NAME = 'idx_third_party_outbox_due'
        GROUP BY INDEX_NAME
        HAVING COUNT(*) = 5
           AND GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX SEPARATOR ',') = 'outbox_enqueued,status,next_retry_time,report_start_time,id'
    ) AS valid_outbox_index
);
SET @ddl = IF(
    @has_due_index = 0,
    'ALTER TABLE third_party_report_logs ADD INDEX idx_third_party_outbox_due (outbox_enqueued, status, next_retry_time, report_start_time, id)',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- 迁移后核验字段与索引；历史记录 outbox_enqueued 默认 0，不会被意外纳入发送。
SELECT COLUMN_NAME FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'third_party_report_logs'
  AND COLUMN_NAME IN ('outbox_enqueued', 'short_link_id', 'cloak_name', 'short_code', 'click_time', 'next_retry_time');
SHOW INDEX FROM third_party_report_logs;
