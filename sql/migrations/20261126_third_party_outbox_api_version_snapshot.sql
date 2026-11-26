-- 首次发送时冻结 Meta Graph API 版本，避免重试时因配置变化而改变请求协议。
-- 仅保存版本标识，不保存 access token 或其它凭据；历史行保持 NULL，首次后续发送时再绑定。
SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'third_party_report_logs'
      AND COLUMN_NAME = 'destination_api_version'
      AND COLUMN_TYPE = 'varchar(20)' AND IS_NULLABLE = 'YES'
);
SET @ddl = IF(
    @has_col = 0,
    'ALTER TABLE third_party_report_logs ADD COLUMN destination_api_version VARCHAR(20) NULL COMMENT ''首次发送时冻结的 Meta Graph API 版本；不保存凭据'' AFTER destination_pixel_id',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'third_party_report_logs'
  AND COLUMN_NAME = 'destination_api_version';
