-- Cap Reservation 关键表物理结构后置核验。
-- 不修改旧 migration；此版本专门阻断同名错误表绕过 IF NOT EXISTS 的情况。
-- 仅允许在隔离 MySQL CI 或经审批的发布迁移窗口执行。

SET @cap_reservation_physical_schema_valid = (
    (SELECT ENGINE FROM information_schema.TABLES
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cap_reservations') = 'InnoDB'
    AND
    (SELECT COUNT(*) FROM information_schema.STATISTICS
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cap_reservations'
       AND INDEX_NAME = 'PRIMARY') = 1
    AND
    (SELECT GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX)
     FROM information_schema.STATISTICS
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cap_reservations'
       AND INDEX_NAME = 'PRIMARY') = 'id'
    AND
    (SELECT MAX(NON_UNIQUE) FROM information_schema.STATISTICS
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cap_reservations'
       AND INDEX_NAME = 'PRIMARY') = 0
);
SET @cap_reservation_physical_validation_sql = IF(
    @cap_reservation_physical_schema_valid,
    'SELECT 1',
    'SELECT * FROM __cap_reservations_physical_schema_mismatch__'
);
PREPARE cap_reservation_physical_validation FROM @cap_reservation_physical_validation_sql;
EXECUTE cap_reservation_physical_validation;
DEALLOCATE PREPARE cap_reservation_physical_validation;
