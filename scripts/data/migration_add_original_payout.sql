-- ============================================
-- 迁移脚本：为 postback_conversions 表添加 original_payout 字段
-- 创建时间：2025-01-XX
-- 说明：添加原始 payout (PO) 字段，payout 字段将存储扣后 payout (PO(扣))
-- ============================================

-- 添加 original_payout 字段（原始支付金额 PO）
ALTER TABLE `postback_conversions` 
ADD COLUMN `original_payout` FLOAT NULL DEFAULT NULL COMMENT '原始支付金额（PO）' AFTER `event_value`;

-- 对于旧数据，将现有的 payout 值复制到 original_payout
-- 注意：这假设旧数据中的 payout 是原始值（如果没有扣量计算）
-- 如果旧数据中 payout 已经是扣后的，需要根据实际情况调整
UPDATE `postback_conversions` 
SET `original_payout` = `payout` 
WHERE `original_payout` IS NULL AND `payout` IS NOT NULL;

-- 验证字段是否添加成功
SELECT 
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    COLUMN_COMMENT
FROM 
    INFORMATION_SCHEMA.COLUMNS
WHERE 
    TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'postback_conversions'
    AND COLUMN_NAME IN ('original_payout', 'payout')
ORDER BY 
    ORDINAL_POSITION;

