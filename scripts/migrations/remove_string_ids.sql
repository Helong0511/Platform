-- ============================================
-- 数据库迁移脚本：移除字符串ID字段
-- 说明：将CPL系统中的字符串ID（advertiser_id, publisher_id）改为使用自增ID
-- 执行日期：2025-12-19
-- 
-- 执行前请确保：
-- 1. 已备份数据库
-- 2. 已停止应用服务
-- 3. 已更新代码到最新版本
-- ============================================

-- ============================================
-- 1. 修改 advertisers 表
-- ============================================

-- 删除 advertiser_id 字段的唯一索引（如果存在）
-- 注意：MySQL 5.7+ 支持 IF EXISTS，旧版本可能需要手动检查
SET @exist := (SELECT COUNT(*) FROM information_schema.statistics 
               WHERE table_schema = DATABASE() 
               AND table_name = 'advertisers' 
               AND index_name = 'advertiser_id');
SET @sqlstmt := IF(@exist > 0, 'DROP INDEX `advertiser_id` ON `advertisers`', 'SELECT "Index advertiser_id does not exist"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @exist := (SELECT COUNT(*) FROM information_schema.statistics 
               WHERE table_schema = DATABASE() 
               AND table_name = 'advertisers' 
               AND index_name = 'idx_advertiser_id');
SET @sqlstmt := IF(@exist > 0, 'DROP INDEX `idx_advertiser_id` ON `advertisers`', 'SELECT "Index idx_advertiser_id does not exist"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 删除 advertiser_id 字段（如果存在）
SET @exist := (SELECT COUNT(*) FROM information_schema.columns 
               WHERE table_schema = DATABASE() 
               AND table_name = 'advertisers' 
               AND column_name = 'advertiser_id');
SET @sqlstmt := IF(@exist > 0, 'ALTER TABLE `advertisers` DROP COLUMN `advertiser_id`', 'SELECT "Column advertiser_id does not exist"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================
-- 2. 修改 publishers 表
-- ============================================

-- 删除 publisher_id 字段的唯一索引（如果存在）
SET @exist := (SELECT COUNT(*) FROM information_schema.statistics 
               WHERE table_schema = DATABASE() 
               AND table_name = 'publishers' 
               AND index_name = 'publisher_id');
SET @sqlstmt := IF(@exist > 0, 'DROP INDEX `publisher_id` ON `publishers`', 'SELECT "Index publisher_id does not exist"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @exist := (SELECT COUNT(*) FROM information_schema.statistics 
               WHERE table_schema = DATABASE() 
               AND table_name = 'publishers' 
               AND index_name = 'idx_publisher_id');
SET @sqlstmt := IF(@exist > 0, 'DROP INDEX `idx_publisher_id` ON `publishers`', 'SELECT "Index idx_publisher_id does not exist"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 删除 publisher_id 字段（如果存在）
SET @exist := (SELECT COUNT(*) FROM information_schema.columns 
               WHERE table_schema = DATABASE() 
               AND table_name = 'publishers' 
               AND column_name = 'publisher_id');
SET @sqlstmt := IF(@exist > 0, 'ALTER TABLE `publishers` DROP COLUMN `publisher_id`', 'SELECT "Column publisher_id does not exist"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================
-- 3. 修改 offers 表
-- ============================================

-- 删除 offer_id 字段的唯一索引（如果存在）
SET @exist := (SELECT COUNT(*) FROM information_schema.statistics 
               WHERE table_schema = DATABASE() 
               AND table_name = 'offers' 
               AND index_name = 'offer_id');
SET @sqlstmt := IF(@exist > 0, 'DROP INDEX `offer_id` ON `offers`', 'SELECT "Index offer_id does not exist"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @exist := (SELECT COUNT(*) FROM information_schema.statistics 
               WHERE table_schema = DATABASE() 
               AND table_name = 'offers' 
               AND index_name = 'idx_offer_id');
SET @sqlstmt := IF(@exist > 0, 'DROP INDEX `idx_offer_id` ON `offers`', 'SELECT "Index idx_offer_id does not exist"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 删除 offer_id 字段（如果存在）
SET @exist := (SELECT COUNT(*) FROM information_schema.columns 
               WHERE table_schema = DATABASE() 
               AND table_name = 'offers' 
               AND column_name = 'offer_id');
SET @sqlstmt := IF(@exist > 0, 'ALTER TABLE `offers` DROP COLUMN `offer_id`', 'SELECT "Column offer_id does not exist"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================
-- 迁移完成
-- ============================================
-- 注意：
-- 1. 此脚本会删除 advertisers、publishers 和 offers 表中的字符串ID字段
-- 2. 系统现在使用自增的 id 字段作为主键和唯一标识
-- 3. 所有外键关系保持不变（其他表中的 advertiser_id、publisher_id 和 offer_id 字段是外键，应保留）
-- 4. 如果字段或索引不存在，脚本会安全跳过，不会报错
-- ============================================

