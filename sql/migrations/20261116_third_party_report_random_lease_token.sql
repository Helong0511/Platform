-- 第三方上报租约改用独立随机令牌，避免 DATETIME 秒级精度碰撞。
-- report_start_time 只负责租约时效判断；lease_token 负责 fencing 身份。
-- 旧记录保持 lease_token=NULL，由应用在下一次原子认领时生成新令牌。
-- 本迁移仅新增可空列与 CHECK，不回填旧租约，避免把历史时间戳伪装成随机令牌。
-- 列追加到表尾，尽量利用 MySQL 8.0.29+ 的 INSTANT ADD COLUMN 能力。

SET @lease_token_column_exists = (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'third_party_report_logs'
      AND COLUMN_NAME = 'lease_token'
);
SET @lease_token_ddl = IF(
    @lease_token_column_exists = 1,
    'SELECT 1',
    'ALTER TABLE third_party_report_logs ADD COLUMN lease_token CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT ''独立随机租约令牌；report_start_time 仅用于过期判断'''
);
PREPARE lease_token_stmt FROM @lease_token_ddl;
EXECUTE lease_token_stmt;
DEALLOCATE PREPARE lease_token_stmt;

SET @lease_token_check_exists = (
    SELECT COUNT(*)
    FROM information_schema.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'third_party_report_logs'
      AND CONSTRAINT_NAME = 'chk_third_party_report_lease_token_v1'
      AND CONSTRAINT_TYPE = 'CHECK'
);
SET @lease_token_check_ddl = IF(
    @lease_token_check_exists = 1,
    'SELECT 1',
    'ALTER TABLE third_party_report_logs ADD CONSTRAINT chk_third_party_report_lease_token_v1 CHECK (lease_token IS NULL OR (lease_token REGEXP ''^[0-9a-f]{32}$'' AND report_start_time IS NOT NULL))'
);
PREPARE lease_token_check_stmt FROM @lease_token_check_ddl;
EXECUTE lease_token_check_stmt;
DEALLOCATE PREPARE lease_token_check_stmt;

-- 强制核验新增列物理定义与 CHECK 约束；不符合时阻止 migration 标记 applied。
SET @lease_token_schema_valid = (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'third_party_report_logs'
      AND COLUMN_NAME = 'lease_token'
      AND COLUMN_TYPE = 'char(32)'
      AND IS_NULLABLE = 'YES'
      AND CHARACTER_SET_NAME = 'ascii'
      AND COLLATION_NAME = 'ascii_bin'
);
-- 同名但表达式错误或 NOT ENFORCED 的约束不能被视为迁移成功。
SET @lease_token_check_valid = (
    SELECT COUNT(*)
    FROM information_schema.TABLE_CONSTRAINTS tc
    JOIN information_schema.CHECK_CONSTRAINTS cc
      ON cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
     AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
    WHERE tc.CONSTRAINT_SCHEMA = DATABASE()
      AND tc.TABLE_NAME = 'third_party_report_logs'
      AND tc.CONSTRAINT_NAME = 'chk_third_party_report_lease_token_v1'
      AND tc.CONSTRAINT_TYPE = 'CHECK'
      AND tc.ENFORCED = 'YES'
      AND (
          REGEXP_REPLACE(REPLACE(LOWER(cc.CHECK_CLAUSE), CHAR(96), ''), '[[:space:](),]', '') =
              CONCAT(
                  'lease_tokenisnullorlease_tokenregexp',
                  CHAR(39), '^[0-9a-f]{32}', CHAR(36), CHAR(39),
                  'andreport_start_timeisnotnull'
              )
          OR REGEXP_REPLACE(REPLACE(LOWER(cc.CHECK_CLAUSE), CHAR(96), ''), '[[:space:](),]', '') =
              CONCAT(
                  'lease_tokenisnullorregexplikelease_token',
                  CHAR(39), '^[0-9a-f]{32}', CHAR(36), CHAR(39),
                  'andreport_start_timeisnotnull'
              )
      )
);
SET @lease_token_verify_sql = IF(
    @lease_token_schema_valid = 1 AND @lease_token_check_valid = 1,
    'SELECT 1',
    'SELECT * FROM __third_party_report_lease_token_validation_failed__'
);
PREPARE lease_token_verify_stmt FROM @lease_token_verify_sql;
EXECUTE lease_token_verify_stmt;
DEALLOCATE PREPARE lease_token_verify_stmt;
