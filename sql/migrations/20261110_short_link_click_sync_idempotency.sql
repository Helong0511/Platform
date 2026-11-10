-- 短链接点击刷盘幂等账本迁移（MySQL 8.0）
--
-- 目的：通过 Redis pending batch + DB 唯一 batch_id，保证 DB COMMIT 响应丢失、
-- 进程在提交后崩溃、Redis ACK 失败时，重试不会重复增加 short_links.click_count。
--
-- 发布顺序：
-- 1. 先在隔离数据库演练；本审计和 CI 禁止连接/执行生产数据库。
-- 2. 生产发布前备份并审批，先执行本迁移，再部署依赖该表的新应用代码。
-- 3. 未执行迁移前禁止部署新应用版本。
-- 4. acknowledged_at 仅在 Redis pending key 删除得到确认后写入；未确认账本记录不可清理。
-- 5. MySQL DDL 隐式提交，回滚需按独立方案处理。
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
