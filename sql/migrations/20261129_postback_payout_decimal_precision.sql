-- 统一第三方 Purchase 日志金额精度到 DECIMAL(24,6)。
-- 同时覆盖 postback、pending postback、cloak 配置及第三方报告日志。
-- 仅扩大精度，不修改历史金额、不进行币种换算。

ALTER TABLE postback_conversions
    MODIFY COLUMN event_value DECIMAL(24, 6) NULL DEFAULT NULL,
    MODIFY COLUMN original_payout DECIMAL(24, 6) NULL DEFAULT NULL,
    MODIFY COLUMN payout DECIMAL(24, 6) NULL DEFAULT NULL;

ALTER TABLE pending_postback_conversions
    MODIFY COLUMN event_value DECIMAL(24, 6) NULL DEFAULT NULL,
    MODIFY COLUMN original_payout DECIMAL(24, 6) NULL DEFAULT NULL,
    MODIFY COLUMN payout DECIMAL(24, 6) NULL DEFAULT NULL;

ALTER TABLE cloak_configs
    MODIFY COLUMN report_value DECIMAL(24, 6) NULL DEFAULT NULL,
    MODIFY COLUMN load_report_value DECIMAL(24, 6) NULL DEFAULT NULL,
    MODIFY COLUMN postback_report_value DECIMAL(24, 6) NULL DEFAULT NULL;

ALTER TABLE third_party_report_logs
    MODIFY COLUMN amount DECIMAL(24, 6) NULL DEFAULT NULL;
