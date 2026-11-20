-- Telegram/Web Postback 审批审计事件；不依赖业务记录外键，保留长期审计轨迹。
CREATE TABLE `telegram_postback_approval_audits` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `pending_conversion_id` INT NULL COMMENT '待确认转化记录 ID；不设外键',
    `conversion_id` INT NULL COMMENT '正式转化记录 ID；不设外键',
    `actor_type` VARCHAR(20) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '操作者类型：telegram/system_user/system',
    `actor_id` VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '操作者 ID；Telegram User ID 独立存储',
    `source` VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '操作来源：telegram/web/ip_whitelist',
    `action` VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '动作：approve/reject/auto_approve',
    `outcome` VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '结果：approved/rejected/already_exists/denied/not_found',
    `previous_status` VARCHAR(20) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '操作前状态',
    `new_status` VARCHAR(20) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '操作后状态',
    `telegram_callback_query_id` VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT 'Telegram 回调唯一 ID',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '审计事件时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_tg_postback_approval_callback` (`telegram_callback_query_id`),
    KEY `idx_tg_postback_audit_pending_created` (`pending_conversion_id`, `created_at`),
    KEY `idx_tg_postback_audit_actor_created` (`actor_type`, `actor_id`, `created_at`),
    KEY `idx_tg_postback_audit_action_outcome_created` (`action`, `outcome`, `created_at`),
    CONSTRAINT `chk_tg_postback_audit_actor_type`
        CHECK (`actor_type` IN ('telegram', 'system_user', 'system')),
    CONSTRAINT `chk_tg_postback_audit_source`
        CHECK (`source` IN ('telegram', 'web', 'ip_whitelist')),
    CONSTRAINT `chk_tg_postback_audit_action`
        CHECK (`action` IN ('approve', 'reject', 'auto_approve')),
    CONSTRAINT `chk_tg_postback_audit_outcome`
        CHECK (`outcome` IN ('approved', 'rejected', 'already_exists', 'denied', 'not_found'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
COMMENT='Telegram/Web Postback 待确认审批不可变审计事件';
