/*
 Navicat Premium Dump SQL

 Source Server         : Platform schema baseline
 Source Server Type    : MySQL
 Source Server Version : 80044 (8.0.44-0ubuntu0.22.04.2)
 Source Host           : omitted (environment-specific)
 Source Schema         : platform

 Target Server Type    : MySQL
 Target Server Version : 80044 (8.0.44-0ubuntu0.22.04.2)
 File Encoding         : 65001

 Date: 29/07/2026 12:30:00
*/

SET NAMES utf8mb4;

-- 若数据库不存在则创建，并切换到该库
CREATE DATABASE IF NOT EXISTS `platform`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_0900_ai_ci;

USE `platform`;

SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for ad_data
-- ----------------------------
DROP TABLE IF EXISTS `ad_data`;
CREATE TABLE IF NOT EXISTS `ad_data`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '广告数据ID',
  `date` DATE NOT NULL COMMENT '数据日期（仅日期，无时间部分）',
  `country_code` VARCHAR(100) NULL DEFAULT NULL COMMENT '国家代码（ISO 二字母；未识别时保留原始国名；无国家时为 NULL）',
  `product_id` INT NOT NULL COMMENT '产品ID',
  `ad_unit` VARCHAR(150) NOT NULL DEFAULT '' COMMENT '广告单元',
  `request_count` INT NOT NULL DEFAULT 0 COMMENT '请求数',
  `match_count` INT NOT NULL DEFAULT 0 COMMENT '匹配数',
  `coverage_rate` DECIMAL(7, 4) NOT NULL DEFAULT 0.0000 COMMENT '覆盖率（百分比数值，如12.3400 代表 12.34%）',
  `display_count` INT NOT NULL DEFAULT 0 COMMENT '展示数',
  `display_rate` DECIMAL(7, 4) NOT NULL DEFAULT 0.0000 COMMENT '展示率',
  `click_count` INT NOT NULL DEFAULT 0 COMMENT '点击数',
  `click_rate` DECIMAL(7, 4) NOT NULL DEFAULT 0.0000 COMMENT '点击率',
  `viewability_rate` DECIMAL(7, 4) NOT NULL DEFAULT 0.0000 COMMENT '可见率',
  `cpc` DECIMAL(12, 4) NOT NULL DEFAULT 0.0000 COMMENT 'CPC',
  `pageviews` INT NOT NULL DEFAULT 0 COMMENT 'PageViews',
  `ecpm_before_deduct` DECIMAL(12, 4) NOT NULL DEFAULT 0.0000 COMMENT 'eCPM未减扣',
  `ecpm_after_deduct` DECIMAL(12, 4) NOT NULL DEFAULT 0.0000 COMMENT 'eCPM已减扣',
  `revenue_before_deduct` DECIMAL(12, 4) NOT NULL DEFAULT 0.0000 COMMENT '收益未减扣',
  `revenue_after_deduct` DECIMAL(12, 4) NOT NULL DEFAULT 0.0000 COMMENT '收益已减扣',
  `data_source` VARCHAR(32) NOT NULL DEFAULT 'legacy' COMMENT '数据来源：zhisuo/gam/excel/legacy 等',
  `upstream_account` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '上游账号标识，如 KE11、leadwin',
  `report_type` VARCHAR(16) NOT NULL DEFAULT 'legacy' COMMENT '报表维度：unit/country/cross/daily/legacy',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  `is_deducted` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已被扣减',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_ad_data_identity`(`date` ASC, `product_id` ASC, `country_code` ASC, `ad_unit` ASC, `data_source` ASC, `report_type` ASC, `upstream_account` ASC) USING BTREE,
  INDEX `idx_ad_data_date_report_type`(`date` ASC, `report_type` ASC, `product_id` ASC) USING BTREE COMMENT '日汇总互斥选源：日期+报表类型',
  INDEX `idx_ad_data_product_date_id`(`product_id` ASC, `date` ASC, `id` ASC) USING BTREE COMMENT '客户范围/产品+日期稳定分页',
  INDEX `idx_ad_data_date_id`(`date` ASC, `id` ASC) USING BTREE COMMENT '默认按日期+id 稳定分页（无产品筛选时）',
  INDEX `idx_ad_data_date_country`(`date` ASC, `country_code` ASC, `product_id` ASC) USING BTREE COMMENT '日期范围+国家筛选/去重/双维度国家组',
  INDEX `idx_ad_data_date_ad_unit`(`date` ASC, `ad_unit` ASC, `product_id` ASC) USING BTREE COMMENT '日期范围+广告单元筛选/去重/单元维度汇总',
  INDEX `idx_ad_data_date_source`(`date` ASC, `data_source` ASC, `report_type` ASC, `product_id` ASC) USING BTREE COMMENT '日期+来源+报表类型；watch/基线按产品+来源聚合',
  INDEX `idx_ad_data_date_account`(`date` ASC, `upstream_account` ASC, `product_id` ASC) USING BTREE COMMENT '日期范围+上游账号筛选',
  CONSTRAINT `fk_ad_data_product` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '广告数据表' ROW_FORMAT = DYNAMIC STATS_SAMPLE_PAGES = 40;

-- ----------------------------
-- Table structure for ad_data_archive
-- ----------------------------
DROP TABLE IF EXISTS `ad_data_archive`;
CREATE TABLE IF NOT EXISTS `ad_data_archive`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '广告数据ID',
  `date` DATE NOT NULL COMMENT '数据日期（仅日期，无时间部分）',
  `country_code` VARCHAR(100) NULL DEFAULT NULL COMMENT '国家代码（ISO 二字母；未识别时保留原始国名；无国家时为 NULL）',
  `product_id` INT NOT NULL COMMENT '产品ID',
  `ad_unit` VARCHAR(150) NOT NULL DEFAULT '' COMMENT '广告单元',
  `request_count` INT NOT NULL DEFAULT 0 COMMENT '请求数',
  `match_count` INT NOT NULL DEFAULT 0 COMMENT '匹配数',
  `coverage_rate` DECIMAL(7, 4) NOT NULL DEFAULT 0.0000 COMMENT '覆盖率（百分比数值）',
  `display_count` INT NOT NULL DEFAULT 0 COMMENT '展示数',
  `display_rate` DECIMAL(7, 4) NOT NULL DEFAULT 0.0000 COMMENT '展示率',
  `click_count` INT NOT NULL DEFAULT 0 COMMENT '点击数',
  `click_rate` DECIMAL(7, 4) NOT NULL DEFAULT 0.0000 COMMENT '点击率',
  `viewability_rate` DECIMAL(7, 4) NOT NULL DEFAULT 0.0000 COMMENT '可见率',
  `cpc` DECIMAL(12,4) NOT NULL DEFAULT 0.0000 COMMENT 'CPC',
  `pageviews` INT NOT NULL DEFAULT 0 COMMENT 'PageViews',
  `ecpm_before_deduct` DECIMAL(12, 4) NOT NULL DEFAULT 0.0000 COMMENT 'eCPM未减扣',
  `ecpm_after_deduct` DECIMAL(12, 4) NOT NULL DEFAULT 0.0000 COMMENT 'eCPM已减扣',
  `revenue_before_deduct` DECIMAL(12, 4) NOT NULL DEFAULT 0.0000 COMMENT '收益未减扣',
  `revenue_after_deduct` DECIMAL(12, 4) NOT NULL DEFAULT 0.0000 COMMENT '收益已减扣',
  `data_source` VARCHAR(32) NOT NULL DEFAULT 'legacy' COMMENT '数据来源：zhisuo/gam/excel/legacy 等',
  `upstream_account` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '上游账号标识，如 KE11、leadwin',
  `report_type` VARCHAR(16) NOT NULL DEFAULT 'legacy' COMMENT '报表维度：unit/country/cross/daily/legacy',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  `is_deducted` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已被扣减',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_ad_data_archive_identity`(`date` ASC, `product_id` ASC, `country_code` ASC, `ad_unit` ASC, `data_source` ASC, `report_type` ASC, `upstream_account` ASC) USING BTREE,
  INDEX `idx_ad_data_archive_product`(`product_id` ASC) USING BTREE COMMENT '外键 fk_ad_data_archive_product 依赖，不可删',
  INDEX `idx_ad_data_archive_date_report_type`(`date` ASC, `report_type` ASC, `product_id` ASC) USING BTREE COMMENT '归档表日期+报表类型',
  INDEX `idx_ad_data_archive_product_date`(`product_id` ASC, `date` ASC, `id` ASC) USING BTREE COMMENT '归档表产品+日期',
  INDEX `idx_ad_data_archive_date_country`(`date` ASC, `country_code` ASC, `product_id` ASC) USING BTREE COMMENT '归档表日期+国家',
  INDEX `idx_ad_data_archive_date_source`(`date` ASC, `data_source` ASC, `report_type` ASC, `product_id` ASC) USING BTREE COMMENT '归档表日期+来源+类型',
  CONSTRAINT `fk_ad_data_archive_product` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '广告数据归档表' ROW_FORMAT = DYNAMIC STATS_SAMPLE_PAGES = 40;

