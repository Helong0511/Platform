-- ============================================
-- 数据库迁移脚本：为 clicks 表添加 short_link_id 字段
-- 说明：添加短链接ID字段，用于记录短链接点击时的 click_id
-- 执行日期：2025-12-23
-- ============================================

-- ============================================
-- 1. 添加 short_link_id 字段到 clicks 表
-- ============================================

-- 检查字段是否已存在
SET @exist := (SELECT COUNT(*) FROM information_schema.columns 
               WHERE table_schema = DATABASE() 
               AND table_name = 'clicks' 
               AND column_name = 'short_link_id');

-- 如果字段不存在，则添加
SET @sqlstmt := IF(@exist = 0, 
    'ALTER TABLE `clicks` ADD COLUMN `short_link_id` int NULL DEFAULT NULL COMMENT ''关联的短链接ID'' AFTER `advertiser_id`', 
    'SELECT "Column short_link_id already exists"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================
-- 2. 添加外键约束（如果不存在）
-- ============================================

-- 检查外键是否已存在
SET @exist := (SELECT COUNT(*) FROM information_schema.table_constraints 
               WHERE table_schema = DATABASE() 
               AND table_name = 'clicks' 
               AND constraint_name = 'clicks_ibfk_short_link');

-- 如果外键不存在，则添加
SET @sqlstmt := IF(@exist = 0, 
    'ALTER TABLE `clicks` ADD CONSTRAINT `clicks_ibfk_short_link` FOREIGN KEY (`short_link_id`) REFERENCES `short_links` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT', 
    'SELECT "Foreign key clicks_ibfk_short_link already exists"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================
-- 3. 添加索引（如果不存在）
-- ============================================

-- 检查索引是否已存在
SET @exist := (SELECT COUNT(*) FROM information_schema.statistics 
               WHERE table_schema = DATABASE() 
               AND table_name = 'clicks' 
               AND index_name = 'idx_short_link_id');

-- 如果索引不存在，则添加
SET @sqlstmt := IF(@exist = 0, 
    'ALTER TABLE `clicks` ADD INDEX `idx_short_link_id`(`short_link_id`)', 
    'SELECT "Index idx_short_link_id already exists"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================
-- 迁移完成
-- ============================================
-- 说明：
-- 1. 添加了 short_link_id 字段到 clicks 表
-- 2. 添加了外键约束，关联到 short_links 表
-- 3. 添加了索引以提高查询性能
-- 4. 如果字段、外键或索引已存在，脚本会安全跳过，不会报错
-- ============================================

