USE `platform`;

-- 检查 clients 字段 notify_url 是否存在
SELECT 
    COUNT(*) INTO @cnt
FROM 
    information_schema.columns
WHERE 
    table_schema = DATABASE()
    AND table_name = 'clients'
    AND column_name = 'notify_url';

-- 如果不存在就添加
SET @sql = IF(
    @cnt = 0,
    'ALTER TABLE `clients` ADD COLUMN `notify_url` VARCHAR(200) NULL COMMENT ''客户广告数据通知地址'' AFTER `chat_id`;',
    'SELECT ''表`clients`字段`notify_url` 已经存在，无需添加'' as msg;'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- ===========================
-- 1. 检查 ad_data.country_code 字段，不存在则添加
-- ===========================
SET @sql := (
    SELECT IF(
        COUNT(*) = 0,
        'ALTER TABLE `ad_data` ADD COLUMN `country_code` VARCHAR(5) NULL DEFAULT ''ZZ'' COMMENT ''国家代码（ISO 3166-1 二字母代码）'' AFTER `date`;',
        'SELECT ''表ad_data的字段country_code已存在，不执行'';'
    )
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'platform'
      AND TABLE_NAME = 'ad_data'
      AND COLUMN_NAME = 'country_code'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ===========================
-- 2. 检查外键 fk_ad_data_country_code，不存在才创建
-- ===========================
SET @sql := (
    SELECT IF(
        COUNT(*) = 0,
        'ALTER TABLE `ad_data` ADD CONSTRAINT `fk_ad_data_country_code` FOREIGN KEY (`country_code`) REFERENCES `countries` (`alpha_2_code`) ON DELETE SET NULL ON UPDATE CASCADE;',
        'SELECT ''表ad_data的fk_ad_data_country_code 外键已存在，不执行'';'
    )
    FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = 'platform'
      AND CONSTRAINT_NAME = 'fk_ad_data_country_code'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ===========================
-- 3. 检查索引 idx_ad_data_country_code，不存在才添加
-- ===========================
SET @sql := (
    SELECT IF(
        COUNT(*) = 0,
        'ALTER TABLE `ad_data` ADD INDEX `idx_ad_data_country_code` (`country_code`);',
        'SELECT ''表ad_data的索引idx_ad_data_country_code已存在，不执行'';'
    )
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = 'platform'
      AND TABLE_NAME = 'ad_data'
      AND INDEX_NAME = 'idx_ad_data_country_code'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

UPDATE `ad_data` SET `country_code` = 'ZZ';
SELECT '表[ad_data]字段[country_code]已经全部替换[全部国家]' as msg;


SET FOREIGN_KEY_CHECKS = 0;
-- 1. 删除旧的唯一性约束
ALTER TABLE `ad_data` DROP INDEX `uq_ad_data_date_product`;

-- 2. 将现有的 NULL country_code 更新为 'ZZ'（全部国家）
-- 这样可以确保唯一性约束不会因为 NULL 值导致问题
UPDATE `ad_data` SET `country_code` = 'ZZ' WHERE `country_code` IS NULL;

-- 3. 添加新的唯一性约束（包含 country_code）
ALTER TABLE `ad_data` 
ADD CONSTRAINT `uq_ad_data_date_product_country` 
UNIQUE (`date`, `product_id`, `country_code`);
SET FOREIGN_KEY_CHECKS = 1;


INSERT INTO `scheduled_tasks` (`task_name`, `description`, `cron_expression`, `function_path`, `is_active`) VALUES 
('Skymobi API获取数据', '每隔30分钟执行一次，从Skymobi API获取广告数据并导入到数据库', '*/30 * * * *', 'app.scheduler_module.tasks.skymobi_task.skymobi_api_task', 0);










