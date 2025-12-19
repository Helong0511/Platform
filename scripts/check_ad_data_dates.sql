-- 检查广告数据表中的日期范围
-- 查看所有数据的日期范围
SELECT 
    MIN(DATE(date)) AS 最早日期,
    MAX(DATE(date)) AS 最新日期,
    COUNT(*) AS 总记录数,
    COUNT(DISTINCT DATE(date)) AS 不同日期数
FROM ad_data;

-- 查看每个月的记录数
SELECT 
    DATE_FORMAT(date, '%Y-%m') AS 年月,
    COUNT(*) AS 记录数,
    MIN(DATE(date)) AS 该月最早日期,
    MAX(DATE(date)) AS 该月最晚日期
FROM ad_data
GROUP BY DATE_FORMAT(date, '%Y-%m')
ORDER BY 年月 DESC
LIMIT 12;

-- 查看当前月的数据
SELECT 
    COUNT(*) AS 当前月记录数
FROM ad_data
WHERE DATE(date) >= DATE_FORMAT(NOW(), '%Y-%m-01')
  AND DATE(date) <= LAST_DAY(NOW());

-- 查看最近30天的数据
SELECT 
    COUNT(*) AS 最近30天记录数
FROM ad_data
WHERE DATE(date) >= DATE_SUB(CURDATE(), INTERVAL 30 DAY);

-- 查看产品状态（只显示激活的产品）
SELECT 
    p.id AS 产品ID,
    p.name AS 产品名称,
    p.is_active AS 是否激活,
    COUNT(ad.id) AS 数据记录数,
    MIN(DATE(ad.date)) AS 最早日期,
    MAX(DATE(ad.date)) AS 最新日期
FROM products p
LEFT JOIN ad_data ad ON p.id = ad.product_id
WHERE p.is_active = 1
GROUP BY p.id, p.name, p.is_active
ORDER BY 数据记录数 DESC
LIMIT 20;

