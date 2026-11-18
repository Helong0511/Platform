-- 为下游转发队列增加独立租约身份与到期时间。
-- next_retry_time 只表示业务重试时间；租约由随机 token 与数据库时钟到期点定义。
-- 旧队列记录保持两列 NULL，首次领取时由 Worker 生成新令牌。
SET @token_exists = (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='postback_forward_queue' AND COLUMN_NAME='lease_token');
SET @token_ddl = IF(@token_exists=1,'SELECT 1','ALTER TABLE postback_forward_queue ADD COLUMN lease_token CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT ''Worker 独立随机租约令牌''');
PREPARE token_stmt FROM @token_ddl; EXECUTE token_stmt; DEALLOCATE PREPARE token_stmt;
SET @expiry_exists = (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='postback_forward_queue' AND COLUMN_NAME='lease_expires_at');
SET @expiry_ddl = IF(@expiry_exists=1,'SELECT 1','ALTER TABLE postback_forward_queue ADD COLUMN lease_expires_at DATETIME(6) NULL COMMENT ''Worker 租约过期时间（数据库时钟）''');
PREPARE expiry_stmt FROM @expiry_ddl; EXECUTE expiry_stmt; DEALLOCATE PREPARE expiry_stmt;
SET @check_exists = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS WHERE CONSTRAINT_SCHEMA=DATABASE() AND TABLE_NAME='postback_forward_queue' AND CONSTRAINT_NAME='chk_forward_queue_lease_pair_v1' AND CONSTRAINT_TYPE='CHECK');
SET @check_ddl = IF(@check_exists=1,'SELECT 1','ALTER TABLE postback_forward_queue ADD CONSTRAINT chk_forward_queue_lease_pair_v1 CHECK ((lease_token IS NULL AND lease_expires_at IS NULL) OR (lease_token IS NOT NULL AND CHAR_LENGTH(lease_token)=32 AND lease_expires_at IS NOT NULL))');
PREPARE check_stmt FROM @check_ddl; EXECUTE check_stmt; DEALLOCATE PREPARE check_stmt;
SET @valid = (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='postback_forward_queue' AND ((COLUMN_NAME='lease_token' AND COLUMN_TYPE='char(32)' AND IS_NULLABLE='YES' AND CHARACTER_SET_NAME='ascii' AND COLLATION_NAME='ascii_bin') OR (COLUMN_NAME='lease_expires_at' AND COLUMN_TYPE='datetime(6)' AND IS_NULLABLE='YES')));
-- 不能只按约束名称判断成功：必须核验完整表达式且 CHECK 实际强制执行。
SET @check_valid = (
    SELECT COUNT(*)
    FROM information_schema.TABLE_CONSTRAINTS tc
    JOIN information_schema.CHECK_CONSTRAINTS cc
      ON cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
     AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
    WHERE tc.CONSTRAINT_SCHEMA = DATABASE()
      AND tc.TABLE_NAME = 'postback_forward_queue'
      AND tc.CONSTRAINT_NAME = 'chk_forward_queue_lease_pair_v1'
      AND tc.CONSTRAINT_TYPE = 'CHECK'
      AND tc.ENFORCED = 'YES'
      AND REGEXP_REPLACE(LOWER(cc.CHECK_CLAUSE), '[[:space:]\x60()]', '') =
          'lease_tokenisnullandlease_expires_atisnullorlease_tokenisnotnullandchar_lengthlease_token=32andlease_expires_atisnotnull'
);
SET @verify_sql = IF(@valid=2 AND @check_valid=1,'SELECT 1','SELECT * FROM __forward_queue_lease_validation_failed__');
PREPARE verify_stmt FROM @verify_sql; EXECUTE verify_stmt; DEALLOCATE PREPARE verify_stmt;
