-- 对齐 ConversionDeductionLog.conversion_id ORM 外键与生产数据库结构。
-- 安全策略：先检查字段范围、孤儿引用和现有外键；发现不一致即失败，不自动丢弃或改写业务数据。
-- 可重复执行：字段已为 INT 且正确外键已存在时不做破坏性变更。

-- ORM 的 ConversionDeductionLog.id 为有符号 Integer；基线旧 DDL 曾使用 BIGINT。
-- 收窄主键前必须确认范围、AUTO_INCREMENT/NOT NULL 属性和不存在外部引用。
SET @cdl_log_id_column_type = (
    SELECT COLUMN_TYPE
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'conversion_deduction_logs'
      AND COLUMN_NAME = 'id'
    LIMIT 1
);
SET @cdl_log_id_nullable = (
    SELECT IS_NULLABLE
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'conversion_deduction_logs'
      AND COLUMN_NAME = 'id'
    LIMIT 1
);
SET @cdl_log_id_extra = (
    SELECT EXTRA
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'conversion_deduction_logs'
      AND COLUMN_NAME = 'id'
    LIMIT 1
);
SET @cdl_log_id_external_fk_count = (
    SELECT COUNT(*)
    FROM information_schema.KEY_COLUMN_USAGE
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND REFERENCED_TABLE_NAME = 'conversion_deduction_logs'
      AND REFERENCED_COLUMN_NAME = 'id'
);
SET @cdl_log_id_type_check_sql = IF(
    @cdl_log_id_column_type IS NULL
    OR @cdl_log_id_column_type NOT IN ('int', 'bigint')
    OR @cdl_log_id_nullable <> 'NO'
    OR @cdl_log_id_extra NOT LIKE '%auto_increment%'
    OR (@cdl_log_id_column_type = 'bigint' AND @cdl_log_id_external_fk_count > 0),
    'SELECT * FROM __cdl_log_primary_key_definition_mismatch__',
    'SELECT 1'
);
PREPARE cdl_log_id_type_check FROM @cdl_log_id_type_check_sql;
EXECUTE cdl_log_id_type_check;
DEALLOCATE PREPARE cdl_log_id_type_check;

SET @cdl_log_id_overflow_count = (
    SELECT COUNT(*)
    FROM conversion_deduction_logs
    WHERE id > 2147483647 OR id < -2147483648
);
SET @cdl_log_id_overflow_check_sql = IF(
    @cdl_log_id_overflow_count = 0,
    'SELECT 1',
    'SELECT * FROM __cdl_log_primary_key_out_of_int_range__'
);
PREPARE cdl_log_id_overflow_check FROM @cdl_log_id_overflow_check_sql;
EXECUTE cdl_log_id_overflow_check;
DEALLOCATE PREPARE cdl_log_id_overflow_check;

SET @cdl_log_id_alter_sql = IF(
    @cdl_log_id_column_type = 'bigint',
    'ALTER TABLE conversion_deduction_logs MODIFY COLUMN id INT NOT NULL AUTO_INCREMENT COMMENT ''记录ID''',
    'SELECT 1'
);
PREPARE cdl_log_id_alter FROM @cdl_log_id_alter_sql;
EXECUTE cdl_log_id_alter;
DEALLOCATE PREPARE cdl_log_id_alter;

SET @cdl_conversion_column_type = (
    SELECT COLUMN_TYPE
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'conversion_deduction_logs'
      AND COLUMN_NAME = 'conversion_id'
    LIMIT 1
);
SET @cdl_postback_column_type = (
    SELECT COLUMN_TYPE
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'postback_conversions'
      AND COLUMN_NAME = 'id'
    LIMIT 1
);
SET @cdl_conversion_nullable = (
    SELECT IS_NULLABLE
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'conversion_deduction_logs'
      AND COLUMN_NAME = 'conversion_id'
    LIMIT 1
);
SET @cdl_any_fk_count = (
    SELECT COUNT(*)
    FROM information_schema.KEY_COLUMN_USAGE
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'conversion_deduction_logs'
      AND COLUMN_NAME = 'conversion_id'
      AND REFERENCED_TABLE_NAME IS NOT NULL
);

-- 使用 COLUMN_TYPE 检查 signed/unsigned；父列必须是 ORM 对应的有符号 INT。
SET @cdl_type_check_sql = IF(
    @cdl_conversion_column_type IS NULL
    OR @cdl_postback_column_type IS NULL
    OR @cdl_postback_column_type <> 'int'
    OR @cdl_conversion_column_type NOT IN ('int', 'bigint')
    OR @cdl_conversion_nullable <> 'YES'
    OR (@cdl_conversion_column_type = 'bigint' AND @cdl_any_fk_count > 0),
    'SELECT * FROM __cdl_conversion_fk_column_type_mismatch__',
    'SELECT 1'
);
PREPARE cdl_type_check FROM @cdl_type_check_sql;
EXECUTE cdl_type_check;
DEALLOCATE PREPARE cdl_type_check;

