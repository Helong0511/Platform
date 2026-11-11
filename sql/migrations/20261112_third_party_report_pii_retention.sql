-- 第三方上报 PII 到期清理元数据。
-- 清理任务默认关闭（THIRD_PARTY_REPORT_PII_RETENTION_DAYS=0）；必须先确定并审批适用保留期限。
-- 仅新增可追踪清理标记与扫描索引，不会在迁移时删除或改写历史数据。
ALTER TABLE third_party_report_logs
    ADD COLUMN pii_scrubbed_at DATETIME NULL
        COMMENT 'PII 按保留策略清理时间；保留事件幂等键' AFTER completed_at,
    ADD INDEX idx_third_party_pii_retention
        (pii_scrubbed_at, created_at, id);

-- 下游转发日志也持久化 URL 参数/请求体/响应体，按相同策略清理已完成且不再有待重试队列的记录。
ALTER TABLE postback_forward_logs
    ADD COLUMN pii_scrubbed_at DATETIME NULL
        COMMENT 'PII 按保留策略清理时间' AFTER completed_at,
    ADD INDEX idx_forward_log_pii_retention
        (pii_scrubbed_at, created_at, id);

