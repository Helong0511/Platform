/*
平台SQL优化文件
生成时间: 2026-02-04

本文件包含生产环境的优化SQL语句。
所有操作使用INPLACE算法以避免表锁定。

优化类别:
1. 索引优化
2. 查询优化
3. 表结构优化
4. 维护操作
*/
-- DROP DATABASE IF EXISTS `platform`;
CREATE DATABASE IF NOT EXISTS `platform` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `platform`;

-- =============================================
-- 1. 索引优化
-- =============================================

-- 创建存储过程来安全创建索引（兼容旧版本MySQL）
DELIMITER $$
CREATE PROCEDURE `create_index_if_not_exists`(IN `p_table` VARCHAR(64), IN `p_index` VARCHAR(64), IN `p_columns` VARCHAR(255))
BEGIN
    DECLARE index_exists INT;
    
    -- 检查索引是否存在
    SELECT COUNT(*) INTO index_exists
    FROM information_schema.statistics 
    WHERE table_schema = DATABASE() 
    AND table_name = p_table 
    AND index_name = p_index;
    
    -- 如果索引不存在，则创建
    IF index_exists = 0 THEN
        SET @sql = CONCAT('CREATE INDEX `', p_index, '` ON `', p_table, '`(', p_columns, ') USING BTREE');
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END$$
DELIMITER ;

-- 优化clicks表索引
CALL `create_index_if_not_exists`('clicks', 'idx_clicks_country_offer', '`country` ASC, `offer_id` ASC');
CALL `create_index_if_not_exists`('clicks', 'idx_clicks_device_offer', '`device_type` ASC, `offer_id` ASC');

-- 优化ad_data表索引
CALL `create_index_if_not_exists`('ad_data', 'idx_ad_data_date_country', '`date` ASC, `country_code` ASC');
CALL `create_index_if_not_exists`('ad_data', 'idx_ad_data_revenue', '`revenue_after_deduct` DESC');

-- 优化offers表索引（不包含新增字段的索引）
CALL `create_index_if_not_exists`('offers', 'idx_offer_status_country', '`status` ASC, `country` ASC');
CALL `create_index_if_not_exists`('offers', 'idx_offer_advertiser_status', '`advertiser_id` ASC, `status` ASC');

-- 优化click_stats表索引
CALL `create_index_if_not_exists`('click_stats', 'idx_stats_time_offer_publisher', '`click_time` ASC, `offer_id` ASC, `publisher_id` ASC');

-- 删除存储过程
DROP PROCEDURE IF EXISTS `create_index_if_not_exists`;

-- 优化postback_conversions表索引
-- 注意：需要先添加缺失的字段，然后再创建索引
-- 这些索引创建语句将在表结构优化后执行

-- =============================================
-- 2. 表结构优化
-- =============================================

-- 创建存储过程来安全添加字段（兼容旧版本MySQL）
DELIMITER $$
CREATE PROCEDURE `add_column_if_not_exists`(IN `p_table` VARCHAR(64), IN `p_column` VARCHAR(64), IN `p_definition` VARCHAR(255))
BEGIN
    DECLARE column_exists INT;
    
    -- 检查字段是否存在
    SELECT COUNT(*) INTO column_exists
    FROM information_schema.columns 
    WHERE table_schema = DATABASE() 
    AND table_name = p_table 
    AND column_name = p_column;
    
    -- 如果字段不存在，则添加
    IF column_exists = 0 THEN
        SET @sql = CONCAT('ALTER TABLE `', p_table, '` ADD COLUMN ', p_definition);
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END$$
DELIMITER ;

-- 为offers表添加缺失的列
CALL `add_column_if_not_exists`('offers', 'app_id', '`app_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT \'\' COMMENT \'应用ID\' AFTER `offer_name`');
CALL `add_column_if_not_exists`('offers', 'create_date', '`create_date` date NULL DEFAULT NULL COMMENT \'创建日期\' AFTER `app_id`');
CALL `add_column_if_not_exists`('offers', 'expire_date', '`expire_date` date NULL DEFAULT NULL COMMENT \'过期日期\' AFTER `create_date`');
CALL `add_column_if_not_exists`('offers', 'currency', '`currency` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT \'货币\' AFTER `affiliate_payout`');
CALL `add_column_if_not_exists`('offers', 'payout_type', '`payout_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT \'支付类型\' AFTER `currency`');
CALL `add_column_if_not_exists`('offers', 'session_lifespan', '`session_lifespan` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT \'会话生命周期\' AFTER `click_validity_hours`');
CALL `add_column_if_not_exists`('offers', 'offerTimezone', '`offerTimezone` int NULL DEFAULT 8 COMMENT \'Offer时区\' AFTER `session_lifespan`');

