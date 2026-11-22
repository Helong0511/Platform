-- 点击归档表补齐主表中的 URL 诊断字段。
-- 若 clicks_archive 尚不存在则安全跳过；后续归档服务创建表时会使用完整 DDL。
-- 若归档表已存在，则仅增加缺失列，不更新或删除任何历史记录。

SET @has_archive_table = (
    SELECT COUNT(*) FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'clicks_archive'
      AND TABLE_TYPE = 'BASE TABLE'
);

SET @has_original_request_url = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'clicks_archive'
      AND COLUMN_NAME = 'original_request_url'
      AND COLUMN_TYPE = 'text'
      AND IS_NULLABLE = 'YES'
      AND COLUMN_DEFAULT IS NULL
      AND EXTRA = ''
);
SET @ddl = IF(
    @has_archive_table = 1 AND @has_original_request_url = 0,
    'ALTER TABLE clicks_archive ADD COLUMN original_request_url TEXT NULL AFTER all_headers',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_final_redirect_url = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'clicks_archive'
      AND COLUMN_NAME = 'final_redirect_url'
      AND COLUMN_TYPE = 'text'
      AND IS_NULLABLE = 'YES'
      AND COLUMN_DEFAULT IS NULL
      AND EXTRA = ''
);
SET @ddl = IF(
    @has_archive_table = 1 AND @has_final_redirect_url = 0,
    'ALTER TABLE clicks_archive ADD COLUMN final_redirect_url TEXT NULL AFTER original_request_url',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- 输出实际列定义，供 migration 日志和人工验收核对。
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'clicks_archive'
  AND COLUMN_NAME IN ('original_request_url', 'final_redirect_url')
ORDER BY ORDINAL_POSITION;
