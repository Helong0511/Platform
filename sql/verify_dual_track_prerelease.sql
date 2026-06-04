-- 预发双轨验证 SQL（USE_TRACKING_TOKEN=true + PERSIST_CLICKS_TO_DB=true）
-- 用法：在 MySQL 客户端执行，替换 :click_id / :short_code 占位符

-- 1. 最近写入的 clicks（按时间倒序）
SELECT click_id, offer_id, publisher_id, short_link_id, click_time, ip
FROM clicks
ORDER BY id DESC
LIMIT 20;

-- 2. 按 click_id 查单条（替换占位符）
-- SET @click_id = 'YOUR_CLICK_ID';
SELECT *
FROM clicks
WHERE click_id = @click_id;

-- 3. 短链点击数与 Redis 队列积压（需在应用侧看 Redis；此处仅 DB）
SELECT short_code, click_count, offer_id, channel_id, updated_at
FROM short_links
WHERE short_code = @short_code;

-- 4. Postback 转化归因快照（raw_data._attribution）
SELECT id, click_id, offer_id, publisher_id, advertiser_id,
       JSON_EXTRACT(raw_data, '$._attribution') AS attribution,
       created_at
FROM postback_conversions
ORDER BY id DESC
LIMIT 20;

-- 5. 双轨：有转化但 clicks 无行（令牌归因、未落库或延迟）
SELECT pc.id, pc.click_id, pc.offer_id, pc.created_at
FROM postback_conversions pc
LEFT JOIN clicks c ON c.click_id = pc.click_id
WHERE c.id IS NULL
ORDER BY pc.id DESC
LIMIT 50;
