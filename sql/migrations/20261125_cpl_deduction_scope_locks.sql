-- CPL 扣量 scope 事务锁表。
-- 锁行永久保留；删除锁行会破坏并发互斥语义。
-- 所有扣量配置写入入口必须在业务事务内先锁定 scope，再读取/修改配置。
CREATE TABLE IF NOT EXISTS conversion_deduction_scope_locks (
    scope_type VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL
        COMMENT 'advertiser/offer/publisher',
    scope_id BIGINT UNSIGNED NOT NULL COMMENT '对应业务对象主键',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (scope_type, scope_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='CPL 扣量配置跨入口事务互斥锁';

-- CREATE TABLE IF NOT EXISTS 不会校验同名旧表结构，必须检查物理定义。
SET @cpl_scope_lock_valid = (
    (SELECT ENGINE FROM information_schema.TABLES
     WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME = 'conversion_deduction_scope_locks') = 'InnoDB'
    AND
    (SELECT COUNT(*) FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME = 'conversion_deduction_scope_locks') = 3
    AND
    EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'conversion_deduction_scope_locks'
          AND COLUMN_NAME = 'scope_type'
          AND COLUMN_TYPE = 'varchar(16)'
          AND CHARACTER_SET_NAME = 'ascii'
          AND COLLATION_NAME = 'ascii_bin'
          AND IS_NULLABLE = 'NO'
    )
    AND
    EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'conversion_deduction_scope_locks'
          AND COLUMN_NAME = 'scope_id'
          AND COLUMN_TYPE = 'bigint unsigned'
          AND IS_NULLABLE = 'NO'
    )
    AND
    EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'conversion_deduction_scope_locks'
          AND COLUMN_NAME = 'created_at'
          AND COLUMN_TYPE = 'datetime(6)'
          AND IS_NULLABLE = 'NO'
    )
    AND
    (SELECT COUNT(*) FROM information_schema.STATISTICS
     WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME = 'conversion_deduction_scope_locks'
       AND INDEX_NAME = 'PRIMARY') = 2
);
SET @cpl_scope_lock_validation_sql = IF(
    @cpl_scope_lock_valid,
    'SELECT 1',
    'SELECT * FROM __cpl_deduction_scope_lock_schema_mismatch__'
);
PREPARE cpl_scope_lock_validation FROM @cpl_scope_lock_validation_sql;
EXECUTE cpl_scope_lock_validation;
DEALLOCATE PREPARE cpl_scope_lock_validation;
