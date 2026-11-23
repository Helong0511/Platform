-- 广告数据查询缓存 Generation 与持久化失效 Outbox（MySQL 8.0.16+）。
-- 业务写入、Generation 递增与 Outbox 登记必须在同一个 InnoDB 事务内完成。
-- 本迁移不执行历史数据回填；旧缓存键由原 TTL 自然过期。

CREATE TABLE IF NOT EXISTS cache_namespace_generations (
    namespace VARCHAR(64) NOT NULL COMMENT '缓存命名空间',
    generation BIGINT NOT NULL DEFAULT 1 COMMENT '数据库权威单调递增版本',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP COMMENT '版本更新时间',
    PRIMARY KEY (namespace),
    CONSTRAINT chk_cache_namespace_generation_positive CHECK (generation > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='缓存命名空间数据库权威 Generation';

CREATE TABLE IF NOT EXISTS cache_invalidation_outbox (
    id BIGINT NOT NULL AUTO_INCREMENT,
    event_key CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL
        COMMENT 'namespace:generation 的 SHA-256 幂等键',
    namespace VARCHAR(64) NOT NULL COMMENT '缓存命名空间',
    generation BIGINT NOT NULL COMMENT '对应数据库权威版本',
    status VARCHAR(16) NOT NULL DEFAULT 'pending'
        COMMENT 'pending/processing/success/failed',
    attempt_count INT NOT NULL DEFAULT 0 COMMENT '已尝试次数',
    max_attempts INT NOT NULL DEFAULT 12 COMMENT '最大自动尝试次数',
    next_retry_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '下次可认领时间',
    locked_by VARCHAR(128) NULL COMMENT '当前 Worker 标识',
    lease_token CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '随机租约 fencing token',
    lease_until DATETIME NULL COMMENT '租约到期时间',
    last_error_type VARCHAR(128) NULL COMMENT '异常类型摘要，不保存异常原文',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    completed_at DATETIME NULL COMMENT '终态完成时间',
    PRIMARY KEY (id),
    UNIQUE KEY uq_cache_invalidation_event_key (event_key),
    KEY idx_cache_invalidation_due (status, next_retry_time, lease_until, id),
    KEY idx_cache_invalidation_namespace_generation (namespace, generation),
    CONSTRAINT chk_cache_invalidation_status
        CHECK (status IN ('pending', 'processing', 'success', 'failed')),
    CONSTRAINT chk_cache_invalidation_counters
        CHECK (attempt_count >= 0 AND max_attempts > 0 AND generation > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='缓存失效持久化 Outbox';

-- 首次安装时初始化广告数据查询缓存命名空间；重复执行不会重置现有版本。
INSERT IGNORE INTO cache_namespace_generations (namespace, generation)
VALUES ('ad_data', 1);

-- 迁移后核验：命名空间初始化必须存在且版本为正数。
SELECT namespace, generation
FROM cache_namespace_generations
WHERE namespace = 'ad_data' AND generation > 0;

SHOW INDEX FROM cache_invalidation_outbox;
