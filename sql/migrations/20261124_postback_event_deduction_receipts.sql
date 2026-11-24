-- 被扣量事件不写入 postback_conversions，必须保留独立幂等收据。
-- 普通转化在主记录同一事务保存后删除临时收据；volume-deducted 事件保留收据。
CREATE TABLE IF NOT EXISTS postback_event_receipts (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '收据 ID',
    platform VARCHAR(50) NOT NULL COMMENT '平台标识',
    conversion_id VARCHAR(255) NOT NULL COMMENT '上游转化唯一标识',
    event_name VARCHAR(100) NOT NULL COMMENT '规范化事件名称',
    created_at DATETIME NOT NULL COMMENT '收据创建时间（应用时区）',
    PRIMARY KEY (id),
    UNIQUE KEY uq_postback_event_receipt_identity (platform, conversion_id, event_name),
    KEY idx_postback_event_receipt_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Postback 事件幂等收据（保留未入库的扣量事件）';
