-- ============================================
-- 数据库迁移脚本：为 short_links 表添加 channel_id 字段
-- 说明：添加渠道ID字段，用于关联短链接和渠道（Publisher）
-- 执行日期：2025-12-25
-- ============================================

-- ============================================
-- 1. 添加 channel_id 字段到 short_links 表
-- ============================================

-- 检查字段是否已存在
SET @exist := (SELECT COUNT(*) FROM information_schema.columns 
               WHERE table_schema = DATABASE() 
               AND table_name = 'short_links' 
               AND column_name = 'channel_id');

-- 如果字段不存在，则添加
SET @sqlstmt := IF(@exist = 0, 
    'ALTER TABLE `short_links` ADD COLUMN `channel_id` int NULL DEFAULT NULL COMMENT ''关联的渠道ID（Publisher ID）'' AFTER `offer_id`', 
    'SELECT "Column channel_id already exists"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================
-- 2. 添加外键约束（如果不存在）
-- ============================================

-- 检查外键是否已存在
SET @exist := (SELECT COUNT(*) FROM information_schema.table_constraints 
               WHERE table_schema = DATABASE() 
               AND table_name = 'short_links' 
               AND constraint_name = 'short_links_ibfk_channel');

-- 如果外键不存在，则添加
SET @sqlstmt := IF(@exist = 0, 
    'ALTER TABLE `short_links` ADD CONSTRAINT `short_links_ibfk_channel` FOREIGN KEY (`channel_id`) REFERENCES `publishers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT', 
    'SELECT "Foreign key short_links_ibfk_channel already exists"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================
-- 3. 添加索引（如果不存在）
-- ============================================

-- 检查索引是否已存在
SET @exist := (SELECT COUNT(*) FROM information_schema.statistics 
               WHERE table_schema = DATABASE() 
               AND table_name = 'short_links' 
               AND index_name = 'idx_short_link_channel_id');

-- 如果索引不存在，则添加
SET @sqlstmt := IF(@exist = 0, 
    'ALTER TABLE `short_links` ADD INDEX `idx_short_link_channel_id`(`channel_id`)', 
    'SELECT "Index idx_short_link_channel_id already exists"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================
-- 迁移完成
-- ============================================
-- 说明：
-- 1. 添加了 channel_id 字段到 short_links 表
-- 2. 添加了外键约束，关联到 publishers 表
-- 3. 添加了索引以提高查询性能
-- 4. 如果字段、外键或索引已存在，脚本会安全跳过，不会报错
-- ============================================

