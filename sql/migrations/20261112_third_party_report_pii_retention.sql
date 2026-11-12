-- 第三方上报与下游转发日志 PII 到期清理元数据。
-- 清理任务默认关闭（THIRD_PARTY_REPORT_PII_RETENTION_DAYS=0）；必须先确定并审批适用保留期限。
-- 本迁移仅新增清理标记与扫描索引，不会删除或改写历史数据。
-- 每个 DDL 均按 information_schema 做存在性检查，可在任意 DDL 边界中断后安全重跑。

SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'third_party_report_logs'
      AND COLUMN_NAME = 'pii_scrubbed_at'
);
SET @ddl = IF(
    @has_col = 0,
    'ALTER TABLE third_party_report_logs ADD COLUMN pii_scrubbed_at DATETIME NULL COMMENT ''PII 按保留策略清理时间；保留事件幂等键'' AFTER completed_at',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- 校验索引完整结构；错误的同名索引不得被当作已完成迁移。
SET @has_index = (
    SELECT COUNT(*)
    FROM (
        SELECT INDEX_NAME
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'third_party_report_logs'
          AND INDEX_NAME = 'idx_third_party_pii_retention'
        GROUP BY INDEX_NAME
        HAVING COUNT(*) = 3
           AND GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX SEPARATOR ',') = 'pii_scrubbed_at,created_at,id'
    ) AS valid_third_party_pii_index
);
SET @ddl = IF(
    @has_index = 0,
    'ALTER TABLE third_party_report_logs ADD INDEX idx_third_party_pii_retention (pii_scrubbed_at, created_at, id)',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'postback_forward_logs'
      AND COLUMN_NAME = 'pii_scrubbed_at'
      AND COLUMN_TYPE = 'datetime' AND IS_NULLABLE = 'YES'
);
SET @ddl = IF(
    @has_col = 0,
    'ALTER TABLE postback_forward_logs ADD COLUMN pii_scrubbed_at DATETIME NULL COMMENT ''PII 按保留策略清理时间'' AFTER completed_at',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- 校验索引完整结构；错误的同名索引不得被当作已完成迁移。
SET @has_index = (
    SELECT COUNT(*)
    FROM (
        SELECT INDEX_NAME
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'postback_forward_logs'
          AND INDEX_NAME = 'idx_forward_log_pii_retention'
        GROUP BY INDEX_NAME
        HAVING COUNT(*) = 3
           AND GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX SEPARATOR ',') = 'pii_scrubbed_at,created_at,id'
    ) AS valid_forward_pii_index
);
SET @ddl = IF(
    @has_index = 0,
    'ALTER TABLE postback_forward_logs ADD INDEX idx_forward_log_pii_retention (pii_scrubbed_at, created_at, id)',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- 迁移后核验；新增标记必须为空，历史 PII 不会在迁移时被清理。
SELECT TABLE_NAME, COLUMN_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND ((TABLE_NAME = 'third_party_report_logs' AND COLUMN_NAME = 'pii_scrubbed_at')
    OR (TABLE_NAME = 'postback_forward_logs' AND COLUMN_NAME = 'pii_scrubbed_at'));
