-- 检查广告数据是否有对应的产品分配记录
-- 这个查询可以帮助诊断为什么查询不到数据

-- 1. 检查 ad_data 表中的数据总数
SELECT 
    COUNT(*) AS ad_data总数,
    COUNT(DISTINCT product_id) AS 不同产品数,
    MIN(DATE(date)) AS 最早日期,
    MAX(DATE(date)) AS 最新日期
FROM ad_data;

-- 2. 检查 product_assignments 表中的数据总数
SELECT 
    COUNT(*) AS 分配记录总数,
    COUNT(DISTINCT product_id) AS 不同产品数,
    MIN(start_date) AS 最早开始日期,
    MAX(COALESCE(end_date, '2099-12-31')) AS 最晚结束日期
FROM product_assignments;

-- 3. 检查哪些 ad_data 记录没有对应的 product_assignments 记录
-- 这个查询会显示没有分配记录的数据
SELECT 
    ad.id AS ad_data_id,
    ad.date AS 数据日期,
    ad.product_id AS 产品ID,
    p.name AS 产品名称,
    p.is_active AS 产品是否激活,
    CASE 
        WHEN pa.id IS NULL THEN '没有分配记录'
        ELSE '有分配记录'
    END AS 分配状态
FROM ad_data ad
LEFT JOIN products p ON ad.product_id = p.id
LEFT JOIN product_assignments pa ON (
    pa.product_id = ad.product_id
    AND ad.date >= pa.start_date
    AND (pa.end_date IS NULL OR ad.date < DATE_ADD(pa.end_date, INTERVAL 1 DAY))
)
WHERE pa.id IS NULL  -- 只显示没有分配记录的数据
LIMIT 100;

-- 4. 检查当前月的数据是否有分配记录
SELECT 
    COUNT(*) AS 当前月数据总数,
    COUNT(pa.id) AS 有分配记录的数量,
    COUNT(*) - COUNT(pa.id) AS 没有分配记录的数量
FROM ad_data ad
LEFT JOIN products p ON ad.product_id = p.id
LEFT JOIN product_assignments pa ON (
    pa.product_id = ad.product_id
    AND ad.date >= pa.start_date
    AND (pa.end_date IS NULL OR ad.date < DATE_ADD(pa.end_date, INTERVAL 1 DAY))
)
WHERE DATE(ad.date) >= DATE_FORMAT(NOW(), '%Y-%m-01')
  AND DATE(ad.date) <= LAST_DAY(NOW())
  AND p.is_active = 1;

-- 5. 检查激活的产品是否有数据但没有分配记录
SELECT 
    p.id AS 产品ID,
    p.name AS 产品名称,
    p.is_active AS 是否激活,
    COUNT(ad.id) AS 数据记录数,
    COUNT(pa.id) AS 分配记录数,
    CASE 
        WHEN COUNT(ad.id) > 0 AND COUNT(pa.id) = 0 THEN '有数据但没有分配记录'
        WHEN COUNT(ad.id) = 0 THEN '没有数据'
        ELSE '正常'
    END AS 状态
FROM products p
LEFT JOIN ad_data ad ON p.id = ad.product_id
LEFT JOIN product_assignments pa ON (
    pa.product_id = p.id
    AND ad.date >= pa.start_date
    AND (pa.end_date IS NULL OR ad.date < DATE_ADD(pa.end_date, INTERVAL 1 DAY))
)
WHERE p.is_active = 1
GROUP BY p.id, p.name, p.is_active
HAVING COUNT(ad.id) > 0 AND COUNT(pa.id) = 0
ORDER BY 数据记录数 DESC;

