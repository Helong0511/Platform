-- 短链接点击刷盘幂等账本迁移（MySQL 8.0）
--
-- 目的：通过 Redis pending batch / DB fallback event + 唯一 batch_id，保证 DB COMMIT
-- 响应丢失、进程在提交后崩溃、Redis ACK 失败时，重试不会重复增加 short_links.click_count。
--
-- 发布顺序：
-- 1. 先在隔离数据库演练；本审计和 CI 禁止连接/执行生产数据库。
-- 2. 生产发布前备份并审批，先执行本迁移，再部署依赖该表的新应用代码。
-- 3. 未执行迁移前禁止部署新应用版本。
-- 4. Redis pending batch 仅在 pending key 删除得到确认后写入 acknowledged_at；DB fallback event 在点击计数与账本同一事务提交时标记 acknowledged。未确认的 pending batch 不可按时间清理。
-- 5. MySQL DDL 隐式提交，回滚需按独立方案处理。
-- 6. 部署前检查每个旧应用节点的 tempfile.gettempdir()/click_counters.json。
--    旧快照没有稳定 batch_id，且可能包含 DB COMMIT 响应不确定的记录；
--    新代码会保留并告警，不会自动重放。必须人工核对后归档，禁止直接累加入库。
CREATE TABLE IF NOT EXISTS short_link_click_sync_batches (
    batch_id VARCHAR(64) NOT NULL COMMENT 'Redis pending batch UUID',
    short_code VARCHAR(20) NOT NULL COMMENT '短链接代码',
    click_count INT NOT NULL COMMENT '本批次待入账点击数',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    acknowledged_at DATETIME NULL COMMENT 'Redis pending key 确认删除时间',
    PRIMARY KEY (batch_id),
    KEY idx_short_click_batch_code_created (short_code, created_at),
    KEY idx_short_click_batch_ack_created (acknowledged_at, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='短链接点击刷盘幂等账本';

-- CREATE TABLE IF NOT EXISTS 不会修复同名错误表；验证字段、默认值、字符集与索引。
-- 结构不匹配时 fail-closed，不自动 DROP/ALTER，避免误伤旧账本数据。
SET @short_click_batch_schema_valid = (
    SELECT
        (SELECT COUNT(*) FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'short_link_click_sync_batches') = 5
        AND (SELECT COUNT(*) FROM information_schema.COLUMNS
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'short_link_click_sync_batches'
               AND COLUMN_NAME = 'batch_id' AND COLUMN_TYPE = 'varchar(64)' AND IS_NULLABLE = 'NO') = 1
        AND (SELECT COUNT(*) FROM information_schema.COLUMNS
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'short_link_click_sync_batches'
               AND COLUMN_NAME = 'short_code' AND COLUMN_TYPE = 'varchar(20)' AND IS_NULLABLE = 'NO') = 1
        AND (SELECT COUNT(*) FROM information_schema.COLUMNS
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'short_link_click_sync_batches'
               AND COLUMN_NAME = 'click_count' AND COLUMN_TYPE = 'int' AND IS_NULLABLE = 'NO') = 1
        AND (SELECT COUNT(*) FROM information_schema.COLUMNS
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'short_link_click_sync_batches'
               AND COLUMN_NAME = 'created_at' AND COLUMN_TYPE = 'datetime' AND IS_NULLABLE = 'NO') = 1
        AND (SELECT COUNT(*) FROM information_schema.COLUMNS
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'short_link_click_sync_batches'
               AND COLUMN_NAME = 'acknowledged_at' AND COLUMN_TYPE = 'datetime' AND IS_NULLABLE = 'YES') = 1
        AND (SELECT COLUMN_DEFAULT FROM information_schema.COLUMNS
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'short_link_click_sync_batches'
               AND COLUMN_NAME = 'created_at') = 'CURRENT_TIMESTAMP'
        AND (SELECT TABLE_COLLATION FROM information_schema.TABLES
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'short_link_click_sync_batches') = 'utf8mb4_unicode_ci'
        AND (SELECT COUNT(*) FROM information_schema.STATISTICS
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'short_link_click_sync_batches') = 5
        AND (SELECT COUNT(DISTINCT INDEX_NAME) FROM information_schema.STATISTICS
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'short_link_click_sync_batches') = 3
        AND (SELECT COUNT(*) FROM information_schema.STATISTICS
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'short_link_click_sync_batches'
               AND SUB_PART IS NOT NULL) = 0
        AND (SELECT COUNT(*) FROM information_schema.STATISTICS
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'short_link_click_sync_batches'
               AND INDEX_TYPE <> 'BTREE') = 0
        AND (SELECT MAX(NON_UNIQUE) FROM information_schema.STATISTICS
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'short_link_click_sync_batches'
               AND INDEX_NAME = 'PRIMARY') = 0
        AND (SELECT COUNT(*) FROM information_schema.STATISTICS
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'short_link_click_sync_batches'
               AND INDEX_NAME <> 'PRIMARY' AND NON_UNIQUE <> 1) = 0
        AND (SELECT GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX)
             FROM information_schema.STATISTICS
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'short_link_click_sync_batches'
               AND INDEX_NAME = 'PRIMARY') = 'batch_id'
        AND (SELECT GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX)
             FROM information_schema.STATISTICS
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'short_link_click_sync_batches'
               AND INDEX_NAME = 'idx_short_click_batch_code_created') = 'short_code,created_at'
        AND (SELECT GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX)
             FROM information_schema.STATISTICS
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'short_link_click_sync_batches'
               AND INDEX_NAME = 'idx_short_click_batch_ack_created') = 'acknowledged_at,created_at'
);
SET @short_click_batch_validation_sql = IF(
    @short_click_batch_schema_valid,
    'SELECT 1',
    'SELECT * FROM __short_link_click_sync_batches_schema_mismatch__'
);
PREPARE short_click_batch_schema_validation FROM @short_click_batch_validation_sql;
EXECUTE short_click_batch_schema_validation;
DEALLOCATE PREPARE short_click_batch_schema_validation;
