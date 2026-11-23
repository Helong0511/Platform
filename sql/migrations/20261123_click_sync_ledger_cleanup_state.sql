-- 点击刷盘账本清理的独立持久化健康状态。
-- 清理失败与点击主入账状态分离；状态表只保存聚合计数和异常类型，不存储原始异常/连接串。
CREATE TABLE IF NOT EXISTS short_link_click_sync_ledger_maintenance (
    id INT NOT NULL COMMENT '固定单例主键，唯一允许值为 1',
    status VARCHAR(16) NOT NULL DEFAULT 'unknown' COMMENT '状态：unknown/healthy/degraded/failed',
    consecutive_failure_count INT NOT NULL DEFAULT 0 COMMENT '连续失败轮数',
    total_failure_count BIGINT NOT NULL DEFAULT 0 COMMENT '累计失败轮数',
    last_attempt_at DATETIME NULL COMMENT '最近一次清理尝试时间（应用时区）',
    last_success_at DATETIME NULL COMMENT '最近一次无错误清理完成时间（应用时区）',
    last_failure_at DATETIME NULL COMMENT '最近一次清理异常时间（应用时区）',
    last_error_type VARCHAR(128) NULL COMMENT '安全错误类别摘要，不保存异常原文',
    last_unacked_scanned_count INT NOT NULL DEFAULT 0 COMMENT '最近一轮扫描的未 ACK 账本数',
    last_acknowledged_count INT NOT NULL DEFAULT 0 COMMENT '最近一轮补记 ACK 数量',
    last_deleted_count INT NOT NULL DEFAULT 0 COMMENT '最近一轮删除的历史 ACK 数量',
    last_redis_check_failures INT NOT NULL DEFAULT 0 COMMENT '最近一轮 Redis 状态检查失败数',
    last_cache_invalidation_failures INT NOT NULL DEFAULT 0 COMMENT '最近一轮缓存失效失败数',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '状态更新时间',
    PRIMARY KEY (id),
    CONSTRAINT chk_click_sync_ledger_maintenance_singleton CHECK (id = 1),
    CONSTRAINT chk_click_sync_ledger_maintenance_status
        CHECK (status IN ('unknown', 'healthy', 'degraded', 'failed'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='短链接点击刷盘账本清理独立健康状态';

INSERT IGNORE INTO short_link_click_sync_ledger_maintenance (id) VALUES (1);
