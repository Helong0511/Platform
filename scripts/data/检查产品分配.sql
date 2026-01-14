-- ============================================
-- 产品分配双向检查SQL脚本
-- ============================================
-- 功能说明：
--   本脚本提供双向检查功能，从两个角度全面检查产品分配情况：
--   1. 从产品角度检查：检查产品是否有分配记录、数据覆盖情况等
--   2. 从分配记录角度检查：检查分配记录的有效性、一致性、时间重叠等
--
-- 使用方法：
--   可以单独执行任何一个查询方法，或者按顺序执行所有查询
--   建议先执行方法2和方法6查看汇总统计，再执行其他详细检查
--
-- 检查项包括：
--   - 产品是否有分配记录
--   - 分配记录对应的产品是否存在
--   - 分配记录与产品的客户ID是否一致
--   - 分配记录的时间范围是否合理
--   - 同一产品的分配记录是否存在时间重叠
--   - 是否存在重复的分配记录
--   - 数据日期是否在分配日期范围内
-- ============================================

USE platform;

-- 方法1：详细列表 - 显示每个产品的分配状态
SELECT 
    p.id AS 产品ID,
    p.name AS 产品名称,
    p.is_active AS 是否激活,
    c.id AS 客户ID,
    u.full_name AS 客户名称,
    CASE 
        WHEN pa_count.count > 0 THEN '✅ 有分配记录'
        ELSE '❌ 没有分配记录'
    END AS 分配状态,
    COALESCE(pa_count.count, 0) AS 分配记录数量,
    pa_info.min_start_date AS 最早分配日期,
    pa_info.max_end_date AS 最晚分配日期,
    data_info.min_date AS 最早数据日期,
    data_info.max_date AS 最新数据日期,
    COALESCE(data_info.ad_count, 0) AS 广告数据记录数,
    COALESCE(data_info.tb_count, 0) AS TB搜索数据记录数,
    COALESCE(data_info.ad_count, 0) + COALESCE(data_info.tb_count, 0) AS 总数据记录数,
    CASE 
        WHEN pa_count.count = 0 THEN '⚠️ 无分配记录，数据无法查询'
        WHEN data_info.min_date < pa_info.min_start_date THEN '⚠️ 有数据在分配日期之前'
        WHEN data_info.max_date > COALESCE(pa_info.max_end_date, '2099-12-31') AND pa_info.max_end_date IS NOT NULL THEN '⚠️ 有数据在分配日期之后'
        ELSE '✅ 数据在分配日期范围内'
    END AS 数据覆盖状态
FROM products p
LEFT JOIN clients c ON p.client_id = c.id
LEFT JOIN users u ON c.user_id = u.id
LEFT JOIN (
    SELECT 
        product_id,
        COUNT(*) AS count
    FROM product_assignments
    GROUP BY product_id
) AS pa_count ON pa_count.product_id = p.id
LEFT JOIN (
    SELECT 
        product_id,
        MIN(start_date) AS min_start_date,
        MAX(COALESCE(end_date, '2099-12-31')) AS max_end_date
    FROM product_assignments
    GROUP BY product_id
) AS pa_info ON pa_info.product_id = p.id
LEFT JOIN (
    SELECT 
        product_id,
        MIN(min_date) AS min_date,
        MAX(max_date) AS max_date,
        SUM(ad_count) AS ad_count,
        SUM(tb_count) AS tb_count
    FROM (
        SELECT 
            product_id,
            MIN(DATE(date)) AS min_date,
            MAX(DATE(date)) AS max_date,
            COUNT(*) AS ad_count,
            0 AS tb_count
        FROM ad_data
        GROUP BY product_id
        UNION ALL
        SELECT 
            product_id,
            MIN(DATE(date)) AS min_date,
            MAX(DATE(date)) AS max_date,
            0 AS ad_count,
            COUNT(*) AS tb_count
        FROM tb_search_data
        GROUP BY product_id
    ) AS combined_data
    GROUP BY product_id
) AS data_info ON data_info.product_id = p.id
ORDER BY 
    COALESCE(pa_count.count, 0) ASC,  -- 没有分配记录的排在前面
    p.id;

