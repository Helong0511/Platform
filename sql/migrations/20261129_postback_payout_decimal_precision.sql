-- 将 Postback 正式转化与待审批金额精度统一到 PO 的 DECIMAL(24,6)。
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
