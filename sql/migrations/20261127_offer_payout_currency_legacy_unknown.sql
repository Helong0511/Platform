-- 新增币种列后，历史 Offer 原 PO 币种无可信来源；不得将默认 USD 当作历史事实。
-- 仅把尚处于系统兜底状态的存量行标记为 legacy_unknown；不改写 payout 金额。
UPDATE offers
SET payout_currency_source = 'legacy_unknown'
WHERE payout_currency_source = 'system_fallback_usd';
