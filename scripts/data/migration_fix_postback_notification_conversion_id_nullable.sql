-- ============================================================
-- 修复 PostbackNotification 表的 conversion_id 字段，允许为 NULL
-- 原因：汇总通知（summary_hourly/summary_daily）没有关联的具体转化记录
-- ============================================================

-- 修改 conversion_id 字段，允许为 NULL
ALTER TABLE `postback_notifications` 
MODIFY COLUMN `conversion_id` int NULL COMMENT '转化记录ID（汇总通知时为NULL）';

-- 更新 notification_type 字段的注释，添加汇总通知类型
ALTER TABLE `postback_notifications` 
MODIFY COLUMN `notification_type` varchar(50) NULL COMMENT '通知类型：conversion, high_value, error, forward, summary_hourly, summary_daily';

-- 注意：如果表中有数据，且 conversion_id 为 NULL 的记录，需要确保：
-- 1. 这些记录的 notification_type 应该是 summary_hourly 或 summary_daily
-- 2. 这些记录必须有 client_id 和 product_id
