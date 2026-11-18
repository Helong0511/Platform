-- 为管理员手动重试设置独立的、不可随自动重试重置的累计预算。
-- attempt_count 仍统计当前自动重试周期；manual_retry_count 统计该事件整个生命周期的人工重新入队次数。
-- 限额由应用以条件 UPDATE 原子执行，旧记录默认 0；重复执行迁移安全。

SET @manual_retry_count_column_exists = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'third_party_report_logs'
      AND COLUMN_NAME = 'manual_retry_count'
      AND COLUMN_TYPE = 'int'
      AND IS_NULLABLE = 'NO'
);
SET @ddl = IF(
    @manual_retry_count_column_exists = 1,
    'SELECT 1',
    'ALTER TABLE third_party_report_logs ADD COLUMN manual_retry_count INT NOT NULL DEFAULT 0 COMMENT ''管理员手动重新入队累计次数；不随自动重试重置'''
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @manual_retry_count_column_valid = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'third_party_report_logs'
      AND COLUMN_NAME = 'manual_retry_count'
      AND COLUMN_TYPE = 'int'
      AND IS_NULLABLE = 'NO'
      AND COLUMN_DEFAULT = '0'
);
SET @verify_sql = IF(
    @manual_retry_count_column_valid = 1,
    'SELECT 1',
    'SELECT * FROM __manual_retry_count_validation_failed__'
);
PREPARE verify_stmt FROM @verify_sql;
EXECUTE verify_stmt;
DEALLOCATE PREPARE verify_stmt;
