-- Postback 通知功能相关数据表
-- 用于支持按客户和产品进行转化通知

-- 1. 客户通知配置表
USE `platform`;

DROP TABLE IF EXISTS client_notification_configs;
CREATE TABLE IF NOT EXISTS client_notification_configs (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '通知配置ID',
    client_id INT NOT NULL UNIQUE COMMENT '客户ID',
    notification_enabled BOOLEAN DEFAULT TRUE COMMENT '是否启用通知',
    notify_on_conversion BOOLEAN DEFAULT TRUE COMMENT '转化时通知',
    notify_on_high_value BOOLEAN DEFAULT FALSE COMMENT '高价值转化通知',
    high_value_threshold DECIMAL(10,2) NULL COMMENT '高价值阈值',
    notify_channels TEXT NULL COMMENT '通知渠道（JSON格式：["telegram", "email", "sms"]）',
    telegram_chat_id VARCHAR(100) NULL COMMENT 'Telegram Chat ID',
    email_address VARCHAR(255) NULL COMMENT '邮箱地址',
    phone_number VARCHAR(20) NULL COMMENT '手机号',
    notification_frequency VARCHAR(20) DEFAULT 'realtime' COMMENT '通知频率：realtime, hourly, daily',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    -- 外键约束
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE,
    
    -- 索引
    INDEX idx_client_notification_config_client (client_id),
    INDEX idx_client_notification_config_enabled (notification_enabled)
) COMMENT='客户通知配置表';

-- 2. 产品通知配置表
DROP TABLE IF EXISTS product_notification_configs;
CREATE TABLE IF NOT EXISTS product_notification_configs (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '通知配置ID',
    product_id INT NOT NULL UNIQUE COMMENT '产品ID',
    notification_enabled BOOLEAN DEFAULT TRUE COMMENT '是否启用通知',
    notify_on_conversion BOOLEAN DEFAULT TRUE COMMENT '转化时通知',
    notify_on_high_value BOOLEAN DEFAULT FALSE COMMENT '高价值转化通知',
    high_value_threshold DECIMAL(10,2) NULL COMMENT '高价值阈值',
    notify_channels TEXT NULL COMMENT '通知渠道（JSON格式：["telegram", "email", "sms"]）',
    telegram_chat_id VARCHAR(100) NULL COMMENT 'Telegram Chat ID',
    email_address VARCHAR(255) NULL COMMENT '邮箱地址',
    phone_number VARCHAR(20) NULL COMMENT '手机号',
    notification_frequency VARCHAR(20) DEFAULT 'realtime' COMMENT '通知频率：realtime, hourly, daily',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    -- 外键约束
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    
    -- 索引
    INDEX idx_product_notification_config_product (product_id),
    INDEX idx_product_notification_config_enabled (notification_enabled)
) COMMENT='产品通知配置表';

-- 3. Postback 通知记录表
DROP TABLE IF EXISTS postback_notifications;
CREATE TABLE IF NOT EXISTS postback_notifications (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '通知记录ID',
    conversion_id INT NOT NULL COMMENT '转化记录ID',
    client_id INT NULL COMMENT '客户ID',
    product_id INT NULL COMMENT '产品ID',
    notification_type VARCHAR(50) NULL COMMENT '通知类型：conversion, high_value, error',
    notification_channel VARCHAR(50) NOT NULL COMMENT '通知渠道：telegram, email, sms',
    notification_status VARCHAR(20) DEFAULT 'pending' COMMENT '通知状态：sent, failed, pending',
    notification_message TEXT NULL COMMENT '通知消息内容',
    error_message TEXT NULL COMMENT '错误信息（如果失败）',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    
    -- 外键约束
    FOREIGN KEY (conversion_id) REFERENCES postback_conversions(id) ON DELETE CASCADE,
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL,
    
    -- 索引
    INDEX idx_postback_notification_conversion (conversion_id),
    INDEX idx_postback_notification_client (client_id),
    INDEX idx_postback_notification_product (product_id),
    INDEX idx_postback_notification_status (notification_status),
    INDEX idx_postback_notification_created_at (created_at)
) COMMENT='Postback通知记录表';

-- 使用说明：
-- 1. 客户通知配置：为每个客户配置通知规则，包括通知渠道、频率、阈值等
-- 2. 产品通知配置：为每个产品配置独立的通知规则（优先级高于客户配置）
-- 3. 通知记录：记录所有通知发送历史，用于统计和故障排查
--
-- 配置示例：
-- INSERT INTO client_notification_configs (client_id, notify_channels, telegram_chat_id, notification_frequency)
-- VALUES (1, '["telegram"]', '123456789', 'realtime');
--
-- INSERT INTO product_notification_configs (product_id, notify_on_high_value, high_value_threshold, notify_channels)
-- VALUES (1, TRUE, 100.00, '["telegram", "email"]');

