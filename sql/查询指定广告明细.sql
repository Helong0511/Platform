-- 指定日期/产品/广告单元/国家 的广告明细（含扣费信息）
USE `platform`;

SELECT
    DATE(a.`date`) AS `日期`,
    p.`name` AS `产品`,
    a.`ad_unit` AS `广告单元`,
    a.`country_code` AS `国家`,
    a.`data_source` AS `数据来源`,
    a.`report_type` AS `报表类型`,
    a.`request_count` AS `请求数`,
    a.`match_count` AS `匹配数`,
    a.`display_count` AS `展示数`,
    a.`click_count` AS `点击数`,
    ROUND(a.`ecpm_before_deduct`, 4) AS `eCPM扣前`,
    ROUND(a.`ecpm_after_deduct`, 4) AS `eCPM扣后`,
    ROUND(a.`revenue_before_deduct`, 4) AS `扣前收益`,
    ROUND(a.`revenue_after_deduct`, 4) AS `扣后收益`,
    ROUND(a.`revenue_before_deduct` - a.`revenue_after_deduct`, 4) AS `扣了多少`,
    ROUND(IFNULL(p.`revenue_deduct_ratio`, 0), 4) AS `扣费比例`,
    ROUND(IFNULL(p.`revenue_deduct_ratio`, 0) * 100, 2) AS `扣费比例_百分数`,
    a.`is_deducted` AS `是否已扣减`,
    a.`updated_at` AS `更新时间`
FROM `ad_data` a
INNER JOIN `products` p ON p.`id` = a.`product_id`
WHERE a.`date` = '2026-07-22'
  AND p.`name` = 'mini.qiggblog.com'
  AND a.`ad_unit` = 'mini.qiggblog.com_0715_banner2'
  AND a.`country_code` = 'AU';
