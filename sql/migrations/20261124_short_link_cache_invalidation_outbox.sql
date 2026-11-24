-- 短链接热点缓存两阶段失效事件；业务变更与事件必须同事务提交。
-- 仅保存受校验的 short_code，不接受任意 Redis key/pattern。
CREATE TABLE IF NOT EXISTS short_link_cache_invalidation_outbox (
    id BIGINT NOT NULL AUTO_INCREMENT,
    event_key CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    group_key CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    short_code VARCHAR(20) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
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
    UNIQUE KEY uq_short_link_cache_invalidation_event_key (event_key),
    UNIQUE KEY uq_short_link_cache_invalidation_group_phase (group_key, phase),
    KEY idx_short_link_cache_invalidation_due (status, run_at, id),
    KEY idx_short_link_cache_invalidation_lease (status, lease_until, id),
    KEY idx_short_link_cache_invalidation_code (short_code, phase, status),
    CONSTRAINT chk_short_link_cache_invalidation_phase
        CHECK (phase IN ('first', 'second')),
    CONSTRAINT chk_short_link_cache_invalidation_status
        CHECK (status IN ('pending', 'processing', 'success', 'failed')),
    CONSTRAINT chk_short_link_cache_invalidation_attempts
        CHECK (attempt_count >= 0 AND max_attempts > 0 AND CHAR_LENGTH(short_code) BETWEEN 1 AND 20)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
