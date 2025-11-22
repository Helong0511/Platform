USE `platform`;

-- ===========================
-- 更新 ad_data 表的唯一性约束，添加 country_code 字段
-- ===========================

-- 1. 删除旧的唯一性约束
ALTER TABLE `ad_data` DROP INDEX `uq_ad_data_date_product`;

-- 2. 将现有的 NULL country_code 更新为 'ZZ'（全部国家）
-- 这样可以确保唯一性约束不会因为 NULL 值导致问题
UPDATE `ad_data` SET `country_code` = 'ZZ' WHERE `country_code` IS NULL;

-- 3. 添加新的唯一性约束（包含 country_code）
ALTER TABLE `ad_data` 
ADD CONSTRAINT `uq_ad_data_date_product_country` 
UNIQUE (`date`, `product_id`, `country_code`);

