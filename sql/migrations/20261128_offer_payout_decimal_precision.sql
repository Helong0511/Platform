-- 扩展 Offer PO 的存储精度，避免三位/六位小数币种在配置阶段被截断。
-- 仅扩大 DECIMAL 精度，不改写历史金额、不执行汇率换算。
-- 生产执行前必须在同规模结构副本演练锁等待、重建时间和磁盘空间。
ALTER TABLE offers
    MODIFY COLUMN payout DECIMAL(24, 6) NULL DEFAULT NULL
        COMMENT '上游支付金额（PO）',
    MODIFY COLUMN affiliate_payout DECIMAL(24, 6) NULL DEFAULT NULL
        COMMENT '扣价后给渠道的金额（PO扣价后）';

ALTER TABLE offer_publisher_assignments
    MODIFY COLUMN affiliate_payout DECIMAL(24, 6) NULL DEFAULT NULL
        COMMENT '该渠道的转化金额（PO）';
