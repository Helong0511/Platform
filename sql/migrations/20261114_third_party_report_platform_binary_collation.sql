-- 第三方上报平台标识采用精确二进制比较，保持 Python 身份 key 语义一致。
--
-- 应用层 platform 只 trim，不做大小写/重音折叠；旧列继承表默认
-- utf8mb4_0900_ai_ci，会使 SQL 的 platform = 比较把 META/meta、cafe/café
-- 当作相等。此 migration 只修改 platform 列，不改写已有 platform 值或 event_key。
--
-- 注意：修改字符列 collation 可能重建该列关联索引。上线前必须在隔离副本
-- 用代表性表规模测量 DDL 时间、锁影响和磁盘空间；不得直接在生产执行。

SET @platform_identity_collation_ok = (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'third_party_report_logs'
      AND COLUMN_NAME = 'platform'
      AND COLUMN_TYPE = 'varchar(100)'
      AND IS_NULLABLE = 'YES'
      AND CHARACTER_SET_NAME = 'utf8mb4'
      AND COLLATION_NAME = 'utf8mb4_bin'
);
SET @ddl = IF(
    @platform_identity_collation_ok = 1,
    'SELECT 1',
    'ALTER TABLE third_party_report_logs MODIFY COLUMN platform VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL DEFAULT NULL COMMENT ''Postback 平台标识；非平台事件为 NULL；按二进制规则精确比较'''
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- 迁移后强制核验，防止因列缺失或结构不匹配而静默标记成功。
SELECT COUNT(*) AS invalid_platform_collation
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'third_party_report_logs'
  AND COLUMN_NAME = 'platform'
  AND COLUMN_TYPE = 'varchar(100)'
  AND IS_NULLABLE = 'YES'
  AND CHARACTER_SET_NAME = 'utf8mb4'
  AND COLLATION_NAME = 'utf8mb4_bin';