-- 方法2：汇总统计 - 快速查看整体情况
SELECT 
    '产品总数' AS 统计项,
    COUNT(*) AS 数量
FROM products
WHERE is_active = 1

UNION ALL

SELECT 
    '有分配记录的产品数' AS 统计项,
    COUNT(DISTINCT pa.product_id) AS 数量
FROM product_assignments pa
INNER JOIN products p ON pa.product_id = p.id
WHERE p.is_active = 1

UNION ALL

SELECT 
    '没有分配记录的产品数' AS 统计项,
    COUNT(*) AS 数量
FROM products p
WHERE p.is_active = 1
  AND NOT EXISTS (
      SELECT 1 
      FROM product_assignments pa
      WHERE pa.product_id = p.id
  )

UNION ALL

SELECT 
    '有数据但没有分配记录的产品数' AS 统计项,
    COUNT(DISTINCT p.id) AS 数量
FROM products p
WHERE p.is_active = 1
  AND (
      EXISTS (SELECT 1 FROM ad_data ad WHERE ad.product_id = p.id)
      OR EXISTS (SELECT 1 FROM tb_search_data tb WHERE tb.product_id = p.id)
  )
  AND NOT EXISTS (
      SELECT 1 
      FROM product_assignments pa
      WHERE pa.product_id = p.id
  );

-- 方法3：只显示没有分配记录的产品（需要修复的产品）
SELECT 
    p.id AS 产品ID,
    p.name AS 产品名称,
    p.is_active AS 是否激活,
    c.id AS 客户ID,
    u.full_name AS 客户名称,
    data_info.min_date AS 最早数据日期,
    data_info.max_date AS 最新数据日期,
    COALESCE(data_info.ad_count, 0) AS 广告数据记录数,
    COALESCE(data_info.tb_count, 0) AS TB搜索数据记录数,
    COALESCE(data_info.ad_count, 0) + COALESCE(data_info.tb_count, 0) AS 总数据记录数,
    '需要创建分配记录' AS 操作建议
FROM products p
LEFT JOIN clients c ON p.client_id = c.id
LEFT JOIN users u ON c.user_id = u.id
INNER JOIN (
    SELECT 
        product_id,
        MIN(min_date) AS min_date,
        MAX(max_date) AS max_date,
        SUM(ad_count) AS ad_count,
        SUM(tb_count) AS tb_count
    FROM (
        SELECT 
            product_id,
            MIN(DATE(date)) AS min_date,
            MAX(DATE(date)) AS max_date,
            COUNT(*) AS ad_count,
            0 AS tb_count
        FROM ad_data
        GROUP BY product_id
        UNION ALL
        SELECT 
            product_id,
            MIN(DATE(date)) AS min_date,
            MAX(DATE(date)) AS max_date,
            0 AS ad_count,
            COUNT(*) AS tb_count
        FROM tb_search_data
        GROUP BY product_id
    ) AS combined_data
    GROUP BY product_id
) AS data_info ON data_info.product_id = p.id
WHERE p.is_active = 1
  AND p.client_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 
      FROM product_assignments pa
      WHERE pa.product_id = p.id
        AND pa.start_date <= data_info.max_date
        AND (pa.end_date IS NULL OR pa.end_date >= data_info.min_date)
  )
ORDER BY (COALESCE(data_info.ad_count, 0) + COALESCE(data_info.tb_count, 0)) DESC;

-- 方法4：只显示有分配记录的产品（正常的产品）
SELECT 
    p.id AS 产品ID,
    p.name AS 产品名称,
    p.is_active AS 是否激活,
    c.id AS 客户ID,
    u.full_name AS 客户名称,
    COUNT(DISTINCT pa.id) AS 分配记录数,
    MIN(pa.start_date) AS 最早分配日期,
    MAX(COALESCE(pa.end_date, '2099-12-31')) AS 最晚分配日期,
    LEAST(
        COALESCE(MIN(DATE(ad.date)), '2099-12-31'),
        COALESCE(MIN(DATE(tb.date)), '2099-12-31')
    ) AS 最早数据日期,
    GREATEST(
        COALESCE(MAX(DATE(ad.date)), '1900-01-01'),
        COALESCE(MAX(DATE(tb.date)), '1900-01-01')
    ) AS 最新数据日期,
    COUNT(DISTINCT ad.id) AS 广告数据记录数,
    COUNT(DISTINCT tb.id) AS TB搜索数据记录数,
    COUNT(DISTINCT ad.id) + COUNT(DISTINCT tb.id) AS 总数据记录数,
    '✅ 正常' AS 状态
