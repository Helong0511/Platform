-- 检查 short_links 表是否存在
USE `platform`;

-- 检查表是否存在
SELECT 
    TABLE_NAME,
    TABLE_COMMENT
FROM 
    INFORMATION_SCHEMA.TABLES
WHERE 
    TABLE_SCHEMA = 'platform' 
    AND TABLE_NAME = 'short_links';

-- 如果表存在，显示表结构
SHOW CREATE TABLE short_links;

-- 如果表不存在，会显示空结果，需要执行创建表的SQL脚本

