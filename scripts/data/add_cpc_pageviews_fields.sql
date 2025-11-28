-- 添加 CPC 和 PageViews 字段到 ad_data 表
-- 执行日期: 2025-01-XX

-- 添加 CPC 字段（Float类型，默认值0.00）
ALTER TABLE `ad_data` 
ADD COLUMN `cpc` FLOAT DEFAULT 0.00 COMMENT 'CPC' AFTER `click_rate`;

-- 添加 PageViews 字段（Integer类型，默认值0）
ALTER TABLE `ad_data` 
ADD COLUMN `pageviews` INT DEFAULT 0 COMMENT 'PageViews' AFTER `cpc`;

-- 验证字段是否添加成功
-- SELECT COLUMN_NAME, DATA_TYPE, COLUMN_DEFAULT, COLUMN_COMMENT 
-- FROM INFORMATION_SCHEMA.COLUMNS 
-- WHERE TABLE_SCHEMA = DATABASE() 
--   AND TABLE_NAME = 'ad_data' 
--   AND COLUMN_NAME IN ('cpc', 'pageviews');

