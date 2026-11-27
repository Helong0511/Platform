-- Offer 上游 PO 与所有渠道下游 PO 使用同一币种，未配置时明确兜底 USD。
-- INSTANT 仅新增元数据列，不重写历史财务金额。
ALTER TABLE offers
    ADD COLUMN payout_currency VARCHAR(3) NOT NULL DEFAULT 'USD'
        COMMENT 'Offer 上游 PO 与全部渠道下游 PO 共用的 ISO 4217 币种',
    ADD COLUMN payout_currency_source VARCHAR(100) NOT NULL DEFAULT 'system_fallback_usd'
        COMMENT 'Offer PO 币种来源归因',
    ALGORITHM=INSTANT;

-- 同一迁移内标记所有存量 Offer：USD 是新数据兜底，不是历史 PO 币种证据。
-- systemd 发布链路在迁移期间停止业务 Worker，避免新建 Offer 与历史标记交错。
UPDATE offers
SET payout_currency_source = 'legacy_unknown';
