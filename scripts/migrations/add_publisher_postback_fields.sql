-- 为渠道表添加Postback配置字段
-- 执行时间: 2025-12-18

ALTER TABLE publishers 
ADD COLUMN postback_url TEXT COMMENT 'Postback URL（渠道的Postback配置）' AFTER price_discount,
ADD COLUMN postback_method VARCHAR(10) DEFAULT 'GET' COMMENT 'Postback请求方式：GET/POST' AFTER postback_url;

