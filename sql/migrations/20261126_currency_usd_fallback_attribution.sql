-- 统一斗篷三阶段币种默认值，并为第三方 Purchase 日志增加币种来源归因。
-- 只对缺失币种的 Purchase 记录补 USD；不改写已有非空币种和金额。
-- 既有非空币种的历史来源无法从该表单独证明，标记 legacy_unknown，后续需结合原始回调/配置快照审计。
ALTER TABLE cloak_configs
    MODIFY COLUMN report_currency VARCHAR(10) NULL DEFAULT 'USD'
        COMMENT '点击 Purchase 货币；未设置时 USD 兜底',
    MODIFY COLUMN load_report_currency VARCHAR(10) NULL DEFAULT 'USD'
        COMMENT '加载 Purchase 货币；未设置时 USD 兜底',
    MODIFY COLUMN postback_report_currency VARCHAR(10) NULL DEFAULT 'USD'
        COMMENT 'postback Purchase 货币；未设置时 USD 兜底';

UPDATE cloak_configs
SET report_currency = 'USD'
WHERE report_currency IS NULL OR TRIM(report_currency) = '';

UPDATE cloak_configs
SET load_report_currency = 'USD'
WHERE load_report_currency IS NULL OR TRIM(load_report_currency) = '';

UPDATE cloak_configs
SET postback_report_currency = 'USD'
WHERE postback_report_currency IS NULL OR TRIM(postback_report_currency) = '';

ALTER TABLE third_party_report_logs
    ADD COLUMN currency_source VARCHAR(100) NULL
        COMMENT '币种来源：upstream_field:* / cloak_config:* / system_fallback_usd / manual_override / legacy_unknown'
        AFTER currency;

UPDATE third_party_report_logs
SET currency = 'USD',
    currency_source = 'system_fallback_usd'
WHERE event = 'Purchase'
  AND (currency IS NULL OR TRIM(currency) = '');

UPDATE third_party_report_logs
SET currency_source = 'legacy_unknown'
WHERE event = 'Purchase'
  AND currency IS NOT NULL
  AND TRIM(currency) <> ''
  AND currency_source IS NULL;

-- 迁移后核验：三阶段默认值及历史 Purchase 归因均应可见。
SELECT COLUMN_NAME, COLUMN_DEFAULT, IS_NULLABLE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'cloak_configs'
  AND COLUMN_NAME IN ('report_currency', 'load_report_currency', 'postback_report_currency');

SELECT currency, currency_source, COUNT(*) AS row_count
FROM third_party_report_logs
WHERE event = 'Purchase'
GROUP BY currency, currency_source
ORDER BY currency, currency_source;
