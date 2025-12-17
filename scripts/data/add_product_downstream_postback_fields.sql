-- 为 products 表添加下游 Postback 相关字段
-- 用于配置产品级别的下游转发功能

USE `platform`;

-- 添加下游 Postback URL 字段（如果不存在）
SET @dbname = DATABASE();
SET @tablename = 'products';
SET @columnname = 'downstream_postback_url';
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE
      (TABLE_SCHEMA = @dbname)
      AND (TABLE_NAME = @tablename)
      AND (COLUMN_NAME = @columnname)
  ) > 0,
  'SELECT 1',
  CONCAT('ALTER TABLE ', @tablename, ' ADD COLUMN ', @columnname, ' VARCHAR(500) NULL COMMENT ''下游 Postback URL（可选，配置后将自动转发转化数据）'' AFTER revenue_deduct_ratio')
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- 添加下游 Postback 请求方式字段（如果不存在）
SET @columnname = 'downstream_postback_method';
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE
      (TABLE_SCHEMA = @dbname)
      AND (TABLE_NAME = @tablename)
      AND (COLUMN_NAME = @columnname)
  ) > 0,
  'SELECT 1',
  CONCAT('ALTER TABLE ', @tablename, ' ADD COLUMN ', @columnname, ' VARCHAR(10) DEFAULT ''GET'' COMMENT ''下游 Postback 请求方式：GET 或 POST（默认GET）'' AFTER downstream_postback_url')
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- 使用说明：
-- 1. downstream_postback_url: 下游系统的接收地址，配置后系统会自动将转化数据转发到此地址
-- 2. downstream_postback_method: 转发方式，支持 GET 和 POST
--    - GET: 数据作为 URL 参数传递
--    - POST: 数据作为 JSON body 传递（推荐）

