-- 禁止 Postback Purchase 币种在 ORM/数据库层静默默认 USD。
-- 历史行保留原值，不推断旧 USD 是人工配置还是历史默认；上线前需只读盘点。
SET @has_column = (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'cloak_configs'
      AND COLUMN_NAME = 'postback_report_currency'
      AND COLUMN_TYPE = 'varchar(10)'
      AND IS_NULLABLE = 'YES'
);
SET @ddl = IF(
    @has_column = 1,
    'ALTER TABLE cloak_configs MODIFY COLUMN postback_report_currency VARCHAR(10) NULL DEFAULT NULL COMMENT ''postback Purchase 货币；NULL 表示未配置''',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- 迁移后核验：字段必须可空且数据库默认值必须为 NULL。
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'cloak_configs'
  AND COLUMN_NAME = 'postback_report_currency';