FROM products p
LEFT JOIN clients c ON p.client_id = c.id
LEFT JOIN users u ON c.user_id = u.id
LEFT JOIN product_assignments pa ON pa.product_id = p.id
LEFT JOIN ad_data ad ON p.id = ad.product_id
LEFT JOIN tb_search_data tb ON p.id = tb.product_id
WHERE p.is_active = 1
  AND pa.id IS NOT NULL
GROUP BY p.id, p.name, p.is_active, c.id, u.full_name
ORDER BY p.id;

-- ============================================
-- 双向检查：从分配记录到产品（反向检查）
-- ============================================

-- 方法5：检查所有分配记录的有效性（从分配记录角度检查）
SELECT 
    pa.id AS 分配记录ID,
    pa.product_id AS 产品ID,
    pa.client_id AS 分配客户ID,
    pa.start_date AS 开始日期,
    pa.end_date AS 结束日期,
    CASE 
        WHEN p.id IS NULL THEN '❌ 产品不存在'
        WHEN p.is_active = 0 THEN '⚠️ 产品已停用'
        WHEN c.id IS NULL THEN '❌ 客户不存在'
        WHEN pa.client_id != p.client_id THEN '⚠️ 客户ID不一致'
        WHEN pa.end_date IS NOT NULL AND pa.start_date > pa.end_date THEN '❌ 日期范围错误（开始日期>结束日期）'
        ELSE '✅ 正常'
    END AS 检查状态,
    p.name AS 产品名称,
    p.is_active AS 产品是否激活,
    p.client_id AS 产品当前客户ID,
    c.company_name AS 分配客户名称,
    pc.company_name AS 产品当前客户名称,
    CASE 
        WHEN p.id IS NULL THEN '需要删除此分配记录'
        WHEN pa.client_id != p.client_id THEN '需要更新分配记录的客户ID或产品的客户ID'
        WHEN pa.end_date IS NOT NULL AND pa.start_date > pa.end_date THEN '需要修正日期范围'
        WHEN p.is_active = 0 THEN '产品已停用，建议检查'
        ELSE '无需操作'
    END AS 操作建议
FROM product_assignments pa
LEFT JOIN products p ON pa.product_id = p.id
LEFT JOIN clients c ON pa.client_id = c.id
LEFT JOIN clients pc ON p.client_id = pc.id
WHERE 
    p.id IS NULL  -- 产品不存在
    OR c.id IS NULL  -- 客户不存在
    OR pa.client_id != p.client_id  -- 客户ID不一致
    OR (pa.end_date IS NOT NULL AND pa.start_date > pa.end_date)  -- 日期范围错误
    OR p.is_active = 0  -- 产品已停用
ORDER BY 
    CASE 
        WHEN p.id IS NULL THEN 1  -- 最严重：产品不存在
        WHEN c.id IS NULL THEN 2  -- 严重：客户不存在
        WHEN pa.client_id != p.client_id THEN 3  -- 警告：客户ID不一致
        WHEN pa.end_date IS NOT NULL AND pa.start_date > pa.end_date THEN 4  -- 警告：日期范围错误
        ELSE 5  -- 信息：产品已停用
    END,
    pa.id;

-- 方法6：分配记录有效性汇总统计
SELECT 
    '分配记录总数' AS 统计项,
    COUNT(*) AS 数量
FROM product_assignments

UNION ALL

SELECT 
    '产品不存在的分配记录数' AS 统计项,
    COUNT(*) AS 数量
FROM product_assignments pa
WHERE NOT EXISTS (SELECT 1 FROM products p WHERE p.id = pa.product_id)

UNION ALL

SELECT 
    '客户不存在的分配记录数' AS 统计项,
    COUNT(*) AS 数量
