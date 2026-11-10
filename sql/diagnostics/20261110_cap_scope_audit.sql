-- Cap 配置范围只读审计（MySQL 8.0）
--
-- 用途：在规划 Cap Redis key 隔离/迁移前，检查历史数据是否存在非法广告主归属、
-- 重复配置、非法类型及同一 Redis 业务 key 下的 DB 计数分歧。
--
-- 安全约束：
-- 1. 本文件仅包含 SELECT，不修改数据库。
-- 2. 本审计分支和 CI 不连接生产数据库；此脚本不得由应用启动或 CI 自动执行。
-- 3. 在任何修复/迁移前，必须在备份后的隔离数据库验证结果并人工确认业务口径。
--
-- 1) advertiser_offer 必须属于 Offer 自身的 advertiser_id；
--    返回记录表示旧数据存在不合法归属，不能直接自动改写 advertiser_id。
SELECT
    c.id AS cap_id,
    c.cap_type,
    c.advertiser_id AS cap_advertiser_id,
    o.advertiser_id AS offer_advertiser_id,
    c.offer_id,
    c.publisher_id,
    c.is_active,
    c.current_daily_count,
    c.current_total_count
FROM offer_caps AS c
JOIN offers AS o ON o.id = c.offer_id
WHERE
    (c.cap_type = 'advertiser_offer'
        AND (c.advertiser_id IS NULL OR c.advertiser_id <> o.advertiser_id))
    OR (c.cap_type = 'offer' AND c.advertiser_id IS NOT NULL)
    OR c.cap_type NOT IN ('offer', 'advertiser_offer')
ORDER BY c.offer_id, c.publisher_id, c.id;

-- 2) 相同业务范围重复配置（包含 inactive 记录）。
--    offer 与 advertiser_offer 是不同配置类型，故 cap_type 参与分组。
SELECT
    c.cap_type,
    c.advertiser_id,
    c.offer_id,
    c.publisher_id,
    COUNT(*) AS duplicate_count,
    GROUP_CONCAT(c.id ORDER BY c.id) AS cap_ids,
    SUM(c.is_active = 1) AS active_count
FROM offer_caps AS c
GROUP BY
    c.cap_type,
    c.advertiser_id,
    c.offer_id,
    c.publisher_id
HAVING COUNT(*) > 1
ORDER BY c.offer_id, c.publisher_id, c.cap_type;

-- 3) 同一旧 Redis key 业务范围下，DB 计数不一致。
--    旧 key 只按 offer_id + publisher_id 生成；该结果用于判断历史计数是否已被
--    同步任务污染。不可直接取平均值或清零，需从转化明细按状态/时间重算。
SELECT
    c.offer_id,
    c.publisher_id,
    COUNT(*) AS cap_rows,
    MIN(c.current_daily_count) AS min_daily_count,
    MAX(c.current_daily_count) AS max_daily_count,
    MIN(c.current_total_count) AS min_total_count,
    MAX(c.current_total_count) AS max_total_count,
    GROUP_CONCAT(c.id ORDER BY c.id) AS cap_ids
FROM offer_caps AS c
WHERE c.is_active = 1
GROUP BY c.offer_id, c.publisher_id
HAVING
    MIN(COALESCE(c.current_daily_count, 0)) <> MAX(COALESCE(c.current_daily_count, 0))
    OR MIN(COALESCE(c.current_total_count, 0)) <> MAX(COALESCE(c.current_total_count, 0))
ORDER BY c.offer_id, c.publisher_id;

-- 4) 非法负值（正常 Cap 配置和计数均不应为负数）。
SELECT
    id AS cap_id,
    cap_type,
    offer_id,
    advertiser_id,
    publisher_id,
    daily_cap,
    total_cap,
    current_daily_count,
    current_total_count
FROM offer_caps
WHERE
    COALESCE(daily_cap, 0) < 0
    OR COALESCE(total_cap, 0) < 0
    OR COALESCE(current_daily_count, 0) < 0
    OR COALESCE(current_total_count, 0) < 0
ORDER BY id;
