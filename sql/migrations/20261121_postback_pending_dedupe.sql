-- 为待审批 Postback 新记录增加唯一幂等键；历史记录保持 NULL，不修改既有业务数据。
-- MySQL UNIQUE 索引允许多条 NULL，因此只约束新入队记录。
ALTER TABLE `pending_postback_conversions`
    ADD COLUMN `dedupe_key` VARCHAR(64) NULL
        COMMENT '待审批入队幂等键（SHA-256）' AFTER `request_ip`,
    ADD UNIQUE KEY `uq_pending_postback_dedupe_key` (`dedupe_key`);
