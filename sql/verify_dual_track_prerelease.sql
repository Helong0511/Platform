-- 预发双轨验证用 SQL（USE_TRACKING_TOKEN=true + PERSIST_CLICKS_TO_DB=true）
-- clicks 表无 short_code 字段，短码在 short_links.short_code，关联字段为 clicks.short_link_id

-- 1) 最近 clicks 是否增长（令牌模式下仍应写库）
SELECT id, click_id, offer_id, publisher_id, advertiser_id, short_link_id, click_time
FROM clicks
ORDER BY id DESC
LIMIT 10;

-- 1b) 同上，并带出短链接代码（联表）
SELECT
  c.id,
  c.click_id,
  c.offer_id,
  c.publisher_id,
  c.short_link_id,
  s.short_code,
  c.click_time
FROM clicks c
LEFT JOIN short_links s ON s.id = c.short_link_id
ORDER BY c.id DESC
LIMIT 10;

-- 2) 指定 click_id 是否在 clicks 表（把下面字符串换成实测 click_id）
SELECT id, click_id, offer_id, publisher_id, short_link_id, click_time
FROM clicks
WHERE click_id = '替换为你的测试click_id'
LIMIT 5;

-- 3) 转化归因快照列（postback_conversions）
SELECT id, conversion_id, click_id, offer_id, publisher_id, advertiser_id, click_time, created_at
FROM postback_conversions
ORDER BY id DESC
LIMIT 10;

-- 4) 指定 click_id 的转化是否带齐快照
-- SELECT id, click_id, offer_id, publisher_id, advertiser_id, click_time
-- FROM postback_conversions
-- WHERE click_id = '替换为你的测试click_id'
-- ORDER BY id DESC LIMIT 5;

-- 5) raw_data 内 _attribution（可选，新转化应有）
-- SELECT id, conversion_id,
--   JSON_EXTRACT(raw_data, '$._attribution.offer_id') AS attr_offer,
--   JSON_EXTRACT(raw_data, '$._attribution.publisher_id') AS attr_pub
-- FROM postback_conversions
-- WHERE click_id = '替换为你的测试click_id'
-- ORDER BY id DESC LIMIT 5;