-- 删除存储过程
DROP PROCEDURE IF EXISTS `add_column_if_not_exists`;

-- 优化数据类型以提高精度
ALTER TABLE `offers` 
MODIFY COLUMN `payout` decimal(10,4) NULL DEFAULT NULL COMMENT '上游支付金额（PO）',
MODIFY COLUMN `affiliate_payout` decimal(10,4) NULL DEFAULT NULL COMMENT '扣价后给渠道的金额（PO扣价后）';

ALTER TABLE `ad_data` 
MODIFY COLUMN `coverage_rate` decimal(5,2) NULL DEFAULT 0 COMMENT '覆盖率',
MODIFY COLUMN `display_rate` decimal(5,2) NULL DEFAULT 0 COMMENT '展示率',
MODIFY COLUMN `click_rate` decimal(5,2) NULL DEFAULT 0 COMMENT '点击率',
MODIFY COLUMN `viewability_rate` decimal(5,2) NULL DEFAULT 0 COMMENT '可见率',
MODIFY COLUMN `cpc` decimal(10,4) NULL DEFAULT 0 COMMENT 'CPC',
MODIFY COLUMN `ecpm_before_deduct` decimal(10,4) NOT NULL DEFAULT 0 COMMENT 'eCPM未减扣',
MODIFY COLUMN `ecpm_after_deduct` decimal(10,4) NOT NULL DEFAULT 0 COMMENT 'eCPM已减扣',
MODIFY COLUMN `revenue_before_deduct` decimal(10,4) NOT NULL DEFAULT 0 COMMENT '收益未减扣',
MODIFY COLUMN `revenue_after_deduct` decimal(10,4) NOT NULL DEFAULT 0 COMMENT '收益已减扣';

-- 为postback_conversions表添加缺失字段
DELIMITER $$
CREATE PROCEDURE `add_column_if_not_exists`(IN `p_table` VARCHAR(64), IN `p_column` VARCHAR(64), IN `p_definition` VARCHAR(255))
BEGIN
    DECLARE column_exists INT;
    
    -- 检查字段是否存在
    SELECT COUNT(*) INTO column_exists
    FROM information_schema.columns 
    WHERE table_schema = DATABASE() 
    AND table_name = p_table 
    AND column_name = p_column;
    
    -- 如果字段不存在，则添加
    IF column_exists = 0 THEN
        SET @sql = CONCAT('ALTER TABLE `', p_table, '` ADD COLUMN ', p_definition);
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END$$
DELIMITER ;

-- 为postback_conversions表添加缺失字段
CALL `add_column_if_not_exists`('postback_conversions', 'publisher_id', '`publisher_id` int NULL DEFAULT NULL COMMENT \'渠道ID\' AFTER `client_id`');
CALL `add_column_if_not_exists`('postback_conversions', 'offer_id', '`offer_id` int NULL DEFAULT NULL COMMENT \'Offer ID\' AFTER `publisher_id`');

-- 删除存储过程
DROP PROCEDURE IF EXISTS `add_column_if_not_exists`;

-- 为postback_conversions表创建索引
DELIMITER $$
CREATE PROCEDURE `create_index_if_not_exists`(IN `p_table` VARCHAR(64), IN `p_index` VARCHAR(64), IN `p_columns` VARCHAR(255))
BEGIN
    DECLARE index_exists INT;
    
    -- 检查索引是否存在
    SELECT COUNT(*) INTO index_exists
    FROM information_schema.statistics 
    WHERE table_schema = DATABASE() 
    AND table_name = p_table 
    AND index_name = p_index;
    
    -- 如果索引不存在，则创建
    IF index_exists = 0 THEN
        SET @sql = CONCAT('CREATE INDEX `', p_index, '` ON `', p_table, '`(', p_columns, ') USING BTREE');
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END$$
DELIMITER ;