FROM product_assignments pa
WHERE NOT EXISTS (SELECT 1 FROM clients c WHERE c.id = pa.client_id)

UNION ALL

SELECT 
    '客户ID不一致的分配记录数' AS 统计项,
    COUNT(*) AS 数量
FROM product_assignments pa
INNER JOIN products p ON pa.product_id = p.id
WHERE pa.client_id != p.client_id

UNION ALL

SELECT 
    '日期范围错误的分配记录数' AS 统计项,
    COUNT(*) AS 数量
FROM product_assignments pa
WHERE pa.end_date IS NOT NULL AND pa.start_date > pa.end_date

UNION ALL

SELECT 
    '产品已停用的分配记录数' AS 统计项,
    COUNT(*) AS 数量
FROM product_assignments pa
INNER JOIN products p ON pa.product_id = p.id
WHERE p.is_active = 0

UNION ALL

SELECT 
    '正常的分配记录数' AS 统计项,
    COUNT(*) AS 数量
FROM product_assignments pa
INNER JOIN products p ON pa.product_id = p.id
INNER JOIN clients c ON pa.client_id = c.id
WHERE pa.client_id = p.client_id
  AND (pa.end_date IS NULL OR pa.start_date <= pa.end_date)
  AND p.is_active = 1;

-- 方法7：显示所有分配记录的详细信息（用于全面检查）
SELECT 
    pa.id AS 分配记录ID,
    pa.product_id AS 产品ID,
    COALESCE(p.name, '❌ 产品不存在') AS 产品名称,
    pa.client_id AS 分配客户ID,
    COALESCE(c.company_name, '❌ 客户不存在') AS 分配客户名称,
    p.client_id AS 产品当前客户ID,
    COALESCE(pc.company_name, 'N/A') AS 产品当前客户名称,
    pa.start_date AS 开始日期,
    pa.end_date AS 结束日期,
    CASE 
        WHEN pa.end_date IS NULL THEN '当前有效'
        WHEN CURDATE() BETWEEN pa.start_date AND pa.end_date THEN '当前有效'
        WHEN CURDATE() < pa.start_date THEN '未来生效'
        ELSE '已过期'
    END AS 分配状态,
    p.is_active AS 产品是否激活,
    CASE 
        WHEN p.id IS NULL THEN '❌ 产品不存在'
        WHEN c.id IS NULL THEN '❌ 客户不存在'
        WHEN pa.client_id != p.client_id THEN '⚠️ 客户ID不一致'
        WHEN pa.end_date IS NOT NULL AND pa.start_date > pa.end_date THEN '❌ 日期范围错误'
        WHEN p.is_active = 0 THEN '⚠️ 产品已停用'
        ELSE '✅ 正常'
    END AS 检查结果
FROM product_assignments pa
LEFT JOIN products p ON pa.product_id = p.id
LEFT JOIN clients c ON pa.client_id = c.id
LEFT JOIN clients pc ON p.client_id = pc.id
ORDER BY 
    CASE 
        WHEN p.id IS NULL THEN 1
        WHEN c.id IS NULL THEN 2
        WHEN pa.client_id != p.client_id THEN 3
        WHEN pa.end_date IS NOT NULL AND pa.start_date > pa.end_date THEN 4
        WHEN p.is_active = 0 THEN 5
        ELSE 6
    END,
    pa.start_date DESC,
    pa.id;

-- 方法8：检查分配记录与产品客户ID的一致性（详细对比）
SELECT 
    pa.id AS 分配记录ID,
    pa.product_id AS 产品ID,
    p.name AS 产品名称,
    pa.client_id AS 分配记录中的客户ID,
    c1.company_name AS 分配记录中的客户名称,
    p.client_id AS 产品表中的客户ID,
    c2.company_name AS 产品表中的客户名称,
    pa.start_date AS 分配开始日期,
    pa.end_date AS 分配结束日期,
    CASE 
        WHEN pa.client_id = p.client_id THEN '✅ 一致'
        ELSE '⚠️ 不一致'
    END AS 客户ID一致性,
    CASE 
        WHEN pa.client_id != p.client_id THEN CONCAT('需要同步：分配记录的客户ID=', pa.client_id, '，产品的客户ID=', p.client_id)
        ELSE '无需操作'
    END AS 操作建议
