-- 将 Postback 正式转化、待审批与斗篷 Purchase 金额精度统一到 DECIMAL(24,6)。
-- 仅扩大列精度，不改写历史金额、不执行汇率换算。
-- MySQL DDL 隐式提交；执行前应核对实际表结构并在生产结构副本演练。

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
