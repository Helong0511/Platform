-- =====================================================
-- 修复字符集排序规则冲突问题
-- 问题：ad_data.country_code 使用 utf8mb4_unicode_ci
--      countries.alpha_2_code 使用 utf8mb4_0900_ai_ci
-- 解决方案：统一使用 utf8mb4_unicode_ci
-- =====================================================

USE platform;

SET FOREIGN_KEY_CHECKS = 0;

-- 方案1：修改 countries 表的 alpha_2_code 字段排序规则（推荐）
-- 这样可以保持与 ad_data 表的一致性
ALTER TABLE `countries` 
MODIFY COLUMN `alpha_2_code` char(2) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '国家二字代码';

-- 如果还有其他相关字段需要统一，可以一并修改
ALTER TABLE `countries` 
MODIFY COLUMN `alpha_3_code` char(3) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '国家三字代码';

ALTER TABLE `countries` 
MODIFY COLUMN `numeric_code` char(3) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '国家数字代码';

ALTER TABLE `countries` 
MODIFY COLUMN `country_name_zh` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '国家中文名称';

ALTER TABLE `countries` 
MODIFY COLUMN `country_name_en` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '国家英文名称';

-- 可选：如果 official_name_zh 和 official_name_en 也需要统一
ALTER TABLE `countries` 
MODIFY COLUMN `official_name_zh` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '官方中文名称';

ALTER TABLE `countries` 
MODIFY COLUMN `official_name_en` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '官方英文名称';

ALTER TABLE `countries` 
MODIFY COLUMN `continent` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '所属大洲';

ALTER TABLE `countries` 
MODIFY COLUMN `subregion` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '所属地区';

SET FOREIGN_KEY_CHECKS = 1;

-- 验证修改结果
SELECT 
    TABLE_NAME,
    COLUMN_NAME,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM 
    INFORMATION_SCHEMA.COLUMNS
WHERE 
    TABLE_SCHEMA = 'platform'
    AND TABLE_NAME IN ('ad_data', 'countries')
    AND COLUMN_NAME IN ('country_code', 'alpha_2_code')
ORDER BY 
    TABLE_NAME, COLUMN_NAME;

