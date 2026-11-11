-- Cap Redis reservation 持久化账本迁移（MySQL 8.0.16+；CHECK 约束从 8.0.16 起强制执行）
--
-- 目的：
-- 1. 在 Redis INCR 前独立持久化 PREPARED，避免进程崩溃后失去预留意图。
-- 2. 保存稳定 reservation_key 与 Redis key 快照，为重复 Postback 和恢复 Worker 提供依据。
-- 3. 保留业务对象删除后的账本证据，因此本表不对 offers/publishers 建立级联外键。
--
-- 发布约束：
-- 1. 本脚本仅供正式发布流程评审；本次审计、CI 和自动化测试严禁连接或执行生产数据库。
-- 2. 先在隔离 MySQL 8.0 环境演练并检查 ORM metadata、索引和唯一约束。
-- 3. 生产发布前必须备份、审批；先执行迁移并验证，再部署写入该表的应用代码。
-- 4. MySQL DDL 会隐式提交；失败回退必须按独立回退方案执行，不能依赖事务 rollback。
-- 5. 仅增加账本表并不代表恢复机制已经启用。必须同时部署完整 ledger service、
--    Redis token 三态核验、Postback 生命周期接入和带 DB lease 的恢复 Worker。
-- 6. PREPARED/RESERVED 历史记录不得按固定时间直接删除；只有确认终态并满足保留策略后才可归档。
--
-- 重要语义：
-- - reservation_key 是事件 + Cap scope + cap_kind + Daily business_date 的 SHA-256。
-- - publisher_id 为 NULL 表示 Offer 全局渠道 scope，不能与具体 publisher_id 混淆。
-- - Daily 的 business_date 必须填写；Total 的 business_date 必须为 NULL。
-- - redis_token_key 保存完整 token key 快照，不能在恢复时根据当前配置重新推导。

CREATE TABLE IF NOT EXISTS cap_reservations (
    id INT NOT NULL AUTO_INCREMENT COMMENT '预留账本主键',
    reservation_key VARCHAR(64) NOT NULL COMMENT '稳定预留键：正式事件键与 Cap scope 的 SHA-256',
    platform VARCHAR(50) NOT NULL COMMENT 'Postback 平台',
    conversion_id VARCHAR(255) NOT NULL COMMENT '正式转化事件 ID',
    event_name VARCHAR(100) NOT NULL DEFAULT 'default' COMMENT '标准化事件名称',
    offer_id INT NOT NULL COMMENT '预留时的 Offer ID 快照',
    publisher_id INT NULL COMMENT '预留时的 Publisher ID 快照；NULL 表示全局渠道范围',
    cap_kind VARCHAR(10) NOT NULL COMMENT 'Cap 类型：daily 或 total',
    business_date DATE NULL COMMENT 'Daily 业务日期；Total 必须为 NULL',
    redis_counter_key VARCHAR(255) NOT NULL COMMENT 'Redis 计数器 Key 快照',
    redis_token_key VARCHAR(512) NOT NULL COMMENT 'Redis reservation token Key 快照',
    redis_reserved BOOLEAN NOT NULL DEFAULT FALSE COMMENT '是否确认 Redis Lua 已成功预留；区分 fail-open 无 token 路径',
    redis_token_cleaned BOOLEAN NOT NULL DEFAULT FALSE COMMENT '终态后是否已清理 Redis token；清理失败由恢复任务重试',
    state VARCHAR(24) NOT NULL DEFAULT 'PREPARED'
        COMMENT 'PREPARED/RESERVED/COMMITTED/ROLLED_BACK/NEEDS_RECONCILIATION',
    attempts INT NOT NULL DEFAULT 0 COMMENT '恢复尝试次数',
    lease_owner VARCHAR(64) NULL COMMENT '恢复 Worker 租约持有者',
    lease_expires_at DATETIME NULL COMMENT '恢复 Worker 租约到期时间',
    last_error TEXT NULL COMMENT '最近一次恢复错误摘要',
    prepared_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'PREPARED 创建时间',
    reserved_at DATETIME NULL COMMENT 'Redis 预留确认时间',
    finalized_at DATETIME NULL COMMENT '终态确认时间',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uq_cap_reservation_key (reservation_key),
    KEY idx_cap_reservation_state_updated (state, updated_at),
    KEY idx_cap_reservation_lease (state, lease_expires_at),
    KEY idx_cap_reservation_event (platform, conversion_id, event_name),
    KEY idx_cap_reservation_scope (offer_id, publisher_id, cap_kind, business_date),
    CONSTRAINT chk_cap_reservation_key_sha256 CHECK (LENGTH(reservation_key) = 64),
    CONSTRAINT chk_cap_reservation_offer_positive CHECK (offer_id > 0),
    CONSTRAINT chk_cap_reservation_publisher_positive CHECK (publisher_id IS NULL OR publisher_id > 0),
    CONSTRAINT chk_cap_reservation_attempts_nonnegative CHECK (attempts >= 0),
    CONSTRAINT chk_cap_reservation_kind_date CHECK (
        (cap_kind = 'daily' AND business_date IS NOT NULL) OR
        (cap_kind = 'total' AND business_date IS NULL)
    ),
    CONSTRAINT chk_cap_reservation_state CHECK (
        state IN ('PREPARED', 'RESERVED', 'COMMITTED', 'ROLLED_BACK', 'NEEDS_RECONCILIATION')
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Cap Redis 预留持久化账本';

-- 迁移后人工核验（仅隔离环境或正式发布审批窗口执行）：
-- SHOW CREATE TABLE cap_reservations;
-- SHOW INDEX FROM cap_reservations;
-- SELECT COUNT(*) FROM cap_reservations;
