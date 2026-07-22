-- 查询今天「按收益扣费比例」实际产生扣费的广告明细
-- 条件：扣前收益 > 扣后收益（或 is_deducted=1），并展示产品配置的扣费比例
-- 用法：在 MySQL 中直接执行；时区按服务器/会话 DATE(CURDATE())

USE `platform`;

SELECT
    DATE(a.`date`) AS `日期`,
    p.`name` AS `产品`,
    a.`ad_unit` AS `广告单元`,
    a.`country_code` AS `国家`,
    ROUND(a.`revenue_before_deduct`, 4) AS `扣前收益`,
    ROUND(a.`revenue_after_deduct`, 4) AS `扣后收益`,
    ROUND(a.`revenue_before_deduct` - a.`revenue_after_deduct`, 4) AS `扣了多少`,
    ROUND(IFNULL(p.`revenue_deduct_ratio`, 0) * 100, 2) AS `扣费比例_百分数`,
    ROUND(IFNULL(p.`revenue_deduct_ratio`, 0), 4) AS `扣费比例`,
    -- 实际扣费率（便于核对是否与配置一致）：(扣前-扣后)/扣前
    ROUND(
        CASE
            WHEN a.`revenue_before_deduct` > 0
            THEN (a.`revenue_before_deduct` - a.`revenue_after_deduct`) / a.`revenue_before_deduct`
            ELSE NULL
        END,
        4
    ) AS `实际扣费率`
FROM `ad_data` a
INNER JOIN `products` p ON p.`id` = a.`product_id`
WHERE a.`date` = CURDATE()
  AND (
        a.`is_deducted` = 1
        OR (a.`revenue_before_deduct` - a.`revenue_after_deduct`) > 0.0001
      )
ORDER BY
    `扣了多少` DESC,
    p.`name`,
    a.`country_code`,
    a.`ad_unit`;

-- 仅看汇总（有没有扣费、扣了多少）：
-- SELECT
--     COUNT(*) AS 扣费行数,
--     ROUND(SUM(a.revenue_before_deduct - a.revenue_after_deduct), 4) AS 总扣费金额,
--     COUNT(DISTINCT a.product_id) AS 涉及产品数
-- FROM ad_data a
-- WHERE a.date = CURDATE()
--   AND (a.is_deducted = 1 OR (a.revenue_before_deduct - a.revenue_after_deduct) > 0.0001);
