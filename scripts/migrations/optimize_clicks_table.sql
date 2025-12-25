-- ============================================
-- Clicks 表优化迁移脚本
-- ============================================
-- 目的：优化 clicks 表的查询性能
-- 添加复合索引以支持常见的统计查询
-- ============================================

-- ============================================
-- 1. 添加复合索引（时间范围 + Offer + Publisher）
-- ============================================
-- 用于最常见的统计查询：按时间范围 + offer_id + publisher_id 分组统计
-- 查询示例：
--   SELECT offer_id, publisher_id, COUNT(*) 
--   FROM clicks 
--   WHERE click_time >= ? AND click_time < ? 
--     AND offer_id = ? AND publisher_id = ?
--   GROUP BY offer_id, publisher_id

-- 检查索引是否已存在
SET @exist := (SELECT COUNT(*) FROM information_schema.statistics 
               WHERE table_schema = DATABASE() 
               AND table_name = 'clicks' 
               AND index_name = 'idx_clicks_time_offer_publisher');

-- 如果索引不存在，则添加
SET @sqlstmt := IF(@exist = 0, 
    'ALTER TABLE `clicks` ADD INDEX `idx_clicks_time_offer_publisher`(`click_time`, `offer_id`, `publisher_id`)', 
    'SELECT "Index idx_clicks_time_offer_publisher already exists"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================
-- 2. 添加复合索引（时间范围 + Offer）
-- ============================================
-- 用于按Offer统计的查询
-- 查询示例：
--   SELECT COUNT(*) 
--   FROM clicks 
--   WHERE click_time >= ? AND click_time < ? 
--     AND offer_id = ?

-- 检查索引是否已存在
SET @exist := (SELECT COUNT(*) FROM information_schema.statistics 
               WHERE table_schema = DATABASE() 
               AND table_name = 'clicks' 
               AND index_name = 'idx_clicks_time_offer');

-- 如果索引不存在，则添加
SET @sqlstmt := IF(@exist = 0, 
    'ALTER TABLE `clicks` ADD INDEX `idx_clicks_time_offer`(`click_time`, `offer_id`)', 
    'SELECT "Index idx_clicks_time_offer already exists"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================
-- 3. 添加复合索引（Offer + Publisher + 时间）（可选）
-- ============================================
-- 用于先按 offer_id 和 publisher_id 过滤，再按时间排序的查询
-- 查询示例：
--   SELECT * 
--   FROM clicks 
--   WHERE offer_id = ? AND publisher_id = ? 
--   ORDER BY click_time DESC 
--   LIMIT 100

-- 检查索引是否已存在
SET @exist := (SELECT COUNT(*) FROM information_schema.statistics 
               WHERE table_schema = DATABASE() 
               AND table_name = 'clicks' 
               AND index_name = 'idx_clicks_offer_publisher_time');

-- 如果索引不存在，则添加
SET @sqlstmt := IF(@exist = 0, 
    'ALTER TABLE `clicks` ADD INDEX `idx_clicks_offer_publisher_time`(`offer_id`, `publisher_id`, `click_time`)', 
    'SELECT "Index idx_clicks_offer_publisher_time already exists"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================
-- 4. 验证索引
-- ============================================
-- 查看所有索引
SELECT 
    INDEX_NAME,
    COLUMN_NAME,
    SEQ_IN_INDEX,
    CARDINALITY
FROM information_schema.STATISTICS
WHERE table_schema = DATABASE()
  AND table_name = 'clicks'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;

-- ============================================
-- 迁移完成
-- ============================================
-- 说明：
-- 1. 添加了3个复合索引以优化常见查询
-- 2. 索引创建是安全的，如果已存在会跳过
-- 3. 索引创建可能需要一些时间（取决于数据量）
-- 4. 建议在低峰期执行
-- ============================================

