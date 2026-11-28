-- 为 receipt-only Pending 阻断审计增加明确结果枚举，兼容 Web/IP/Telegram 入口。
-- 仅扩展 CHECK 白名单，不修改既有审计记录。
ALTER TABLE `telegram_postback_approval_audits`
    DROP CHECK `chk_tg_postback_audit_outcome`,
    ADD CONSTRAINT `chk_tg_postback_audit_outcome`
        CHECK (`outcome` IN (
            'approved',
            'rejected',
            'already_exists',
            'denied',
            'not_found',
            'already_processed',
            'duplicate_callback',
            'event_receipt_exists'
        ));
