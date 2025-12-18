-- 修改 postback_conversions 表，添加 CPL 系统所需字段
-- 注意：执行前请备份数据库

USE `platform`;

-- 检查字段是否已存在，如果不存在则添加
-- 添加 click_id 字段
SET @exist := (SELECT COUNT(*) FROM information_schema.COLUMNS 
               WHERE TABLE_SCHEMA = 'platform' 
               AND TABLE_NAME = 'postback_conversions' 
               AND COLUMN_NAME = 'click_id');
SET @sqlstmt := IF(@exist = 0, 
    'ALTER TABLE postback_conversions ADD COLUMN click_id VARCHAR(255) COMMENT ''关联的Click ID'' AFTER conversion_id',
    'SELECT ''Column click_id already exists'' AS message');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 添加 click_time 字段
SET @exist := (SELECT COUNT(*) FROM information_schema.COLUMNS 
               WHERE TABLE_SCHEMA = 'platform' 
               AND TABLE_NAME = 'postback_conversions' 
               AND COLUMN_NAME = 'click_time');
SET @sqlstmt := IF(@exist = 0, 
    'ALTER TABLE postback_conversions ADD COLUMN click_time DATETIME COMMENT ''点击时间'' AFTER click_id',
    'SELECT ''Column click_time already exists'' AS message');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 添加 conversion_status 字段
SET @exist := (SELECT COUNT(*) FROM information_schema.COLUMNS 
               WHERE TABLE_SCHEMA = 'platform' 
               AND TABLE_NAME = 'postback_conversions' 
               AND COLUMN_NAME = 'conversion_status');
SET @sqlstmt := IF(@exist = 0, 
    'ALTER TABLE postback_conversions ADD COLUMN conversion_status VARCHAR(20) DEFAULT ''Pending'' COMMENT ''转化状态：Approved/Pending'' AFTER click_time',
    'SELECT ''Column conversion_status already exists'' AS message');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 添加索引
SET @exist := (SELECT COUNT(*) FROM information_schema.STATISTICS 
               WHERE TABLE_SCHEMA = 'platform' 
               AND TABLE_NAME = 'postback_conversions' 
               AND INDEX_NAME = 'idx_postback_click_id');
SET @sqlstmt := IF(@exist = 0, 
    'ALTER TABLE postback_conversions ADD INDEX idx_postback_click_id (click_id)',
    'SELECT ''Index idx_postback_click_id already exists'' AS message');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @exist := (SELECT COUNT(*) FROM information_schema.STATISTICS 
               WHERE TABLE_SCHEMA = 'platform' 
               AND TABLE_NAME = 'postback_conversions' 
               AND INDEX_NAME = 'idx_postback_conversion_status');
SET @sqlstmt := IF(@exist = 0, 
    'ALTER TABLE postback_conversions ADD INDEX idx_postback_conversion_status (conversion_status)',
    'SELECT ''Index idx_postback_conversion_status already exists'' AS message');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

