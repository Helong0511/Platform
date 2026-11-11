-- 第三方 Postback CAPI 事务性 Outbox 扩展
-- 仅在隔离 MySQL 8.0.16+ 演练并完成备份/审批后，方可由发布流程执行。
-- 本迁移不连接或执行生产数据库；access_token 等凭据绝不写入 Outbox。
ALTER TABLE third_party_report_logs
    ADD COLUMN outbox_enqueued TINYINT(1) NOT NULL DEFAULT 0
        COMMENT '是否由转化事务创建的持久化 Outbox 事件' AFTER amount,
    ADD COLUMN short_link_id INT NULL
        COMMENT '用于恢复像素配置的短链接 ID（非外键，保留删除后的证据）' AFTER outbox_enqueued,
    ADD COLUMN cloak_name VARCHAR(100) NULL
        COMMENT '斗篷配置名称（仅配置引用）' AFTER short_link_id,
    ADD COLUMN short_code VARCHAR(100) NULL
        COMMENT '短链接短码（仅配置引用）' AFTER cloak_name,
    ADD COLUMN click_time DATETIME NULL
        COMMENT '点击发生时间，用于稳定构造 Meta event_time/fbc' AFTER short_code,
    ADD COLUMN next_retry_time DATETIME NULL
        COMMENT 'Outbox 下次可重试时间' AFTER click_time,
    ADD INDEX idx_third_party_outbox_due
        (outbox_enqueued, status, next_retry_time, report_start_time, id);
