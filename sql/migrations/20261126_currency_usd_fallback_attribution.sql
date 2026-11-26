-- 统一斗篷三阶段币种默认值，并为 Postback/第三方 Purchase 持久化币种来源归因。
-- 缺失币种统一补 USD；还原可证明的上游字段来源；不改写任何金额。
-- 既有非空第三方 Purchase 币种来源无法仅凭旧日志证明，标记 legacy_unknown。
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

-- Postback payout 正式记录增加币种与来源。
ALTER TABLE postback_conversions
    ADD COLUMN currency VARCHAR(10) NOT NULL DEFAULT 'USD'
        COMMENT 'Postback payout 的 ISO 4217 币种；缺失时 USD 兜底' AFTER payout,
    ADD COLUMN currency_source VARCHAR(100) NOT NULL DEFAULT 'system_fallback_usd'
        COMMENT 'Postback payout 币种来源归因' AFTER currency;

-- 仅对 JSON_VALID 的历史原始回调解析币种；非空无效代码原样保留，后续 ISO 审计识别。
UPDATE postback_conversions
SET
    currency = UPPER(COALESCE(
        NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_data, '$.currency'))), ''),
        NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_data, '$.currency_code'))), ''),
        NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_data, '$.currencyCode'))), ''),
        NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_data, '$._payload.currency'))), ''),
        NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_data, '$._payload.currency_code'))), ''),
        NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_data, '$._payload.currencyCode'))), ''),
        'USD'
    )),
    currency_source = CASE
        WHEN NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_data, '$.currency'))), '') IS NOT NULL
            THEN 'upstream_field:currency'
        WHEN NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_data, '$.currency_code'))), '') IS NOT NULL
            THEN 'upstream_field:currency_code'
        WHEN NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_data, '$.currencyCode'))), '') IS NOT NULL
            THEN 'upstream_field:currencyCode'
        WHEN NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_data, '$._payload.currency'))), '') IS NOT NULL
            THEN 'upstream_field:currency'
        WHEN NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_data, '$._payload.currency_code'))), '') IS NOT NULL
            THEN 'upstream_field:currency_code'
        WHEN NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_data, '$._payload.currencyCode'))), '') IS NOT NULL
            THEN 'upstream_field:currencyCode'
        ELSE 'system_fallback_usd'
    END
WHERE JSON_VALID(raw_data) = 1;

UPDATE postback_conversions
SET currency = 'USD', currency_source = 'system_fallback_usd'
WHERE raw_data IS NULL OR JSON_VALID(raw_data) = 0;

-- 待审批 Postback 记录也保存币种与来源；审批通过时原样复制到正式转化。
ALTER TABLE pending_postback_conversions
    ADD COLUMN currency VARCHAR(10) NOT NULL DEFAULT 'USD'
        COMMENT '待确认 Postback payout 的 ISO 4217 币种' AFTER payout,
    ADD COLUMN currency_source VARCHAR(100) NOT NULL DEFAULT 'system_fallback_usd'
        COMMENT '待确认 Postback payout 币种来源' AFTER currency;

UPDATE pending_postback_conversions
SET
    currency = UPPER(COALESCE(
        NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_data, '$.currency'))), ''),
        NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_data, '$.currency_code'))), ''),
        NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_data, '$.currencyCode'))), ''),
        NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_data, '$._payload.currency'))), ''),
        NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_data, '$._payload.currency_code'))), ''),
        NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_data, '$._payload.currencyCode'))), ''),
        'USD'
    )),
    currency_source = CASE
        WHEN NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_data, '$.currency'))), '') IS NOT NULL
            THEN 'upstream_field:currency'
        WHEN NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_data, '$.currency_code'))), '') IS NOT NULL
            THEN 'upstream_field:currency_code'
        WHEN NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_data, '$.currencyCode'))), '') IS NOT NULL
            THEN 'upstream_field:currencyCode'
        WHEN NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_data, '$._payload.currency'))), '') IS NOT NULL
            THEN 'upstream_field:currency'
        WHEN NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_data, '$._payload.currency_code'))), '') IS NOT NULL
            THEN 'upstream_field:currency_code'
        WHEN NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_data, '$._payload.currencyCode'))), '') IS NOT NULL
            THEN 'upstream_field:currencyCode'
        ELSE 'system_fallback_usd'
    END
WHERE JSON_VALID(raw_data) = 1;

UPDATE pending_postback_conversions
SET currency = 'USD', currency_source = 'system_fallback_usd'
WHERE raw_data IS NULL OR JSON_VALID(raw_data) = 0;

-- 第三方上报日志保留独立币种来源。
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

-- 迁移后核验：正式/待审批 Postback 与第三方 Purchase 的币种/来源归因均应可见。
SELECT currency, currency_source, COUNT(*) AS row_count
FROM postback_conversions
GROUP BY currency, currency_source
ORDER BY currency, currency_source;

SELECT currency, currency_source, COUNT(*) AS row_count
FROM pending_postback_conversions
GROUP BY currency, currency_source
ORDER BY currency, currency_source;

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
