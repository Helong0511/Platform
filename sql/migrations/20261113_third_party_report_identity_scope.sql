-- 第三方上报身份作用域与目的地身份（MySQL 8.0）
--
-- 目标：
-- 1. 显式保存 platform / identity_scope，避免仅从 event_key 哈希猜测平台归属。
-- 2. 保存非敏感 Facebook Pixel ID，供事件目的地一致性核验；不保存 access_token。
-- 3. 所有迁移前历史行默认 legacy_unresolved，不自动猜测归属。
--
-- 安全约束：
-- - 不回填历史 platform / destination_pixel_id。
-- - 旧 Outbox 行在人工/可审计 reconciliation 前不得自动升级作用域。
-- - 该 DDL 是增量 schema，不代表旧 Worker 已被阻止消费新行；发布前必须停止旧 Worker。
-- - 不修改任何已登记历史 migration 或其 checksum。

SET @has_platform = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'third_party_report_logs'
      AND COLUMN_NAME = 'platform'
      AND COLUMN_TYPE = 'varchar(100)'
      AND IS_NULLABLE = 'YES'
);
SET @ddl = IF(
    @has_platform = 0,
    'ALTER TABLE third_party_report_logs ADD COLUMN platform VARCHAR(100) NULL COMMENT ''Postback 平台标识；历史归属未知时保持 NULL'' AFTER event_key',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_identity_scope = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'third_party_report_logs'
      AND COLUMN_NAME = 'identity_scope'
      AND COLUMN_TYPE = 'varchar(32)'
      AND IS_NULLABLE = 'NO'
      AND COLUMN_DEFAULT = 'legacy_unresolved'
);
SET @ddl = IF(
    @has_identity_scope = 0,
    'ALTER TABLE third_party_report_logs ADD COLUMN identity_scope VARCHAR(32) NOT NULL DEFAULT ''legacy_unresolved'' COMMENT ''unscoped/platform_scoped/legacy_unresolved；历史行不猜归属'' AFTER platform',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_destination_pixel = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'third_party_report_logs'
      AND COLUMN_NAME = 'destination_pixel_id'
      AND COLUMN_TYPE = 'varchar(100)'
      AND IS_NULLABLE = 'YES'
);
SET @ddl = IF(
    @has_destination_pixel = 0,
    'ALTER TABLE third_party_report_logs ADD COLUMN destination_pixel_id VARCHAR(100) NULL COMMENT ''非敏感 Meta Pixel 目的地 ID；不保存 access_token'' AFTER identity_scope',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- 校验复合索引完整结构；同名但列序错误的索引不能被视为迁移成功。
SET @has_scope_due_index = (
    SELECT COUNT(*)
    FROM (
        SELECT INDEX_NAME
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'third_party_report_logs'
          AND INDEX_NAME = 'idx_third_party_scope_due'
        GROUP BY INDEX_NAME
        HAVING COUNT(*) = 7
           AND MAX(NON_UNIQUE) = 1
           AND MAX(INDEX_TYPE) = 'BTREE'
           AND MAX(SUB_PART) IS NULL
           AND SUM(CASE WHEN COLLATION = 'A' THEN 1 ELSE 0 END) = 7
           AND GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX SEPARATOR ',') =
               'identity_scope,platform,outbox_enqueued,status,next_retry_time,report_start_time,id'
    ) AS valid_scope_due_index
);
SET @ddl = IF(
    @has_scope_due_index = 0,
    'ALTER TABLE third_party_report_logs ADD INDEX idx_third_party_scope_due (identity_scope, platform, outbox_enqueued, status, next_retry_time, report_start_time, id)',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- 迁移后所有旧行必须保持 legacy_unresolved；不得按 source 或 event_key 推断平台。
SELECT identity_scope, COUNT(*) AS row_count
FROM third_party_report_logs
GROUP BY identity_scope
ORDER BY identity_scope;

SELECT COUNT(*) AS invalid_scope_rows
FROM third_party_report_logs
WHERE identity_scope NOT IN ('legacy_unresolved', 'unscoped', 'platform_scoped')
   OR (identity_scope = 'platform_scoped' AND (platform IS NULL OR platform = ''))
   OR (identity_scope = 'unscoped' AND platform IS NOT NULL);

SHOW INDEX FROM third_party_report_logs;
