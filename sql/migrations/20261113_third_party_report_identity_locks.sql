-- 第三方上报跨入口基础身份锁表（MySQL 8.0）
--
-- 目标：
-- 1. 让直接发送与 Postback Outbox 对相同四字段基础身份使用同一行锁。
-- 2. 在同一业务事务内完成锁行创建/锁定、身份查询与事件行写入。
-- 3. 保留规范化完整身份值，发现 SHA-256 键碰撞时 fail closed。
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
    identity_value VARBINARY(4096) NOT NULL
        COMMENT '长度前缀编码的完整 UTF-8 基础身份，用于碰撞核验',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        COMMENT '锁行首次创建时间；锁行永久保留',
    PRIMARY KEY (identity_key)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='第三方上报跨直接发送与 Postback 的基础身份仲裁锁';
