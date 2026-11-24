-- Offer 热点缓存失效事件；业务变更与两阶段清理任务必须同事务提交。
-- 只保存 Offer 主键和固定阶段，不存储任意 Redis key/pattern 或敏感业务载荷。
CREATE TABLE IF NOT EXISTS offer_cache_invalidation_outbox (
    id BIGINT NOT NULL AUTO_INCREMENT,
    event_key CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    offer_id INT NOT NULL,
    phase VARCHAR(8) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    status VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'pending',
    attempt_count INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 12,
    run_at DATETIME(6) NOT NULL,
    locked_by VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
    lease_token CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL,
    lease_until DATETIME(6) NULL,
    last_error_type VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    completed_at DATETIME(6) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_offer_cache_invalidation_event_key (event_key),
    KEY idx_offer_cache_invalidation_due (status, run_at, lease_until, id),
    KEY idx_offer_cache_invalidation_offer (offer_id, phase, status),
    CONSTRAINT chk_offer_cache_invalidation_phase
        CHECK (phase IN ('first', 'second')),
    CONSTRAINT chk_offer_cache_invalidation_status
        CHECK (status IN ('pending', 'processing', 'success', 'failed')),
    CONSTRAINT chk_offer_cache_invalidation_attempts
        CHECK (attempt_count >= 0 AND max_attempts > 0 AND offer_id > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
