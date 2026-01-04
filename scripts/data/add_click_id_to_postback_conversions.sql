-- 为 postback_conversions 表添加 click_id 字段
-- 用于关联 Click 记录，支持 CPL 系统

-- 检查字段是否已存在，如果不存在则添加
SET @db_name = DATABASE();
SET @table_name = 'postback_conversions';
SET @column_name = 'click_id';

-- 检查字段是否存在
SELECT COUNT(*) INTO @column_exists
FROM information_schema.columns
WHERE table_schema = @db_name
  AND table_name = @table_name
  AND column_name = @column_name;

-- 如果字段不存在，则添加
SET @sql = IF(@column_exists = 0,
    CONCAT('ALTER TABLE `', @table_name, '` ',
           'ADD COLUMN `click_id` VARCHAR(255) NULL COMMENT ''关联的Click ID'' AFTER `client_id`, ',
           'ADD INDEX `idx_postback_click_id` (`click_id`)'),
    'SELECT ''字段 click_id 已存在，无需添加'' AS message');

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 显示结果
SELECT IF(@column_exists = 0, '字段 click_id 已成功添加', '字段 click_id 已存在') AS result;

