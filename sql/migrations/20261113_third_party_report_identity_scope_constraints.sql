-- 第三方上报身份作用域数据库级完整性约束（MySQL 8.0.16+）
--
-- 目标：数据库本身拒绝非法 identity_scope，以及 platform 与作用域不匹配的数据。
-- 历史 legacy_unresolved 记录必须保持 platform=NULL；不推断、不回填历史归属。
-- MySQL 8.0.16 起 CHECK 约束才会被执行；Runner 最低版本为 8.0.16。
-- 发现异常行时 fail closed，不自动修正业务身份。

SET @invalid_identity_scope_rows = (
    SELECT COUNT(*)
    FROM third_party_report_logs
    WHERE identity_scope NOT IN ('legacy_unresolved', 'unscoped', 'platform_scoped')
       OR (identity_scope = 'platform_scoped' AND
           (platform IS NULL OR LENGTH(TRIM(platform)) = 0))
       OR (identity_scope IN ('unscoped', 'legacy_unresolved') AND platform IS NOT NULL)
);
SET @ddl = IF(
    @invalid_identity_scope_rows > 0,
    'SELECT * FROM __third_party_report_identity_scope_data_mismatch__',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- 同名约束必须确实是作用域约束；同名但定义不相关时停止，不静默跳过。
SET @has_named_check = (
    SELECT COUNT(*)
    FROM information_schema.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'third_party_report_logs'
      AND CONSTRAINT_NAME = 'chk_third_party_identity_scope_v1'
      AND CONSTRAINT_TYPE = 'CHECK'
);
SET @has_valid_check = (
    SELECT COUNT(*)
    FROM information_schema.TABLE_CONSTRAINTS tc
    JOIN information_schema.CHECK_CONSTRAINTS cc
      ON cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
     AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
    WHERE tc.CONSTRAINT_SCHEMA = DATABASE()
      AND tc.TABLE_NAME = 'third_party_report_logs'
      AND tc.CONSTRAINT_NAME = 'chk_third_party_identity_scope_v1'
      AND tc.CONSTRAINT_TYPE = 'CHECK'
      AND LOWER(cc.CHECK_CLAUSE) LIKE '%identity_scope%'
      AND LOWER(cc.CHECK_CLAUSE) LIKE '%platform%'
      AND LOWER(cc.CHECK_CLAUSE) LIKE '%legacy_unresolved%'
      AND LOWER(cc.CHECK_CLAUSE) LIKE '%platform_scoped%'
      AND LOWER(cc.CHECK_CLAUSE) LIKE '%unscoped%'
);
SET @ddl = IF(
    @has_named_check > 0 AND @has_valid_check = 0,
    'SELECT * FROM __third_party_report_identity_scope_constraint_mismatch__',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
    @has_valid_check = 0,
    'ALTER TABLE third_party_report_logs ADD CONSTRAINT chk_third_party_identity_scope_v1 CHECK ((identity_scope IN (''legacy_unresolved'', ''unscoped'', ''platform_scoped'')) AND ((identity_scope = ''platform_scoped'' AND platform IS NOT NULL AND LENGTH(TRIM(platform)) > 0) OR (identity_scope IN (''unscoped'', ''legacy_unresolved'') AND platform IS NULL)))',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- 最终核验。
SELECT COUNT(*) AS invalid_identity_scope_rows
FROM third_party_report_logs
WHERE identity_scope NOT IN ('legacy_unresolved', 'unscoped', 'platform_scoped')
   OR (identity_scope = 'platform_scoped' AND
       (platform IS NULL OR LENGTH(TRIM(platform)) = 0))
   OR (identity_scope IN ('unscoped', 'legacy_unresolved') AND platform IS NOT NULL);
