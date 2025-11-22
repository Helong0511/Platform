USE `platform`;

-- ===========================
-- 1. 检查 ad_data.country_code 字段，不存在则添加
-- ===========================
SET @sql := (
    SELECT IF(
        COUNT(*) = 0,
        'ALTER TABLE `ad_data` ADD COLUMN `country_code` VARCHAR(5) NULL DEFAULT ''ZZ'' COMMENT ''国家代码（ISO 3166-1 二字母代码）'' AFTER `date`;',
        'SELECT ''字段已存在，不执行'';'
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
        'SELECT ''外键已存在，不执行'';'
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
        'SELECT ''索引已存在，不执行'';'
    )
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = 'platform'
      AND TABLE_NAME = 'ad_data'
      AND INDEX_NAME = 'idx_ad_data_country_code'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

