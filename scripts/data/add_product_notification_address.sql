-- 在 products 表中添加通知地址字段
-- 用于接收 Postback 转化通知

-- 添加通知地址字段
ALTER TABLE products 
ADD COLUMN notification_address VARCHAR(500) NULL 
COMMENT '通知地址（Telegram Chat ID、邮箱地址、Webhook URL等，用于接收转化通知）' 
AFTER downstream_postback_method;

-- 使用说明：
-- 1. Telegram Chat ID：直接填写数字，如 '123456789'
-- 2. 邮箱地址：填写邮箱，如 'product@example.com'
-- 3. Webhook URL：填写完整 URL，如 'https://example.com/webhook'
--
-- 配置示例：
-- UPDATE products SET notification_address = '123456789' WHERE id = 1;  -- Telegram Chat ID
-- UPDATE products SET notification_address = 'product1@example.com' WHERE id = 2;  -- 邮箱
-- UPDATE products SET notification_address = 'https://example.com/webhook' WHERE id = 3;  -- Webhook

