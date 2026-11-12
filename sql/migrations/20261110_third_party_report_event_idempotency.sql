-- 第三方上报日志事件级幂等迁移（MySQL 8.0）
--
-- 目的：
-- 1. 同一 adsid 的 ViewContent 与 Purchase 必须分别留痕。
-- 2. 同一 source/adsid/event/conversion_id 的重试复用同一日志和稳定 event_id。
-- 3. 替换过宽的 unique_source_adsid 唯一约束。
--
-- 可恢复性：每个 DDL 都先检查 information_schema。脚本可在任意 DDL 边界中断后安全重跑；
-- 回填步骤只更新 event_key IS NULL 的行。若发现缺失键或碰撞，必须先人工修复数据再继续。
-- 发布约束：先在隔离 MySQL 演练；备份并审批后再发布。禁止在审计/CI 中连接生产数据库。
-- MySQL DDL 会隐式提交；本脚本可续跑，但不提供危险的自动 DROP/数据回滚。
--
-- 迁移前检查：
-- SHOW INDEX FROM third_party_report_logs;
-- SELECT COUNT(*) FROM third_party_report_logs;

-- 1. 仅当字段不存在时添加；已存在时作为 no-op。
SET @has_event_key = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'third_party_report_logs'
      AND COLUMN_NAME = 'event_key'
      AND COLUMN_TYPE = 'varchar(64)'
);
SET @ddl = IF(
    @has_event_key = 0,
    'ALTER TABLE third_party_report_logs ADD COLUMN event_key VARCHAR(64) NULL COMMENT ''事件幂等键：稳定事件身份字段的 SHA-256（ViewContent 不含后补 conversion_id）'' AFTER event',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- 2. 与 app/core/third_party_report.py 的长度前缀算法保持一致；
-- ViewContent 的后补 conversion_id 是关联元数据，不参与事件身份。
UPDATE third_party_report_logs
SET event_key = SHA2(
    CONCAT(
        CHAR_LENGTH(source), ':', source,
        CHAR_LENGTH(adsid), ':', adsid,
        CHAR_LENGTH(event), ':', event,
        CHAR_LENGTH(CASE WHEN event = 'ViewContent' THEN '' ELSE COALESCE(conversion_id, '') END), ':',
        CASE WHEN event = 'ViewContent' THEN '' ELSE COALESCE(conversion_id, '') END
    ),
    256
)
WHERE event_key IS NULL;

-- 3. 先检查无缺失值/碰撞；若有结果，停止发布并修复数据，不得强行建立唯一键。
SELECT COUNT(*) AS missing_event_keys
FROM third_party_report_logs
WHERE event_key IS NULL OR event_key = '';

SELECT event_key, COUNT(*) AS duplicate_count
FROM third_party_report_logs
GROUP BY event_key
HAVING COUNT(*) > 1;

-- 4. 可重复执行的 NOT NULL 收敛；若历史回填仍有 NULL，MySQL 会拒绝并保留可诊断状态。
ALTER TABLE third_party_report_logs
    MODIFY COLUMN event_key VARCHAR(64) NOT NULL
    COMMENT '事件幂等键：稳定事件身份字段的 SHA-256（ViewContent 不含后补 conversion_id）';

-- 5. 先建立新唯一索引，成功后才移除旧索引。
-- 若 event_key 存在重复值，新索引创建会失败，但旧唯一索引仍保留，
-- 避免迁移中断时第三方事件表暂时失去唯一性保护。
-- 必须核对唯一性、列数和列顺序。若同名索引结构错误，按“缺失”处理，
-- 后续 ADD UNIQUE INDEX 会因同名索引冲突而明确失败；绝不能因此删除旧唯一索引。
SET @has_event_unique = (
    SELECT COUNT(*)
    FROM (
        SELECT INDEX_NAME
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'third_party_report_logs'
          AND INDEX_NAME = 'unique_event_key'
        GROUP BY INDEX_NAME
        HAVING COUNT(*) = 1
           AND MAX(NON_UNIQUE) = 0
           AND MAX(SEQ_IN_INDEX) = 1
           AND MAX(SUB_PART) IS NULL
           AND MAX(COLUMN_NAME) = 'event_key'
    ) AS valid_event_index
);
SET @ddl = IF(
    @has_event_unique = 0,
    'ALTER TABLE third_party_report_logs ADD UNIQUE INDEX unique_event_key (event_key)',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- 6. 新唯一索引确认存在后，才删除旧的过宽唯一索引（若仍存在）。
SET @has_event_unique = (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'third_party_report_logs'
      AND INDEX_NAME = 'unique_event_key'
);
SET @has_old_unique = (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'third_party_report_logs'
      AND INDEX_NAME = 'unique_source_adsid'
);
-- 旧索引必须确实是原始的 UNIQUE(source, adsid) BTREE；同名错误索引不得被误删。
SET @has_old_unique_valid = (
    SELECT COUNT(*)
    FROM (
        SELECT INDEX_NAME
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'third_party_report_logs'
          AND INDEX_NAME = 'unique_source_adsid'
        GROUP BY INDEX_NAME
        HAVING COUNT(*) = 2
           AND MAX(NON_UNIQUE) = 0
           AND MAX(INDEX_TYPE) = 'BTREE'
           AND MAX(SUB_PART) IS NULL
           AND SUM(CASE WHEN COLLATION = 'A' THEN 1 ELSE 0 END) = 2
           AND GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX SEPARATOR ',') = 'source,adsid'
    ) AS valid_legacy_unique_index
);
SET @ddl = IF(
    @has_old_unique > 0 AND @has_old_unique_valid = 0,
    'SELECT * FROM __third_party_report_legacy_unique_schema_mismatch__',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
    @has_event_unique > 0 AND @has_old_unique_valid > 0,
    'ALTER TABLE third_party_report_logs DROP INDEX unique_source_adsid',
    'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- 7. 迁移后验证。
SHOW INDEX FROM third_party_report_logs;
SELECT COUNT(*) AS rows_without_event_key
FROM third_party_report_logs
WHERE event_key IS NULL OR event_key = '';
