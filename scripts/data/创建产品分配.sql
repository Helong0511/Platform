-- 为没有历史分配记录的产品创建分配记录
-- 使用数据的最早日期作为分配开始日期
-- 同时检查 ad_data 和 tb_search_data 两个表

USE platform;

-- 为所有没有分配记录的产品创建分配记录
-- 使用 ad_data 和 tb_search_data 两个表中最早的数据日期作为 start_date
INSERT INTO product_assignments (product_id, client_id, start_date, end_date, created_at, updated_at)
SELECT 
    product_data.product_id,
    product_data.client_id,
    product_data.min_date AS start_date,
    NULL AS end_date,  -- NULL 表示当前有效
    NOW() AS created_at,
    NOW() AS updated_at
FROM (
    -- 合并 ad_data 和 tb_search_data 两个表的数据，找出每个产品的最早日期
    SELECT 
        product_id,
        client_id,
        MIN(min_date) AS min_date
    FROM (
        -- 从 ad_data 表获取数据
        SELECT 
            p.id AS product_id,
            p.client_id,
            MIN(DATE(ad.date)) AS min_date
        FROM products p
        INNER JOIN ad_data ad ON p.id = ad.product_id
        WHERE p.is_active = 1
          AND p.client_id IS NOT NULL
        GROUP BY p.id, p.client_id
        
        UNION ALL
        
        -- 从 tb_search_data 表获取数据
        SELECT 
            p.id AS product_id,
            p.client_id,
            MIN(DATE(tb.date)) AS min_date
        FROM products p
        INNER JOIN tb_search_data tb ON p.id = tb.product_id
        WHERE p.is_active = 1
          AND p.client_id IS NOT NULL
        GROUP BY p.id, p.client_id
    ) AS all_data
    GROUP BY product_id, client_id
) AS product_data
WHERE NOT EXISTS (
    -- 只处理没有分配记录的产品
    -- 检查是否已有分配记录覆盖这个日期范围
    SELECT 1 
    FROM product_assignments pa
    WHERE pa.product_id = product_data.product_id
      AND pa.start_date <= product_data.min_date
      AND (pa.end_date IS NULL OR pa.end_date >= product_data.min_date)
);

-- 显示创建的结果
SELECT 
    COUNT(*) AS 创建的分配记录数,
    '修复完成！请刷新页面查看数据。' AS 提示
FROM product_assignments
WHERE created_at >= DATE_SUB(NOW(), INTERVAL 1 MINUTE);

-- 显示创建的分配记录详情
SELECT 
    pa.id AS 分配记录ID,
    p.id AS 产品ID,
    p.name AS 产品名称,
    u.full_name AS 客户名称,
    pa.start_date AS 分配开始日期,
    pa.end_date AS 分配结束日期,
    pa.created_at AS 创建时间
FROM product_assignments pa
INNER JOIN products p ON pa.product_id = p.id
LEFT JOIN clients c ON p.client_id = c.id
LEFT JOIN users u ON c.user_id = u.id
WHERE pa.created_at >= DATE_SUB(NOW(), INTERVAL 1 MINUTE)
ORDER BY pa.id DESC;