-- ----------------------------
-- Table structure for ad_data_day_baseline
-- ----------------------------
DROP TABLE IF EXISTS `ad_data_day_baseline`;
CREATE TABLE IF NOT EXISTS `ad_data_day_baseline`  (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `stat_date` DATE NOT NULL COMMENT '标准日（业务日）',
  `product_id` INT NOT NULL COMMENT '产品ID',
  `data_source` VARCHAR(32) NOT NULL COMMENT '数据来源 zhisuo/gam/...',
  `request_count` INT NOT NULL DEFAULT 0 COMMENT '汇总请求数',
  `revenue_before` DECIMAL(14, 4) NOT NULL DEFAULT 0.0000 COMMENT '汇总收益扣前',
  `row_count` INT NOT NULL DEFAULT 0 COMMENT '明细行数',
  `frozen_at` DATETIME NOT NULL COMMENT '冻结时间',
  `freeze_batch_id` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '冻结批次',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_ad_data_day_baseline`(`stat_date` ASC, `product_id` ASC, `data_source` ASC) USING BTREE,
  INDEX `idx_baseline_stat_date`(`stat_date` ASC) USING BTREE,
  INDEX `idx_baseline_product`(`product_id` ASC) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '广告数据日标准快照（倒扣对比用）' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for ad_data_health_alert
-- ----------------------------
DROP TABLE IF EXISTS `ad_data_health_alert`;
CREATE TABLE IF NOT EXISTS `ad_data_health_alert`  (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `alert_type` VARCHAR(32) NOT NULL COMMENT 'baseline_drop/missing/streak/today_gap/dod_drop',
  `stat_date` DATE NOT NULL COMMENT '相关业务日',
  `product_id` INT NOT NULL COMMENT '产品ID',
  `product_name` VARCHAR(100) NOT NULL DEFAULT '' COMMENT '产品名快照',
  `data_source` VARCHAR(32) NOT NULL DEFAULT '' COMMENT '数据来源',
  `metric` VARCHAR(32) NOT NULL DEFAULT '' COMMENT 'request_count/revenue_before/revenue_after/...',
  `baseline_value` DECIMAL(14, 4) NULL DEFAULT NULL COMMENT '标准值或对照值',
  `current_value` DECIMAL(14, 4) NULL DEFAULT NULL COMMENT '当前值',
  `drop_ratio` DECIMAL(10, 6) NULL DEFAULT NULL COMMENT '下降比例 0~1',
  `detail` TEXT NULL COMMENT '可读说明',
  `batch_id` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '触发批次',
  `notified` TINYINT NOT NULL DEFAULT 0 COMMENT '是否已Telegram',
  `created_at` DATETIME NOT NULL COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_health_alert_date_type`(`stat_date` ASC, `alert_type` ASC) USING BTREE,
  INDEX `idx_health_alert_created`(`created_at` ASC) USING BTREE,
  INDEX `idx_health_alert_product`(`product_id` ASC) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '广告数据健康巡检告警' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for ad_data_health_settings
-- ----------------------------
DROP TABLE IF EXISTS `ad_data_health_settings`;
CREATE TABLE IF NOT EXISTS `ad_data_health_settings`  (
  `id` INT NOT NULL DEFAULT 1 COMMENT '固定单行 id=1',
  `drop_ratio` DECIMAL(8, 4) NOT NULL DEFAULT 0.0200 COMMENT '跌幅阈值',
  `request_floor` INT NOT NULL DEFAULT 100 COMMENT '请求数地板',
  `revenue_floor` DECIMAL(12, 4) NOT NULL DEFAULT 1.0000 COMMENT '收益地板',
  `enable_baseline_drop` TINYINT NOT NULL DEFAULT 1 COMMENT '倒扣vs标准',
  `enable_missing` TINYINT NOT NULL DEFAULT 1 COMMENT '昨天缺数',
  `enable_streak` TINYINT NOT NULL DEFAULT 1 COMMENT '连续断档',
  `enable_today_gap` TINYINT NOT NULL DEFAULT 1 COMMENT '昨有今无',
  `enable_dod_drop` TINYINT NOT NULL DEFAULT 1 COMMENT '昨天vs前天日环比',
  `enable_telegram` TINYINT NOT NULL DEFAULT 1 COMMENT '是否发Telegram',
  `cooldown_hours` INT NOT NULL DEFAULT 24 COMMENT '同类告警冷却小时',
  `watch_products` TEXT NULL COMMENT '重点关注产品（每行一个域名/URL，支持带或不带 https://）',
  `watch_effective_date` DATE NULL COMMENT '重点关注生效日期（含当天；空=立即生效）',
  `watch_expire_date` DATE NULL COMMENT '重点关注失效日期（含当天；空=长期有效）',
  `updated_at` DATETIME NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '广告数据健康巡检配置' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for admin_notification_configs
-- ----------------------------
DROP TABLE IF EXISTS `admin_notification_configs`;
CREATE TABLE IF NOT EXISTS `admin_notification_configs`  (
  `id` INT NOT NULL DEFAULT 1 COMMENT '配置ID（固定为1，单例模式）',
  `telegram_enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用 Telegram 通知',
  `telegram_chat_id` VARCHAR(100) NULL DEFAULT NULL COMMENT '管理员 Telegram Chat ID',
  `notify_all_conversions` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '通知所有转化',
  `notify_forward_failure` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '通知转发失败',
  `notify_forward_success` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '通知转发成功（可选）',
  `notify_system_errors` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '通知系统异常',
  `notify_statistics` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '定时统计通知',
  `statistics_frequency` VARCHAR(20) NOT NULL DEFAULT 'hourly' COMMENT '统计频率：hourly, daily',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  CONSTRAINT `check_single_record` CHECK (`id` = 1)
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '管理员通知配置表（单例模式）' ROW_FORMAT = DYNAMIC;

-- 默认种子行（本机测试 Chat ID）
INSERT INTO `admin_notification_configs`
(`id`, `telegram_enabled`, `telegram_chat_id`, `notify_all_conversions`, `notify_forward_failure`,
 `notify_forward_success`, `notify_system_errors`, `notify_statistics`, `statistics_frequency`)
VALUES
(1, 1, '5312177749', 1, 1, 0, 1, 0, 'hourly')
ON DUPLICATE KEY UPDATE `id` = `id`;

-- ----------------------------
-- Table structure for advertiser_tests
-- ----------------------------
DROP TABLE IF EXISTS `advertiser_tests`;
CREATE TABLE IF NOT EXISTS `advertiser_tests`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '测试记录ID',
  `advertiser_id` INT NOT NULL COMMENT '广告主ID',
  `advertiser_name` VARCHAR(100) NULL DEFAULT NULL COMMENT '广告主名称',
  `advertiser_offer_id` VARCHAR(100) NULL DEFAULT NULL COMMENT '上游系统中的Offer ID',
  `offer_id` INT NOT NULL COMMENT '平台内的Offer ID',
  `offer_name` VARCHAR(200) NULL DEFAULT NULL COMMENT 'Offer名称',
  `price` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT '价格',
  `country` VARCHAR(50) NULL DEFAULT NULL COMMENT '国家',
  `click_id` VARCHAR(255) NULL DEFAULT NULL COMMENT '测试生成的Click ID',
  `click_url` TEXT NULL COMMENT '测试生成的Click Url',
  `test_time` DATETIME NULL DEFAULT NULL COMMENT '测试时间',
  `created_at` DATETIME NOT NULL COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_advertiser_id`(`advertiser_id` ASC) USING BTREE,
  INDEX `idx_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_test_time`(`test_time` ASC) USING BTREE,
  CONSTRAINT `advertiser_tests_ibfk_1` FOREIGN KEY (`advertiser_id`) REFERENCES `advertisers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `advertiser_tests_ibfk_2` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '广告主联调测试记录表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for advertisers
-- ----------------------------
DROP TABLE IF EXISTS `advertisers`;
CREATE TABLE IF NOT EXISTS `advertisers`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '广告主ID',
  `advertiser_name` VARCHAR(100) NOT NULL COMMENT '广告主名称',
  `email` VARCHAR(255) NULL DEFAULT NULL COMMENT '邮箱（可选）',
  `mobile` VARCHAR(20) NULL DEFAULT NULL COMMENT '手机号',
  `advertiser_params` VARCHAR(255) NULL DEFAULT NULL COMMENT '广告主参数',
  `is_active` TINYINT(1) NULL DEFAULT 1 COMMENT '是否激活',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_advertiser_name`(`advertiser_name` ASC) USING BTREE,
  INDEX `idx_is_active`(`is_active` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '广告主表（上游）' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for affiliate_tests
-- ----------------------------
DROP TABLE IF EXISTS `affiliate_tests`;
CREATE TABLE IF NOT EXISTS `affiliate_tests`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '测试记录ID',
  `publisher_id` INT NOT NULL COMMENT '渠道ID',
  `click_id` VARCHAR(255) NOT NULL COMMENT '下游提供的Click ID',
  `offer_id` INT NOT NULL COMMENT 'Offer ID',
  `offer_name` VARCHAR(200) NULL DEFAULT NULL COMMENT 'Offer名称',
  `price` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT '价格',
  `country` VARCHAR(50) NULL DEFAULT NULL COMMENT '国家',
  `platform` VARCHAR(50) NULL DEFAULT NULL COMMENT '平台',
  `postback_time` DATETIME NULL DEFAULT NULL COMMENT 'Postback发送时间',
  `status` VARCHAR(50) NULL DEFAULT NULL COMMENT '发送状态：Send Success/Failed',
  `affiliate_return_content` TEXT NULL COMMENT '渠道返回内容',
  `created_at` DATETIME NOT NULL COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_publisher_id`(`publisher_id` ASC) USING BTREE,
  INDEX `idx_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_click_id`(`click_id` ASC) USING BTREE,
  INDEX `idx_status`(`status` ASC) USING BTREE,
  INDEX `idx_postback_time`(`postback_time` ASC) USING BTREE,
  CONSTRAINT `affiliate_tests_ibfk_1` FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `affiliate_tests_ibfk_2` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '渠道联调测试记录表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for clicks
-- ----------------------------
DROP TABLE IF EXISTS `clicks`;
CREATE TABLE IF NOT EXISTS `clicks`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '点击记录ID',
  `click_id` VARCHAR(255) NOT NULL COMMENT '点击ID（系统生成，唯一标识）',
  `offer_id` INT NULL DEFAULT NULL COMMENT '关联的Offer ID',
  `publisher_id` INT NULL DEFAULT NULL COMMENT '关联的渠道ID',
  `advertiser_id` INT NULL DEFAULT NULL COMMENT '关联的广告主ID',
  `short_link_id` INT NULL DEFAULT NULL COMMENT '关联的短链接ID',
  `click_time` DATETIME NOT NULL COMMENT '点击时间',
  `ip` VARCHAR(50) NULL DEFAULT NULL COMMENT '点击IP地址',
  `device` VARCHAR(100) NULL DEFAULT NULL COMMENT '设备信息',
  `country` VARCHAR(50) NULL DEFAULT NULL COMMENT '国家',
  `user_agent` TEXT NULL COMMENT 'User Agent',
  `referer` TEXT NULL COMMENT '来源页面',
  `os` VARCHAR(50) NULL DEFAULT NULL COMMENT '操作系统名称',
  `os_version` VARCHAR(50) NULL DEFAULT NULL COMMENT '操作系统版本',
  `browser` VARCHAR(50) NULL DEFAULT NULL COMMENT '浏览器名称',
  `browser_version` VARCHAR(50) NULL DEFAULT NULL COMMENT '浏览器版本',
  `accept_language` VARCHAR(200) NULL DEFAULT NULL COMMENT '接受的语言',
  `accept_encoding` VARCHAR(200) NULL DEFAULT NULL COMMENT '接受的编码',
  `is_bot` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否为机器人/爬虫',
  `device_type` VARCHAR(20) NULL DEFAULT NULL COMMENT '设备类型（mobile/tablet/desktop）',
  `device_brand` VARCHAR(50) NULL DEFAULT NULL COMMENT '设备品牌',
  `device_model` VARCHAR(100) NULL DEFAULT NULL COMMENT '设备型号',
  `url_params` TEXT NULL COMMENT 'URL参数（JSON格式）',
  `all_headers` TEXT NULL COMMENT '所有请求头（JSON格式）',
  `original_request_url` TEXT NULL COMMENT '原始点击URL（用户访问的短链接URL）',
  `final_redirect_url` TEXT NULL COMMENT '最终跳转URL（系统重定向后的URL）',
  `conversion_id` INT NULL DEFAULT NULL COMMENT '关联的转化ID（如果已转化）',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `click_id`(`click_id` ASC) USING BTREE,
  INDEX `idx_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_publisher_id`(`publisher_id` ASC) USING BTREE,
  INDEX `idx_advertiser_id`(`advertiser_id` ASC) USING BTREE,
  INDEX `idx_click_time`(`click_time` ASC) USING BTREE,
  INDEX `idx_conversion_id`(`conversion_id` ASC) USING BTREE,
  INDEX `idx_short_link_id`(`short_link_id` ASC) USING BTREE,
  INDEX `idx_clicks_time_offer_publisher`(`click_time` ASC, `offer_id` ASC, `publisher_id` ASC) USING BTREE,
  INDEX `idx_clicks_time_offer`(`click_time` ASC, `offer_id` ASC) USING BTREE,
  INDEX `idx_clicks_offer_publisher_time`(`offer_id` ASC, `publisher_id` ASC, `click_time` ASC) USING BTREE,
  INDEX `idx_ip`(`ip` ASC) USING BTREE,
  INDEX `idx_country`(`country` ASC) USING BTREE,
  INDEX `idx_click_time_publisher`(`click_time` ASC, `publisher_id` ASC) USING BTREE,
  INDEX `idx_safe_delete`(`advertiser_id` ASC, `offer_id` ASC, `publisher_id` ASC, `created_at` ASC) USING BTREE,
  INDEX `idx_clicks_created_at_id`(`created_at` ASC, `id` ASC) USING BTREE,
  CONSTRAINT `clicks_ibfk_1` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `clicks_ibfk_2` FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `clicks_ibfk_3` FOREIGN KEY (`advertiser_id`) REFERENCES `advertisers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `clicks_ibfk_short_link` FOREIGN KEY (`short_link_id`) REFERENCES `short_links` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '点击记录表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for clicks_archive
-- ----------------------------
DROP TABLE IF EXISTS `clicks_archive`;
CREATE TABLE IF NOT EXISTS `clicks_archive`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '点击记录ID',
  `click_id` VARCHAR(255) NOT NULL COMMENT '点击ID（系统生成，唯一标识）',
  `offer_id` INT NULL DEFAULT NULL COMMENT '关联的Offer ID',
  `publisher_id` INT NULL DEFAULT NULL COMMENT '关联的渠道ID',
  `advertiser_id` INT NULL DEFAULT NULL COMMENT '关联的广告主ID',
  `short_link_id` INT NULL DEFAULT NULL COMMENT '关联的短链接ID',
  `click_time` DATETIME NOT NULL COMMENT '点击时间',
  `ip` VARCHAR(50) NULL DEFAULT NULL COMMENT '点击IP地址',
  `device` VARCHAR(100) NULL DEFAULT NULL COMMENT '设备信息',
  `country` VARCHAR(50) NULL DEFAULT NULL COMMENT '国家',
  `user_agent` TEXT NULL COMMENT 'User Agent',
  `referer` TEXT NULL COMMENT '来源页面',
  `conversion_id` INT NULL DEFAULT NULL COMMENT '关联的转化ID（如果已转化）',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `os` VARCHAR(50) NULL DEFAULT NULL COMMENT '操作系统名称',
  `os_version` VARCHAR(50) NULL DEFAULT NULL COMMENT '操作系统版本',
  `browser` VARCHAR(50) NULL DEFAULT NULL COMMENT '浏览器名称',
  `browser_version` VARCHAR(50) NULL DEFAULT NULL COMMENT '浏览器版本',
  `accept_language` VARCHAR(200) NULL DEFAULT NULL COMMENT '接受的语言',
  `accept_encoding` VARCHAR(200) NULL DEFAULT NULL COMMENT '接受的编码',
  `is_bot` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否为机器人/爬虫',
  `device_type` VARCHAR(20) NULL DEFAULT NULL COMMENT '设备类型（mobile/tablet/desktop）',
  `device_brand` VARCHAR(50) NULL DEFAULT NULL COMMENT '设备品牌',
  `device_model` VARCHAR(100) NULL DEFAULT NULL COMMENT '设备型号',
  `url_params` TEXT NULL COMMENT 'URL参数（JSON格式）',
  `all_headers` TEXT NULL COMMENT '所有请求头（JSON格式）',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_click_id`(`click_id` ASC) USING BTREE,
  INDEX `idx_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_publisher_id`(`publisher_id` ASC) USING BTREE,
  INDEX `idx_advertiser_id`(`advertiser_id` ASC) USING BTREE,
  INDEX `idx_short_link_id`(`short_link_id` ASC) USING BTREE,
  INDEX `idx_click_time`(`click_time` ASC) USING BTREE,
  INDEX `idx_conversion_id`(`conversion_id` ASC) USING BTREE,
  INDEX `idx_clicks_time_offer_publisher`(`click_time` ASC, `offer_id` ASC, `publisher_id` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '点击记录归档表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for client_notification_configs
-- ----------------------------
DROP TABLE IF EXISTS `client_notification_configs`;
CREATE TABLE IF NOT EXISTS `client_notification_configs`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '通知配置ID',
  `client_id` INT NOT NULL COMMENT '客户ID',
  `notification_enabled` TINYINT(1) NULL DEFAULT NULL COMMENT '是否启用通知',
  `notify_on_conversion` TINYINT(1) NULL DEFAULT NULL COMMENT '转化时通知',
  `notify_on_high_value` TINYINT(1) NULL DEFAULT NULL COMMENT '高价值转化通知',
  `high_value_threshold` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT '高价值阈值',
  `notify_channels` TEXT NULL COMMENT '通知渠道（JSON格式：[\"telegram\", \"email\", \"sms\"]）',
  `telegram_chat_id` VARCHAR(100) NULL DEFAULT NULL COMMENT 'Telegram Chat ID',
  `email_address` VARCHAR(255) NULL DEFAULT NULL COMMENT '邮箱地址',
  `phone_number` VARCHAR(20) NULL DEFAULT NULL COMMENT '手机号',
  `notification_frequency` VARCHAR(20) NULL DEFAULT NULL COMMENT '通知频率：realtime, hourly, daily',
  `created_at` DATETIME NULL DEFAULT NULL COMMENT '创建时间',
  `updated_at` DATETIME NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `ix_client_notification_configs_client_id`(`client_id` ASC) USING BTREE,
  INDEX `idx_client_notification_config_enabled`(`notification_enabled` ASC) USING BTREE,
  CONSTRAINT `client_notification_configs_ibfk_1` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '客户通知配置表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for clients
-- ----------------------------
DROP TABLE IF EXISTS `clients`;
CREATE TABLE IF NOT EXISTS `clients`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '客户ID',
  `user_id` INT NOT NULL COMMENT '用户ID',
  `company_name` VARCHAR(100) NOT NULL COMMENT '公司名称',
  `contact_person` VARCHAR(50) NULL DEFAULT NULL COMMENT '联系人',
  `phone` VARCHAR(20) NULL DEFAULT NULL COMMENT '联系电话',
  `address` TEXT NULL COMMENT '公司地址',
  `allowed_ips` TEXT NULL COMMENT 'IP白名单，多个IP用逗号分隔，为空则不限制',
  `key` VARCHAR(36) NOT NULL COMMENT '客户唯一标识UUID',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
  `api_enabled` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否允许API访问（开启后允许客户通过API查询产品和广告数据，并显示API对接菜单）',
  `password_change_enabled` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否允许客户修改密码（开启后客户可以修改自己的密码）',
  `chat_id` VARCHAR(20) NULL DEFAULT NULL COMMENT '15位聊天ID',
  `notify_url` VARCHAR(200) NULL DEFAULT NULL COMMENT '客户广告数据通知地址',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_clients_key`(`key` ASC) USING BTREE,
  UNIQUE INDEX `chat_id`(`chat_id` ASC) USING BTREE,
  INDEX `idx_client_user`(`user_id` ASC) USING BTREE,
  FULLTEXT INDEX `ft_clients_search`(`company_name`, `contact_person`) WITH PARSER `ngram`,
  CONSTRAINT `fk_clients_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '客户表（下游商户）' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for conversion_deduction_configs
-- ----------------------------
DROP TABLE IF EXISTS `conversion_deduction_configs`;
CREATE TABLE IF NOT EXISTS `conversion_deduction_configs`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '配置ID',
  `advertiser_id` INT NULL DEFAULT NULL COMMENT '广告主ID（如果配置在广告主级别）',
  `offer_id` INT NULL DEFAULT NULL COMMENT 'Offer ID（如果配置在Offer级别）',
  `publisher_id` INT NULL DEFAULT NULL COMMENT '渠道ID（如果配置在渠道级别）',
  `volume_deduction_ratio` DECIMAL(5, 4) NULL DEFAULT 0.0000 COMMENT '按比例扣量比例（0-1，如0.10表示扣量10%）',
  `amount_deduction_ratio` DECIMAL(5, 4) NULL DEFAULT 0.0000 COMMENT '按比例扣金额比例（0-1，如0.10表示扣金额10%）',
  `deduction_strategy` VARCHAR(50) NULL DEFAULT 'random' COMMENT '扣减策略：random（随机）/proportional（按比例）/round_robin（轮询）',
  `enable_volume_deduction` TINYINT(1) NULL DEFAULT 0 COMMENT '是否启用按比例扣量',
  `enable_amount_deduction` TINYINT(1) NULL DEFAULT 0 COMMENT '是否启用按比例扣金额',
  `priority` INT NULL DEFAULT 0 COMMENT '优先级（数字越大优先级越高）',
  `is_active` TINYINT(1) NULL DEFAULT 1 COMMENT '是否激活',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_advertiser_id`(`advertiser_id` ASC) USING BTREE,
  INDEX `idx_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_publisher_id`(`publisher_id` ASC) USING BTREE,
  INDEX `idx_is_active`(`is_active` ASC) USING BTREE,
  INDEX `idx_priority`(`priority` ASC) USING BTREE,
  CONSTRAINT `conversion_deduction_configs_ibfk_1` FOREIGN KEY (`advertiser_id`) REFERENCES `advertisers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `conversion_deduction_configs_ibfk_2` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `conversion_deduction_configs_ibfk_3` FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '转化扣减配置表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for conversion_deduction_logs
-- ----------------------------
DROP TABLE IF EXISTS `conversion_deduction_logs`;
CREATE TABLE IF NOT EXISTS `conversion_deduction_logs`  (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '记录ID',
  `conversion_id` BIGINT NULL DEFAULT NULL COMMENT '转化记录ID（关联postback_conversions.id，可为NULL因为扣量的转化可能不保存）',
  `click_id` VARCHAR(255) NULL DEFAULT NULL COMMENT '点击ID',
  `advertiser_id` INT NULL DEFAULT NULL COMMENT '广告主ID',
  `offer_id` INT NULL DEFAULT NULL COMMENT 'Offer ID',
  `publisher_id` INT NULL DEFAULT NULL COMMENT '渠道ID',
  `original_volume` INT NULL DEFAULT 1 COMMENT '原始转化数量（通常为1）',
  `original_amount` DECIMAL(10, 2) NOT NULL COMMENT '原始转化金额',
  `deducted_volume` INT NULL DEFAULT 0 COMMENT '扣减的转化数量',
  `deducted_amount` DECIMAL(10, 2) NULL DEFAULT 0.00 COMMENT '扣减的转化金额',
  `final_volume` INT NULL DEFAULT 1 COMMENT '最终转化数量（扣减后）',
  `final_amount` DECIMAL(10, 2) NOT NULL COMMENT '最终转化金额（扣减后）',
  `deduction_config_id` INT NULL DEFAULT NULL COMMENT '使用的扣减配置ID',
  `volume_deduction_ratio` DECIMAL(5, 4) NULL DEFAULT NULL COMMENT '使用的扣量比例',
  `amount_deduction_ratio` DECIMAL(5, 4) NULL DEFAULT NULL COMMENT '使用的扣金额比例',
  `deduction_strategy` VARCHAR(50) NULL DEFAULT NULL COMMENT '使用的扣减策略',
  `deduction_reason` TEXT NULL COMMENT '扣减原因说明',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_conversion_id`(`conversion_id` ASC) USING BTREE,
  INDEX `idx_click_id`(`click_id` ASC) USING BTREE,
  INDEX `idx_advertiser_id`(`advertiser_id` ASC) USING BTREE,
  INDEX `idx_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_publisher_id`(`publisher_id` ASC) USING BTREE,
  INDEX `idx_created_at`(`created_at` ASC) USING BTREE,
  INDEX `idx_deduction_config_id`(`deduction_config_id` ASC) USING BTREE,
  INDEX `idx_cdl_offer_pub_created`(`offer_id` ASC, `publisher_id` ASC, `created_at` ASC) USING BTREE,
  INDEX `idx_cdl_adv_created`(`advertiser_id` ASC, `created_at` ASC) USING BTREE,
  CONSTRAINT `conversion_deduction_logs_ibfk_1` FOREIGN KEY (`advertiser_id`) REFERENCES `advertisers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `conversion_deduction_logs_ibfk_2` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `conversion_deduction_logs_ibfk_3` FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `conversion_deduction_logs_ibfk_4` FOREIGN KEY (`deduction_config_id`) REFERENCES `conversion_deduction_configs` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '转化扣减执行记录表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for countries
-- ----------------------------
DROP TABLE IF EXISTS `countries`;
CREATE TABLE IF NOT EXISTS `countries`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `alpha_2_code` char(2) NOT NULL COMMENT '国家二字代码',
  `alpha_3_code` char(3) NOT NULL COMMENT '国家三字代码',
  `numeric_code` char(3) NOT NULL COMMENT '国家数字代码',
  `country_name_zh` VARCHAR(100) NOT NULL COMMENT '国家中文名称',
  `country_name_en` VARCHAR(100) NOT NULL COMMENT '国家英文名称',
  `official_name_zh` VARCHAR(150) NULL DEFAULT NULL COMMENT '官方中文名称',
  `official_name_en` VARCHAR(150) NULL DEFAULT NULL COMMENT '官方英文名称',
  `independent_status` TINYINT(1) NULL DEFAULT 1 COMMENT '是否独立国家',
  `continent` VARCHAR(50) NULL DEFAULT NULL COMMENT '所属大洲',
  `subregion` VARCHAR(50) NULL DEFAULT NULL COMMENT '所属地区',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `alpha_2_code`(`alpha_2_code` ASC) USING BTREE,
  UNIQUE INDEX `alpha_3_code`(`alpha_3_code` ASC) USING BTREE,
  UNIQUE INDEX `numeric_code`(`numeric_code` ASC) USING BTREE,
  INDEX `idx_country_name_zh`(`country_name_zh` ASC) USING BTREE,
  INDEX `idx_country_name_en`(`country_name_en` ASC) USING BTREE,
  INDEX `idx_continent`(`continent` ASC) USING BTREE,
  INDEX `idx_subregion`(`subregion` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'ISO 3166-1 国家代码表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for country_aliases
-- ----------------------------
DROP TABLE IF EXISTS `country_aliases`;
CREATE TABLE IF NOT EXISTS `country_aliases`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `alias_name` VARCHAR(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '别名原文',
  `alias_normalized` VARCHAR(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '规范化键',
  `alpha_2_code` char(2) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '映射 ISO 二字代码',
  `remark` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '备注',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_country_alias_normalized`(`alias_normalized` ASC) USING BTREE,
  INDEX `idx_country_alias_alpha2`(`alpha_2_code` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '国家英文别名映射表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for offer_caps
-- ----------------------------
DROP TABLE IF EXISTS `offer_caps`;
CREATE TABLE IF NOT EXISTS `offer_caps`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Cap配置ID',
  `cap_type` VARCHAR(50) NOT NULL COMMENT 'Cap类型：advertiser_offer/offer',
  `advertiser_id` INT NULL DEFAULT NULL COMMENT '广告主ID（如果是advertiser_offer类型）',
  `offer_id` INT NOT NULL COMMENT 'Offer ID',
  `publisher_id` INT NULL DEFAULT NULL COMMENT '渠道ID（如果为空，表示所有渠道）',
  `daily_cap` INT NULL DEFAULT NULL COMMENT '每日Cap',
  `total_cap` INT NULL DEFAULT NULL COMMENT '总Cap',
  `current_daily_count` INT NULL DEFAULT NULL COMMENT '当前每日计数',
  `current_total_count` INT NULL DEFAULT NULL COMMENT '当前总计数',
  `cap_start_date` DATETIME NULL DEFAULT NULL COMMENT 'Cap开始日期（用于Total Cap）',
  `is_active` TINYINT(1) NULL DEFAULT NULL COMMENT '是否激活',
  `created_at` DATETIME NOT NULL COMMENT '创建时间',
  `updated_at` DATETIME NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_advertiser_id`(`advertiser_id` ASC) USING BTREE,
  INDEX `idx_publisher_id`(`publisher_id` ASC) USING BTREE,
  INDEX `idx_is_active`(`is_active` ASC) USING BTREE,
  INDEX `idx_cap_type`(`cap_type` ASC) USING BTREE,
  INDEX `idx_offer_caps_lookup`(`offer_id` ASC, `publisher_id` ASC, `is_active` ASC, `cap_type` ASC) USING BTREE,
  CONSTRAINT `offer_caps_ibfk_1` FOREIGN KEY (`advertiser_id`) REFERENCES `advertisers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `offer_caps_ibfk_2` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `offer_caps_ibfk_3` FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = 'Offer Cap限额配置表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for offer_discounts
-- ----------------------------
DROP TABLE IF EXISTS `offer_discounts`;
CREATE TABLE IF NOT EXISTS `offer_discounts`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '扣量配置ID',
  `discount_type` VARCHAR(50) NOT NULL COMMENT '扣量类型：offer/channel',
  `offer_id` INT NULL DEFAULT NULL COMMENT 'Offer ID（如果是offer类型）',
  `publisher_id` INT NOT NULL COMMENT '渠道ID',
  `discount_ratio` DECIMAL(12, 4) NOT NULL COMMENT '扣量比例（0-100）',
  `is_active` TINYINT(1) NULL DEFAULT NULL COMMENT '是否激活',
  `created_at` DATETIME NOT NULL COMMENT '创建时间',
  `updated_at` DATETIME NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_is_active`(`is_active` ASC) USING BTREE,
  INDEX `idx_publisher_id`(`publisher_id` ASC) USING BTREE,
  INDEX `idx_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_discount_type`(`discount_type` ASC) USING BTREE,
  CONSTRAINT `offer_discounts_ibfk_1` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `offer_discounts_ibfk_2` FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = 'Offer扣量/扣价配置表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for offer_publisher_assignments
-- ----------------------------
DROP TABLE IF EXISTS `offer_publisher_assignments`;
CREATE TABLE IF NOT EXISTS `offer_publisher_assignments`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '分配ID',
  `offer_id` INT NOT NULL COMMENT 'Offer ID',
  `publisher_id` INT NOT NULL COMMENT '渠道ID',
  `downstream_cap` INT NULL DEFAULT NULL COMMENT '该渠道的下游转化上限',
  `affiliate_payout` DECIMAL(10, 2) NULL DEFAULT NULL COMMENT '该渠道的扣价后给渠道的金额（PO扣价后）',
  `is_active` TINYINT(1) NULL DEFAULT 1 COMMENT '是否激活',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_offer_publisher`(`offer_id` ASC, `publisher_id` ASC) USING BTREE,
  INDEX `idx_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_publisher_id`(`publisher_id` ASC) USING BTREE,
  INDEX `idx_is_active`(`is_active` ASC) USING BTREE,
  CONSTRAINT `offer_publisher_assignments_ibfk_1` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `offer_publisher_assignments_ibfk_2` FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = 'Offer-渠道分配表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for offers
-- ----------------------------
DROP TABLE IF EXISTS `offers`;
CREATE TABLE IF NOT EXISTS `offers`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Offer ID（主键）',
  `offer_name` VARCHAR(200) NOT NULL COMMENT 'Offer名称',
  `advertiser_offer_id` VARCHAR(100) NULL DEFAULT NULL COMMENT '上游系统中的Offer ID（ADV Offer ID）',
  `advertiser_id` INT NOT NULL COMMENT '关联的广告主ID',
  `preview_link` TEXT NULL COMMENT '预览链接',
  `payout` DECIMAL(10, 2) NULL DEFAULT NULL COMMENT '上游支付金额（PO）',
  `affiliate_payout` DECIMAL(10, 2) NULL DEFAULT NULL COMMENT '扣价后给渠道的金额（PO扣价后）',
  `country` VARCHAR(50) NULL DEFAULT NULL COMMENT '国家',
  `category` VARCHAR(50) NULL DEFAULT NULL COMMENT '分类',
  `type` VARCHAR(50) NULL DEFAULT NULL COMMENT '类型',
  `status` VARCHAR(20) NULL DEFAULT 'Active' COMMENT '状态：Active/Inactive',
  `upstream_cap` INT NULL DEFAULT NULL COMMENT '上游转化上限',
  `downstream_cap` INT NULL DEFAULT NULL COMMENT '下游转化上限',
  `advertiser_tracklink` TEXT NULL COMMENT '上游的Tracklink（不显示给下游，建立单子时配置我们的参数）',
  `downstream_tracklink` TEXT NULL COMMENT '生成给下游的Tracklink',
  `postback_url` TEXT NULL COMMENT 'Postback URL（配置我们的参数）',
  `postback_method` VARCHAR(10) NULL DEFAULT 'GET' COMMENT 'Postback请求方式：GET/POST',
  `is_active` TINYINT(1) NULL DEFAULT 1 COMMENT '是否激活',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `click_validity_hours` INT NULL DEFAULT 720 COMMENT '点击有效期（小时），默认720小时（30天）',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_advertiser_id`(`advertiser_id` ASC) USING BTREE,
  INDEX `idx_status`(`status` ASC) USING BTREE,
  INDEX `idx_is_active`(`is_active` ASC) USING BTREE,
  INDEX `idx_country`(`country` ASC) USING BTREE,
  FULLTEXT INDEX `ft_offer_name`(`offer_name`),
  CONSTRAINT `offers_ibfk_1` FOREIGN KEY (`advertiser_id`) REFERENCES `advertisers` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = 'Offer表（单子表）' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for pending_postback_conversions
-- ----------------------------
DROP TABLE IF EXISTS `pending_postback_conversions`;
CREATE TABLE IF NOT EXISTS `pending_postback_conversions`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '待确认记录ID',
  `platform` VARCHAR(50) NOT NULL COMMENT '平台名称',
  `conversion_id` VARCHAR(255) NOT NULL COMMENT '转化ID',
  `event_name` VARCHAR(100) NULL DEFAULT NULL COMMENT '事件名称',
  `event_value` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT '事件价值',
  `original_payout` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT '原始支付金额（PO）',
  `payout` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT '扣后支付金额（PO(扣)）',
  `devad_id` VARCHAR(255) NULL DEFAULT NULL COMMENT '设备广告ID',
  `os` VARCHAR(20) NULL DEFAULT NULL COMMENT '操作系统',
  `carrier` VARCHAR(50) NULL DEFAULT NULL COMMENT '用户运营商',
  `ip` VARCHAR(50) NULL DEFAULT NULL COMMENT 'IP地址',
  `gid` VARCHAR(100) NULL DEFAULT NULL COMMENT '渠道ID',
  `product_id` INT NULL DEFAULT NULL COMMENT '关联的产品ID',
  `client_id` INT NULL DEFAULT NULL COMMENT '关联的客户ID',
  `click_id` VARCHAR(255) NULL DEFAULT NULL COMMENT '关联的Click ID',
  `click_time` DATETIME NULL DEFAULT NULL COMMENT '点击时间',
  `raw_data` TEXT NULL COMMENT '原始回调数据（JSON格式）',
  `request_ip` VARCHAR(50) NOT NULL COMMENT '请求IP地址（不在白名单）',
  `status` VARCHAR(20) NULL DEFAULT NULL COMMENT '状态：pending(待确认)/approved(已批准)/rejected(已拒绝)',
  `telegram_message_id` INT NULL DEFAULT NULL COMMENT 'Telegram 消息ID（用于更新消息）',
  `telegram_chat_id` VARCHAR(50) NULL DEFAULT NULL COMMENT 'Telegram Chat ID',
  `created_at` DATETIME NOT NULL COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL COMMENT '更新时间',
  `approved_at` DATETIME NULL DEFAULT NULL COMMENT '批准时间',
  `rejected_at` DATETIME NULL DEFAULT NULL COMMENT '拒绝时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `product_id`(`product_id` ASC) USING BTREE,
  INDEX `client_id`(`client_id` ASC) USING BTREE,
  INDEX `ix_pending_postback_conversions_platform`(`platform` ASC) USING BTREE,
  INDEX `idx_status`(`status` ASC) USING BTREE,
  INDEX `idx_request_ip`(`request_ip` ASC) USING BTREE,
  INDEX `idx_created_at`(`created_at` ASC) USING BTREE,
  INDEX `idx_pending_click_id`(`click_id` ASC) USING BTREE,
  CONSTRAINT `pending_postback_conversions_ibfk_1` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `pending_postback_conversions_ibfk_2` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '待确认Postback转化表（非白名单IP请求）' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for postback_conversions
-- ----------------------------
DROP TABLE IF EXISTS `postback_conversions`;
CREATE TABLE IF NOT EXISTS `postback_conversions`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '转化记录ID',
  `platform` VARCHAR(50) NOT NULL COMMENT '平台名称：macan, addermobi等',
  `conversion_id` VARCHAR(255) NOT NULL COMMENT '转化ID（各平台唯一标识，如Macan的clk_id）',
  `transaction_id` VARCHAR(255) NULL DEFAULT NULL COMMENT '上游事务ID（幂等）',
  `request_id` VARCHAR(128) NULL DEFAULT NULL COMMENT '请求防重放ID',
  `event_name` VARCHAR(100) NULL DEFAULT NULL COMMENT '事件名称（如purchase, install等）',
  `event_value` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT '事件价值（购买价格等）',
  `original_payout` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT '原始支付金额（PO）',
  `payout` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT '支付金额（确认的广告单元价格）',
  `devad_id` VARCHAR(255) NULL DEFAULT NULL COMMENT '设备广告ID（IDFA或GAID）',
  `os` VARCHAR(20) NULL DEFAULT NULL COMMENT '操作系统（IOS或Android）',
  `carrier` VARCHAR(50) NULL DEFAULT NULL COMMENT '用户运营商',
  `ip` VARCHAR(50) NULL DEFAULT NULL COMMENT '点击IP地址',
  `gid` VARCHAR(100) NULL DEFAULT NULL COMMENT '渠道ID（Channel ID）',
  `product_id` INT NULL DEFAULT NULL COMMENT '关联的产品ID（可选，用于关联产品）',
  `client_id` INT NULL DEFAULT NULL COMMENT '关联的客户ID（可选，用于关联客户）',
  `offer_id` INT NULL DEFAULT NULL COMMENT 'Offer ID（转化时快照）',
  `publisher_id` INT NULL DEFAULT NULL COMMENT '渠道 ID（转化时快照）',
  `advertiser_id` INT NULL DEFAULT NULL COMMENT '广告主 ID（转化时快照）',
  `raw_data` TEXT NULL COMMENT '原始回调数据（JSON格式，保存完整回调数据以便后续分析）',
  `created_at` DATETIME NOT NULL COMMENT '创建时间（记录回调接收时间）',
  `click_id` VARCHAR(255) NULL DEFAULT NULL COMMENT '关联的Click ID',
  `click_time` DATETIME NULL DEFAULT NULL COMMENT '点击时间',
  `conversion_status` VARCHAR(20) NULL DEFAULT 'Pending' COMMENT '转化状态：Approved/Pending',
  `is_deducted` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已被扣减',
  `deduction_type` VARCHAR(20) NULL DEFAULT NULL COMMENT '扣减类型：volume（扣量）/amount（扣金额）/both（两者）',
  `original_volume` INT NULL DEFAULT 1 COMMENT '原始转化数量',
  `deducted_volume` INT NULL DEFAULT 0 COMMENT '扣减的转化数量',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_postback_platform_conversion_event`(`platform` ASC, `conversion_id` ASC, `event_name` ASC) USING BTREE COMMENT '防止同一平台的同一转化ID和事件名称重复处理',
  UNIQUE INDEX `uq_postback_transaction_id`(`transaction_id` ASC) USING BTREE,
  UNIQUE INDEX `uq_postback_request_id`(`request_id` ASC) USING BTREE,
  INDEX `idx_postback_platform_conversion`(`platform` ASC, `conversion_id` ASC) USING BTREE COMMENT '平台和转化ID复合索引（优化平台查询）',
  INDEX `idx_postback_product`(`product_id` ASC) USING BTREE COMMENT '产品ID索引（优化产品关联查询）',
  INDEX `idx_postback_client`(`client_id` ASC) USING BTREE COMMENT '客户ID索引（优化客户关联查询）',
  INDEX `idx_postback_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_postback_publisher_id`(`publisher_id` ASC) USING BTREE,
  INDEX `idx_postback_advertiser_id`(`advertiser_id` ASC) USING BTREE,
  INDEX `idx_postback_created_at`(`created_at` ASC) USING BTREE COMMENT '创建时间索引（优化时间范围查询）',
  INDEX `idx_postback_platform_event`(`platform` ASC, `event_name` ASC) USING BTREE COMMENT '平台和事件名称复合索引（优化事件统计查询）',
  INDEX `idx_click_id`(`click_id` ASC) USING BTREE,
  INDEX `idx_conversion_status`(`conversion_status` ASC) USING BTREE,
  INDEX `idx_postback_conversion_id`(`conversion_id` ASC) USING BTREE,
  INDEX `idx_is_deducted`(`is_deducted` ASC) USING BTREE,
  INDEX `idx_deduction_type`(`deduction_type` ASC) USING BTREE,
  INDEX `idx_postback_created_at_click_id`(`created_at` ASC, `click_id` ASC) USING BTREE,
  INDEX `idx_postback_created_at_platform`(`created_at` ASC, `platform` ASC) USING BTREE,
  INDEX `idx_postback_created_at_status`(`created_at` ASC, `conversion_status` ASC) USING BTREE,
  CONSTRAINT `postback_conversions_ibfk_1` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `postback_conversions_ibfk_2` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `postback_conversions_ibfk_advertiser` FOREIGN KEY (`advertiser_id`) REFERENCES `advertisers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `postback_conversions_ibfk_offer` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `postback_conversions_ibfk_publisher` FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = 'Postback转化事件表，统一存储所有平台的postback回调数据' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for postback_forward_logs
-- ----------------------------
DROP TABLE IF EXISTS `postback_forward_logs`;
CREATE TABLE IF NOT EXISTS `postback_forward_logs`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '转发日志ID',
  `conversion_id` INT NOT NULL COMMENT '关联的转化记录ID',
  `product_id` INT NULL DEFAULT NULL COMMENT '产品ID',
  `publisher_id` INT NULL DEFAULT NULL COMMENT '渠道ID（转发到渠道时使用）',
  `downstream_url` VARCHAR(500) NOT NULL COMMENT '下游URL',
  `request_method` VARCHAR(10) NOT NULL COMMENT '请求方式：GET 或 POST',
  `request_data` TEXT NULL COMMENT '请求数据（JSON格式，用于POST请求）',
  `request_params` TEXT NULL COMMENT '请求参数（URL参数，用于GET请求）',
  `response_status` INT NULL DEFAULT NULL COMMENT '响应状态码',
  `response_body` TEXT NULL COMMENT '响应内容',
  `success` TINYINT(1) NULL DEFAULT NULL COMMENT '是否转发成功',
  `error_message` TEXT NULL COMMENT '错误信息（如果转发失败）',
  `retry_count` INT NULL DEFAULT NULL COMMENT '重试次数',
  `created_at` DATETIME NOT NULL COMMENT '创建时间',
  `completed_at` DATETIME NULL DEFAULT NULL COMMENT '完成时间',
  `pii_scrubbed_at` DATETIME NULL DEFAULT NULL COMMENT 'PII 按保留策略清理时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_forward_log_product`(`product_id` ASC) USING BTREE,
  INDEX `idx_forward_log_conversion`(`conversion_id` ASC) USING BTREE,
  INDEX `idx_forward_log_success`(`success` ASC) USING BTREE,
  INDEX `idx_forward_log_created_at`(`created_at` ASC) USING BTREE,
  INDEX `idx_forward_log_pii_retention`(`pii_scrubbed_at` ASC, `created_at` ASC, `id` ASC) USING BTREE,
  INDEX `idx_forward_log_publisher`(`publisher_id` ASC) USING BTREE,
  CONSTRAINT `postback_forward_logs_ibfk_1` FOREIGN KEY (`conversion_id`) REFERENCES `postback_conversions` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `postback_forward_logs_ibfk_2` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `postback_forward_logs_ibfk_3` FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = 'Postback下游转发日志表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for postback_forward_queue
-- ----------------------------
DROP TABLE IF EXISTS `postback_forward_queue`;
CREATE TABLE IF NOT EXISTS `postback_forward_queue`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '队列ID',
  `conversion_id` INT NOT NULL COMMENT '关联的转化记录ID',
  `product_id` INT NULL DEFAULT NULL COMMENT '产品ID（产品级转发时使用）',
  `publisher_id` INT NULL DEFAULT NULL COMMENT '渠道ID（渠道级转发时使用）',
  `downstream_url` VARCHAR(500) NOT NULL COMMENT '下游URL',
  `request_method` VARCHAR(10) NOT NULL COMMENT '请求方式：GET 或 POST',
  `request_data` TEXT NULL COMMENT '请求数据（JSON格式，用于POST请求）',
  `request_params` TEXT NULL COMMENT '请求参数（URL参数，用于GET请求）',
  `retry_count` INT NULL DEFAULT NULL COMMENT '已重试次数',
  `next_retry_time` DATETIME NOT NULL COMMENT '下次重试时间',
  `created_at` DATETIME NOT NULL COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_forward_queue_time`(`next_retry_time` ASC) USING BTREE,
  INDEX `idx_forward_queue_conversion`(`conversion_id` ASC) USING BTREE,
  INDEX `ix_postback_forward_queue_product_id`(`product_id` ASC) USING BTREE,
  INDEX `ix_postback_forward_queue_created_at`(`created_at` ASC) USING BTREE,
  INDEX `idx_forward_queue_publisher`(`publisher_id` ASC) USING BTREE,
  CONSTRAINT `postback_forward_queue_ibfk_1` FOREIGN KEY (`conversion_id`) REFERENCES `postback_conversions` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `postback_forward_queue_ibfk_2` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `postback_forward_queue_ibfk_publisher` FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = 'Postback转发重试队列表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for postback_ip_whitelist
-- ----------------------------
DROP TABLE IF EXISTS `postback_ip_whitelist`;
CREATE TABLE IF NOT EXISTS `postback_ip_whitelist`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '白名单ID',
  `ip_address` VARCHAR(45) NOT NULL COMMENT 'IP地址（支持IPv4和IPv6）',
  `description` VARCHAR(255) NULL DEFAULT NULL COMMENT 'IP地址描述/备注',
  `is_active` TINYINT(1) NOT NULL COMMENT '是否启用',
  `created_at` DATETIME NOT NULL COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `ix_postback_ip_whitelist_ip_address`(`ip_address` ASC) USING BTREE,
  INDEX `idx_is_active`(`is_active` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = 'Postback接收IP白名单表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for postback_notifications
-- ----------------------------
DROP TABLE IF EXISTS `postback_notifications`;
CREATE TABLE IF NOT EXISTS `postback_notifications`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '通知记录ID',
  `conversion_id` INT NULL DEFAULT NULL COMMENT '转化记录ID（汇总通知时为NULL）',
  `client_id` INT NULL DEFAULT NULL COMMENT '客户ID',
  `product_id` INT NULL DEFAULT NULL COMMENT '产品ID',
  `publisher_id` INT NULL DEFAULT NULL COMMENT '渠道ID（转发通知时使用）',
  `notification_type` VARCHAR(50) NULL DEFAULT NULL COMMENT '通知类型：conversion, high_value, error, forward, summary_hourly, summary_daily',
  `notification_channel` VARCHAR(50) NOT NULL COMMENT '通知渠道：telegram, email, sms, webhook',
  `notification_status` VARCHAR(20) NULL DEFAULT NULL COMMENT '通知状态：sent, failed, pending',
  `notification_message` TEXT NULL COMMENT '通知消息内容',
  `error_message` TEXT NULL COMMENT '错误信息（如果失败）',
  `auto_notify` TINYINT(1) NULL DEFAULT NULL COMMENT '是否自动通知（True=自动通知，False=手动通知）',
  `postback_url` TEXT NULL COMMENT 'Postback URL（转发通知时使用）',
  `created_at` DATETIME NOT NULL COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_postback_notification_publisher`(`publisher_id` ASC) USING BTREE,
  INDEX `idx_postback_notification_conversion`(`conversion_id` ASC) USING BTREE,
  INDEX `idx_postback_notification_product`(`product_id` ASC) USING BTREE,
  INDEX `idx_postback_notification_created_at`(`created_at` ASC) USING BTREE,
  INDEX `idx_postback_notification_client`(`client_id` ASC) USING BTREE,
  INDEX `idx_postback_notification_auto_notify`(`auto_notify` ASC) USING BTREE,
  INDEX `idx_postback_notification_status`(`notification_status` ASC) USING BTREE,
  CONSTRAINT `postback_notifications_ibfk_1` FOREIGN KEY (`conversion_id`) REFERENCES `postback_conversions` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `postback_notifications_ibfk_2` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `postback_notifications_ibfk_3` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `postback_notifications_ibfk_4` FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = 'Postback通知发送记录表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for product_assignments
-- ----------------------------
DROP TABLE IF EXISTS `product_assignments`;
CREATE TABLE IF NOT EXISTS `product_assignments`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '分配记录ID',
  `product_id` INT NOT NULL COMMENT '产品ID',
  `client_id` INT NOT NULL COMMENT '客户ID',
  `start_date` DATE NOT NULL COMMENT '分配开始日期',
  `end_date` DATE NULL DEFAULT NULL COMMENT '分配结束日期（NULL表示当前有效）',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_product_assignments_client`(`client_id` ASC) USING BTREE,
  INDEX `idx_product_assignments_date`(`product_id` ASC, `start_date` ASC, `end_date` ASC) USING BTREE,
  INDEX `idx_product_assignments_active`(`product_id` ASC, `end_date` ASC) USING BTREE,
  CONSTRAINT `fk_product_assignments_client` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `fk_product_assignments_product` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '产品分配历史表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for product_notification_configs
-- ----------------------------
DROP TABLE IF EXISTS `product_notification_configs`;
CREATE TABLE IF NOT EXISTS `product_notification_configs`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '通知配置ID',
  `product_id` INT NOT NULL COMMENT '产品ID',
  `notification_enabled` TINYINT(1) NULL DEFAULT NULL COMMENT '是否启用通知',
  `notify_on_conversion` TINYINT(1) NULL DEFAULT NULL COMMENT '转化时通知',
  `notify_on_high_value` TINYINT(1) NULL DEFAULT NULL COMMENT '高价值转化通知',
  `high_value_threshold` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT '高价值阈值',
  `notify_channels` TEXT NULL COMMENT '通知渠道（JSON格式：[\"telegram\", \"email\", \"sms\"]）',
  `telegram_chat_id` VARCHAR(100) NULL DEFAULT NULL COMMENT 'Telegram Chat ID',
  `email_address` VARCHAR(255) NULL DEFAULT NULL COMMENT '邮箱地址',
  `phone_number` VARCHAR(20) NULL DEFAULT NULL COMMENT '手机号',
  `notification_frequency` VARCHAR(20) NULL DEFAULT NULL COMMENT '通知频率：realtime, hourly, daily',
  `created_at` DATETIME NULL DEFAULT NULL COMMENT '创建时间',
  `updated_at` DATETIME NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `ix_product_notification_configs_product_id`(`product_id` ASC) USING BTREE,
  INDEX `idx_product_notification_config_enabled`(`notification_enabled` ASC) USING BTREE,
  CONSTRAINT `product_notification_configs_ibfk_1` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '产品通知配置表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for products
-- ----------------------------
DROP TABLE IF EXISTS `products`;
CREATE TABLE IF NOT EXISTS `products`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '产品ID',
  `client_id` INT NOT NULL COMMENT '客户ID',
  `name` VARCHAR(100) NOT NULL COMMENT '产品名称',
  `ecpm_deduct_ratio` DECIMAL(12, 4) NOT NULL DEFAULT 0 COMMENT 'eCPM减扣比例',
  `revenue_deduct_ratio` DECIMAL(12, 4) NOT NULL DEFAULT 0 COMMENT '收益减扣比例',
  `cplpo_deduct_ratio` DECIMAL(12, 4) NOT NULL DEFAULT 0 COMMENT 'CPL PO减扣比例 ',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
  `notification_address` VARCHAR(500) NULL DEFAULT NULL COMMENT '通知地址（Telegram Chat ID、邮箱地址、Webhook URL等，用于接收转化通知）',
  `downstream_postback_method` VARCHAR(10) NULL DEFAULT 'GET' COMMENT '下游 Postback 请求方式：GET 或 POST（默认GET）',
  `downstream_postback_success_check` TEXT NULL COMMENT '产品下游 Postback 转发成功检查配置（JSON格式，用于检查产品下游 Postback URL 的响应内容是否表示成功）',
  `downstream_postback_url` VARCHAR(500) NULL DEFAULT NULL COMMENT '下游 Postback URL（可选，配置后将自动转发转化数据）',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_product_client`(`client_id` ASC) USING BTREE,
  UNIQUE INDEX `uq_products_name`(`name` ASC) USING BTREE,
  FULLTEXT INDEX `ft_products_name`(`name`) WITH PARSER `ngram`,
  FULLTEXT INDEX `ft_name`(`name`),
  CONSTRAINT `fk_products_client` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '产品表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for publishers
-- ----------------------------
DROP TABLE IF EXISTS `publishers`;
CREATE TABLE IF NOT EXISTS `publishers`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '渠道ID',
  `publisher_name` VARCHAR(100) NOT NULL COMMENT '渠道名称',
  `email` VARCHAR(255) NULL DEFAULT NULL COMMENT '邮箱（可选）',
  `price_discount` DECIMAL(5, 2) NULL DEFAULT 0.00 COMMENT '渠道级别的价格扣量比例（0-100）',
  `postback_url` TEXT NULL COMMENT 'Postback URL（渠道的Postback配置）',
  `postback_method` VARCHAR(10) NULL DEFAULT 'GET' COMMENT 'Postback请求方式：GET/POST',
  `postback_success_check` TEXT NULL COMMENT '渠道 Postback 转发成功检查配置（JSON格式，用于检查渠道 Postback URL 的响应内容是否表示成功）',
  `active_advertiser_count` INT NULL DEFAULT 0 COMMENT '活跃的广告主数量',
  `client_id` INT NULL DEFAULT NULL COMMENT '关联的客户ID',
  `is_active` TINYINT(1) NULL DEFAULT 1 COMMENT '是否激活',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_publisher_name`(`publisher_name` ASC) USING BTREE,
  INDEX `idx_is_active`(`is_active` ASC) USING BTREE,
  INDEX `idx_client_id`(`client_id` ASC) USING BTREE,
  CONSTRAINT `fk_publishers_client_id` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '渠道表（下游）' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for scheduled_tasks
-- ----------------------------
DROP TABLE IF EXISTS `scheduled_tasks`;
CREATE TABLE IF NOT EXISTS `scheduled_tasks`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '定时任务ID',
  `task_name` VARCHAR(100) NOT NULL COMMENT '任务名称（唯一）',
  `last_run_time` DATETIME(6) NULL DEFAULT NULL COMMENT '上次开始执行时间',
  `last_finish_time` DATETIME(6) NULL DEFAULT NULL COMMENT '上次完成执行时间',
  `is_running` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否正在执行',
  `last_run_pid` INT NULL DEFAULT NULL COMMENT '上次执行的进程ID',
  `last_run_host` VARCHAR(100) NULL DEFAULT NULL COMMENT '上次执行的服务器主机名',
  `run_count` INT NOT NULL DEFAULT 0 COMMENT '执行次数',
  `success_count` INT NOT NULL DEFAULT 0 COMMENT '成功次数',
  `error_count` INT NOT NULL DEFAULT 0 COMMENT '失败次数',
  `last_error` TEXT NULL COMMENT '最后一次错误信息',
  `status` VARCHAR(20) NOT NULL DEFAULT 'idle' COMMENT '任务状态 idle/running/success/error',
  `retry_count` INT NOT NULL DEFAULT 0 COMMENT '连续失败重试计数',
  `last_success_at` DATETIME NULL DEFAULT NULL COMMENT '上次成功完成时间',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  `cron_expression` VARCHAR(100) NULL DEFAULT NULL COMMENT 'Cron表达式',
  `description` TEXT NULL COMMENT '任务描述',
  `function_path` VARCHAR(255) NULL DEFAULT NULL COMMENT '执行函数路径（例如：app.scheduler_module.tasks.simple_task.simple_info_task）',
  `task_params` JSON NULL COMMENT '任务扩展参数（JSON），如 GAM 产品白名单',
  `standard_report_type` VARCHAR(20) NULL DEFAULT NULL COMMENT '标准数据维度（country/cross/unit/daily），用于多维度汇总选源',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_scheduled_tasks_task_name`(`task_name` ASC) USING BTREE,
  INDEX `idx_scheduled_task_is_running`(`is_running` ASC) USING BTREE,
  INDEX `idx_scheduled_task_is_active`(`is_active` ASC) USING BTREE,
  INDEX `idx_scheduled_task_status`(`status` ASC) USING BTREE,
  FULLTEXT INDEX `ft_tasks_search`(`task_name`, `description`) WITH PARSER `ngram`
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '定时任务执行记录表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for short_links
-- ----------------------------
DROP TABLE IF EXISTS `short_links`;
CREATE TABLE IF NOT EXISTS `short_links`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '短链接ID',
  `short_code` VARCHAR(20) NOT NULL COMMENT '短链接代码（唯一）',
  `original_url` TEXT NOT NULL COMMENT '原始URL',
  `title` VARCHAR(200) NULL DEFAULT NULL COMMENT '短链接标题（可选）',
  `description` TEXT NULL COMMENT '短链接描述（可选）',
  `created_by` INT NULL DEFAULT NULL COMMENT '创建者用户ID',
  `offer_id` INT NULL DEFAULT NULL COMMENT '关联的Offer ID',
  `channel_id` INT NULL DEFAULT NULL COMMENT '关联的渠道ID（Publisher ID）',
  `show_count` INT NOT NULL DEFAULT 0 COMMENT '展示次数',
  `click_count` INT NOT NULL DEFAULT 0 COMMENT '点击次数',
  `is_active` TINYINT(1) NULL DEFAULT 1 COMMENT '是否激活',
  `expires_at` DATETIME NULL DEFAULT NULL COMMENT '过期时间（可选）',
  `facebook_pixel_id` VARCHAR(50) NULL DEFAULT NULL COMMENT 'Facebook 像素 ID',
  `facebook_access_token` VARCHAR(500) NULL DEFAULT NULL COMMENT 'Facebook 访问令牌',
  `facebook_api_version` VARCHAR(20) NULL DEFAULT NULL COMMENT 'Facebook API 版本',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `short_code`(`short_code` ASC) USING BTREE,
  INDEX `idx_short_link_created_by`(`created_by` ASC) USING BTREE,
  INDEX `idx_short_link_active`(`is_active` ASC) USING BTREE,
  INDEX `idx_short_link_created_at`(`created_at` ASC) USING BTREE,
  INDEX `idx_short_link_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_short_link_channel_id`(`channel_id` ASC) USING BTREE,
  INDEX `idx_short_links_created_by_active_created`(`created_by` ASC, `is_active` ASC, `created_at` DESC) USING BTREE,
  INDEX `idx_short_links_offer_channel`(`offer_id` ASC, `channel_id` ASC) USING BTREE,
  FULLTEXT INDEX `ft_title`(`title`),
  FULLTEXT INDEX `ft_description`(`description`),
  CONSTRAINT `short_links_ibfk_1` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `short_links_ibfk_channel` FOREIGN KEY (`channel_id`) REFERENCES `publishers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `short_links_ibfk_offer` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '短链接表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for tb_search_data
-- ----------------------------
DROP TABLE IF EXISTS `tb_search_data`;
CREATE TABLE IF NOT EXISTS `tb_search_data`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `date` DATE NOT NULL COMMENT '日期（仅日期，无时间部分）',
  `product_id` INT NOT NULL COMMENT '产品ID',
  `country_code` VARCHAR(100) NULL DEFAULT NULL COMMENT '国家代码（ISO 二字母；未识别时保留原始国名；无国家时为 NULL）',
  `redirects` INT NOT NULL DEFAULT 0 COMMENT 'REDIRECTS',
  `searches` INT NOT NULL DEFAULT 0 COMMENT 'SEARCHES',
  `monetized` INT NOT NULL DEFAULT 0 COMMENT 'MONETIZED',
  `clicks` INT NOT NULL DEFAULT 0 COMMENT 'CLICKS',
  `revenue` DECIMAL(12,4) NOT NULL DEFAULT 0.0000 COMMENT 'REVENUE（扣减后）',
  `rpm` DECIMAL(10,4) NOT NULL DEFAULT 0.0000 COMMENT 'RPM（扣减后）',
  `revenue_before_deduct` DECIMAL(12,4) NOT NULL DEFAULT 0.0000 COMMENT 'REVENUE（扣减前）',
  `rpm_before_deduct` DECIMAL(10,4) NOT NULL DEFAULT 0.0000 COMMENT 'RPM（扣减前）',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_tb_search_data_date_product_country`(`date` ASC, `product_id` ASC, `country_code` ASC) USING BTREE,
  INDEX `idx_tb_search_data_product`(`product_id` ASC) USING BTREE COMMENT '外键 tb_search_data_ibfk_1 依赖，不可删',
  INDEX `idx_tb_search_data_country_code`(`country_code` ASC) USING BTREE,
  CONSTRAINT `tb_search_data_ibfk_1` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = 'TB搜索数据表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for third_party_report_logs
-- ----------------------------
DROP TABLE IF EXISTS `third_party_report_logs`;
CREATE TABLE IF NOT EXISTS `third_party_report_logs`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '日志ID',
  `source` VARCHAR(50) NOT NULL COMMENT '上报来源：short_link/斗篷点击, postback/转化回调',
  `adsid` VARCHAR(500) NOT NULL COMMENT '广告事件ID',
  `event` VARCHAR(50) NOT NULL COMMENT '事件类型：ViewContent, Purchase',
  `event_key` VARCHAR(64) NOT NULL COMMENT '事件幂等键：稳定事件身份字段的 SHA-256（ViewContent 不含后补 conversion_id）',
  `use_hash` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否对email、ip、phone进行哈希处理：True=哈希，False=不哈希',
  `email` VARCHAR(255) NULL DEFAULT NULL COMMENT '邮箱（原始值）',
  `ip` VARCHAR(50) NULL DEFAULT NULL COMMENT 'IP地址（原始值）',
  `phone` VARCHAR(50) NULL DEFAULT NULL COMMENT '手机号（原始值）',
  `ua` TEXT NULL COMMENT '用户代理',
  `report_params` TEXT NULL COMMENT '完整上报参数（JSON格式）',
  `status` VARCHAR(20) NOT NULL COMMENT '上报状态：pending, success, failed',
  `attempt_count` INT NULL DEFAULT 0 COMMENT '尝试次数',
  `max_attempts` INT NULL DEFAULT 3 COMMENT '最大尝试次数',
  `response_status` INT NULL DEFAULT NULL COMMENT '响应状态码',
  `response_body` TEXT NULL COMMENT '响应内容',
  `log_id` VARCHAR(100) NULL DEFAULT NULL COMMENT '第三方返回的logId',
  `error_message` TEXT NULL COMMENT '错误信息（如果失败）',
  `created_at` DATETIME NOT NULL COMMENT '创建时间',
  `report_start_time` DATETIME NULL DEFAULT NULL COMMENT '上报开始时间',
  `report_success_time` DATETIME NULL DEFAULT NULL COMMENT '上报成功时间',
  `completed_at` DATETIME NULL DEFAULT NULL COMMENT '完成时间',
  `pii_scrubbed_at` DATETIME NULL DEFAULT NULL COMMENT 'PII 按保留策略清理时间；保留事件幂等键',
  `conversion_id` VARCHAR(255) NULL DEFAULT NULL COMMENT '转化ID',
  `currency` VARCHAR(10) NULL DEFAULT NULL COMMENT '货币类型',
  `amount` DECIMAL(12, 4) NULL DEFAULT NULL COMMENT '支付金额',
  `outbox_enqueued` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否由转化事务创建的持久化 Outbox 事件',
  `short_link_id` INT NULL DEFAULT NULL COMMENT '用于恢复像素配置的短链接 ID（非外键，保留删除后的证据）',
  `cloak_name` VARCHAR(100) NULL DEFAULT NULL COMMENT '斗篷配置名称（仅配置引用）',
  `short_code` VARCHAR(100) NULL DEFAULT NULL COMMENT '短链接短码（仅配置引用）',
  `click_time` DATETIME NULL DEFAULT NULL COMMENT '点击发生时间，用于稳定构造 Meta event_time/fbc',
  `next_retry_time` DATETIME NULL DEFAULT NULL COMMENT 'Outbox 下次可重试时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `unique_event_key`(`event_key` ASC) USING BTREE,
  INDEX `idx_third_party_source`(`source` ASC) USING BTREE,
  INDEX `idx_third_party_adsid`(`adsid` ASC) USING BTREE,
  INDEX `idx_third_party_event`(`event` ASC) USING BTREE,
  INDEX `idx_third_party_status`(`status` ASC) USING BTREE,
  INDEX `idx_third_party_created_at`(`created_at` ASC) USING BTREE,
  INDEX `idx_third_party_pii_retention`(`pii_scrubbed_at` ASC, `created_at` ASC, `id` ASC) USING BTREE,
  INDEX `idx_third_party_status_created`(`status` ASC, `created_at` ASC) USING BTREE,
  INDEX `idx_conversion_id`(`conversion_id` ASC) USING BTREE,
  INDEX `idx_third_party_outbox_due`(`outbox_enqueued` ASC, `status` ASC, `next_retry_time` ASC, `report_start_time` ASC, `id` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '第三方上报日志表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for cloak_configs
-- ----------------------------
DROP TABLE IF EXISTS `cloak_configs`;
CREATE TABLE IF NOT EXISTS `cloak_configs`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '配置ID',
  `cloak_name` VARCHAR(100) NOT NULL COMMENT '斗篷名称（如 master）',
  `pixel_id` VARCHAR(50) NOT NULL COMMENT '主像素ID',
  `access_token` VARCHAR(500) NOT NULL COMMENT '主像素Token',
  `backup_pixel_id` VARCHAR(50) NULL DEFAULT NULL COMMENT '备份像素ID',
  `backup_access_token` VARCHAR(500) NULL DEFAULT NULL COMMENT '备份像素Token',
  `report_event` VARCHAR(64) NOT NULL DEFAULT 'ViewContent' COMMENT '斗篷点击与测上报的CAPI event_name',
  `report_value` DECIMAL(12,4) NULL DEFAULT NULL COMMENT '购物类事件金额',
  `report_currency` VARCHAR(10) NULL DEFAULT 'USD' COMMENT '购物类事件货币',
  `click_report_enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '桥页按钮跳转是否做 Facebook 上报',
  `load_report_enabled` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '桥页加载完成是否做 Facebook 上报',
  `load_report_event` VARCHAR(64) NOT NULL DEFAULT 'PageView' COMMENT '加载完成 CAPI event_name',
  `load_report_value` DECIMAL(12,4) NULL DEFAULT NULL COMMENT '加载上报为 Purchase 时的金额',
  `load_report_currency` VARCHAR(10) NULL DEFAULT 'USD' COMMENT '加载上报为 Purchase 时的货币',
  `postback_report_enabled` TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'postback 转化是否按斗篷配置做 Facebook 上报（0=保持原逻辑按 payout 发 Purchase）',
  `postback_report_event` VARCHAR(64) NOT NULL DEFAULT 'Purchase' COMMENT 'postback 转化 CAPI event_name',
  `postback_report_value` DECIMAL(12,4) NULL DEFAULT NULL COMMENT 'postback 为 Purchase 时固定金额；NULL 则用 postback 的 payout',
  `postback_report_currency` VARCHAR(10) NULL DEFAULT 'USD' COMMENT 'postback Purchase 货币',
  `is_enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_cloak_name`(`cloak_name` ASC) USING BTREE,
  INDEX `idx_cloak_enabled`(`is_enabled` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '斗篷配置表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for token_blacklist
-- ----------------------------
DROP TABLE IF EXISTS `token_blacklist`;
CREATE TABLE IF NOT EXISTS `token_blacklist`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '黑名单ID',
  `token_jti` VARCHAR(64) NOT NULL COMMENT 'JWT令牌ID（jti）',
  `user_id` INT NOT NULL COMMENT '用户ID',
  `revoked_at` DATETIME NOT NULL COMMENT '撤销时间',
  `expires_at` DATETIME NOT NULL COMMENT 'Token过期时间',
  `reason` VARCHAR(200) NULL DEFAULT NULL COMMENT '撤销原因（用户退出、强制退出等）',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `ix_token_blacklist_token_jti`(`token_jti` ASC) USING BTREE,
  INDEX `ix_token_blacklist_revoked_at`(`revoked_at` ASC) USING BTREE,
  INDEX `idx_blacklist_user`(`user_id` ASC) USING BTREE,
  INDEX `idx_blacklist_expires`(`expires_at` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = 'JWT令牌黑名单表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for user_audit_logs
-- ----------------------------
DROP TABLE IF EXISTS `user_audit_logs`;
CREATE TABLE IF NOT EXISTS `user_audit_logs`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '日志ID',
  `user_id` INT NULL DEFAULT NULL COMMENT '用户ID（可为空，记录未登录访问）',
  `username` VARCHAR(50) NULL DEFAULT NULL COMMENT '用户名（冗余字段，便于查询）',
  `action_type` VARCHAR(50) NOT NULL COMMENT '操作类型：LOGIN, LOGOUT, CREATE, UPDATE, DELETE, VIEW, ACCESS等',
  `resource_type` VARCHAR(50) NULL DEFAULT NULL COMMENT '资源类型：USER, CLIENT, PRODUCT, AD_DATA, SCHEDULED_TASK等',
  `resource_id` INT NULL DEFAULT NULL COMMENT '资源ID',
  `resource_name` VARCHAR(255) NULL DEFAULT NULL COMMENT '资源名称（冗余字段，便于查询）',
  `ip_address` VARCHAR(50) NULL DEFAULT NULL COMMENT 'IP地址',
  `user_agent` VARCHAR(500) NULL DEFAULT NULL COMMENT '用户代理（浏览器信息）',
  `request_method` VARCHAR(10) NULL DEFAULT NULL COMMENT 'HTTP请求方法',
  `request_path` VARCHAR(500) NULL DEFAULT NULL COMMENT '请求路径',
  `request_params` TEXT NULL COMMENT '请求参数（JSON格式，不包含敏感信息）',
  `status_code` INT NULL DEFAULT NULL COMMENT 'HTTP状态码',
  `success` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '操作是否成功',
  `error_message` TEXT NULL COMMENT '错误信息（如果失败）',
  `details` TEXT NULL COMMENT '详细信息（JSON格式）',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_audit_log_user_id`(`user_id` ASC) USING BTREE,
  INDEX `idx_audit_log_username`(`username` ASC) USING BTREE,
  INDEX `idx_audit_log_action_type`(`action_type` ASC) USING BTREE,
  INDEX `idx_audit_log_resource_type`(`resource_type` ASC) USING BTREE,
  INDEX `idx_audit_log_ip_address`(`ip_address` ASC) USING BTREE,
  INDEX `idx_audit_log_request_path`(`request_path` ASC) USING BTREE,
  INDEX `idx_audit_log_success`(`success` ASC) USING BTREE,
  INDEX `idx_audit_log_created_at`(`created_at` ASC) USING BTREE,
  INDEX `idx_audit_log_user_action`(`user_id` ASC, `action_type` ASC) USING BTREE,
  INDEX `idx_audit_log_resource`(`resource_type` ASC, `resource_id` ASC) USING BTREE,
  CONSTRAINT `fk_user_audit_logs_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '用户操作日志表（审计日志）' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for user_sessions
-- ----------------------------
DROP TABLE IF EXISTS `user_sessions`;
CREATE TABLE IF NOT EXISTS `user_sessions`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '会话ID',
  `user_id` INT NOT NULL COMMENT '用户ID',
  `token_jti` VARCHAR(64) NOT NULL COMMENT 'JWT令牌ID（jti）',
  `token_type` VARCHAR(16) NOT NULL DEFAULT 'access' COMMENT '令牌类型 access/refresh',
  `ip_address` VARCHAR(50) NULL DEFAULT NULL COMMENT '登录IP地址',
  `user_agent` VARCHAR(500) NULL DEFAULT NULL COMMENT '用户代理（浏览器信息）',
  `device_info` VARCHAR(200) NULL DEFAULT NULL COMMENT '设备信息（移动端/桌面端）',
  `location` VARCHAR(200) NULL DEFAULT NULL COMMENT '登录位置（可选，通过IP解析）',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否活跃',
  `last_activity` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '最后活动时间',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间（登录时间）',
  `expires_at` DATETIME(6) NOT NULL COMMENT '过期时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_user_sessions_token_jti`(`token_jti` ASC) USING BTREE,
  INDEX `idx_session_user_active`(`user_id` ASC, `is_active` ASC) USING BTREE,
  INDEX `idx_session_expires`(`expires_at` ASC) USING BTREE,
  INDEX `idx_ip_address`(`ip_address` ASC) USING BTREE,
  INDEX `idx_is_active`(`is_active` ASC) USING BTREE,
  INDEX `idx_last_activity`(`last_activity` ASC) USING BTREE,
  INDEX `ix_user_sessions_token_type`(`token_type` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '用户会话表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for users
-- ----------------------------
DROP TABLE IF EXISTS `users`;
CREATE TABLE IF NOT EXISTS `users`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '用户ID',
  `username` VARCHAR(50) NOT NULL COMMENT '用户名称(登录名称)',
  `hashed_password` VARCHAR(191) NOT NULL COMMENT '用户Hash密码',
  `full_name` VARCHAR(100) NULL DEFAULT NULL COMMENT '用户全名',
  `email` VARCHAR(100) NULL DEFAULT NULL COMMENT '用户邮箱',
  `role` ENUM('admin','client') NOT NULL DEFAULT 'client' COMMENT '用户角色(ADMIN 管理员 / CLIENT 客户)',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
  `login_restricted` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否限制登录',
  `login_message` TEXT NULL COMMENT '登录提示消息',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_users_username`(`username` ASC) USING BTREE,
  UNIQUE INDEX `uq_users_email`(`email` ASC) USING BTREE,
  FULLTEXT INDEX `ft_users_search`(`username`, `full_name`, `email`) WITH PARSER `ngram`
) ENGINE = InnoDB AUTO_INCREMENT = 1000 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '用户表' ROW_FORMAT = DYNAMIC;

DROP TABLE IF EXISTS `sensitive_path_probe_logs`;
-- 敏感路径拦截日志表
CREATE TABLE IF NOT EXISTS `sensitive_path_probe_logs` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `request_path` VARCHAR(1024) NOT NULL COMMENT '请求路径',
  `method` VARCHAR(16) NULL COMMENT '请求方法',
  `client_ip` VARCHAR(64) NULL COMMENT '客户端IP',
  `user_agent` VARCHAR(512) NULL COMMENT '用户代理',
  `query_string` VARCHAR(2048) NULL COMMENT '查询字符串',
  `matched_rule` VARCHAR(255) NULL COMMENT '命中规则',
  `severity_level` TINYINT NOT NULL DEFAULT 2 COMMENT '预警等级：1低危 2中危 3高危 4危急',
  `action_taken` VARCHAR(64) NULL COMMENT '处置动作：blocked_404/auto_blocked_ip等',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  INDEX `idx_sensitive_probe_created_at` (`created_at`),
  INDEX `idx_sensitive_probe_ip_created` (`client_ip`, `created_at`),
  INDEX `idx_sensitive_probe_severity_created` (`severity_level`, `created_at`),
  INDEX `ix_sensitive_path_probe_logs_method` (`method`),
  INDEX `ix_sensitive_path_probe_logs_client_ip` (`client_ip`),
  INDEX `ix_sensitive_path_probe_logs_matched_rule` (`matched_rule`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='敏感路径探测拦截日志表';

-- ----------------------------
-- Table structure for sensitive_blocked_ips
-- ----------------------------
DROP TABLE IF EXISTS `sensitive_blocked_ips`;
CREATE TABLE IF NOT EXISTS `sensitive_blocked_ips` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `blocked_ip` VARCHAR(64) NOT NULL COMMENT '封禁IP',
  `reason` VARCHAR(255) NULL COMMENT '封禁原因',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE INDEX `blocked_ip` (`blocked_ip`),
  INDEX `idx_sensitive_blocked_ip_active` (`is_active`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='敏感路径防护IP黑名单表';

-- ----------------------------
-- Procedure structure for purge_clicks_safe
-- ----------------------------
DROP PROCEDURE IF EXISTS `purge_clicks_safe`;
delimiter ;;
CREATE PROCEDURE `purge_clicks_safe`(IN p_delete_before_date DATETIME,
    IN p_batch_size INT,
    IN p_sleep_seconds DECIMAL(8,3),
    IN p_max_batches INT,
    IN p_dry_run BOOLEAN)
BEGIN
    DECLARE v_batch INT DEFAULT 0;
    DECLARE v_selected INT DEFAULT 0;
    DECLARE v_deleted INT DEFAULT 0;
    DECLARE v_total_deleted BIGINT DEFAULT 0;
    DECLARE v_remaining BIGINT DEFAULT 0;

    SET SESSION innodb_lock_wait_timeout = 5;

    CREATE TEMPORARY TABLE IF NOT EXISTS tmp_delete_ids (
        id BIGINT PRIMARY KEY
    ) ENGINE=InnoDB;

    purge_loop: LOOP
        SET v_batch = v_batch + 1;

        IF v_batch > p_max_batches THEN
            SELECT 'STOP_MAX_BATCHES' AS status, p_max_batches AS max_batches, v_total_deleted AS total_deleted;
            LEAVE purge_loop;
        END IF;

        TRUNCATE TABLE tmp_delete_ids;

        INSERT INTO tmp_delete_ids (id)
        SELECT c.id
        FROM clicks c
        WHERE c.created_at < p_delete_before_date
          AND c.click_id IS NOT NULL
          AND c.conversion_id IS NULL
          AND NOT EXISTS (
              SELECT 1
              FROM postback_conversions pc
              WHERE pc.conversion_id = c.click_id
          )
          AND NOT EXISTS (
              SELECT 1
              FROM pending_postback_conversions ppc
              WHERE ppc.click_id = c.click_id
          )
        ORDER BY c.id
        LIMIT p_batch_size;

        SET v_selected = ROW_COUNT();

        IF v_selected = 0 THEN
            LEAVE purge_loop;
        END IF;

        IF p_dry_run THEN
            SELECT
                'DRY_RUN' AS status,
                v_batch   AS batch_no,
                v_selected AS candidate_rows;
        ELSE
            START TRANSACTION;
                DELETE c
                FROM clicks c
                INNER JOIN tmp_delete_ids t ON t.id = c.id;
                SET v_deleted = ROW_COUNT();
            COMMIT;

            SET v_total_deleted = v_total_deleted + v_deleted;

            SELECT
                'DELETED' AS status,
                v_batch AS batch_no,
                v_selected AS selected_rows,
                v_deleted AS deleted_rows,
                v_total_deleted AS total_deleted;
        END IF;

        IF p_sleep_seconds > 0 THEN
            DO SLEEP(p_sleep_seconds);
        END IF;
    END LOOP;

    SELECT COUNT(*) INTO v_remaining
    FROM clicks c
    WHERE c.created_at < p_delete_before_date
      AND c.click_id IS NOT NULL
      AND c.conversion_id IS NULL
      AND NOT EXISTS (
          SELECT 1
          FROM postback_conversions pc
          WHERE pc.conversion_id = c.click_id
      )
      AND NOT EXISTS (
          SELECT 1
          FROM pending_postback_conversions ppc
          WHERE ppc.click_id = c.click_id
      );

    SELECT
        p_delete_before_date AS delete_before_date,
        p_batch_size AS batch_size,
        p_dry_run AS dry_run,
        v_batch AS batches_ran,
        v_total_deleted AS total_deleted,
        v_remaining AS remaining_count;

    DROP TEMPORARY TABLE IF EXISTS tmp_delete_ids;
END
;;
delimiter ;

-- ----------------------------
-- Procedure structure for purge_clicks_bots_safe
-- ----------------------------
DROP PROCEDURE IF EXISTS `purge_clicks_bots_safe`;
delimiter ;;
CREATE PROCEDURE `purge_clicks_bots_safe`(
    IN p_batch_size INT,
    IN p_sleep_seconds DECIMAL(8,3),
    IN p_max_batches INT,
    IN p_dry_run BOOLEAN)
BEGIN
    DECLARE v_batch INT DEFAULT 0;
    DECLARE v_selected INT DEFAULT 0;
    DECLARE v_deleted INT DEFAULT 0;
    DECLARE v_total_deleted BIGINT DEFAULT 0;
    DECLARE v_remaining BIGINT DEFAULT 0;

    SET SESSION innodb_lock_wait_timeout = 5;

    CREATE TEMPORARY TABLE IF NOT EXISTS tmp_bot_delete_ids (
        id BIGINT PRIMARY KEY
    ) ENGINE=InnoDB;

    bot_purge_loop: LOOP
        SET v_batch = v_batch + 1;

        IF v_batch > p_max_batches THEN
            SELECT 'STOP_MAX_BATCHES' AS status, p_max_batches AS max_batches, v_total_deleted AS total_deleted;
            LEAVE bot_purge_loop;
        END IF;

        TRUNCATE TABLE tmp_bot_delete_ids;

        INSERT INTO tmp_bot_delete_ids (id)
        SELECT c.id
        FROM clicks c
        WHERE c.is_bot = 1
          AND c.click_id IS NOT NULL
          AND c.conversion_id IS NULL
          AND NOT EXISTS (
              SELECT 1
              FROM postback_conversions pc
              WHERE pc.conversion_id = c.click_id
          )
          AND NOT EXISTS (
              SELECT 1
              FROM pending_postback_conversions ppc
              WHERE ppc.click_id = c.click_id
          )
        ORDER BY c.id
        LIMIT p_batch_size;

        SET v_selected = ROW_COUNT();

        IF v_selected = 0 THEN
            LEAVE bot_purge_loop;
        END IF;

        IF p_dry_run THEN
            SELECT
                'DRY_RUN' AS status,
                v_batch AS batch_no,
                v_selected AS candidate_rows;
        ELSE
            START TRANSACTION;
                DELETE c
                FROM clicks c
                INNER JOIN tmp_bot_delete_ids t ON t.id = c.id;
                SET v_deleted = ROW_COUNT();
            COMMIT;

            SET v_total_deleted = v_total_deleted + v_deleted;

            SELECT
                'DELETED' AS status,
                v_batch AS batch_no,
                v_selected AS selected_rows,
                v_deleted AS deleted_rows,
                v_total_deleted AS total_deleted;
        END IF;

        IF p_sleep_seconds > 0 THEN
            DO SLEEP(p_sleep_seconds);
        END IF;
    END LOOP;

    SELECT COUNT(*) INTO v_remaining
    FROM clicks c
    WHERE c.is_bot = 1
      AND c.click_id IS NOT NULL
      AND c.conversion_id IS NULL
      AND NOT EXISTS (
          SELECT 1
          FROM postback_conversions pc
          WHERE pc.conversion_id = c.click_id
      )
      AND NOT EXISTS (
          SELECT 1
          FROM pending_postback_conversions ppc
          WHERE ppc.click_id = c.click_id
      );

    SELECT
        p_batch_size AS batch_size,
        p_dry_run AS dry_run,
        v_batch AS batches_ran,
        v_total_deleted AS total_deleted,
        v_remaining AS remaining_bot_count;

    DROP TEMPORARY TABLE IF EXISTS tmp_bot_delete_ids;
END
;;
delimiter ;

-- ----------------------------
-- View structure for scheduler_jobs
-- ----------------------------
DROP VIEW IF EXISTS `scheduler_jobs`;
CREATE ALGORITHM = UNDEFINED SQL SECURITY DEFINER VIEW `scheduler_jobs` AS
SELECT
  `scheduled_tasks`.`id` AS `id`,
  `scheduled_tasks`.`task_name` AS `job_name`,
  `scheduled_tasks`.`last_run_time` AS `last_run`,
  `scheduled_tasks`.`last_success_at` AS `last_success`,
  `scheduled_tasks`.`last_error` AS `last_error`,
  `scheduled_tasks`.`retry_count` AS `retry_count`,
  `scheduled_tasks`.`status` AS `status`,
  `scheduled_tasks`.`is_running` AS `is_running`,
  `scheduled_tasks`.`is_active` AS `is_active`,
  `scheduled_tasks`.`cron_expression` AS `cron_expression`,
  `scheduled_tasks`.`updated_at` AS `updated_at`
FROM `scheduled_tasks`;

-- ----------------------------
-- Triggers structure for table postback_conversions
-- 空字符串统一转为 NULL，避免 UNIQUE 索引把多条空串当重复
-- ----------------------------
DROP TRIGGER IF EXISTS `trg_postback_conversions_empty_ids_bi`;
DELIMITER ;;
CREATE TRIGGER `trg_postback_conversions_empty_ids_bi` BEFORE INSERT ON `postback_conversions` FOR EACH ROW BEGIN
  IF NEW.`transaction_id` IS NOT NULL AND TRIM(NEW.`transaction_id`) = '' THEN
    SET NEW.`transaction_id` = NULL;
  END IF;
  IF NEW.`request_id` IS NOT NULL AND TRIM(NEW.`request_id`) = '' THEN
    SET NEW.`request_id` = NULL;
  END IF;
END
;;
DELIMITER ;

DROP TRIGGER IF EXISTS `trg_postback_conversions_empty_ids_bu`;
DELIMITER ;;
CREATE TRIGGER `trg_postback_conversions_empty_ids_bu` BEFORE UPDATE ON `postback_conversions` FOR EACH ROW BEGIN
  IF NEW.`transaction_id` IS NOT NULL AND TRIM(NEW.`transaction_id`) = '' THEN
    SET NEW.`transaction_id` = NULL;
  END IF;
  IF NEW.`request_id` IS NOT NULL AND TRIM(NEW.`request_id`) = '' THEN
    SET NEW.`request_id` = NULL;
  END IF;
END
;;
DELIMITER ;

-- 管理员账号由应用首次启动时根据 FIRST_SUPERUSER / FIRST_SUPERUSER_PASSWORD 创建。
-- 客户及 API key 必须通过平台业务流程生成，禁止在全量结构文件中固化凭据。

INSERT INTO `countries` VALUES 
(1, 'AA', 'AAA', '000', '未知区域', 'Unknown', '未知区域', 'Unknown', 1, '全球', '任意地区'),
(2, 'AF', 'AFG', '004', '阿富汗', 'Afghanistan', '阿富汗伊斯兰共和国', 'Islamic Republic of Afghanistan', 1, '亚洲', '中亚'),
(3, 'AX', 'ALA', '248', '奥兰群岛', 'Åland Islands', NULL, NULL, 0, '欧洲', '北欧'),
(4, 'AL', 'ALB', '008', '阿尔巴尼亚', 'Albania', '阿尔巴尼亚共和国', 'Republic of Albania', 1, '欧洲', '南欧'),
(5, 'DZ', 'DZA', '012', '阿尔及利亚', 'Algeria', '阿尔及利亚人民民主共和国', 'People\'s Democratic Republic of Algeria', 1, '非洲', '北非'),
(6, 'AS', 'ASM', '016', '美属萨摩亚', 'American Samoa', NULL, NULL, 0, '大洋洲', '波利尼西亚'),
(7, 'AD', 'AND', '020', '安道尔', 'Andorra', '安道尔公国', 'Principality of Andorra', 1, '欧洲', '南欧'),
(8, 'AO', 'AGO', '024', '安哥拉', 'Angola', '安哥拉共和国', 'Republic of Angola', 1, '非洲', '中非'),
(9, 'AI', 'AIA', '660', '安圭拉', 'Anguilla', NULL, NULL, 0, '美洲', '加勒比'),
(10, 'AQ', 'ATA', '010', '南极洲', 'Antarctica', NULL, NULL, 0, '南极洲', NULL),
(11, 'AG', 'ATG', '028', '安提瓜和巴布达', 'Antigua and Barbuda', NULL, NULL, 1, '美洲', '加勒比'),
(12, 'AR', 'ARG', '032', '阿根廷', 'Argentina', '阿根廷共和国', 'Argentine Republic', 1, '美洲', '南美洲'),
(13, 'AM', 'ARM', '051', '亚美尼亚', 'Armenia', '亚美尼亚共和国', 'Republic of Armenia', 1, '亚洲', '西亚'),
(14, 'AW', 'ABW', '533', '阿鲁巴', 'Aruba', NULL, NULL, 0, '美洲', '加勒比'),
(15, 'AU', 'AUS', '036', '澳大利亚', 'Australia', '澳大利亚联邦', 'Commonwealth of Australia', 1, '大洋洲', '澳大利亚和新西兰'),
(16, 'AT', 'AUT', '040', '奥地利', 'Austria', '奥地利共和国', 'Republic of Austria', 1, '欧洲', '中欧'),
(17, 'AZ', 'AZE', '031', '阿塞拜疆', 'Azerbaijan', '阿塞拜疆共和国', 'Republic of Azerbaijan', 1, '亚洲', '西亚'),
(18, 'BS', 'BHS', '044', '巴哈马', 'Bahamas', '巴哈马联邦', 'Commonwealth of the Bahamas', 1, '美洲', '加勒比'),
(19, 'BH', 'BHR', '048', '巴林', 'Bahrain', '巴林王国', 'Kingdom of Bahrain', 1, '亚洲', '西亚'),
(20, 'BD', 'BGD', '050', '孟加拉国', 'Bangladesh', '孟加拉人民共和国', 'People\'s Republic of Bangladesh', 1, '亚洲', '南亚'),
(21, 'BB', 'BRB', '052', '巴巴多斯', 'Barbados', NULL, NULL, 1, '美洲', '加勒比'),
(22, 'BY', 'BLR', '112', '白俄罗斯', 'Belarus', '白俄罗斯共和国', 'Republic of Belarus', 1, '欧洲', '东欧'),
(23, 'BE', 'BEL', '056', '比利时', 'Belgium', '比利时王国', 'Kingdom of Belgium', 1, '欧洲', '西欧'),
(24, 'BZ', 'BLZ', '084', '伯利兹', 'Belize', NULL, NULL, 1, '美洲', '中美洲'),
(25, 'BJ', 'BEN', '204', '贝宁', 'Benin', '贝宁共和国', 'Republic of Benin', 1, '非洲', '西非'),
(26, 'BM', 'BMU', '060', '百慕大', 'Bermuda', NULL, NULL, 0, '美洲', '北大西洋'),
(27, 'BT', 'BTN', '064', '不丹', 'Bhutan', '不丹王国', 'Kingdom of Bhutan', 1, '亚洲', '南亚'),
(28, 'BO', 'BOL', '068', '玻利维亚', 'Bolivia', '多民族玻利维亚国', 'Plurinational State of Bolivia', 1, '美洲', '南美洲'),
(29, 'BQ', 'BES', '535', '荷兰加勒比区', 'Bonaire, Sint Eustatius and Saba', NULL, NULL, 0, '美洲', '加勒比'),
(30, 'BA', 'BIH', '070', '波黑', 'Bosnia and Herzegovina', '波斯尼亚和黑塞哥维那', 'Bosnia and Herzegovina', 1, '欧洲', '南欧'),
(31, 'BW', 'BWA', '072', '博茨瓦纳', 'Botswana', '博茨瓦纳共和国', 'Republic of Botswana', 1, '非洲', '南非'),
(32, 'BV', 'BVT', '074', '布韦岛', 'Bouvet Island', NULL, NULL, 0, '南极洲', NULL),
(33, 'BR', 'BRA', '076', '巴西', 'Brazil', '巴西联邦共和国', 'Federative Republic of Brazil', 1, '美洲', '南美洲'),
(34, 'IO', 'IOT', '086', '英属印度洋领地', 'British Indian Ocean Territory', NULL, NULL, 0, '亚洲', '印度洋'),
(35, 'BN', 'BRN', '096', '文莱', 'Brunei Darussalam', '文莱达鲁萨兰国', 'Nation of Brunei, the Abode of Peace', 1, '亚洲', '东南亚'),
(36, 'BG', 'BGR', '100', '保加利亚', 'Bulgaria', '保加利亚共和国', 'Republic of Bulgaria', 1, '欧洲', '东欧'),
(37, 'BF', 'BFA', '854', '布基纳法索', 'Burkina Faso', NULL, NULL, 1, '非洲', '西非'),
(38, 'BI', 'BDI', '108', '布隆迪', 'Burundi', '布隆迪共和国', 'Republic of Burundi', 1, '非洲', '东非'),
(39, 'CV', 'CPV', '132', '佛得角', 'Cabo Verde', '佛得角共和国', 'Republic of Cabo Verde', 1, '非洲', '西非'),
(40, 'KH', 'KHM', '116', '柬埔寨', 'Cambodia', '柬埔寨王国', 'Kingdom of Cambodia', 1, '亚洲', '东南亚'),
(41, 'CM', 'CMR', '120', '喀麦隆', 'Cameroon', '喀麦隆共和国', 'Republic of Cameroon', 1, '非洲', '中非'),
(42, 'CA', 'CAN', '124', '加拿大', 'Canada', NULL, NULL, 1, '美洲', '北美洲'),
(43, 'KY', 'CYM', '136', '开曼群岛', 'Cayman Islands', NULL, NULL, 0, '美洲', '加勒比'),
(44, 'CF', 'CAF', '140', '中非', 'Central African Republic', '中非共和国', 'Central African Republic', 1, '非洲', '中非'),
(45, 'TD', 'TCD', '148', '乍得', 'Chad', '乍得共和国', 'Republic of Chad', 1, '非洲', '中非'),
(46, 'CL', 'CHL', '152', '智利', 'Chile', '智利共和国', 'Republic of Chile', 1, '美洲', '南美洲'),
(47, 'CN', 'CHN', '156', '中国', 'China', '中华人民共和国', 'People\'s Republic of China', 1, '亚洲', '东亚'),
(48, 'CX', 'CXR', '162', '圣诞岛', 'Christmas Island', NULL, NULL, 0, '亚洲', '印度洋'),
(49, 'CC', 'CCK', '166', '科科斯（基林）群岛', 'Cocos (Keeling) Islands', NULL, NULL, 0, '亚洲', '印度洋'),
(50, 'CO', 'COL', '170', '哥伦比亚', 'Colombia', '哥伦比亚共和国', 'Republic of Colombia', 1, '美洲', '南美洲'),
(51, 'KM', 'COM', '174', '科摩罗', 'Comoros', '科摩罗联盟', 'Union of the Comoros', 1, '非洲', '东非'),
(52, 'CG', 'COG', '178', '刚果（布）', 'Congo', '刚果共和国', 'Republic of the Congo', 1, '非洲', '中非'),
(53, 'CD', 'COD', '180', '刚果（金）', 'Congo, Democratic Republic of the', '刚果民主共和国', 'Democratic Republic of the Congo', 1, '非洲', '中非'),
(54, 'CK', 'COK', '184', '库克群岛', 'Cook Islands', NULL, NULL, 0, '大洋洲', '波利尼西亚'),
(55, 'CR', 'CRI', '188', '哥斯达黎加', 'Costa Rica', '哥斯达黎加共和国', 'Republic of Costa Rica', 1, '美洲', '中美洲'),
(56, 'CI', 'CIV', '384', '科特迪瓦', 'Côte d\'Ivoire', '科特迪瓦共和国', 'Republic of Côte d\'Ivoire', 1, '非洲', '西非'),
(57, 'HR', 'HRV', '191', '克罗地亚', 'Croatia', '克罗地亚共和国', 'Republic of Croatia', 1, '欧洲', '南欧'),
(58, 'CU', 'CUB', '192', '古巴', 'Cuba', '古巴共和国', 'Republic of Cuba', 1, '美洲', '加勒比'),
(59, 'CW', 'CUW', '531', '库拉索', 'Curaçao', NULL, NULL, 0, '美洲', '加勒比'),
(60, 'CY', 'CYP', '196', '塞浦路斯', 'Cyprus', '塞浦路斯共和国', 'Republic of Cyprus', 1, '亚洲', '西亚'),
(61, 'CZ', 'CZE', '203', '捷克', 'Czechia', '捷克共和国', 'Czech Republic', 1, '欧洲', '中欧'),
(62, 'DK', 'DNK', '208', '丹麦', 'Denmark', '丹麦王国', 'Kingdom of Denmark', 1, '欧洲', '北欧'),
(63, 'DJ', 'DJI', '262', '吉布提', 'Djibouti', '吉布提共和国', 'Republic of Djibouti', 1, '非洲', '东非'),
(64, 'DM', 'DMA', '212', '多米尼克', 'Dominica', '多米尼克国', 'Commonwealth of Dominica', 1, '美洲', '加勒比'),
(65, 'DO', 'DOM', '214', '多米尼加', 'Dominican Republic', '多米尼加共和国', 'Dominican Republic', 1, '美洲', '加勒比'),
(66, 'EC', 'ECU', '218', '厄瓜多尔', 'Ecuador', '厄瓜多尔共和国', 'Republic of Ecuador', 1, '美洲', '南美洲'),
(67, 'EG', 'EGY', '818', '埃及', 'Egypt', '阿拉伯埃及共和国', 'Arab Republic of Egypt', 1, '非洲', '北非'),
(68, 'SV', 'SLV', '222', '萨尔瓦多', 'El Salvador', '萨尔瓦多共和国', 'Republic of El Salvador', 1, '美洲', '中美洲'),
(69, 'GQ', 'GNQ', '226', '赤道几内亚', 'Equatorial Guinea', '赤道几内亚共和国', 'Republic of Equatorial Guinea', 1, '非洲', '中非'),
(70, 'ER', 'ERI', '232', '厄立特里亚', 'Eritrea', '厄立特里亚国', 'State of Eritrea', 1, '非洲', '东非'),
(71, 'EE', 'EST', '233', '爱沙尼亚', 'Estonia', '爱沙尼亚共和国', 'Republic of Estonia', 1, '欧洲', '北欧'),
(72, 'SZ', 'SWZ', '748', '斯威士兰', 'Eswatini', '斯威士兰王国', 'Kingdom of Eswatini', 1, '非洲', '南非'),
(73, 'ET', 'ETH', '231', '埃塞俄比亚', 'Ethiopia', '埃塞俄比亚联邦民主共和国', 'Federal Democratic Republic of Ethiopia', 1, '非洲', '东非'),
(74, 'FK', 'FLK', '238', '福克兰群岛（马尔维纳斯）', 'Falkland Islands (Malvinas)', NULL, NULL, 0, '美洲', '南美洲'),
(75, 'FO', 'FRO', '234', '法罗群岛', 'Faroe Islands', NULL, NULL, 0, '欧洲', '北欧'),
(76, 'FJ', 'FJI', '242', '斐济', 'Fiji', '斐济共和国', 'Republic of Fiji', 1, '大洋洲', '美拉尼西亚'),
(77, 'FI', 'FIN', '246', '芬兰', 'Finland', '芬兰共和国', 'Republic of Finland', 1, '欧洲', '北欧'),
(78, 'FR', 'FRA', '250', '法国', 'France', '法兰西共和国', 'French Republic', 1, '欧洲', '西欧'),
(79, 'GF', 'GUF', '254', '法属圭亚那', 'French Guiana', NULL, NULL, 0, '美洲', '南美洲'),
(80, 'PF', 'PYF', '258', '法属波利尼西亚', 'French Polynesia', NULL, NULL, 0, '大洋洲', '波利尼西亚'),
(81, 'TF', 'ATF', '260', '法属南部领地', 'French Southern Territories', NULL, NULL, 0, '南极洲', NULL),
(82, 'GA', 'GAB', '266', '加蓬', 'Gabon', '加蓬共和国', 'Gabonese Republic', 1, '非洲', '中非'),
(83, 'GM', 'GMB', '270', '冈比亚', 'Gambia', '冈比亚共和国', 'Republic of the Gambia', 1, '非洲', '西非'),
(84, 'GE', 'GEO', '268', '格鲁吉亚', 'Georgia', NULL, NULL, 1, '亚洲', '西亚'),
(85, 'DE', 'DEU', '276', '德国', 'Germany', '德意志联邦共和国', 'Federal Republic of Germany', 1, '欧洲', '中欧'),
(86, 'GH', 'GHA', '288', '加纳', 'Ghana', '加纳共和国', 'Republic of Ghana', 1, '非洲', '西非'),
(87, 'GI', 'GIB', '292', '直布罗陀', 'Gibraltar', NULL, NULL, 0, '欧洲', '南欧'),
(88, 'GR', 'GRC', '300', '希腊', 'Greece', '希腊共和国', 'Hellenic Republic', 1, '欧洲', '南欧'),
(89, 'GL', 'GRL', '304', '格陵兰', 'Greenland', NULL, NULL, 0, '美洲', '北美洲'),
(90, 'GD', 'GRD', '308', '格林纳达', 'Grenada', NULL, NULL, 1, '美洲', '加勒比'),
(91, 'GP', 'GLP', '312', '瓜德罗普', 'Guadeloupe', NULL, NULL, 0, '美洲', '加勒比'),
(92, 'GU', 'GUM', '316', '关岛', 'Guam', NULL, NULL, 0, '大洋洲', '密克罗尼西亚'),
(93, 'GT', 'GTM', '320', '危地马拉', 'Guatemala', '危地马拉共和国', 'Republic of Guatemala', 1, '美洲', '中美洲'),
(94, 'GG', 'GGY', '831', '根西', 'Guernsey', NULL, NULL, 0, '欧洲', '北欧'),
(95, 'GN', 'GIN', '324', '几内亚', 'Guinea', '几内亚共和国', 'Republic of Guinea', 1, '非洲', '西非'),
(96, 'GW', 'GNB', '624', '几内亚比绍', 'Guinea-Bissau', '几内亚比绍共和国', 'Republic of Guinea-Bissau', 1, '非洲', '西非'),
(97, 'GY', 'GUY', '328', '圭亚那', 'Guyana', '圭亚那合作共和国', 'Co-operative Republic of Guyana', 1, '美洲', '南美洲'),
(98, 'HT', 'HTI', '332', '海地', 'Haiti', '海地共和国', 'Republic of Haiti', 1, '美洲', '加勒比'),
(99, 'HM', 'HMD', '334', '赫德岛和麦克唐纳群岛', 'Heard Island and McDonald Islands', NULL, NULL, 0, '南极洲', NULL),
(100, 'VA', 'VAT', '336', '梵蒂冈', 'Holy See', '梵蒂冈城国', 'Vatican City State', 1, '欧洲', '南欧'),
(101, 'HN', 'HND', '340', '洪都拉斯', 'Honduras', '洪都拉斯共和国', 'Republic of Honduras', 1, '美洲', '中美洲'),
(102, 'HK', 'HKG', '344', '香港', 'Hong Kong', '中华人民共和国香港特别行政区', 'Hong Kong Special Administrative Region of China', 0, '亚洲', '东亚'),
(103, 'HU', 'HUN', '348', '匈牙利', 'Hungary', NULL, NULL, 1, '欧洲', '东欧'),
(104, 'IS', 'ISL', '352', '冰岛', 'Iceland', '冰岛共和国', 'Republic of Iceland', 1, '欧洲', '北欧'),
(105, 'IN', 'IND', '356', '印度', 'India', '印度共和国', 'Republic of India', 1, '亚洲', '南亚'),
(106, 'ID', 'IDN', '360', '印度尼西亚', 'Indonesia', '印度尼西亚共和国', 'Republic of Indonesia', 1, '亚洲', '东南亚'),
(107, 'IR', 'IRN', '364', '伊朗', 'Iran', '伊朗伊斯兰共和国', 'Islamic Republic of Iran', 1, '亚洲', '西亚'),
(108, 'IQ', 'IRQ', '368', '伊拉克', 'Iraq', '伊拉克共和国', 'Republic of Iraq', 1, '亚洲', '西亚'),
(109, 'IE', 'IRL', '372', '爱尔兰', 'Ireland', NULL, NULL, 1, '欧洲', '西欧'),
(110, 'IM', 'IMN', '833', '马恩岛', 'Isle of Man', NULL, NULL, 0, '欧洲', '北欧'),
(111, 'IL', 'ISR', '376', '以色列', 'Israel', '以色列国', 'State of Israel', 1, '亚洲', '西亚'),
(112, 'IT', 'ITA', '380', '意大利', 'Italy', '意大利共和国', 'Italian Republic', 1, '欧洲', '南欧'),
(113, 'JM', 'JAM', '388', '牙买加', 'Jamaica', NULL, NULL, 1, '美洲', '加勒比'),
(114, 'JP', 'JPN', '392', '日本', 'Japan', NULL, NULL, 1, '亚洲', '东亚'),
(115, 'JE', 'JEY', '832', '泽西', 'Jersey', NULL, NULL, 0, '欧洲', '北欧'),
(116, 'JO', 'JOR', '400', '约旦', 'Jordan', '约旦哈希姆王国', 'Hashemite Kingdom of Jordan', 1, '亚洲', '西亚'),
(117, 'KZ', 'KAZ', '398', '哈萨克斯坦', 'Kazakhstan', '哈萨克斯坦共和国', 'Republic of Kazakhstan', 1, '亚洲', '中亚'),
(118, 'KE', 'KEN', '404', '肯尼亚', 'Kenya', '肯尼亚共和国', 'Republic of Kenya', 1, '非洲', '东非'),
(119, 'KI', 'KIR', '296', '基里巴斯', 'Kiribati', '基里巴斯共和国', 'Republic of Kiribati', 1, '大洋洲', '密克罗尼西亚'),
(120, 'KP', 'PRK', '408', '朝鲜', 'Korea (Democratic People\'s Republic of)', '朝鲜民主主义人民共和国', 'Democratic People\'s Republic of Korea', 1, '亚洲', '东亚'),
(121, 'KR', 'KOR', '410', '韩国', 'Korea, Republic of', '大韩民国', 'Republic of Korea', 1, '亚洲', '东亚'),
(122, 'KW', 'KWT', '414', '科威特', 'Kuwait', '科威特国', 'State of Kuwait', 1, '亚洲', '西亚'),
(123, 'KG', 'KGZ', '417', '吉尔吉斯斯坦', 'Kyrgyzstan', '吉尔吉斯共和国', 'Kyrgyz Republic', 1, '亚洲', '中亚'),
(124, 'LA', 'LAO', '418', '老挝', 'Lao People\'s Democratic Republic', '老挝人民民主共和国', 'Lao People\'s Democratic Republic', 1, '亚洲', '东南亚'),
(125, 'LV', 'LVA', '428', '拉脱维亚', 'Latvia', '拉脱维亚共和国', 'Republic of Latvia', 1, '欧洲', '北欧'),
(126, 'LB', 'LBN', '422', '黎巴嫩', 'Lebanon', '黎巴嫩共和国', 'Republic of Lebanon', 1, '亚洲', '西亚'),
(127, 'LS', 'LSO', '426', '莱索托', 'Lesotho', '莱索托王国', 'Kingdom of Lesotho', 1, '非洲', '南非'),
(128, 'LR', 'LBR', '430', '利比里亚', 'Liberia', '利比里亚共和国', 'Republic of Liberia', 1, '非洲', '西非'),
(129, 'LY', 'LBY', '434', '利比亚', 'Libya', '利比亚国', 'State of Libya', 1, '非洲', '北非'),
(130, 'LI', 'LIE', '438', '列支敦士登', 'Liechtenstein', '列支敦士登公国', 'Principality of Liechtenstein', 1, '欧洲', '中欧'),
(131, 'LT', 'LTU', '440', '立陶宛', 'Lithuania', '立陶宛共和国', 'Republic of Lithuania', 1, '欧洲', '北欧'),
(132, 'LU', 'LUX', '442', '卢森堡', 'Luxembourg', '卢森堡大公国', 'Grand Duchy of Luxembourg', 1, '欧洲', '西欧'),
(133, 'MO', 'MAC', '446', '澳门', 'Macao', '中华人民共和国澳门特别行政区', 'Macao Special Administrative Region of China', 0, '亚洲', '东亚'),
(134, 'MG', 'MDG', '450', '马达加斯加', 'Madagascar', '马达加斯加共和国', 'Republic of Madagascar', 1, '非洲', '东非'),
(135, 'MW', 'MWI', '454', '马拉维', 'Malawi', '马拉维共和国', 'Republic of Malawi', 1, '非洲', '东非'),
(136, 'MY', 'MYS', '458', '马来西亚', 'Malaysia', NULL, NULL, 1, '亚洲', '东南亚'),
(137, 'MV', 'MDV', '462', '马尔代夫', 'Maldives', '马尔代夫共和国', 'Republic of Maldives', 1, '亚洲', '南亚'),
(138, 'ML', 'MLI', '466', '马里', 'Mali', '马里共和国', 'Republic of Mali', 1, '非洲', '西非'),
(139, 'MT', 'MLT', '470', '马耳他', 'Malta', '马耳他共和国', 'Republic of Malta', 1, '欧洲', '南欧'),
(140, 'MH', 'MHL', '584', '马绍尔群岛', 'Marshall Islands', '马绍尔群岛共和国', 'Republic of the Marshall Islands', 1, '大洋洲', '密克罗尼西亚'),
(141, 'MQ', 'MTQ', '474', '马提尼克', 'Martinique', NULL, NULL, 0, '美洲', '加勒比'),
(142, 'MR', 'MRT', '478', '毛里塔尼亚', 'Mauritania', '毛里塔尼亚伊斯兰共和国', 'Islamic Republic of Mauritania', 1, '非洲', '西非'),
(143, 'MU', 'MUS', '480', '毛里求斯', 'Mauritius', '毛里求斯共和国', 'Republic of Mauritius', 1, '非洲', '东非'),
(144, 'YT', 'MYT', '175', '马约特', 'Mayotte', NULL, NULL, 0, '非洲', '东非'),
(145, 'MX', 'MEX', '484', '墨西哥', 'Mexico', '墨西哥合众国', 'United Mexican States', 1, '美洲', '北美洲'),
(146, 'FM', 'FSM', '583', '密克罗尼西亚联邦', 'Micronesia (Federated States of)', '密克罗尼西亚联邦', 'Federated States of Micronesia', 1, '大洋洲', '密克罗尼西亚'),
(147, 'MD', 'MDA', '498', '摩尔多瓦', 'Moldova', '摩尔多瓦共和国', 'Republic of Moldova', 1, '欧洲', '东欧'),
(148, 'MC', 'MCO', '492', '摩纳哥', 'Monaco', '摩纳哥公国', 'Principality of Monaco', 1, '欧洲', '西欧'),
(149, 'MN', 'MNG', '496', '蒙古', 'Mongolia', '蒙古国', 'Mongolia', 1, '亚洲', '东亚'),
(150, 'ME', 'MNE', '499', '黑山', 'Montenegro', '黑山', 'Montenegro', 1, '欧洲', '南欧'),
(151, 'MS', 'MSR', '500', '蒙特塞拉特', 'Montserrat', NULL, NULL, 0, '美洲', '加勒比'),
(152, 'MA', 'MAR', '504', '摩洛哥', 'Morocco', '摩洛哥王国', 'Kingdom of Morocco', 1, '非洲', '北非'),
(153, 'MZ', 'MOZ', '508', '莫桑比克', 'Mozambique', '莫桑比克共和国', 'Republic of Mozambique', 1, '非洲', '东非'),
(154, 'MM', 'MMR', '104', '缅甸', 'Myanmar', '缅甸联邦共和国', 'Republic of the Union of Myanmar', 1, '亚洲', '东南亚'),
(155, 'NA', 'NAM', '516', '纳米比亚', 'Namibia', '纳米比亚共和国', 'Republic of Namibia', 1, '非洲', '南非'),
(156, 'NR', 'NRU', '520', '瑙鲁', 'Nauru', '瑙鲁共和国', 'Republic of Nauru', 1, '大洋洲', '密克罗尼西亚'),
(157, 'NP', 'NPL', '524', '尼泊尔', 'Nepal', '尼泊尔联邦民主共和国', 'Federal Democratic Republic of Nepal', 1, '亚洲', '南亚'),
(158, 'NL', 'NLD', '528', '荷兰', 'Netherlands', '荷兰王国', 'Kingdom of the Netherlands', 1, '欧洲', '西欧'),
(159, 'NC', 'NCL', '540', '新喀里多尼亚', 'New Caledonia', NULL, NULL, 0, '大洋洲', '美拉尼西亚'),
(160, 'NZ', 'NZL', '554', '新西兰', 'New Zealand', NULL, NULL, 1, '大洋洲', '澳大利亚和新西兰'),
(161, 'NI', 'NIC', '558', '尼加拉瓜', 'Nicaragua', '尼加拉瓜共和国', 'Republic of Nicaragua', 1, '美洲', '中美洲'),
(162, 'NE', 'NER', '562', '尼日尔', 'Niger', '尼日尔共和国', 'Republic of Niger', 1, '非洲', '西非'),
(163, 'NG', 'NGA', '566', '尼日利亚', 'Nigeria', '尼日利亚联邦共和国', 'Federal Republic of Nigeria', 1, '非洲', '西非'),
(164, 'NU', 'NIU', '570', '纽埃', 'Niue', NULL, NULL, 0, '大洋洲', '波利尼西亚'),
(165, 'NF', 'NFK', '574', '诺福克岛', 'Norfolk Island', NULL, NULL, 0, '大洋洲', '澳大利亚和新西兰'),
(166, 'MK', 'MKD', '807', '北马其顿', 'North Macedonia', '北马其顿共和国', 'Republic of North Macedonia', 1, '欧洲', '南欧'),
(167, 'MP', 'MNP', '580', '北马里亚纳群岛', 'Northern Mariana Islands', NULL, NULL, 0, '大洋洲', '密克罗尼西亚'),
(168, 'NO', 'NOR', '578', '挪威', 'Norway', '挪威王国', 'Kingdom of Norway', 1, '欧洲', '北欧'),
(169, 'OM', 'OMN', '512', '阿曼', 'Oman', '阿曼苏丹国', 'Sultanate of Oman', 1, '亚洲', '西亚'),
(170, 'PK', 'PAK', '586', '巴基斯坦', 'Pakistan', '巴基斯坦伊斯兰共和国', 'Islamic Republic of Pakistan', 1, '亚洲', '南亚'),
(171, 'PW', 'PLW', '585', '帕劳', 'Palau', '帕劳共和国', 'Republic of Palau', 1, '大洋洲', '密克罗尼西亚'),
(172, 'PS', 'PSE', '275', '巴勒斯坦', 'Palestine, State of', '巴勒斯坦国', 'State of Palestine', 1, '亚洲', '西亚'),
(173, 'PA', 'PAN', '591', '巴拿马', 'Panama', '巴拿马共和国', 'Republic of Panama', 1, '美洲', '中美洲'),
(174, 'PG', 'PNG', '598', '巴布亚新几内亚', 'Papua New Guinea', '巴布亚新几内亚独立国', 'Independent State of Papua New Guinea', 1, '大洋洲', '美拉尼西亚'),
(175, 'PY', 'PRY', '600', '巴拉圭', 'Paraguay', '巴拉圭共和国', 'Republic of Paraguay', 1, '美洲', '南美洲'),
(176, 'PE', 'PER', '604', '秘鲁', 'Peru', '秘鲁共和国', 'Republic of Peru', 1, '美洲', '南美洲'),
(177, 'PH', 'PHL', '608', '菲律宾', 'Philippines', '菲律宾共和国', 'Republic of the Philippines', 1, '亚洲', '东南亚'),
(178, 'PN', 'PCN', '612', '皮特凯恩群岛', 'Pitcairn', NULL, NULL, 0, '大洋洲', '波利尼西亚'),
(179, 'PL', 'POL', '616', '波兰', 'Poland', '波兰共和国', 'Republic of Poland', 1, '欧洲', '东欧'),
(180, 'PT', 'PRT', '620', '葡萄牙', 'Portugal', '葡萄牙共和国', 'Portuguese Republic', 1, '欧洲', '南欧'),
(181, 'PR', 'PRI', '630', '波多黎各', 'Puerto Rico', NULL, NULL, 0, '美洲', '加勒比'),
(182, 'QA', 'QAT', '634', '卡塔尔', 'Qatar', '卡塔尔国', 'State of Qatar', 1, '亚洲', '西亚'),
(183, 'RE', 'REU', '638', '留尼汪', 'Réunion', NULL, NULL, 0, '非洲', '东非'),
(184, 'RO', 'ROU', '642', '罗马尼亚', 'Romania', NULL, NULL, 1, '欧洲', '东欧'),
(185, 'RU', 'RUS', '643', '俄罗斯', 'Russian Federation', '俄罗斯联邦', 'Russian Federation', 1, '欧洲', '东欧'),
(186, 'RW', 'RWA', '646', '卢旺达', 'Rwanda', '卢旺达共和国', 'Republic of Rwanda', 1, '非洲', '东非'),
(187, 'BL', 'BLM', '652', '圣巴泰勒米', 'Saint Barthélemy', NULL, NULL, 0, '美洲', '加勒比'),
(188, 'SH', 'SHN', '654', '圣赫勒拿', 'Saint Helena, Ascension and Tristan da Cunha', NULL, NULL, 0, '非洲', '西非'),
(189, 'KN', 'KNA', '659', '圣基茨和尼维斯', 'Saint Kitts and Nevis', '圣基茨和尼维斯联邦', 'Federation of Saint Kitts and Nevis', 1, '美洲', '加勒比'),
(190, 'LC', 'LCA', '662', '圣卢西亚', 'Saint Lucia', NULL, NULL, 1, '美洲', '加勒比'),
(191, 'MF', 'MAF', '663', '法属圣马丁', 'Saint Martin (French part)', NULL, NULL, 0, '美洲', '加勒比'),
(192, 'PM', 'SPM', '666', '圣皮埃尔和密克隆', 'Saint Pierre and Miquelon', NULL, NULL, 0, '美洲', '北美洲'),
(193, 'VC', 'VCT', '670', '圣文森特和格林纳丁斯', 'Saint Vincent and the Grenadines', NULL, NULL, 1, '美洲', '加勒比'),
(194, 'WS', 'WSM', '882', '萨摩亚', 'Samoa', '萨摩亚独立国', 'Independent State of Samoa', 1, '大洋洲', '波利尼西亚'),
(195, 'SM', 'SMR', '674', '圣马力诺', 'San Marino', '圣马力诺共和国', 'Republic of San Marino', 1, '欧洲', '南欧'),
(196, 'ST', 'STP', '678', '圣多美和普林西比', 'Sao Tome and Principe', '圣多美和普林西比民主共和国', 'Democratic Republic of Sao Tome and Principe', 1, '非洲', '中非'),
(197, 'SA', 'SAU', '682', '沙特阿拉伯', 'Saudi Arabia', '沙特阿拉伯王国', 'Kingdom of Saudi Arabia', 1, '亚洲', '西亚'),
(198, 'SN', 'SEN', '686', '塞内加尔', 'Senegal', '塞内加尔共和国', 'Republic of Senegal', 1, '非洲', '西非'),
(199, 'RS', 'SRB', '688', '塞尔维亚', 'Serbia', '塞尔维亚共和国', 'Republic of Serbia', 1, '欧洲', '南欧'),
(200, 'SC', 'SYC', '690', '塞舌尔', 'Seychelles', '塞舌尔共和国', 'Republic of Seychelles', 1, '非洲', '东非'),
(201, 'SL', 'SLE', '694', '塞拉利昂', 'Sierra Leone', '塞拉利昂共和国', 'Republic of Sierra Leone', 1, '非洲', '西非'),
(202, 'SG', 'SGP', '702', '新加坡', 'Singapore', '新加坡共和国', 'Republic of Singapore', 1, '亚洲', '东南亚'),
(203, 'SX', 'SXM', '534', '荷属圣马丁', 'Sint Maarten (Dutch part)', NULL, NULL, 0, '美洲', '加勒比'),
(204, 'SK', 'SVK', '703', '斯洛伐克', 'Slovakia', '斯洛伐克共和国', 'Slovak Republic', 1, '欧洲', '中欧'),
(205, 'SI', 'SVN', '705', '斯洛文尼亚', 'Slovenia', '斯洛文尼亚共和国', 'Republic of Slovenia', 1, '欧洲', '南欧'),
(206, 'SB', 'SLB', '090', '所罗门群岛', 'Solomon Islands', NULL, NULL, 1, '大洋洲', '美拉尼西亚'),
(207, 'SO', 'SOM', '706', '索马里', 'Somalia', '索马里联邦共和国', 'Federal Republic of Somalia', 1, '非洲', '东非'),
(208, 'ZA', 'ZAF', '710', '南非', 'South Africa', '南非共和国', 'Republic of South Africa', 1, '非洲', '南非'),
(209, 'GS', 'SGS', '239', '南乔治亚和南桑威奇群岛', 'South Georgia and the South Sandwich Islands', NULL, NULL, 0, '南极洲', NULL),
(210, 'SS', 'SSD', '728', '南苏丹', 'South Sudan', '南苏丹共和国', 'Republic of South Sudan', 1, '非洲', '东非'),
(211, 'ES', 'ESP', '724', '西班牙', 'Spain', '西班牙王国', 'Kingdom of Spain', 1, '欧洲', '南欧'),
(212, 'LK', 'LKA', '144', '斯里兰卡', 'Sri Lanka', '斯里兰卡民主社会主义共和国', 'Democratic Socialist Republic of Sri Lanka', 1, '亚洲', '南亚'),
(213, 'SD', 'SDN', '729', '苏丹', 'Sudan', '苏丹共和国', 'Republic of the Sudan', 1, '非洲', '北非'),
(214, 'SR', 'SUR', '740', '苏里南', 'Suriname', '苏里南共和国', 'Republic of Suriname', 1, '美洲', '南美洲'),
(215, 'SJ', 'SJM', '744', '斯瓦尔巴和扬马延', 'Svalbard and Jan Mayen', NULL, NULL, 0, '欧洲', '北欧'),
(216, 'SE', 'SWE', '752', '瑞典', 'Sweden', '瑞典王国', 'Kingdom of Sweden', 1, '欧洲', '北欧'),
(217, 'CH', 'CHE', '756', '瑞士', 'Switzerland', '瑞士联邦', 'Swiss Confederation', 1, '欧洲', '中欧'),
(218, 'SY', 'SYR', '760', '叙利亚', 'Syrian Arab Republic', '阿拉伯叙利亚共和国', 'Syrian Arab Republic', 1, '亚洲', '西亚'),
(219, 'TW', 'TWN', '158', '台湾', 'Taiwan, Province of China', '中国台湾省', 'Taiwan, Province of China', 0, '亚洲', '东亚'),
(220, 'TJ', 'TJK', '762', '塔吉克斯坦', 'Tajikistan', '塔吉克斯坦共和国', 'Republic of Tajikistan', 1, '亚洲', '中亚'),
(221, 'TZ', 'TZA', '834', '坦桑尼亚', 'Tanzania', '坦桑尼亚联合共和国', 'United Republic of Tanzania', 1, '非洲', '东非'),
(222, 'TH', 'THA', '764', '泰国', 'Thailand', '泰王国', 'Kingdom of Thailand', 1, '亚洲', '东南亚'),
(223, 'TL', 'TLS', '626', '东帝汶', 'Timor-Leste', '东帝汶民主共和国', 'Democratic Republic of Timor-Leste', 1, '亚洲', '东南亚'),
(224, 'TG', 'TGO', '768', '多哥', 'Togo', '多哥共和国', 'Togolese Republic', 1, '非洲', '西非'),
(225, 'TK', 'TKL', '772', '托克劳', 'Tokelau', NULL, NULL, 0, '大洋洲', '波利尼西亚'),
(226, 'TO', 'TON', '776', '汤加', 'Tonga', '汤加王国', 'Kingdom of Tonga', 1, '大洋洲', '波利尼西亚'),
(227, 'TT', 'TTO', '780', '特立尼达和多巴哥', 'Trinidad and Tobago', '特立尼达和多巴哥共和国', 'Republic of Trinidad and Tobago', 1, '美洲', '加勒比'),
(228, 'TN', 'TUN', '788', '突尼斯', 'Tunisia', '突尼斯共和国', 'Republic of Tunisia', 1, '非洲', '北非'),
(229, 'TR', 'TUR', '792', '土耳其', 'Turkey', '土耳其共和国', 'Republic of Turkey', 1, '亚洲', '西亚'),
(230, 'TM', 'TKM', '795', '土库曼斯坦', 'Turkmenistan', '土库曼斯坦', 'Turkmenistan', 1, '亚洲', '中亚'),
(231, 'TC', 'TCA', '796', '特克斯和凯科斯群岛', 'Turks and Caicos Islands', NULL, NULL, 0, '美洲', '加勒比'),
(232, 'TV', 'TUV', '798', '图瓦卢', 'Tuvalu', NULL, NULL, 1, '大洋洲', '波利尼西亚'),
(233, 'UG', 'UGA', '800', '乌干达', 'Uganda', '乌干达共和国', 'Republic of Uganda', 1, '非洲', '东非'),
(234, 'UA', 'UKR', '804', '乌克兰', 'Ukraine', NULL, NULL, 1, '欧洲', '东欧'),
(235, 'AE', 'ARE', '784', '阿联酋', 'United Arab Emirates', '阿拉伯联合酋长国', 'United Arab Emirates', 1, '亚洲', '西亚'),
(236, 'GB', 'GBR', '826', '英国', 'United Kingdom', '大不列颠及北爱尔兰联合王国', 'United Kingdom of Great Britain and Northern Ireland', 1, '欧洲', '西欧'),
(237, 'US', 'USA', '840', '美国', 'United States', '美利坚合众国', 'United States of America', 1, '美洲', '北美洲'),
(238, 'UM', 'UMI', '581', '美国本土外小岛屿', 'United States Minor Outlying Islands', NULL, NULL, 0, '大洋洲', '密克罗尼西亚'),
(239, 'UY', 'URY', '858', '乌拉圭', 'Uruguay', '乌拉圭东岸共和国', 'Oriental Republic of Uruguay', 1, '美洲', '南美洲'),
(240, 'UZ', 'UZB', '860', '乌兹别克斯坦', 'Uzbekistan', '乌兹别克斯坦共和国', 'Republic of Uzbekistan', 1, '亚洲', '中亚'),
(241, 'VU', 'VUT', '548', '瓦努阿图', 'Vanuatu', '瓦努阿图共和国', 'Republic of Vanuatu', 1, '大洋洲', '美拉尼西亚'),
(242, 'VE', 'VEN', '862', '委内瑞拉', 'Venezuela', '委内瑞拉玻利瓦尔共和国', 'Bolivarian Republic of Venezuela', 1, '美洲', '南美洲'),
(243, 'VN', 'VNM', '704', '越南', 'Viet Nam', '越南社会主义共和国', 'Socialist Republic of Viet Nam', 1, '亚洲', '东南亚'),
(244, 'VG', 'VGB', '092', '英属维尔京群岛', 'Virgin Islands (British)', NULL, NULL, 0, '美洲', '加勒比'),
(245, 'VI', 'VIR', '850', '美属维尔京群岛', 'Virgin Islands (U.S.)', NULL, NULL, 0, '美洲', '加勒比'),
(246, 'WF', 'WLF', '876', '瓦利斯和富图纳', 'Wallis and Futuna', NULL, NULL, 0, '大洋洲', '波利尼西亚'),
(247, 'EH', 'ESH', '732', '西撒哈拉', 'Western Sahara', NULL, NULL, 0, '非洲', '北非'),
(248, 'YE', 'YEM', '887', '也门', 'Yemen', '也门共和国', 'Republic of Yemen', 1, '亚洲', '西亚'),
(249, 'ZM', 'ZMB', '894', '赞比亚', 'Zambia', '赞比亚共和国', 'Republic of Zambia', 1, '非洲', '东非'),
(250, 'ZW', 'ZWE', '716', '津巴布韦', 'Zimbabwe', '津巴布韦共和国', 'Republic of Zimbabwe', 1, '非洲', '东非'),
(251, 'ZZ', 'ZZZ', '111', '全部区域', 'All Country', '全部区域', 'All Country', 1, '全球', '全部地区'),
(252, 'KV', 'XKX', '900', '科索沃', 'Kosovo', '科索沃共和国', 'Republic of Kosovo', 1, '欧洲', '东南欧'),
(253, 'XK', 'XXK', '926', '科索沃', 'Kosovo', '科索沃共和国', 'Republic of Kosovo', 1, '欧洲', '南欧');

INSERT INTO `country_aliases` VALUES 
(1, 'United States', 'united states', 'US', '美国'),
(2, 'United Kingdom', 'united kingdom', 'GB', '内置'),
(3, 'Great Britain', 'great britain', 'GB', '内置'),
(4, 'Germany', 'germany', 'DE', '德国'),
(5, 'Japan', 'japan', 'JP', '日本'),
(6, 'Australia', 'australia', 'AU', '澳大利亚'),
(7, 'Brazil', 'brazil', 'BR', '巴西'),
(8, 'Canada', 'canada', 'CA', '加拿大'),
(9, 'South Korea', 'south korea', 'KR', '韩国'),
(10, 'Republic of Korea', 'republic of korea', 'KR', '韩国'),
(11, 'Korea', 'korea', 'KR', '韩国'),
(12, 'Turkiye', 'turkiye', 'TR', '土耳其'),
(13, 'Turkey', 'turkey', 'TR', '土耳其'),
(14, 'Vietnam', 'vietnam', 'VN', '越南'),
(15, 'Viet Nam', 'viet nam', 'VN', '越南'),
(16, 'India', 'india', 'IN', '内置'),
(17, 'Indonesia', 'indonesia', 'ID', '印度尼西亚'),
(18, 'Philippines', 'philippines', 'PH', '菲律宾'),
(19, 'Malaysia', 'malaysia', 'MY', '马拉西亚'),
(20, 'Singapore', 'singapore', 'SG', '新加坡'),
(21, 'Thailand', 'thailand', 'TH', '泰国'),
(22, 'Mexico', 'mexico', 'MX', '内置'),
(23, 'France', 'france', 'FR', '法国'),
(24, 'Italy', 'italy', 'IT', '内置'),
(25, 'Spain', 'spain', 'ES', '内置'),
(26, 'Netherlands', 'netherlands', 'NL', '内置'),
(27, 'Poland', 'poland', 'PL', '内置'),
(28, 'Taiwan', 'taiwan', 'TW', '台湾'),
(29, 'Hong Kong', 'hong kong', 'HK', '内置'),
(30, 'Russia', 'russia', 'RU', '内置'),
(31, 'Ukraine', 'ukraine', 'UA', '乌克兰'),
(32, 'Saudi Arabia', 'saudi arabia', 'SA', '内置'),
(33, 'United Arab Emirates', 'united arab emirates', 'AE', '内置'),
(34, 'UAE', 'uae', 'AE', '内置'),
(35, 'U.S. Virgin Islands', 'us virgin islands', 'VI', '美属维尔京群岛'),
(36, 'United States Virgin Islands', 'united states virgin islands', 'VI', '美属维尔京群岛'),
(37, 'Virgin Islands, U.S.', 'virgin islands, us', 'VI', '美属维尔京群岛'),
(38, 'British Virgin Islands', 'british virgin islands', 'VG', '英属维尔京群岛'),
(39, 'Virgin Islands, UK', 'virgin islands, uk', 'VG', '英属维尔京群岛'),
(40, 'Puerto Rico', 'puerto rico', 'PR', '内置'),
(41, 'Guam', 'guam', 'GU', '内置'),
(42, 'American Samoa', 'american samoa', 'AS', '内置'),
(43, 'Northern Mariana Islands', 'northern mariana islands', 'MP', '内置'),
(44, 'Cayman Islands', 'cayman islands', 'KY', '内置'),
(45, 'Bermuda', 'bermuda', 'BM', '内置'),
(46, 'Hong Kong SAR', 'hong kong sar', 'HK', '内置'),
(47, 'Macau', 'macau', 'MO', '内置'),
(48, 'Macao', 'macao', 'MO', '内置'),
(49, 'Laos', 'laos', 'LA', '老挝'),
(50, 'Kosovo', 'kosovo', 'XK', '科索沃'),
(51, 'Republic of Kosovo', 'republic of kosovo', 'XK', '科索沃'),
(52, 'Falkland Islands (Islas Malvinas)', 'falkland islands islas malvinas', 'GB', '福克兰群岛 属于 英国');


-- 短链接点击刷盘幂等账本：解决 DB COMMIT 与 Redis ACK 之间的崩溃/响应丢失窗口。
CREATE TABLE IF NOT EXISTS short_link_click_sync_batches (
    batch_id VARCHAR(64) NOT NULL COMMENT 'Redis pending batch UUID',
    short_code VARCHAR(20) NOT NULL COMMENT '短链接代码',
    click_count INT NOT NULL COMMENT '本批次待入账点击数',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    acknowledged_at DATETIME NULL COMMENT 'Redis pending key 确认删除时间',
    PRIMARY KEY (batch_id),
    KEY idx_short_click_batch_code_created (short_code, created_at),
    KEY idx_short_click_batch_ack_created (acknowledged_at, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='短链接点击刷盘幂等账本';

-- Cap Reservation 持久化账本：与 Postback DB 事务解耦，支持 Redis 预留崩溃恢复。
CREATE TABLE IF NOT EXISTS cap_reservations (
    id INT NOT NULL AUTO_INCREMENT COMMENT '预留账本主键',
    reservation_key VARCHAR(64) NOT NULL COMMENT '稳定预留键：正式事件键与 Cap scope 的 SHA-256',
    platform VARCHAR(50) NOT NULL COMMENT 'Postback 平台',
    conversion_id VARCHAR(255) NOT NULL COMMENT '正式转化事件 ID',
    event_name VARCHAR(100) NOT NULL DEFAULT 'default' COMMENT '标准化事件名称',
    offer_id INT NOT NULL COMMENT '预留时的 Offer ID 快照',
    publisher_id INT NULL COMMENT '预留时的 Publisher ID 快照；NULL 表示全局渠道范围',
    cap_kind VARCHAR(10) NOT NULL COMMENT 'Cap 类型：daily 或 total',
    business_date DATE NULL COMMENT 'Daily 业务日期；Total 必须为 NULL',
    redis_counter_key VARCHAR(255) NOT NULL COMMENT 'Redis 计数器 Key 快照',
    redis_token_key VARCHAR(512) NOT NULL COMMENT 'Redis reservation token Key 快照',
    redis_reserved BOOLEAN NOT NULL DEFAULT FALSE COMMENT '是否确认 Redis Lua 已成功预留；区分 fail-open 无 token 路径',
    redis_token_cleaned BOOLEAN NOT NULL DEFAULT FALSE COMMENT '终态后是否已清理 Redis token；清理失败由恢复任务重试',
    state VARCHAR(24) NOT NULL DEFAULT 'PREPARED'
        COMMENT 'PREPARED/RESERVED/COMMITTED/ROLLED_BACK/NEEDS_RECONCILIATION',
    attempts INT NOT NULL DEFAULT 0 COMMENT '恢复尝试次数',
    lease_owner VARCHAR(64) NULL COMMENT '恢复 Worker 租约持有者',
    lease_expires_at DATETIME NULL COMMENT '恢复 Worker 租约到期时间',
    last_error TEXT NULL COMMENT '最近一次恢复错误摘要',
    prepared_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'PREPARED 创建时间',
    reserved_at DATETIME NULL COMMENT 'Redis 预留确认时间',
    finalized_at DATETIME NULL COMMENT '终态确认时间',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uq_cap_reservation_key (reservation_key),
    KEY idx_cap_reservation_state_updated (state, updated_at),
    KEY idx_cap_reservation_lease (state, lease_expires_at),
    KEY idx_cap_reservation_event (platform, conversion_id, event_name),
    KEY idx_cap_reservation_scope (offer_id, publisher_id, cap_kind, business_date),
    CONSTRAINT chk_cap_reservation_key_sha256 CHECK (LENGTH(reservation_key) = 64),
    CONSTRAINT chk_cap_reservation_offer_positive CHECK (offer_id > 0),
    CONSTRAINT chk_cap_reservation_publisher_positive CHECK (publisher_id IS NULL OR publisher_id > 0),
    CONSTRAINT chk_cap_reservation_attempts_nonnegative CHECK (attempts >= 0),
    CONSTRAINT chk_cap_reservation_kind_date CHECK (
        (cap_kind = 'daily' AND business_date IS NOT NULL) OR
        (cap_kind = 'total' AND business_date IS NULL)
    ),
    CONSTRAINT chk_cap_reservation_state CHECK (
        state IN ('PREPARED', 'RESERVED', 'COMMITTED', 'ROLLED_BACK', 'NEEDS_RECONCILIATION')
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Cap Redis 预留持久化账本';

-- 迁移后人工核验（仅隔离环境或正式发布审批窗口执行）：
-- SHOW CREATE TABLE cap_reservations;
-- SHOW INDEX FROM cap_reservations;
-- SELECT COUNT(*) FROM cap_reservations;

SET FOREIGN_KEY_CHECKS = 1;
