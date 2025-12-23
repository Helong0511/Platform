-- ============================================
-- 数据库迁移脚本：移除字符串ID字段（简化版）
-- 说明：将CPL系统中的字符串ID（advertiser_id, publisher_id）改为使用自增ID
-- 执行日期：2025-12-19
-- 
-- 注意：此版本适用于 MySQL 8.0+，如果使用旧版本请使用 remove_string_ids.sql
-- ============================================

-- ============================================
-- 1. 修改 advertisers 表
-- ============================================

-- 删除 advertiser_id 字段的唯一索引
DROP INDEX IF EXISTS `advertiser_id` ON `advertisers`;
DROP INDEX IF EXISTS `idx_advertiser_id` ON `advertisers`;

-- 删除 advertiser_id 字段
ALTER TABLE `advertisers` DROP COLUMN IF EXISTS `advertiser_id`;

-- ============================================
-- 2. 修改 publishers 表
-- ============================================

-- 删除 publisher_id 字段的唯一索引
DROP INDEX IF EXISTS `publisher_id` ON `publishers`;
DROP INDEX IF EXISTS `idx_publisher_id` ON `publishers`;

-- 删除 publisher_id 字段
ALTER TABLE `publishers` DROP COLUMN IF EXISTS `publisher_id`;

-- ============================================
-- 3. 修改 offers 表
-- ============================================

-- 删除 offer_id 字段的唯一索引
DROP INDEX IF EXISTS `offer_id` ON `offers`;
DROP INDEX IF EXISTS `idx_offer_id` ON `offers`;

-- 删除 offer_id 字段
ALTER TABLE `offers` DROP COLUMN IF EXISTS `offer_id`;

-- ============================================
-- 迁移完成
-- ============================================
-- 注意：
-- 1. 此脚本会删除 advertisers、publishers 和 offers 表中的字符串ID字段
-- 2. 系统现在使用自增的 id 字段作为主键和唯一标识
-- 3. 所有外键关系保持不变（其他表中的 advertiser_id、publisher_id 和 offer_id 字段是外键，应保留）
-- ============================================

