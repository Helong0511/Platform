-- 禁止 Postback Purchase 币种在 ORM/数据库层静默默认 USD。
-- 历史行保留原值，不推断旧 USD 是人工配置还是历史默认；上线前需只读盘点。
-- 直接 MODIFY：若目标表/列不存在则失败，不允许迁移 runner 将 no-op 误记为成功。
ALTER TABLE cloak_configs
    ALTER COLUMN postback_report_currency DROP DEFAULT,
    ALGORITHM=INSTANT;

-- 迁移后核验：字段必须可空且数据库默认值必须为 NULL。
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'cloak_configs'
  AND COLUMN_NAME = 'postback_report_currency';