FROM product_assignments pa
INNER JOIN products p ON pa.product_id = p.id
LEFT JOIN clients c1 ON pa.client_id = c1.id
LEFT JOIN clients c2 ON p.client_id = c2.id
WHERE pa.client_id != p.client_id
ORDER BY pa.id;

-- 方法9：检查同一产品的分配记录时间重叠问题
SELECT 
    pa1.id AS 分配记录1_ID,
    pa1.product_id AS 产品ID,
    p.name AS 产品名称,
    pa1.client_id AS 客户ID1,
    c1.company_name AS 客户名称1,
    pa1.start_date AS 开始日期1,
    pa1.end_date AS 结束日期1,
    pa2.id AS 分配记录2_ID,
    pa2.client_id AS 客户ID2,
    c2.company_name AS 客户名称2,
    pa2.start_date AS 开始日期2,
    pa2.end_date AS 结束日期2,
    CASE 
        WHEN pa1.client_id = pa2.client_id THEN '⚠️ 同一客户的时间重叠'
        ELSE '❌ 不同客户的时间重叠（严重问题）'
    END AS 重叠类型,
    CASE 
        WHEN pa1.start_date <= COALESCE(pa2.end_date, '2099-12-31') 
         AND COALESCE(pa1.end_date, '2099-12-31') >= pa2.start_date THEN '是'
        ELSE '否'
    END AS 是否重叠,
    CASE 
        WHEN pa1.client_id != pa2.client_id THEN '需要修正：同一产品不能同时分配给不同客户'
        WHEN pa1.start_date <= COALESCE(pa2.end_date, '2099-12-31') 
         AND COALESCE(pa1.end_date, '2099-12-31') >= pa2.start_date THEN '需要调整日期范围，避免重叠'
        ELSE '无需操作'
    END AS 操作建议
FROM product_assignments pa1
INNER JOIN product_assignments pa2 ON pa1.product_id = pa2.product_id AND pa1.id < pa2.id
INNER JOIN products p ON pa1.product_id = p.id
LEFT JOIN clients c1 ON pa1.client_id = c1.id
LEFT JOIN clients c2 ON pa2.client_id = c2.id
WHERE pa1.start_date <= COALESCE(pa2.end_date, '2099-12-31') 
  AND COALESCE(pa1.end_date, '2099-12-31') >= pa2.start_date
ORDER BY pa1.product_id, pa1.start_date;

-- 方法10：检查是否有重复的分配记录（完全相同或几乎相同）
SELECT 
    pa1.id AS 分配记录1_ID,
    pa2.id AS 分配记录2_ID,
    pa1.product_id AS 产品ID,
    p.name AS 产品名称,
    pa1.client_id AS 客户ID,
    c.company_name AS 客户名称,
    pa1.start_date AS 开始日期,
    pa1.end_date AS 结束日期,
    CASE 
        WHEN pa1.id != pa2.id 
         AND pa1.product_id = pa2.product_id 
         AND pa1.client_id = pa2.client_id 
         AND pa1.start_date = pa2.start_date 
         AND COALESCE(pa1.end_date, '1900-01-01') = COALESCE(pa2.end_date, '1900-01-01') THEN '❌ 完全重复'
        WHEN pa1.id != pa2.id 
         AND pa1.product_id = pa2.product_id 
         AND pa1.client_id = pa2.client_id 
         AND pa1.start_date = pa2.start_date THEN '⚠️ 部分重复（开始日期相同）'
        ELSE '其他'
    END AS 重复类型,
    '建议删除重复记录' AS 操作建议
FROM product_assignments pa1
INNER JOIN product_assignments pa2 ON pa1.product_id = pa2.product_id 
    AND pa1.client_id = pa2.client_id 
    AND pa1.start_date = pa2.start_date
    AND pa1.id < pa2.id
INNER JOIN products p ON pa1.product_id = p.id
LEFT JOIN clients c ON pa1.client_id = c.id
ORDER BY pa1.product_id, pa1.start_date;

-- 方法11：双向检查综合诊断报告
SELECT 
    '=== 双向检查综合诊断报告 ===' AS 诊断报告