-- 创建postback_conversions表索引
CALL `create_index_if_not_exists`('postback_conversions', 'idx_conversion_publisher_time', '`publisher_id` ASC, `click_time` ASC');
CALL `create_index_if_not_exists`('postback_conversions', 'idx_conversion_offer_time', '`offer_id` ASC, `click_time` ASC');

-- 为新增字段创建索引
CALL `create_index_if_not_exists`('offers', 'idx_offer_create_date', '`create_date` ASC');
CALL `create_index_if_not_exists`('offers', 'idx_offer_expire_date', '`expire_date` ASC');

-- 删除存储过程
DROP PROCEDURE IF EXISTS `create_index_if_not_exists`;

-- =============================================
-- 3. 优化用新表
-- =============================================

-- 创建offer缓存表，用于频繁访问的数据
CREATE TABLE IF NOT EXISTS `offer_cache` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '缓存ID',
  `offer_id` int NOT NULL COMMENT 'Offer ID',
  `cache_data` json NOT NULL COMMENT '缓存数据',
  `last_updated` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
  `is_valid` tinyint(1) NOT NULL DEFAULT 1 COMMENT '是否有效',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_last_updated`(`last_updated` ASC) USING BTREE,
  INDEX `idx_is_valid`(`is_valid` ASC) USING BTREE,
  CONSTRAINT `fk_offer_cache_offer` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'Offer缓存表' ROW_FORMAT = DYNAMIC;

-- 创建数据同步日志表，用于监控
CREATE TABLE IF NOT EXISTS `data_sync_logs` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '日志ID',
  `sync_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '同步类型',
  `sync_status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '同步状态',
  `start_time` datetime NOT NULL COMMENT '开始时间',
  `end_time` datetime NULL DEFAULT NULL COMMENT '结束时间',
  `sync_count` int NOT NULL DEFAULT 0 COMMENT '同步数量',
  `error_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '错误信息',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_sync_type`(`sync_type` ASC) USING BTREE,
  INDEX `idx_sync_status`(`sync_status` ASC) USING BTREE,
  INDEX `idx_start_time`(`start_time` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '数据同步日志表' ROW_FORMAT = DYNAMIC;

-- 创建offer流量类型关联表
CREATE TABLE IF NOT EXISTS `offer_traffic_types` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `offer_id` int NOT NULL COMMENT 'Offer ID',
  `traffic_id` int NOT NULL COMMENT '流量类型ID',
  `traffic_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '流量类型名称',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_offer_traffic`(`offer_id` ASC, `traffic_id` ASC) USING BTREE,
  INDEX `idx_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_traffic_id`(`traffic_id` ASC) USING BTREE,
  CONSTRAINT `fk_offer_traffic_offer` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'Offer流量类型关联表' ROW_FORMAT = DYNAMIC;

-- 创建点击统计聚合表（按天）
CREATE TABLE IF NOT EXISTS `click_stats_aggregated` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '汇总ID',
  `stat_date` date NOT NULL COMMENT '统计日期',
  `offer_id` int NOT NULL COMMENT 'Offer ID',
  `publisher_id` int NOT NULL COMMENT '渠道ID',
  `click_count` int NOT NULL DEFAULT 0 COMMENT '点击数',
  `unique_ip_count` int NOT NULL DEFAULT 0 COMMENT '唯一IP数',
  `avg_click_time` time NULL DEFAULT NULL COMMENT '平均点击时间',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_stat_offer_publisher`(`stat_date` ASC, `offer_id` ASC, `publisher_id` ASC) USING BTREE,
  INDEX `idx_stat_date`(`stat_date` ASC) USING BTREE,
  INDEX `idx_stat_offer`(`offer_id` ASC) USING BTREE,
  INDEX `idx_stat_publisher`(`publisher_id` ASC) USING BTREE,
  CONSTRAINT `fk_stats_aggregated_offer` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `fk_stats_aggregated_publisher` FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '点击统计汇总表' ROW_FORMAT = DYNAMIC;

