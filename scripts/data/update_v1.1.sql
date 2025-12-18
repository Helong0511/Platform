-- 添加 PostbackForwardQueue 表和 Offer.click_validity_hours 字段

-- 1. 添加 click_validity_hours 列到 offers 表
ALTER TABLE offers ADD COLUMN click_validity_hours INT DEFAULT 720 COMMENT '点击有效期（小时），默认720小时（30天）';

-- 2. 创建 postback_forward_queue 表
CREATE TABLE IF NOT EXISTS postback_forward_queue (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '队列ID',
    conversion_id INT NOT NULL COMMENT '关联的转化记录ID',
    product_id INT NOT NULL COMMENT '产品ID',
    downstream_url VARCHAR(500) NOT NULL COMMENT '下游URL',
    request_method VARCHAR(10) NOT NULL COMMENT '请求方式：GET 或 POST',
    request_data TEXT COMMENT '请求数据（JSON格式，用于POST请求）',
    request_params TEXT COMMENT '请求参数（URL参数，用于GET请求）',
    retry_count INT DEFAULT 0 COMMENT '已重试次数',
    next_retry_time DATETIME NOT NULL COMMENT '下次重试时间',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    
    INDEX idx_postback_forward_queue_conversion_id (conversion_id),
    INDEX idx_postback_forward_queue_product_id (product_id),
    INDEX idx_postback_forward_queue_next_retry_time (next_retry_time),
    
    CONSTRAINT fk_postback_forward_queue_conversion FOREIGN KEY (conversion_id) REFERENCES postback_conversions(id) ON DELETE CASCADE,
    CONSTRAINT fk_postback_forward_queue_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Postback 转发队列';
