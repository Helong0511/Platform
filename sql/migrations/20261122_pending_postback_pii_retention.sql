-- 为待审批 Postback 终态记录增加独立 PII 清理标记与批量扫描索引。
-- 默认保留期限为 0（关闭）；本迁移不改写历史数据、不清理 pending 记录。
-- 仅 approved/rejected 终态允许按单独审批后的策略清除个人信息载荷。
-- 每个 DDL 均按 information_schema 检查，允许在 DDL 边界中断后安全重跑。

SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'pending_postback_conversions'
      AND COLUMN_NAME = 'pii_scrubbed_at'
      AND COLUMN_TYPE = 'datetime'
      AND IS_NULLABLE = 'YES'
      AND COLUMN_DEFAULT IS NULL
      AND EXTRA = ''
);
SET @ddl = IF(
    @has_col = 0,
    'ALTER TABLE pending_postback_conversions ADD COLUMN pii_scrubbed_at DATETIME NULL COMMENT ''终态 Postback 个人信息按独立保留策略清理时间'' AFTER rejected_at',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- 错误的同名索引不得被当作迁移已完成；必须具有精确列序和普通 BTREE 非唯一属性。
SET @has_index = (
    SELECT COUNT(*)
    FROM (
        SELECT INDEX_NAME
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'pending_postback_conversions'
          AND INDEX_NAME = 'idx_pending_postback_pii_retention'
        GROUP BY INDEX_NAME
        HAVING COUNT(*) = 4
           AND MAX(NON_UNIQUE) = 1
           AND MAX(INDEX_TYPE) = 'BTREE'
           AND MAX(SUB_PART) IS NULL
           AND SUM(CASE WHEN COLLATION = 'A' THEN 1 ELSE 0 END) = 4
           AND GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX SEPARATOR ',') =
               'pii_scrubbed_at,status,created_at,id'
    ) AS valid_pending_postback_pii_index
);
SET @ddl = IF(
    @has_index = 0,
    'ALTER TABLE pending_postback_conversions ADD INDEX idx_pending_postback_pii_retention (pii_scrubbed_at, status, created_at, id)',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- 核验新字段存在；历史记录 pii_scrubbed_at 必须仍为空，禁止迁移阶段清理业务数据。
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'pending_postback_conversions'
  AND COLUMN_NAME = 'pii_scrubbed_at';