-- 创建按小时聚合的表
CREATE TABLE IF NOT EXISTS `click_hourly_aggregates` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '聚合ID',
  `agg_hour` datetime NOT NULL COMMENT '聚合小时',
  `offer_id` int NOT NULL COMMENT 'Offer ID',
  `publisher_id` int NOT NULL COMMENT '渠道ID',
  `click_count` int NOT NULL DEFAULT 0 COMMENT '点击数',
  `unique_ip_count` int NOT NULL DEFAULT 0 COMMENT '唯一IP数',
  `country_distribution` json NULL COMMENT '国家分布',
  `device_distribution` json NULL COMMENT '设备分布',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_hour_offer_publisher`(`agg_hour` ASC, `offer_id` ASC, `publisher_id` ASC) USING BTREE,
  INDEX `idx_agg_hour`(`agg_hour` ASC) USING BTREE,
  INDEX `idx_agg_offer`(`offer_id` ASC) USING BTREE,
  INDEX `idx_agg_publisher`(`publisher_id` ASC) USING BTREE,
  CONSTRAINT `fk_hourly_aggregate_offer` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `fk_hourly_aggregate_publisher` FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '点击小时聚合表' ROW_FORMAT = DYNAMIC;

-- =============================================
-- 4. 查询优化示例
-- =============================================

/*
-- 优化的Offer列表查询
SELECT o.id, o.offer_name, o.status, o.country, o.payout, o.affiliate_payout, 
       a.advertiser_name, o.create_date, o.expire_date
FROM offers o
JOIN advertisers a ON o.advertiser_id = a.id
WHERE o.status = 'Active'
  AND (o.expire_date IS NULL OR o.expire_date >= CURDATE())
ORDER BY o.id DESC
LIMIT 20;

-- 优化的点击统计查询（使用聚合表）
SELECT o.offer_name, 
       sa.click_count,
       sa.unique_ip_count
FROM click_stats_aggregated sa
JOIN offers o ON sa.offer_id = o.id
WHERE sa.stat_date BETWEEN '2026-01-01' AND '2026-01-31'
ORDER BY sa.click_count DESC
LIMIT 10;

-- 优化的小时级点击趋势查询（使用小时聚合表）
SELECT 
    ha.agg_hour,
    o.offer_name,
    ha.click_count
FROM click_hourly_aggregates ha
JOIN offers o ON ha.offer_id = o.id
WHERE ha.agg_hour BETWEEN '2026-01-31 00:00:00' AND '2026-01-31 23:59:59'
ORDER BY ha.agg_hour ASC;

-- 优化的实时点击查询（使用索引）
SELECT 
    c.id, c.click_id, c.offer_id, c.publisher_id, c.click_time,
    c.ip, c.device_type, c.country, o.offer_name
FROM clicks c
JOIN offers o ON c.offer_id = o.id
WHERE c.click_time >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
ORDER BY c.click_time DESC
LIMIT 0, 100; -- 分页查询

-- 优化的转化统计查询
SELECT o.offer_name, 
       COUNT(pc.id) as conversion_count,
       SUM(pc.payout) as total_payout,
       ROUND(COUNT(pc.id) / COUNT(c.id) * 100, 2) as conversion_rate
FROM clicks c
LEFT JOIN postback_conversions pc ON c.click_id = pc.click_id
JOIN offers o ON c.offer_id = o.id
WHERE c.click_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY o.offer_name
HAVING conversion_count > 0
ORDER BY conversion_rate DESC
LIMIT 10;
*/

-- =============================================
-- 5. 维护操作
-- =============================================

-- 创建旧数据归档存储过程
DROP PROCEDURE IF EXISTS `archive_old_data`;
DELIMITER $$
CREATE PROCEDURE `archive_old_data`(IN `days_old` INT)
BEGIN
    -- 归档点击数据
    INSERT INTO clicks_archive
    SELECT * FROM clicks
    WHERE click_time < DATE_SUB(NOW(), INTERVAL days_old DAY)
    LIMIT 10000;
    
    -- 删除已归档的点击数据
    WHILE (SELECT COUNT(*) FROM clicks WHERE click_time < DATE_SUB(NOW(), INTERVAL days_old DAY)) > 0 DO
        DELETE FROM clicks
        WHERE click_time < DATE_SUB(NOW(), INTERVAL days_old DAY)
        LIMIT 10000;
        DO SLEEP(0.5);
    END WHILE;
    
    -- 归档广告数据
    INSERT INTO ad_data_archive
    SELECT * FROM ad_data
    WHERE date < DATE_SUB(NOW(), INTERVAL days_old DAY)
    LIMIT 10000;
    
    -- 删除已归档的广告数据
    WHILE (SELECT COUNT(*) FROM ad_data WHERE date < DATE_SUB(NOW(), INTERVAL days_old DAY)) > 0 DO
        DELETE FROM ad_data
        WHERE date < DATE_SUB(NOW(), INTERVAL days_old DAY)
        LIMIT 10000;
        DO SLEEP(0.5);
    END WHILE;
END$$
DELIMITER ;

-- 创建更新offer缓存的存储过程
DROP PROCEDURE IF EXISTS `update_offer_cache`;
DELIMITER $$
CREATE PROCEDURE `update_offer_cache`(IN `p_offer_id` INT)
BEGIN
    DECLARE offer_data JSON;
    
    -- 获取offer数据及相关信息
    SELECT JSON_OBJECT(
        'id', o.id,
        'offer_name', o.offer_name,
        'status', o.status,
        'country', o.country,
        'payout', o.payout,
        'affiliate_payout', o.affiliate_payout,
        'advertiser_name', a.advertiser_name,
        'create_date', o.create_date,
        'expire_date', o.expire_date,
        'preview_link', o.preview_link
    ) INTO offer_data
    FROM offers o
    JOIN advertisers a ON o.advertiser_id = a.id
    WHERE o.id = p_offer_id;
    
    -- 更新或插入缓存
    INSERT INTO offer_cache (offer_id, cache_data, is_valid)
    VALUES (p_offer_id, offer_data, 1)
    ON DUPLICATE KEY UPDATE
        cache_data = offer_data,
        is_valid = 1,
        last_updated = CURRENT_TIMESTAMP;
END$$
DELIMITER ;

-- 创建按月归档clicks数据的存储过程
DROP PROCEDURE IF EXISTS `archive_clicks_by_month`;
DELIMITER $$
CREATE PROCEDURE `archive_clicks_by_month`(IN `months_to_keep` INT)
BEGIN
    DECLARE cut_off_date DATE;
    DECLARE table_name VARCHAR(64);
    DECLARE archive_table VARCHAR(64);
    DECLARE start_date DATE;
    DECLARE end_date DATE;
    
    -- 计算 cutoff 日期
    SET cut_off_date = DATE_SUB(CURDATE(), INTERVAL months_to_keep MONTH);
    
    -- 循环处理每个月的数据
    SET start_date = DATE_FORMAT(cut_off_date, '%Y-%m-01');
    WHILE start_date < DATE_SUB(CURDATE(), INTERVAL 1 MONTH) DO
        SET end_date = DATE_ADD(start_date, INTERVAL 1 MONTH);
        SET table_name = CONCAT('clicks_', DATE_FORMAT(start_date, '%Y%m'));
        SET archive_table = CONCAT('clicks_archive_', DATE_FORMAT(start_date, '%Y%m'));
        
        -- 创建归档表
        SET @create_sql = CONCAT('CREATE TABLE IF NOT EXISTS `', archive_table, '` LIKE `clicks`;');
        PREPARE stmt FROM @create_sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
        
        -- 移动数据到归档表
        SET @insert_sql = CONCAT('INSERT INTO `', archive_table, '` SELECT * FROM clicks WHERE click_time >= ''', start_date, ''' AND click_time < ''', end_date, ''';');
        PREPARE stmt FROM @insert_sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
        
        -- 删除原表数据
        SET @delete_sql = CONCAT('DELETE FROM clicks WHERE click_time >= ''', start_date, ''' AND click_time < ''', end_date, ''';');
        PREPARE stmt FROM @delete_sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
        
        -- 优化归档表
        SET @optimize_sql = CONCAT('OPTIMIZE TABLE `', archive_table, '`;');
        PREPARE stmt FROM @optimize_sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
        
        SET start_date = end_date;
    END WHILE;
    
    -- 优化主表
    OPTIMIZE TABLE clicks;
END$$
DELIMITER ;

-- 创建更新点击统计聚合表的存储过程
DROP PROCEDURE IF EXISTS `update_click_aggregates`;
DELIMITER $$
CREATE PROCEDURE `update_click_aggregates`(IN `p_date` DATE)
BEGIN
    DECLARE start_datetime DATETIME;
    DECLARE end_datetime DATETIME;
    
    SET start_datetime = CONCAT(p_date, ' 00:00:00');
    SET end_datetime = CONCAT(DATE_ADD(p_date, INTERVAL 1 DAY), ' 00:00:00');
    
    -- 更新按天聚合表
    INSERT INTO click_stats_aggregated (stat_date, offer_id, publisher_id, click_count, unique_ip_count)
    SELECT 
        p_date,
        offer_id,
        publisher_id,
        COUNT(*) as click_count,
        COUNT(DISTINCT ip) as unique_ip_count
    FROM clicks
    WHERE click_time >= start_datetime AND click_time < end_datetime
    GROUP BY offer_id, publisher_id
    ON DUPLICATE KEY UPDATE
        click_count = VALUES(click_count),
        unique_ip_count = VALUES(unique_ip_count),
        updated_at = CURRENT_TIMESTAMP;
    
    -- 更新按小时聚合表
    INSERT INTO click_hourly_aggregates (agg_hour, offer_id, publisher_id, click_count, unique_ip_count)
    SELECT 
        DATE_FORMAT(click_time, '%Y-%m-%d %H:00:00'),
        offer_id,
        publisher_id,
        COUNT(*) as click_count,
        COUNT(DISTINCT ip) as unique_ip_count
    FROM clicks
    WHERE click_time >= start_datetime AND click_time < end_datetime
    GROUP BY DATE_FORMAT(click_time, '%Y-%m-%d %H:00:00'), offer_id, publisher_id
    ON DUPLICATE KEY UPDATE
        click_count = VALUES(click_count),
        unique_ip_count = VALUES(unique_ip_count),
        updated_at = CURRENT_TIMESTAMP;
END$$
DELIMITER ;

-- 创建清理旧click_stats数据的存储过程
DROP PROCEDURE IF EXISTS `cleanup_old_click_stats`;
DELIMITER $$
CREATE PROCEDURE `cleanup_old_click_stats`(IN `months_to_keep` INT)
BEGIN
    DECLARE cut_off_date DATETIME;
    
    -- 计算 cutoff 日期
    SET cut_off_date = DATE_SUB(NOW(), INTERVAL months_to_keep MONTH);
    
    -- 删除旧数据（分批处理）
    WHILE (SELECT COUNT(*) FROM click_stats WHERE click_time < cut_off_date) > 0 DO
        DELETE FROM click_stats
        WHERE click_time < cut_off_date
        LIMIT 10000;
        DO SLEEP(0.5);
    END WHILE;
    
    -- 优化表
    OPTIMIZE TABLE click_stats;
END$$
DELIMITER ;

-- =============================================
-- 6. MySQL配置建议
-- =============================================

/*
生产环境推荐的my.cnf/my.ini设置：

[mysqld]
# 缓冲池设置
innodb_buffer_pool_size = 8G
innodb_buffer_pool_instances = 8

# 日志设置
innodb_log_file_size = 1G
innodb_log_buffer_size = 32M

# 刷新设置
innodb_flush_method = O_DIRECT
innodb_flush_log_at_trx_commit = 2

# 连接设置
max_connections = 1000

# 缓冲区设置
sort_buffer_size = 2M
read_buffer_size = 1M
read_rnd_buffer_size = 4M

# 临时表设置
tmp_table_size = 64M
max_heap_table_size = 64M

# 线程设置
thread_cache_size = 100

# 慢查询日志
slow_query_log = 1
slow_query_log_file = /var/log/mysql/slow-query.log
long_query_time = 1

# 查询缓存（现代MySQL建议禁用）
query_cache_size = 0
query_cache_type = 0

# 字符集
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci

# 时区
default-time-zone = +08:00
*/

-- =============================================
-- 7. 执行说明
-- =============================================

/*
生产环境执行步骤：

1. 执行任何更改前备份数据库
2. 分部分执行此文件，从索引优化开始
3. 在低流量期间运行
4. 执行期间监控服务器负载
5. 执行后验证性能改进

推荐执行顺序：
1. 索引优化（第1节）
2. 表结构优化（第2节）
3. 新表创建（第3节）
4. 维护存储过程（第5节）

验证步骤：
1. 对常用查询运行EXPLAIN
2. 监控慢查询日志
3. 检查服务器性能指标
4. 验证数据完整性
*/