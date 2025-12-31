-- ============================================
-- 迁移脚本：为clicks表添加软件、硬件信息和URL参数字段
-- 创建时间：2025-01-XX
-- 说明：扩展clicks表以记录完整的点击信息，包括软件信息、硬件信息和URL参数
-- ============================================

-- 添加软件信息字段
ALTER TABLE `clicks` 
ADD COLUMN `os` VARCHAR(50) NULL DEFAULT NULL COMMENT '操作系统名称' AFTER `referer`,
ADD COLUMN `os_version` VARCHAR(50) NULL DEFAULT NULL COMMENT '操作系统版本' AFTER `os`,
ADD COLUMN `browser` VARCHAR(50) NULL DEFAULT NULL COMMENT '浏览器名称' AFTER `os_version`,
ADD COLUMN `browser_version` VARCHAR(50) NULL DEFAULT NULL COMMENT '浏览器版本' AFTER `browser`,
ADD COLUMN `accept_language` VARCHAR(200) NULL DEFAULT NULL COMMENT '接受的语言' AFTER `browser_version`,
ADD COLUMN `accept_encoding` VARCHAR(200) NULL DEFAULT NULL COMMENT '接受的编码' AFTER `accept_language`,
ADD COLUMN `is_bot` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否为机器人/爬虫' AFTER `accept_encoding`;

-- 添加硬件信息字段
ALTER TABLE `clicks` 
ADD COLUMN `device_type` VARCHAR(20) NULL DEFAULT NULL COMMENT '设备类型（mobile/tablet/desktop）' AFTER `is_bot`,
ADD COLUMN `device_brand` VARCHAR(50) NULL DEFAULT NULL COMMENT '设备品牌' AFTER `device_type`,
ADD COLUMN `device_model` VARCHAR(100) NULL DEFAULT NULL COMMENT '设备型号' AFTER `device_brand`;

-- 添加URL参数和请求头字段（JSON格式存储）
ALTER TABLE `clicks` 
ADD COLUMN `url_params` TEXT NULL DEFAULT NULL COMMENT 'URL参数（JSON格式）' AFTER `device_model`,
ADD COLUMN `all_headers` TEXT NULL DEFAULT NULL COMMENT '所有请求头（JSON格式）' AFTER `url_params`;

-- 为device_type添加索引（用于快速查询设备类型）
ALTER TABLE `clicks` 
ADD INDEX `idx_device_type` (`device_type` ASC) USING BTREE;

-- 为os和browser添加索引（用于快速查询操作系统和浏览器）
ALTER TABLE `clicks` 
ADD INDEX `idx_os` (`os` ASC) USING BTREE,
ADD INDEX `idx_browser` (`browser` ASC) USING BTREE;

-- 为is_bot添加索引（用于过滤机器人流量）
ALTER TABLE `clicks` 
ADD INDEX `idx_is_bot` (`is_bot` ASC) USING BTREE;

-- 验证字段是否添加成功
SELECT 
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    COLUMN_COMMENT
FROM 
    INFORMATION_SCHEMA.COLUMNS
WHERE 
    TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'clicks'
    AND COLUMN_NAME IN (
        'os', 'os_version', 'browser', 'browser_version',
        'accept_language', 'accept_encoding', 'is_bot',
        'device_type', 'device_brand', 'device_model',
        'url_params', 'all_headers'
    )
ORDER BY 
    ORDINAL_POSITION;

