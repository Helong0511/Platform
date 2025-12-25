-- ============================================
-- Short Links 表优化迁移脚本
-- ============================================
-- 目的：优化 short_links 表的索引结构
-- 1. 删除重复索引（short_code 已有唯一索引，不需要普通索引）
-- 2. 可选：添加管理后台查询优化索引
-- ============================================

-- ============================================
-- 1. 删除重复索引（推荐立即执行）
-- ============================================
-- short_code 字段已有 UNIQUE INDEX，不需要额外的普通索引
-- 删除重复索引可以提高插入性能并节省存储空间

-- 检查索引是否存在
SET @exist := (SELECT COUNT(*) FROM information_schema.statistics 
               WHERE table_schema = DATABASE() 
               AND table_name = 'short_links' 
               AND index_name = 'idx_short_link_code');

-- 如果索引存在，则删除
SET @sqlstmt := IF(@exist > 0, 
    'ALTER TABLE `short_links` DROP INDEX `idx_short_link_code`', 
    'SELECT "Index idx_short_link_code does not exist, skipping"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================
-- 2. 添加列表查询优化索引（可选）
-- ============================================
-- 用于管理后台列表查询：按创建者 + 激活状态过滤，按创建时间排序
-- 查询示例：
--   SELECT * FROM short_links 
--   WHERE created_by = ? AND is_active = ? 
--   ORDER BY created_at DESC
--   LIMIT ? OFFSET ?

-- 检查索引是否已存在
SET @exist := (SELECT COUNT(*) FROM information_schema.statistics 
               WHERE table_schema = DATABASE() 
               AND table_name = 'short_links' 
               AND index_name = 'idx_short_links_created_by_active_created');

-- 如果索引不存在，则添加
SET @sqlstmt := IF(@exist = 0, 
    'ALTER TABLE `short_links` ADD INDEX `idx_short_links_created_by_active_created`(`created_by`, `is_active`, `created_at` DESC)', 
    'SELECT "Index idx_short_links_created_by_active_created already exists"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================
-- 3. 添加 Offer + Channel 查询索引（可选）
-- ============================================
-- 用于按Offer和Channel查询短链接
-- 查询示例：
--   SELECT * FROM short_links 
--   WHERE offer_id = ? AND channel_id = ?

-- 检查索引是否已存在
SET @exist := (SELECT COUNT(*) FROM information_schema.statistics 
               WHERE table_schema = DATABASE() 
               AND table_name = 'short_links' 
               AND index_name = 'idx_short_links_offer_channel');

-- 如果索引不存在，则添加
SET @sqlstmt := IF(@exist = 0, 
    'ALTER TABLE `short_links` ADD INDEX `idx_short_links_offer_channel`(`offer_id`, `channel_id`)', 
    'SELECT "Index idx_short_links_offer_channel already exists"');
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
    NON_UNIQUE,
    CARDINALITY
FROM information_schema.STATISTICS
WHERE table_schema = DATABASE()
  AND table_name = 'short_links'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;

-- ============================================
-- 迁移完成
-- ============================================
-- 说明：
-- 1. 删除了重复的 short_code 索引（已有唯一索引）
-- 2. 添加了列表查询优化索引（可选，如果管理后台查询慢）
-- 3. 添加了 Offer+Channel 查询索引（可选，如果这种查询频繁）
-- 4. 所有操作都是安全的，如果索引已存在会跳过
-- 5. 建议在低峰期执行
-- ============================================

