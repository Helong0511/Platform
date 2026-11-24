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

-- 已存在的同名表必须具备本迁移要求的完整结构；不能把 CREATE IF NOT EXISTS 的警告当作成功。
SET @generation_schema_valid = (
    SELECT
        (SELECT COUNT(*) FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cache_namespace_generations'
           AND ((COLUMN_NAME = 'namespace' AND COLUMN_TYPE = 'varchar(64)' AND IS_NULLABLE = 'NO')
             OR (COLUMN_NAME = 'generation' AND COLUMN_TYPE = 'bigint' AND IS_NULLABLE = 'NO')
             OR (COLUMN_NAME = 'updated_at' AND COLUMN_TYPE = 'datetime' AND IS_NULLABLE = 'NO'))) = 3
        AND (SELECT COUNT(*) FROM information_schema.STATISTICS
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cache_namespace_generations'
               AND INDEX_NAME = 'PRIMARY' AND COLUMN_NAME = 'namespace' AND SEQ_IN_INDEX = 1) = 1
        AND (SELECT COUNT(*) FROM information_schema.TABLES
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cache_namespace_generations'
               AND ENGINE = 'InnoDB' AND TABLE_COLLATION = 'utf8mb4_unicode_ci') = 1
        AND (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
             WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = 'cache_namespace_generations'
               AND CONSTRAINT_NAME = 'chk_cache_namespace_generation_positive'
               AND CONSTRAINT_TYPE = 'CHECK') = 1
);
SET @ddl = IF(
    @generation_schema_valid = 1,
    'SELECT 1',
    'SELECT * FROM __cache_namespace_generations_schema_mismatch__'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @outbox_schema_valid = (
    SELECT
        (SELECT COUNT(*) FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cache_invalidation_outbox'
           AND COLUMN_NAME IN (
               'id', 'event_key', 'namespace', 'generation', 'status',
               'attempt_count', 'max_attempts', 'next_retry_time', 'locked_by',
               'lease_token', 'lease_until', 'last_error_type', 'created_at', 'completed_at'
           )) = 14
        AND (SELECT COUNT(*) FROM information_schema.STATISTICS
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cache_invalidation_outbox'
               AND INDEX_NAME = 'PRIMARY' AND COLUMN_NAME = 'id' AND SEQ_IN_INDEX = 1) = 1
        AND (SELECT COUNT(*) FROM (
             SELECT INDEX_NAME FROM information_schema.STATISTICS
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cache_invalidation_outbox'
               AND INDEX_NAME = 'uq_cache_invalidation_event_key'
             GROUP BY INDEX_NAME
             HAVING MAX(NON_UNIQUE) = 0
                AND GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX SEPARATOR ',') = 'event_key'
        ) AS valid_event_key_index) = 1
        AND (SELECT COUNT(*) FROM (
             SELECT INDEX_NAME FROM information_schema.STATISTICS
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cache_invalidation_outbox'
               AND INDEX_NAME = 'idx_cache_invalidation_due'
             GROUP BY INDEX_NAME
             HAVING MAX(NON_UNIQUE) = 1
                AND GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX SEPARATOR ',') = 'status,next_retry_time,lease_until,id'
        ) AS valid_due_index) = 1
        AND (SELECT COUNT(*) FROM (
             SELECT INDEX_NAME FROM information_schema.STATISTICS
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cache_invalidation_outbox'
               AND INDEX_NAME = 'idx_cache_invalidation_namespace_generation'
             GROUP BY INDEX_NAME
             HAVING MAX(NON_UNIQUE) = 1
                AND GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX SEPARATOR ',') = 'namespace,generation'
        ) AS valid_namespace_index) = 1
        AND (SELECT COUNT(*) FROM information_schema.TABLES
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cache_invalidation_outbox'
               AND ENGINE = 'InnoDB' AND TABLE_COLLATION = 'utf8mb4_unicode_ci') = 1
        AND (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
             WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = 'cache_invalidation_outbox'
               AND CONSTRAINT_NAME IN ('chk_cache_invalidation_status', 'chk_cache_invalidation_counters')
               AND CONSTRAINT_TYPE = 'CHECK') = 2
);
SET @ddl = IF(
    @outbox_schema_valid = 1,
    'SELECT 1',
    'SELECT * FROM __cache_invalidation_outbox_schema_mismatch__'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- 迁移后核验：命名空间初始化必须存在且版本为正数。
SELECT namespace, generation
FROM cache_namespace_generations
WHERE namespace = 'ad_data' AND generation > 0;

SHOW INDEX FROM cache_invalidation_outbox;
