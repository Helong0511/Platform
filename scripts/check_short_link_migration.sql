-- ============================================
-- 检查 short_link_id 字段是否已添加到 clicks 表
-- ============================================

-- 检查字段是否存在
SELECT 
    CASE 
        WHEN COUNT(*) > 0 THEN '字段已存在'
        ELSE '字段不存在，需要执行迁移'
    END AS status,
    COUNT(*) AS field_count
FROM information_schema.columns 
WHERE table_schema = DATABASE() 
AND table_name = 'clicks' 
AND column_name = 'short_link_id';

-- 如果字段不存在，显示需要执行的SQL
SELECT 
    '如果字段不存在，请执行以下SQL:' AS instruction,
    'ALTER TABLE `clicks` ADD COLUMN `short_link_id` int NULL DEFAULT NULL COMMENT ''关联的短链接ID'' AFTER `advertiser_id`;' AS sql_statement;

