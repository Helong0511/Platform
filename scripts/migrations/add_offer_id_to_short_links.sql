-- ============================================
-- 数据库迁移脚本：为 short_links 表添加 offer_id 字段
-- 说明：添加Offer ID字段，用于关联短链接和Offer
-- 执行日期：2025-12-25
-- ============================================

-- ============================================
-- 1. 添加 offer_id 字段到 short_links 表
-- ============================================

-- 检查字段是否已存在
SET @exist := (SELECT COUNT(*) FROM information_schema.columns 
               WHERE table_schema = DATABASE() 
               AND table_name = 'short_links' 
               AND column_name = 'offer_id');

-- 如果字段不存在，则添加
SET @sqlstmt := IF(@exist = 0, 
    'ALTER TABLE `short_links` ADD COLUMN `offer_id` int NULL DEFAULT NULL COMMENT ''关联的Offer ID'' AFTER `created_by`', 
    'SELECT "Column offer_id already exists"');
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
               AND constraint_name = 'short_links_ibfk_offer');

-- 如果外键不存在，则添加
SET @sqlstmt := IF(@exist = 0, 
    'ALTER TABLE `short_links` ADD CONSTRAINT `short_links_ibfk_offer` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT', 
    'SELECT "Foreign key short_links_ibfk_offer already exists"');
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
               AND index_name = 'idx_short_link_offer_id');

-- 如果索引不存在，则添加
SET @sqlstmt := IF(@exist = 0, 
    'ALTER TABLE `short_links` ADD INDEX `idx_short_link_offer_id`(`offer_id`)', 
    'SELECT "Index idx_short_link_offer_id already exists"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================
-- 迁移完成
-- ============================================
-- 说明：
-- 1. 添加了 offer_id 字段到 short_links 表
-- 2. 添加了外键约束，关联到 offers 表
-- 3. 添加了索引以提高查询性能
-- 4. 如果字段、外键或索引已存在，脚本会安全跳过，不会报错
-- ============================================

