-- Cap Reservation reservation_key 必须是小写 64 位 SHA-256 十六进制字符串。
-- 旧迁移保持不变；此迁移为历史已创建表补充严格 CHECK，并校验同名约束定义。
-- MySQL 8.0.16+ 强制执行 CHECK；使用二进制 collation 和 case-sensitive 模式拒绝大写字符。

SET @cap_reservation_hex_check_count = (
    SELECT COUNT(*)
    FROM information_schema.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'cap_reservations'
      AND CONSTRAINT_TYPE = 'CHECK'
      AND CONSTRAINT_NAME = 'chk_cap_reservation_key_hex'
);
SET @cap_reservation_hex_check_clause = (
    SELECT CHECK_CLAUSE
    FROM information_schema.CHECK_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND CONSTRAINT_NAME = 'chk_cap_reservation_key_hex'
    LIMIT 1
);
SET @cap_reservation_hex_migration_sql = CASE
    WHEN @cap_reservation_hex_check_count = 0 THEN
        'ALTER TABLE cap_reservations ADD CONSTRAINT chk_cap_reservation_key_hex CHECK (REGEXP_LIKE(reservation_key COLLATE utf8mb4_bin, ''^[0-9a-f]{64}$'', ''c''))'
    WHEN @cap_reservation_hex_check_count = 1
         AND LOWER(@cap_reservation_hex_check_clause) LIKE '%regexp_like%'
         AND @cap_reservation_hex_check_clause LIKE '%[0-9a-f]%'
         AND @cap_reservation_hex_check_clause LIKE '%{64}%'
         AND LOWER(@cap_reservation_hex_check_clause) LIKE '%utf8mb4_bin%'
        THEN 'SELECT 1'
    ELSE
        'SELECT * FROM __cap_reservation_hex_check_mismatch__'
END;
PREPARE cap_reservation_hex_check_migration FROM @cap_reservation_hex_migration_sql;
EXECUTE cap_reservation_hex_check_migration;
DEALLOCATE PREPARE cap_reservation_hex_check_migration;

-- 再次读取实际约束，避免 ALTER 未生效或同名错误定义被误认为成功。
SET @cap_reservation_hex_check_valid = (
    SELECT COUNT(*) = 1
       AND LOWER(MAX(CHECK_CLAUSE)) LIKE '%regexp_like%'
       AND MAX(CHECK_CLAUSE) LIKE '%[0-9a-f]%'
       AND MAX(CHECK_CLAUSE) LIKE '%{64}%'
       AND LOWER(MAX(CHECK_CLAUSE)) LIKE '%utf8mb4_bin%'
    FROM information_schema.CHECK_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND CONSTRAINT_NAME = 'chk_cap_reservation_key_hex'
);
SET @cap_reservation_hex_postcondition_sql = IF(
    @cap_reservation_hex_check_valid,
    'SELECT 1',
    'SELECT * FROM __cap_reservation_hex_postcondition_failed__'
);
PREPARE cap_reservation_hex_postcondition FROM @cap_reservation_hex_postcondition_sql;
EXECUTE cap_reservation_hex_postcondition;
DEALLOCATE PREPARE cap_reservation_hex_postcondition;
