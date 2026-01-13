-- ============================================
-- 全文索引性能优化迁移脚本
-- 创建时间: 2025-01-XX
-- 说明: 为搜索字段添加全文索引，提升搜索查询性能
-- ============================================

-- 注意：全文索引只支持 MyISAM 和 InnoDB 引擎（MySQL 5.6+）
-- 本脚本假设使用 InnoDB 引擎

-- ============================================
-- 1. 为Offer表添加全文索引
-- ============================================

-- 检查全文索引是否已存在
SET @index_exists = (
    SELECT COUNT(*) 
    FROM information_schema.statistics 
    WHERE table_schema = DATABASE() 
    AND table_name = 'offers' 
    AND index_name = 'ft_offer_name'
);

SET @sql = IF(@index_exists = 0,
    'ALTER TABLE `offers` ADD FULLTEXT INDEX `ft_offer_name` (`offer_name`)',
    'SELECT "全文索引 ft_offer_name 已存在，跳过创建" AS message'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================
-- 2. 为ShortLink表添加全文索引
-- ============================================

-- 为title添加全文索引
SET @index_exists = (
    SELECT COUNT(*) 
    FROM information_schema.statistics 
    WHERE table_schema = DATABASE() 
    AND table_name = 'short_links' 
    AND index_name = 'ft_title'
);

SET @sql = IF(@index_exists = 0,
    'ALTER TABLE `short_links` ADD FULLTEXT INDEX `ft_title` (`title`)',
    'SELECT "全文索引 ft_title 已存在，跳过创建" AS message'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 为description添加全文索引
SET @index_exists = (
    SELECT COUNT(*) 
    FROM information_schema.statistics 
    WHERE table_schema = DATABASE() 
    AND table_name = 'short_links' 
    AND index_name = 'ft_description'
);

SET @sql = IF(@index_exists = 0,
    'ALTER TABLE `short_links` ADD FULLTEXT INDEX `ft_description` (`description`)',
    'SELECT "全文索引 ft_description 已存在，跳过创建" AS message'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================
-- 3. 为Product表添加全文索引
-- ============================================

SET @index_exists = (
    SELECT COUNT(*) 
    FROM information_schema.statistics 
    WHERE table_schema = DATABASE() 
    AND table_name = 'products' 
    AND index_name = 'ft_name'
);

SET @sql = IF(@index_exists = 0,
    'ALTER TABLE `products` ADD FULLTEXT INDEX `ft_name` (`name`)',
    'SELECT "全文索引 ft_name 已存在，跳过创建" AS message'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================
-- 4. 验证全文索引是否创建成功
-- ============================================

SELECT 
    TABLE_NAME,
    INDEX_NAME,
    COLUMN_NAME,
    INDEX_TYPE,
    COMMENT
FROM 
    information_schema.statistics
WHERE 
    table_schema = DATABASE()
    AND INDEX_TYPE = 'FULLTEXT'
    AND TABLE_NAME IN ('offers', 'short_links', 'products')
ORDER BY 
    TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;

-- ============================================
-- 5. 显示所有表的全文索引（用于验证）
-- ============================================

SELECT 
    TABLE_NAME,
    INDEX_NAME,
    GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX SEPARATOR ', ') AS COLUMNS,
    INDEX_TYPE
FROM 
    information_schema.statistics
WHERE 
    table_schema = DATABASE()
    AND INDEX_TYPE = 'FULLTEXT'
GROUP BY 
    TABLE_NAME, INDEX_NAME, INDEX_TYPE
ORDER BY 
    TABLE_NAME, INDEX_NAME;

-- ============================================
-- 注意事项
-- ============================================
-- 1. 全文索引创建可能需要一些时间，取决于表的大小
-- 2. 全文索引只支持 CHAR、VARCHAR 和 TEXT 类型的列
-- 3. 全文索引的最小词长度由 ft_min_word_len 配置决定（默认4）
-- 4. 如果搜索词长度小于最小词长度，全文索引不会生效，会回退到LIKE查询
-- 5. 全文索引支持中文搜索，但需要确保数据库字符集为 utf8mb4
-- 6. 如果表中有大量数据，创建全文索引可能需要较长时间，建议在低峰期执行
