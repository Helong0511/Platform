-- 为 offer_publisher_assignments 表添加渠道级别的下游Cap和下游PO字段
-- 迁移日期: 2024-12-19
-- 说明: 每个渠道现在可以有自己的下游Cap和下游PO配置

-- 添加 downstream_cap 字段（该渠道的下游转化上限）
ALTER TABLE `offer_publisher_assignments` 
ADD COLUMN `downstream_cap` int NULL COMMENT '该渠道的下游转化上限' AFTER `publisher_id`;

-- 添加 affiliate_payout 字段（该渠道的扣价后给渠道的金额）
ALTER TABLE `offer_publisher_assignments` 
ADD COLUMN `affiliate_payout` decimal(10,2) NULL COMMENT '该渠道的扣价后给渠道的金额（PO扣价后）' AFTER `downstream_cap`;

-- 验证字段是否添加成功
-- SELECT COLUMN_NAME, COLUMN_TYPE, COLUMN_COMMENT 
-- FROM information_schema.COLUMNS 
-- WHERE TABLE_SCHEMA = 'platform' 
-- AND TABLE_NAME = 'offer_publisher_assignments'
-- AND COLUMN_NAME IN ('downstream_cap', 'affiliate_payout');

