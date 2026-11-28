-- 币种归因结构迁移：只执行元数据 DDL 与低基数配置回退，不在迁移事务中扫描/更新大表。
-- Postback / pending / report log 的历史数据回填由 scripts/backfill_currency_attribution.py 分批执行。
-- 所有金额字段保持原值；无币种时 USD 兜底；非空无效币种不得自动替换为 USD。
ALTER TABLE cloak_configs
    ADD COLUMN report_currency_source VARCHAR(100) NULL COMMENT '点击阶段币种来源归因',
    ADD COLUMN load_report_currency_source VARCHAR(100) NULL COMMENT '加载阶段币种来源归因',
    ADD COLUMN postback_report_currency_source VARCHAR(100) NULL COMMENT 'postback 阶段币种来源归因',
    ALGORITHM=INSTANT;

UPDATE cloak_configs
SET
    report_currency_source = CASE
        WHEN report_currency IS NULL OR TRIM(report_currency) = '' THEN 'system_fallback_usd'
        ELSE 'legacy_unknown'
    END,
    load_report_currency_source = CASE
        WHEN load_report_currency IS NULL OR TRIM(load_report_currency) = '' THEN 'system_fallback_usd'
        ELSE 'legacy_unknown'
    END,
    postback_report_currency_source = CASE
        WHEN postback_report_currency IS NULL OR TRIM(postback_report_currency) = '' THEN 'system_fallback_usd'
        ELSE 'legacy_unknown'
    END;

ALTER TABLE cloak_configs
    ALTER COLUMN report_currency SET DEFAULT 'USD',
    ALTER COLUMN load_report_currency SET DEFAULT 'USD',
    ALTER COLUMN postback_report_currency SET DEFAULT 'USD',
    ALGORITHM=INSTANT;

UPDATE cloak_configs
SET report_currency = 'USD'
WHERE report_currency IS NULL OR TRIM(report_currency) = '';

UPDATE cloak_configs
SET load_report_currency = 'USD'
WHERE load_report_currency IS NULL OR TRIM(load_report_currency) = '';

UPDATE cloak_configs
SET postback_report_currency = 'USD'
WHERE postback_report_currency IS NULL OR TRIM(postback_report_currency) = '';

ALTER TABLE postback_conversions
    ADD COLUMN currency VARCHAR(10) NOT NULL DEFAULT 'USD'
        COMMENT 'Postback payout 的 ISO 4217 币种；缺失时 USD 兜底',
    ADD COLUMN currency_source VARCHAR(100) NOT NULL DEFAULT 'system_fallback_usd'
        COMMENT 'Postback payout 币种来源归因',
    ALGORITHM=INSTANT;

ALTER TABLE pending_postback_conversions
    ADD COLUMN currency VARCHAR(10) NOT NULL DEFAULT 'USD'
        COMMENT '待确认 Postback payout 的 ISO 4217 币种',
    ADD COLUMN currency_source VARCHAR(100) NOT NULL DEFAULT 'system_fallback_usd'
        COMMENT '待确认 Postback payout 币种来源',
    ALGORITHM=INSTANT;

ALTER TABLE conversion_deduction_logs
    ADD COLUMN currency VARCHAR(10) NOT NULL DEFAULT 'USD'
        COMMENT '扣减金额对应的 ISO 4217 币种',
    ADD COLUMN currency_source VARCHAR(100) NOT NULL DEFAULT 'system_fallback_usd'
        COMMENT '扣减金额币种来源归因',
    ALGORITHM=INSTANT;

ALTER TABLE third_party_report_logs
    ADD COLUMN currency_source VARCHAR(100) NULL
        COMMENT '币种来源：upstream_field:* / cloak_config:* / system_fallback_usd / manual_override / legacy_unknown',
    ALGORITHM=INSTANT;

-- 迁移后结构核验；历史回填脚本会输出逐表币种来源分组和无效代码明细。
SELECT TABLE_NAME, COLUMN_NAME, COLUMN_DEFAULT, IS_NULLABLE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND (
      (TABLE_NAME = 'cloak_configs' AND COLUMN_NAME IN ('report_currency', 'load_report_currency', 'postback_report_currency'))
      OR (TABLE_NAME IN ('postback_conversions', 'pending_postback_conversions') AND COLUMN_NAME IN ('currency', 'currency_source'))
      OR (TABLE_NAME = 'conversion_deduction_logs' AND COLUMN_NAME IN ('currency', 'currency_source'))
      OR (TABLE_NAME = 'third_party_report_logs' AND COLUMN_NAME = 'currency_source')
  )
ORDER BY TABLE_NAME, ORDINAL_POSITION;
