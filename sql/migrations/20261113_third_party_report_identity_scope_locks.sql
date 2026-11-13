-- 第三方上报跨入口基础身份锁表（MySQL 8.0）
--
-- 目标：
-- 1. 让直接发送与 Postback Outbox 对相同四字段基础身份使用同一行锁。
-- 2. 在同一业务事务内完成锁行创建/锁定、身份查询与事件行写入。
-- 3. 仅保留独立 SHA-512 指纹，发现 SHA-256 键碰撞时 fail closed，避免锁表永久保存原始点击标识。
--
-- 生命周期：
-- - 锁行永久保留，不做 TTL、不按事件日志清理。
-- - 删除锁行可能让并发事务分别锁住不同记录，重新引入身份竞态。
-- - 本 migration 只创建锁表；应用发布必须确保旧 Worker 已停止消费，
--   旧版本代码不会自动使用该锁表。
--
-- 不修改任何既有 migration 或 manifest checksum。

CREATE TABLE IF NOT EXISTS third_party_report_identity_locks (
    identity_key CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL
        COMMENT '四字段基础事件身份 SHA-256',
    identity_fingerprint BINARY(64) NOT NULL
        COMMENT '基础身份的独立 SHA-512 指纹；不保存原始点击标识',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        COMMENT '锁行首次创建时间；锁行永久保留',
    PRIMARY KEY (identity_key)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='第三方上报跨直接发送与 Postback 的基础身份仲裁锁';

-- CREATE TABLE IF NOT EXISTS 遇到同名错误表时不会报错，因此必须核验完整物理结构。
SET @identity_lock_schema_valid = (
    (SELECT ENGINE FROM information_schema.TABLES
     WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME = 'third_party_report_identity_locks') = 'InnoDB'
    AND
    (SELECT TABLE_COLLATION FROM information_schema.TABLES
     WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME = 'third_party_report_identity_locks') = 'utf8mb4_0900_ai_ci'
    AND
    (SELECT COUNT(*) FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME = 'third_party_report_identity_locks') = 3
    AND
    EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'third_party_report_identity_locks'
          AND COLUMN_NAME = 'identity_key'
          AND COLUMN_TYPE = 'char(64)'
          AND CHARACTER_SET_NAME = 'ascii'
          AND COLLATION_NAME = 'ascii_bin'
          AND IS_NULLABLE = 'NO'
    )
    AND
    EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'third_party_report_identity_locks'
          AND COLUMN_NAME = 'identity_fingerprint'
          AND COLUMN_TYPE = 'binary(64)'
          AND IS_NULLABLE = 'NO'
    )
    AND
    EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'third_party_report_identity_locks'
          AND COLUMN_NAME = 'created_at'
          AND COLUMN_TYPE = 'datetime'
          AND IS_NULLABLE = 'NO'
          AND COLUMN_DEFAULT = 'CURRENT_TIMESTAMP'
    )
    AND
    (SELECT COUNT(*) FROM information_schema.STATISTICS
     WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME = 'third_party_report_identity_locks'
       AND INDEX_NAME = 'PRIMARY'
       AND COLUMN_NAME = 'identity_key'
       AND SEQ_IN_INDEX = 1
       AND NON_UNIQUE = 0) = 1
    AND
    (SELECT COUNT(*) FROM information_schema.STATISTICS
     WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME = 'third_party_report_identity_locks'
       AND INDEX_NAME = 'PRIMARY') = 1
);
SET @identity_lock_validation_sql = IF(
    @identity_lock_schema_valid,
    'SELECT 1',
    'SELECT * FROM __third_party_report_identity_lock_schema_mismatch__'
);
PREPARE identity_lock_validation FROM @identity_lock_validation_sql;
EXECUTE identity_lock_validation;
DEALLOCATE PREPARE identity_lock_validation;