-- BIGINT 收窄为 INT 前必须证明所有非 NULL 引用都在有符号 INT 范围内。
SET @cdl_overflow_count = (
    SELECT COUNT(*)
    FROM conversion_deduction_logs
    WHERE conversion_id > 2147483647 OR conversion_id < -2147483648
);
SET @cdl_overflow_check_sql = IF(
    @cdl_overflow_count = 0,
    'SELECT 1',
    'SELECT * FROM __cdl_conversion_id_out_of_int_range__'
);
PREPARE cdl_overflow_check FROM @cdl_overflow_check_sql;
EXECUTE cdl_overflow_check;
DEALLOCATE PREPARE cdl_overflow_check;

-- 不允许在存在孤儿引用时建立约束；输出数量供运维先行核对和修复。
SET @cdl_orphan_count = (
    SELECT COUNT(*)
    FROM conversion_deduction_logs cdl
    LEFT JOIN postback_conversions pc ON pc.id = cdl.conversion_id
    WHERE cdl.conversion_id IS NOT NULL AND pc.id IS NULL
);
SET @cdl_orphan_check_sql = IF(
    @cdl_orphan_count = 0,
    'SELECT 1',
    'SELECT * FROM __cdl_conversion_id_orphan_rows__'
);
PREPARE cdl_orphan_check FROM @cdl_orphan_check_sql;
EXECUTE cdl_orphan_check;
DEALLOCATE PREPARE cdl_orphan_check;

SET @cdl_alter_type_sql = IF(
    @cdl_conversion_column_type = 'bigint',
    'ALTER TABLE conversion_deduction_logs MODIFY COLUMN conversion_id INT NULL DEFAULT NULL COMMENT ''转化记录ID（关联postback_conversions.id，可为NULL因为扣量的转化可能不保存）''',
    'SELECT 1'
);
PREPARE cdl_alter_type FROM @cdl_alter_type_sql;
EXECUTE cdl_alter_type;
DEALLOCATE PREPARE cdl_alter_type;

SET @cdl_fk_count = (
    SELECT COUNT(*)
    FROM information_schema.KEY_COLUMN_USAGE k
    JOIN information_schema.REFERENTIAL_CONSTRAINTS r
      ON r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA
     AND r.CONSTRAINT_NAME = k.CONSTRAINT_NAME
     AND r.TABLE_NAME = k.TABLE_NAME
    WHERE k.CONSTRAINT_SCHEMA = DATABASE()
      AND k.TABLE_NAME = 'conversion_deduction_logs'
      AND k.COLUMN_NAME = 'conversion_id'
      AND k.REFERENCED_TABLE_NAME = 'postback_conversions'
      AND k.REFERENCED_COLUMN_NAME = 'id'
      AND r.DELETE_RULE = 'SET NULL'
      AND r.UPDATE_RULE = 'RESTRICT'
);
SET @cdl_fk_sql = IF(
    @cdl_fk_count = 1,
    'SELECT 1',
    IF(
        @cdl_any_fk_count = 0,
        'ALTER TABLE conversion_deduction_logs ADD CONSTRAINT fk_cdl_postback_conversion FOREIGN KEY (conversion_id) REFERENCES postback_conversions(id) ON DELETE SET NULL ON UPDATE RESTRICT',
        'SELECT * FROM __cdl_conversion_fk_rule_mismatch__'
    )
);
PREPARE cdl_fk_stmt FROM @cdl_fk_sql;
EXECUTE cdl_fk_stmt;
DEALLOCATE PREPARE cdl_fk_stmt;

-- 最终验收：字段类型与 FK 规则必须匹配。
SET @cdl_final_ok = (
    SELECT COUNT(*)
    FROM information_schema.KEY_COLUMN_USAGE k
    JOIN information_schema.REFERENTIAL_CONSTRAINTS r
      ON r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA
     AND r.CONSTRAINT_NAME = k.CONSTRAINT_NAME
     AND r.TABLE_NAME = k.TABLE_NAME
    JOIN information_schema.COLUMNS c
      ON c.TABLE_SCHEMA = k.CONSTRAINT_SCHEMA
     AND c.TABLE_NAME = k.TABLE_NAME
     AND c.COLUMN_NAME = k.COLUMN_NAME
    JOIN information_schema.COLUMNS p
      ON p.TABLE_SCHEMA = k.REFERENCED_TABLE_SCHEMA
     AND p.TABLE_NAME = k.REFERENCED_TABLE_NAME
     AND p.COLUMN_NAME = k.REFERENCED_COLUMN_NAME
    WHERE k.CONSTRAINT_SCHEMA = DATABASE()
      AND k.TABLE_NAME = 'conversion_deduction_logs'
      AND k.COLUMN_NAME = 'conversion_id'
      AND k.REFERENCED_TABLE_NAME = 'postback_conversions'
      AND k.REFERENCED_COLUMN_NAME = 'id'
      AND r.DELETE_RULE = 'SET NULL'
      AND r.UPDATE_RULE = 'RESTRICT'
      AND c.DATA_TYPE = 'int'
      AND p.DATA_TYPE = 'int'
);
SET @cdl_final_sql = IF(
    @cdl_final_ok = 1,
    'SELECT 1',
    'SELECT * FROM __cdl_conversion_fk_final_validation_failed__'
);
PREPARE cdl_final_check FROM @cdl_final_sql;
EXECUTE cdl_final_check;
DEALLOCATE PREPARE cdl_final_check;
