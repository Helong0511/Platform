-- 为 products 表添加下游 Postback 相关字段
-- 用于配置产品级别的下游转发功能
-- 
-- 注意：如果字段已存在，执行此脚本会报错，可以忽略或先检查字段是否存在

USE `platform`;

-- 添加下游 Postback URL 字段
ALTER TABLE `products` 
ADD COLUMN `downstream_postback_url` VARCHAR(500) NULL COMMENT '下游 Postback URL（可选，配置后将自动转发转化数据）' AFTER `revenue_deduct_ratio`;

-- 添加下游 Postback 请求方式字段
ALTER TABLE `products` 
ADD COLUMN `downstream_postback_method` VARCHAR(10) DEFAULT 'GET' COMMENT '下游 Postback 请求方式：GET 或 POST（默认GET）' AFTER `downstream_postback_url`;

-- 使用说明：
-- 1. downstream_postback_url: 下游系统的接收地址，配置后系统会自动将转化数据转发到此地址
-- 2. downstream_postback_method: 转发方式，支持 GET 和 POST
--    - GET: 数据作为 URL 参数传递
--    - POST: 数据作为 JSON body 传递（推荐）
--
-- 如果字段已存在，执行前请先检查：
-- SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS 
-- WHERE TABLE_SCHEMA = 'platform' AND TABLE_NAME = 'products' 
-- AND COLUMN_NAME IN ('downstream_postback_url', 'downstream_postback_method');