UNION ALL
SELECT 
    CONCAT('1. 产品总数: ', COUNT(*)) AS 诊断报告
FROM products
WHERE is_active = 1
UNION ALL
SELECT 
    CONCAT('2. 有分配记录的产品数: ', COUNT(DISTINCT pa.product_id)) AS 诊断报告
FROM product_assignments pa
INNER JOIN products p ON pa.product_id = p.id
WHERE p.is_active = 1
UNION ALL
SELECT 
    CONCAT('3. 没有分配记录的产品数: ', COUNT(*)) AS 诊断报告
FROM products p
WHERE p.is_active = 1
  AND NOT EXISTS (SELECT 1 FROM product_assignments pa WHERE pa.product_id = p.id)
UNION ALL
SELECT 
    CONCAT('4. 分配记录总数: ', COUNT(*)) AS 诊断报告
FROM product_assignments
UNION ALL
SELECT 
    CONCAT('5. 产品不存在的分配记录数: ', COUNT(*)) AS 诊断报告
FROM product_assignments pa
WHERE NOT EXISTS (SELECT 1 FROM products p WHERE p.id = pa.product_id)
UNION ALL
SELECT 
    CONCAT('6. 客户ID不一致的分配记录数: ', COUNT(*)) AS 诊断报告
FROM product_assignments pa
INNER JOIN products p ON pa.product_id = p.id
WHERE pa.client_id != p.client_id
UNION ALL
SELECT 
    CONCAT('7. 时间重叠的分配记录数: ', COUNT(DISTINCT CONCAT(pa1.product_id, '-', LEAST(pa1.id, pa2.id)))) AS 诊断报告
FROM product_assignments pa1
INNER JOIN product_assignments pa2 ON pa1.product_id = pa2.product_id AND pa1.id < pa2.id
WHERE pa1.start_date <= COALESCE(pa2.end_date, '2099-12-31') 
  AND COALESCE(pa1.end_date, '2099-12-31') >= pa2.start_date
UNION ALL
SELECT 
    CONCAT('8. 正常的分配记录数: ', COUNT(*)) AS 诊断报告
FROM product_assignments pa
INNER JOIN products p ON pa.product_id = p.id
INNER JOIN clients c ON pa.client_id = c.id
WHERE pa.client_id = p.client_id
  AND (pa.end_date IS NULL OR pa.start_date <= pa.end_date)
  AND p.is_active = 1;

-- 方法12：快速问题诊断（只显示有问题的情况）
SELECT 
    '产品问题' AS 问题类型,
    CONCAT('产品ID: ', p.id, ', 名称: ', p.name) AS 问题描述,
    '没有分配记录' AS 问题详情
FROM products p
WHERE p.is_active = 1
  AND NOT EXISTS (SELECT 1 FROM product_assignments pa WHERE pa.product_id = p.id)
UNION ALL
SELECT 
    '分配记录问题' AS 问题类型,
    CONCAT('分配记录ID: ', pa.id, ', 产品ID: ', pa.product_id) AS 问题描述,
    '产品不存在' AS 问题详情
FROM product_assignments pa
WHERE NOT EXISTS (SELECT 1 FROM products p WHERE p.id = pa.product_id)
UNION ALL
SELECT 
    '分配记录问题' AS 问题类型,
    CONCAT('分配记录ID: ', pa.id, ', 产品ID: ', pa.product_id) AS 问题描述,
    CONCAT('客户ID不一致: 分配记录=', pa.client_id, ', 产品=', p.client_id) AS 问题详情
FROM product_assignments pa
INNER JOIN products p ON pa.product_id = p.id
WHERE pa.client_id != p.client_id
UNION ALL
SELECT 
    '分配记录问题' AS 问题类型,
    CONCAT('分配记录ID: ', pa.id) AS 问题描述,
    CONCAT('日期范围错误: 开始日期(', pa.start_date, ') > 结束日期(', pa.end_date, ')') AS 问题详情
FROM product_assignments pa
WHERE pa.end_date IS NOT NULL AND pa.start_date > pa.end_date
ORDER BY 问题类型, 问题描述;

