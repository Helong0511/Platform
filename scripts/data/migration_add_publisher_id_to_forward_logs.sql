-- ============================================
-- 迁移脚本：为 postback_forward_logs 表添加 publisher_id 字段
-- 创建时间：2025-01-XX
-- 说明：添加渠道ID字段，用于记录转发到渠道时的渠道信息
-- ============================================

-- 添加 publisher_id 字段（渠道ID）
ALTER TABLE `postback_forward_logs` 
ADD COLUMN `publisher_id` INT NULL DEFAULT NULL COMMENT '渠道ID（转发到渠道时使用）' AFTER `product_id`;

-- 添加外键约束
ALTER TABLE `postback_forward_logs`
ADD CONSTRAINT `fk_forward_log_publisher` 
FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) 
ON DELETE SET NULL ON UPDATE RESTRICT;

-- 添加索引
ALTER TABLE `postback_forward_logs`
ADD INDEX `idx_forward_log_publisher` (`publisher_id` ASC) USING BTREE;

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
    AND TABLE_NAME = 'postback_forward_logs'
    AND COLUMN_NAME = 'publisher_id';

