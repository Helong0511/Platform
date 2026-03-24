/*
 Navicat Premium Dump SQL

 Source Server         : 广告平台
 Source Server Type    : MySQL
 Source Server Version : 80044 (8.0.44-0ubuntu0.22.04.2)
 Source Host           : 43.156.101.243:3306
 Source Schema         : platform

 Target Server Type    : MySQL
 Target Server Version : 80044 (8.0.44-0ubuntu0.22.04.2)
 File Encoding         : 65001

 Date: 24/03/2026 11:36:28
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for ad_data
-- ----------------------------
DROP TABLE IF EXISTS `ad_data`;
CREATE TABLE `ad_data`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '广告数据ID',
  `date` datetime NOT NULL COMMENT '数据日期',
  `country_code` varchar(5) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT 'ZZ' COMMENT '国家代码（ISO 3166-1 二字母代码）',
  `product_id` int NOT NULL COMMENT '产品ID',
  `request_count` int NOT NULL DEFAULT 0 COMMENT '请求数',
  `match_count` int NOT NULL DEFAULT 0 COMMENT '匹配数',
  `coverage_rate` float NULL DEFAULT 0 COMMENT '覆盖率',
  `display_count` int NOT NULL DEFAULT 0 COMMENT '展示数',
  `display_rate` float NULL DEFAULT 0 COMMENT '展示率',
  `click_count` int NOT NULL DEFAULT 0 COMMENT '点击数',
  `click_rate` float NULL DEFAULT 0 COMMENT '点击率',
  `viewability_rate` float NULL DEFAULT 0 COMMENT '可见率',
  `cpc` float NULL DEFAULT 0 COMMENT 'CPC',
  `pageviews` int NULL DEFAULT 0 COMMENT 'PageViews',
  `ecpm_before_deduct` float NOT NULL DEFAULT 0 COMMENT 'eCPM未减扣',
  `ecpm_after_deduct` float NOT NULL DEFAULT 0 COMMENT 'eCPM已减扣',
  `revenue_before_deduct` float NOT NULL DEFAULT 0 COMMENT '收益未减扣',
  `revenue_after_deduct` float NOT NULL DEFAULT 0 COMMENT '收益已减扣',
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  `is_deducted` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否已被扣减',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_ad_data_date_product_country`(`date` ASC, `product_id` ASC, `country_code` ASC) USING BTREE,
  INDEX `idx_ad_data_date`(`date` ASC) USING BTREE,
  INDEX `idx_ad_data_product`(`product_id` ASC) USING BTREE,
  INDEX `idx_ad_data_date_product`(`date` ASC, `product_id` ASC) USING BTREE,
  INDEX `idx_ad_data_country_code`(`country_code` ASC) USING BTREE,
  CONSTRAINT `fk_ad_data_product` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '广告数据表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for ad_data_archive
-- ----------------------------
DROP TABLE IF EXISTS `ad_data_archive`;
CREATE TABLE `ad_data_archive`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '广告数据ID',
  `date` datetime NOT NULL COMMENT '数据日期',
  `country_code` varchar(2) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '国家代码（ISO 3166-1 二字母代码）',
  `product_id` int NOT NULL COMMENT '产品ID',
  `request_count` int NOT NULL DEFAULT 0 COMMENT '请求数',
  `match_count` int NOT NULL DEFAULT 0 COMMENT '匹配数',
  `display_count` int NOT NULL DEFAULT 0 COMMENT '展示数',
  `click_count` int NOT NULL DEFAULT 0 COMMENT '点击数',
  `ecpm_before_deduct` float NOT NULL DEFAULT 0 COMMENT 'eCPM未减扣',
  `ecpm_after_deduct` float NOT NULL DEFAULT 0 COMMENT 'eCPM已减扣',
  `revenue_before_deduct` float NOT NULL DEFAULT 0 COMMENT '收益未减扣',
  `revenue_after_deduct` float NOT NULL DEFAULT 0 COMMENT '收益已减扣',
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_ad_data_archive_date_product_country`(`date` ASC, `product_id` ASC, `country_code` ASC) USING BTREE,
  INDEX `idx_ad_data_archive_date`(`date` ASC) USING BTREE,
  INDEX `idx_ad_data_archive_product`(`product_id` ASC) USING BTREE,
  INDEX `idx_ad_data_archive_date_product`(`date` ASC, `product_id` ASC) USING BTREE,
  INDEX `idx_ad_data_archive_country_code`(`country_code` ASC) USING BTREE,
  CONSTRAINT `fk_ad_data_archive_country_code` FOREIGN KEY (`country_code`) REFERENCES `countries` (`alpha_2_code`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `fk_ad_data_archive_product` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '广告数据归档表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for admin_notification_configs
-- ----------------------------
DROP TABLE IF EXISTS `admin_notification_configs`;
CREATE TABLE `admin_notification_configs`  (
  `id` int NOT NULL DEFAULT 1 COMMENT '配置ID（固定为1，单例模式）',
  `telegram_enabled` tinyint(1) NOT NULL DEFAULT 1 COMMENT '是否启用 Telegram 通知',
  `telegram_chat_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '管理员 Telegram Chat ID',
  `notify_all_conversions` tinyint(1) NOT NULL DEFAULT 1 COMMENT '通知所有转化',
  `notify_forward_failure` tinyint(1) NOT NULL DEFAULT 1 COMMENT '通知转发失败',
  `notify_forward_success` tinyint(1) NOT NULL DEFAULT 0 COMMENT '通知转发成功（可选）',
  `notify_system_errors` tinyint(1) NOT NULL DEFAULT 1 COMMENT '通知系统异常',
  `notify_statistics` tinyint(1) NOT NULL DEFAULT 0 COMMENT '定时统计通知',
  `statistics_frequency` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'hourly' COMMENT '统计频率：hourly, daily',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  CONSTRAINT `check_single_record` CHECK (`id` = 1)
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '管理员通知配置表（单例模式）' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for advertiser_tests
-- ----------------------------
DROP TABLE IF EXISTS `advertiser_tests`;
CREATE TABLE `advertiser_tests`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '测试记录ID',
  `advertiser_id` int NOT NULL COMMENT '广告主ID',
  `advertiser_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '广告主名称',
  `advertiser_offer_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '上游系统中的Offer ID',
  `offer_id` int NOT NULL COMMENT '平台内的Offer ID',
  `offer_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT 'Offer名称',
  `price` float NULL DEFAULT NULL COMMENT '价格',
  `country` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '国家',
  `click_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '测试生成的Click ID',
  `click_url` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '测试生成的Click Url',
  `test_time` datetime NULL DEFAULT NULL COMMENT '测试时间',
  `created_at` datetime NOT NULL COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_advertiser_id`(`advertiser_id` ASC) USING BTREE,
  INDEX `idx_test_time`(`test_time` ASC) USING BTREE,
  INDEX `ix_advertiser_tests_id`(`id` ASC) USING BTREE,
  INDEX `ix_advertiser_tests_advertiser_id`(`advertiser_id` ASC) USING BTREE,
  INDEX `idx_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `ix_advertiser_tests_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `ix_advertiser_tests_test_time`(`test_time` ASC) USING BTREE,
  CONSTRAINT `advertiser_tests_ibfk_1` FOREIGN KEY (`advertiser_id`) REFERENCES `advertisers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `advertiser_tests_ibfk_2` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for advertisers
-- ----------------------------
DROP TABLE IF EXISTS `advertisers`;
CREATE TABLE `advertisers`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '广告主ID',
  `advertiser_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '广告主名称',
  `email` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '邮箱（可选）',
  `mobile` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '手机号',
  `advertiser_params` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '广告主参数',
  `is_active` tinyint(1) NULL DEFAULT 1 COMMENT '是否激活',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_advertiser_name`(`advertiser_name` ASC) USING BTREE,
  INDEX `idx_is_active`(`is_active` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '广告主表（上游）' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for affiliate_tests
-- ----------------------------
DROP TABLE IF EXISTS `affiliate_tests`;
CREATE TABLE `affiliate_tests`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '测试记录ID',
  `publisher_id` int NOT NULL COMMENT '渠道ID',
  `click_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '下游提供的Click ID',
  `offer_id` int NOT NULL COMMENT 'Offer ID',
  `offer_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT 'Offer名称',
  `price` float NULL DEFAULT NULL COMMENT '价格',
  `country` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '国家',
  `platform` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '平台',
  `postback_time` datetime NULL DEFAULT NULL COMMENT 'Postback发送时间',
  `status` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '发送状态：Send Success/Failed',
  `affiliate_return_content` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '渠道返回内容',
  `created_at` datetime NOT NULL COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_publisher_id`(`publisher_id` ASC) USING BTREE,
  INDEX `ix_affiliate_tests_id`(`id` ASC) USING BTREE,
  INDEX `idx_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `ix_affiliate_tests_click_id`(`click_id` ASC) USING BTREE,
  INDEX `ix_affiliate_tests_status`(`status` ASC) USING BTREE,
  INDEX `idx_postback_time`(`postback_time` ASC) USING BTREE,
  INDEX `ix_affiliate_tests_postback_time`(`postback_time` ASC) USING BTREE,
  INDEX `idx_status`(`status` ASC) USING BTREE,
  INDEX `idx_click_id`(`click_id` ASC) USING BTREE,
  INDEX `ix_affiliate_tests_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `ix_affiliate_tests_publisher_id`(`publisher_id` ASC) USING BTREE,
  CONSTRAINT `affiliate_tests_ibfk_1` FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `affiliate_tests_ibfk_2` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for clicks
-- ----------------------------
DROP TABLE IF EXISTS `clicks`;
CREATE TABLE `clicks`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '点击记录ID',
  `click_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '点击ID（系统生成，唯一标识）',
  `offer_id` int NULL DEFAULT NULL COMMENT '关联的Offer ID',
  `publisher_id` int NULL DEFAULT NULL COMMENT '关联的渠道ID',
  `advertiser_id` int NULL DEFAULT NULL COMMENT '关联的广告主ID',
  `short_link_id` int NULL DEFAULT NULL COMMENT '关联的短链接ID',
  `click_time` datetime NOT NULL COMMENT '点击时间',
  `ip` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '点击IP地址',
  `device` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '设备信息',
  `country` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '国家',
  `user_agent` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT 'User Agent',
  `referer` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '来源页面',
  `os` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '操作系统名称',
  `os_version` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '操作系统版本',
  `browser` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '浏览器名称',
  `browser_version` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '浏览器版本',
  `accept_language` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '接受的语言',
  `accept_encoding` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '接受的编码',
  `is_bot` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否为机器人/爬虫',
  `device_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '设备类型（mobile/tablet/desktop）',
  `device_brand` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '设备品牌',
  `device_model` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '设备型号',
  `url_params` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT 'URL参数（JSON格式）',
  `all_headers` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '所有请求头（JSON格式）',
  `original_request_url` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '原始点击URL（用户访问的短链接URL）',
  `final_redirect_url` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '最终跳转URL（系统重定向后的URL）',
  `conversion_id` int NULL DEFAULT NULL COMMENT '关联的转化ID（如果已转化）',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `click_id`(`click_id` ASC) USING BTREE,
  INDEX `idx_click_id`(`click_id` ASC) USING BTREE,
  INDEX `idx_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_publisher_id`(`publisher_id` ASC) USING BTREE,
  INDEX `idx_advertiser_id`(`advertiser_id` ASC) USING BTREE,
  INDEX `idx_click_time`(`click_time` ASC) USING BTREE,
  INDEX `idx_conversion_id`(`conversion_id` ASC) USING BTREE,
  INDEX `idx_short_link_id`(`short_link_id` ASC) USING BTREE,
  INDEX `idx_clicks_time_offer_publisher`(`click_time` ASC, `offer_id` ASC, `publisher_id` ASC) USING BTREE,
  INDEX `idx_clicks_time_offer`(`click_time` ASC, `offer_id` ASC) USING BTREE,
  INDEX `idx_clicks_offer_publisher_time`(`offer_id` ASC, `publisher_id` ASC, `click_time` ASC) USING BTREE,
  INDEX `idx_device_type`(`device_type` ASC) USING BTREE,
  INDEX `idx_os`(`os` ASC) USING BTREE,
  INDEX `idx_browser`(`browser` ASC) USING BTREE,
  INDEX `idx_is_bot`(`is_bot` ASC) USING BTREE,
  INDEX `idx_ip`(`ip` ASC) USING BTREE,
  INDEX `idx_country`(`country` ASC) USING BTREE,
  INDEX `idx_click_time_offer`(`click_time` ASC, `offer_id` ASC) USING BTREE,
  INDEX `idx_click_time_publisher`(`click_time` ASC, `publisher_id` ASC) USING BTREE,
  INDEX `idx_click_time_offer_publisher`(`click_time` ASC, `offer_id` ASC, `publisher_id` ASC) USING BTREE,
  INDEX `idx_safe_delete`(`advertiser_id` ASC, `offer_id` ASC, `publisher_id` ASC, `created_at` ASC) USING BTREE,
  CONSTRAINT `clicks_ibfk_1` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `clicks_ibfk_2` FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `clicks_ibfk_3` FOREIGN KEY (`advertiser_id`) REFERENCES `advertisers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `clicks_ibfk_short_link` FOREIGN KEY (`short_link_id`) REFERENCES `short_links` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '点击记录表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for clicks_archive
-- ----------------------------
DROP TABLE IF EXISTS `clicks_archive`;
CREATE TABLE `clicks_archive`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '点击记录ID',
  `click_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '点击ID（系统生成，唯一标识）',
  `offer_id` int NULL DEFAULT NULL COMMENT '关联的Offer ID',
  `publisher_id` int NULL DEFAULT NULL COMMENT '关联的渠道ID',
  `advertiser_id` int NULL DEFAULT NULL COMMENT '关联的广告主ID',
  `short_link_id` int NULL DEFAULT NULL COMMENT '关联的短链接ID',
  `click_time` datetime NOT NULL COMMENT '点击时间',
  `ip` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '点击IP地址',
  `device` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '设备信息',
  `country` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '国家',
  `user_agent` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT 'User Agent',
  `referer` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '来源页面',
  `conversion_id` int NULL DEFAULT NULL COMMENT '关联的转化ID（如果已转化）',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `os` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '操作系统名称',
  `os_version` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '操作系统版本',
  `browser` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '浏览器名称',
  `browser_version` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '浏览器版本',
  `accept_language` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '接受的语言',
  `accept_encoding` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '接受的编码',
  `is_bot` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否为机器人/爬虫',
  `device_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '设备类型（mobile/tablet/desktop）',
  `device_brand` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '设备品牌',
  `device_model` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '设备型号',
  `url_params` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT 'URL参数（JSON格式）',
  `all_headers` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '所有请求头（JSON格式）',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_click_id`(`click_id` ASC) USING BTREE,
  INDEX `idx_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_publisher_id`(`publisher_id` ASC) USING BTREE,
  INDEX `idx_advertiser_id`(`advertiser_id` ASC) USING BTREE,
  INDEX `idx_short_link_id`(`short_link_id` ASC) USING BTREE,
  INDEX `idx_click_time`(`click_time` ASC) USING BTREE,
  INDEX `idx_conversion_id`(`conversion_id` ASC) USING BTREE,
  INDEX `idx_clicks_time_offer_publisher`(`click_time` ASC, `offer_id` ASC, `publisher_id` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '点击记录归档表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for client_notification_configs
-- ----------------------------
DROP TABLE IF EXISTS `client_notification_configs`;
CREATE TABLE `client_notification_configs`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '通知配置ID',
  `client_id` int NOT NULL COMMENT '客户ID',
  `notification_enabled` tinyint(1) NULL DEFAULT NULL COMMENT '是否启用通知',
  `notify_on_conversion` tinyint(1) NULL DEFAULT NULL COMMENT '转化时通知',
  `notify_on_high_value` tinyint(1) NULL DEFAULT NULL COMMENT '高价值转化通知',
  `high_value_threshold` float NULL DEFAULT NULL COMMENT '高价值阈值',
  `notify_channels` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '通知渠道（JSON格式：[\"telegram\", \"email\", \"sms\"]）',
  `telegram_chat_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT 'Telegram Chat ID',
  `email_address` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '邮箱地址',
  `phone_number` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '手机号',
  `notification_frequency` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '通知频率：realtime, hourly, daily',
  `created_at` datetime NULL DEFAULT NULL COMMENT '创建时间',
  `updated_at` datetime NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `ix_client_notification_configs_client_id`(`client_id` ASC) USING BTREE,
  INDEX `idx_client_notification_config_enabled`(`notification_enabled` ASC) USING BTREE,
  INDEX `idx_client_notification_config_client`(`client_id` ASC) USING BTREE,
  INDEX `ix_client_notification_configs_id`(`id` ASC) USING BTREE,
  CONSTRAINT `client_notification_configs_ibfk_1` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for clients
-- ----------------------------
DROP TABLE IF EXISTS `clients`;
CREATE TABLE `clients`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '客户ID',
  `user_id` int NOT NULL COMMENT '用户ID',
  `company_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '公司名称',
  `contact_person` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '联系人',
  `phone` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '联系电话',
  `address` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '公司地址',
  `allowed_ips` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT 'IP白名单，多个IP用逗号分隔，为空则不限制',
  `key` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '客户唯一标识UUID',
  `is_active` tinyint(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
  `api_enabled` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否允许API访问（开启后允许客户通过API查询产品和广告数据，并显示API对接菜单）',
  `password_change_enabled` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否允许客户修改密码（开启后客户可以修改自己的密码）',
  `chat_id` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '15位聊天ID',
  `notify_url` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '客户广告数据通知地址',
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_clients_key`(`key` ASC) USING BTREE,
  UNIQUE INDEX `chat_id`(`chat_id` ASC) USING BTREE,
  INDEX `idx_client_user`(`user_id` ASC) USING BTREE,
  INDEX `idx_clients_key`(`key` ASC) USING BTREE,
  FULLTEXT INDEX `ft_clients_search`(`company_name`, `contact_person`) WITH PARSER `ngram`,
  CONSTRAINT `fk_clients_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '客户表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for conversion_deduction_configs
-- ----------------------------
DROP TABLE IF EXISTS `conversion_deduction_configs`;
CREATE TABLE `conversion_deduction_configs`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '配置ID',
  `advertiser_id` int NULL DEFAULT NULL COMMENT '广告主ID（如果配置在广告主级别）',
  `offer_id` int NULL DEFAULT NULL COMMENT 'Offer ID（如果配置在Offer级别）',
  `publisher_id` int NULL DEFAULT NULL COMMENT '渠道ID（如果配置在渠道级别）',
  `volume_deduction_ratio` decimal(5, 4) NULL DEFAULT 0.0000 COMMENT '按比例扣量比例（0-1，如0.10表示扣量10%）',
  `amount_deduction_ratio` decimal(5, 4) NULL DEFAULT 0.0000 COMMENT '按比例扣金额比例（0-1，如0.10表示扣金额10%）',
  `deduction_strategy` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT 'random' COMMENT '扣减策略：random（随机）/proportional（按比例）/round_robin（轮询）',
  `enable_volume_deduction` tinyint(1) NULL DEFAULT 0 COMMENT '是否启用按比例扣量',
  `enable_amount_deduction` tinyint(1) NULL DEFAULT 0 COMMENT '是否启用按比例扣金额',
  `priority` int NULL DEFAULT 0 COMMENT '优先级（数字越大优先级越高）',
  `is_active` tinyint(1) NULL DEFAULT 1 COMMENT '是否激活',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
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
CREATE TABLE `conversion_deduction_logs`  (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '记录ID',
  `conversion_id` bigint NULL DEFAULT NULL COMMENT '转化记录ID（关联postback_conversions.id，可为NULL因为扣量的转化可能不保存）',
  `click_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '点击ID',
  `advertiser_id` int NULL DEFAULT NULL COMMENT '广告主ID',
  `offer_id` int NULL DEFAULT NULL COMMENT 'Offer ID',
  `publisher_id` int NULL DEFAULT NULL COMMENT '渠道ID',
  `original_volume` int NULL DEFAULT 1 COMMENT '原始转化数量（通常为1）',
  `original_amount` decimal(10, 2) NOT NULL COMMENT '原始转化金额',
  `deducted_volume` int NULL DEFAULT 0 COMMENT '扣减的转化数量',
  `deducted_amount` decimal(10, 2) NULL DEFAULT 0.00 COMMENT '扣减的转化金额',
  `final_volume` int NULL DEFAULT 1 COMMENT '最终转化数量（扣减后）',
  `final_amount` decimal(10, 2) NOT NULL COMMENT '最终转化金额（扣减后）',
  `deduction_config_id` int NULL DEFAULT NULL COMMENT '使用的扣减配置ID',
  `volume_deduction_ratio` decimal(5, 4) NULL DEFAULT NULL COMMENT '使用的扣量比例',
  `amount_deduction_ratio` decimal(5, 4) NULL DEFAULT NULL COMMENT '使用的扣金额比例',
  `deduction_strategy` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '使用的扣减策略',
  `deduction_reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT '扣减原因说明',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_conversion_id`(`conversion_id` ASC) USING BTREE,
  INDEX `idx_click_id`(`click_id` ASC) USING BTREE,
  INDEX `idx_advertiser_id`(`advertiser_id` ASC) USING BTREE,
  INDEX `idx_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_publisher_id`(`publisher_id` ASC) USING BTREE,
  INDEX `idx_created_at`(`created_at` ASC) USING BTREE,
  INDEX `idx_deduction_config_id`(`deduction_config_id` ASC) USING BTREE,
  CONSTRAINT `conversion_deduction_logs_ibfk_1` FOREIGN KEY (`advertiser_id`) REFERENCES `advertisers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `conversion_deduction_logs_ibfk_2` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `conversion_deduction_logs_ibfk_3` FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `conversion_deduction_logs_ibfk_4` FOREIGN KEY (`deduction_config_id`) REFERENCES `conversion_deduction_configs` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '转化扣减执行记录表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for countries
-- ----------------------------
DROP TABLE IF EXISTS `countries`;
CREATE TABLE `countries`  (
  `id` int NOT NULL AUTO_INCREMENT,
  `alpha_2_code` char(2) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '国家二字代码',
  `alpha_3_code` char(3) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '国家三字代码',
  `numeric_code` char(3) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '国家数字代码',
  `country_name_zh` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '国家中文名称',
  `country_name_en` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '国家英文名称',
  `official_name_zh` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '官方中文名称',
  `official_name_en` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '官方英文名称',
  `independent_status` tinyint(1) NULL DEFAULT 1 COMMENT '是否独立国家',
  `continent` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '所属大洲',
  `subregion` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '所属地区',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `alpha_2_code`(`alpha_2_code` ASC) USING BTREE,
  UNIQUE INDEX `alpha_3_code`(`alpha_3_code` ASC) USING BTREE,
  UNIQUE INDEX `numeric_code`(`numeric_code` ASC) USING BTREE,
  INDEX `idx_country_name_zh`(`country_name_zh` ASC) USING BTREE,
  INDEX `idx_country_name_en`(`country_name_en` ASC) USING BTREE,
  INDEX `idx_continent`(`continent` ASC) USING BTREE,
  INDEX `idx_subregion`(`subregion` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'ISO 3166-1国家代码表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for offer_caps
-- ----------------------------
DROP TABLE IF EXISTS `offer_caps`;
CREATE TABLE `offer_caps`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'Cap配置ID',
  `cap_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Cap类型：advertiser_offer/offer',
  `advertiser_id` int NULL DEFAULT NULL COMMENT '广告主ID（如果是advertiser_offer类型）',
  `offer_id` int NOT NULL COMMENT 'Offer ID',
  `publisher_id` int NULL DEFAULT NULL COMMENT '渠道ID（如果为空，表示所有渠道）',
  `daily_cap` int NULL DEFAULT NULL COMMENT '每日Cap',
  `total_cap` int NULL DEFAULT NULL COMMENT '总Cap',
  `current_daily_count` int NULL DEFAULT NULL COMMENT '当前每日计数',
  `current_total_count` int NULL DEFAULT NULL COMMENT '当前总计数',
  `cap_start_date` datetime NULL DEFAULT NULL COMMENT 'Cap开始日期（用于Total Cap）',
  `is_active` tinyint(1) NULL DEFAULT NULL COMMENT '是否激活',
  `created_at` datetime NOT NULL COMMENT '创建时间',
  `updated_at` datetime NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `ix_offer_caps_advertiser_id`(`advertiser_id` ASC) USING BTREE,
  INDEX `ix_offer_caps_id`(`id` ASC) USING BTREE,
  INDEX `ix_offer_caps_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_advertiser_id`(`advertiser_id` ASC) USING BTREE,
  INDEX `ix_offer_caps_cap_type`(`cap_type` ASC) USING BTREE,
  INDEX `ix_offer_caps_publisher_id`(`publisher_id` ASC) USING BTREE,
  INDEX `idx_publisher_id`(`publisher_id` ASC) USING BTREE,
  INDEX `idx_is_active`(`is_active` ASC) USING BTREE,
  INDEX `ix_offer_caps_is_active`(`is_active` ASC) USING BTREE,
  INDEX `idx_cap_type`(`cap_type` ASC) USING BTREE,
  CONSTRAINT `offer_caps_ibfk_1` FOREIGN KEY (`advertiser_id`) REFERENCES `advertisers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `offer_caps_ibfk_2` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `offer_caps_ibfk_3` FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for offer_discounts
-- ----------------------------
DROP TABLE IF EXISTS `offer_discounts`;
CREATE TABLE `offer_discounts`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '扣量配置ID',
  `discount_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '扣量类型：offer/channel',
  `offer_id` int NULL DEFAULT NULL COMMENT 'Offer ID（如果是offer类型）',
  `publisher_id` int NOT NULL COMMENT '渠道ID',
  `discount_ratio` float NOT NULL COMMENT '扣量比例（0-100）',
  `is_active` tinyint(1) NULL DEFAULT NULL COMMENT '是否激活',
  `created_at` datetime NOT NULL COMMENT '创建时间',
  `updated_at` datetime NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `ix_offer_discounts_publisher_id`(`publisher_id` ASC) USING BTREE,
  INDEX `idx_is_active`(`is_active` ASC) USING BTREE,
  INDEX `idx_publisher_id`(`publisher_id` ASC) USING BTREE,
  INDEX `ix_offer_discounts_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `ix_offer_discounts_is_active`(`is_active` ASC) USING BTREE,
  INDEX `idx_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_discount_type`(`discount_type` ASC) USING BTREE,
  INDEX `ix_offer_discounts_discount_type`(`discount_type` ASC) USING BTREE,
  INDEX `ix_offer_discounts_id`(`id` ASC) USING BTREE,
  CONSTRAINT `offer_discounts_ibfk_1` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `offer_discounts_ibfk_2` FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for offer_publisher_assignments
-- ----------------------------
DROP TABLE IF EXISTS `offer_publisher_assignments`;
CREATE TABLE `offer_publisher_assignments`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '分配ID',
  `offer_id` int NOT NULL COMMENT 'Offer ID',
  `publisher_id` int NOT NULL COMMENT '渠道ID',
  `downstream_cap` int NULL DEFAULT NULL COMMENT '该渠道的下游转化上限',
  `affiliate_payout` decimal(10, 2) NULL DEFAULT NULL COMMENT '该渠道的扣价后给渠道的金额（PO扣价后）',
  `is_active` tinyint(1) NULL DEFAULT 1 COMMENT '是否激活',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_offer_publisher`(`offer_id` ASC, `publisher_id` ASC) USING BTREE,
  INDEX `idx_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_publisher_id`(`publisher_id` ASC) USING BTREE,
  INDEX `idx_is_active`(`is_active` ASC) USING BTREE,
  CONSTRAINT `offer_publisher_assignments_ibfk_1` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `offer_publisher_assignments_ibfk_2` FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'Offer-渠道分配表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for offers
-- ----------------------------
DROP TABLE IF EXISTS `offers`;
CREATE TABLE `offers`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'Offer ID（主键）',
  `offer_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Offer名称',
  `advertiser_offer_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '上游系统中的Offer ID（ADV Offer ID）',
  `advertiser_id` int NOT NULL COMMENT '关联的广告主ID',
  `preview_link` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '预览链接',
  `payout` decimal(10, 2) NULL DEFAULT NULL COMMENT '上游支付金额（PO）',
  `affiliate_payout` decimal(10, 2) NULL DEFAULT NULL COMMENT '扣价后给渠道的金额（PO扣价后）',
  `country` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '国家',
  `category` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '分类',
  `type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '类型',
  `status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT 'Active' COMMENT '状态：Active/Inactive',
  `upstream_cap` int NULL DEFAULT NULL COMMENT '上游转化上限',
  `downstream_cap` int NULL DEFAULT NULL COMMENT '下游转化上限',
  `advertiser_tracklink` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '上游的Tracklink（不显示给下游，建立单子时配置我们的参数）',
  `downstream_tracklink` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '生成给下游的Tracklink',
  `postback_url` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT 'Postback URL（配置我们的参数）',
  `postback_method` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT 'GET' COMMENT 'Postback请求方式：GET/POST',
  `is_active` tinyint(1) NULL DEFAULT 1 COMMENT '是否激活',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `click_validity_hours` int NULL DEFAULT 720 COMMENT '点击有效期（小时），默认720小时（30天）',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_advertiser_id`(`advertiser_id` ASC) USING BTREE,
  INDEX `idx_status`(`status` ASC) USING BTREE,
  INDEX `idx_is_active`(`is_active` ASC) USING BTREE,
  INDEX `idx_country`(`country` ASC) USING BTREE,
  FULLTEXT INDEX `ft_offer_name`(`offer_name`),
  CONSTRAINT `offers_ibfk_1` FOREIGN KEY (`advertiser_id`) REFERENCES `advertisers` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'Offer表（单子表）' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for pending_postback_conversions
-- ----------------------------
DROP TABLE IF EXISTS `pending_postback_conversions`;
CREATE TABLE `pending_postback_conversions`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '待确认记录ID',
  `platform` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '平台名称',
  `conversion_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '转化ID',
  `event_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '事件名称',
  `event_value` float NULL DEFAULT NULL COMMENT '事件价值',
  `original_payout` float NULL DEFAULT NULL COMMENT '原始支付金额（PO）',
  `payout` float NULL DEFAULT NULL COMMENT '扣后支付金额（PO(扣)）',
  `devad_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '设备广告ID',
  `os` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '操作系统',
  `carrier` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '用户运营商',
  `ip` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT 'IP地址',
  `gid` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '渠道ID',
  `product_id` int NULL DEFAULT NULL COMMENT '关联的产品ID',
  `client_id` int NULL DEFAULT NULL COMMENT '关联的客户ID',
  `click_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '关联的Click ID',
  `click_time` datetime NULL DEFAULT NULL COMMENT '点击时间',
  `raw_data` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '原始回调数据（JSON格式）',
  `request_ip` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '请求IP地址（不在白名单）',
  `status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '状态：pending(待确认)/approved(已批准)/rejected(已拒绝)',
  `telegram_message_id` int NULL DEFAULT NULL COMMENT 'Telegram 消息ID（用于更新消息）',
  `telegram_chat_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT 'Telegram Chat ID',
  `created_at` datetime NOT NULL COMMENT '创建时间',
  `updated_at` datetime NOT NULL COMMENT '更新时间',
  `approved_at` datetime NULL DEFAULT NULL COMMENT '批准时间',
  `rejected_at` datetime NULL DEFAULT NULL COMMENT '拒绝时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `product_id`(`product_id` ASC) USING BTREE,
  INDEX `client_id`(`client_id` ASC) USING BTREE,
  INDEX `ix_pending_postback_conversions_request_ip`(`request_ip` ASC) USING BTREE,
  INDEX `ix_pending_postback_conversions_id`(`id` ASC) USING BTREE,
  INDEX `ix_pending_postback_conversions_platform`(`platform` ASC) USING BTREE,
  INDEX `idx_status`(`status` ASC) USING BTREE,
  INDEX `ix_pending_postback_conversions_status`(`status` ASC) USING BTREE,
  INDEX `idx_request_ip`(`request_ip` ASC) USING BTREE,
  INDEX `ix_pending_postback_conversions_click_id`(`click_id` ASC) USING BTREE,
  INDEX `idx_created_at`(`created_at` ASC) USING BTREE,
  INDEX `ix_pending_postback_conversions_created_at`(`created_at` ASC) USING BTREE,
  CONSTRAINT `pending_postback_conversions_ibfk_1` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `pending_postback_conversions_ibfk_2` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for postback_conversions
-- ----------------------------
DROP TABLE IF EXISTS `postback_conversions`;
CREATE TABLE `postback_conversions`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '转化记录ID',
  `platform` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '平台名称：macan, addermobi等',
  `conversion_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '转化ID（各平台唯一标识，如Macan的clk_id）',
  `event_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '事件名称（如purchase, install等）',
  `event_value` float NULL DEFAULT NULL COMMENT '事件价值（购买价格等）',
  `original_payout` float NULL DEFAULT NULL COMMENT '原始支付金额（PO）',
  `payout` float NULL DEFAULT NULL COMMENT '支付金额（确认的广告单元价格）',
  `devad_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '设备广告ID（IDFA或GAID）',
  `os` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '操作系统（IOS或Android）',
  `carrier` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '用户运营商',
  `ip` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '点击IP地址',
  `gid` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '渠道ID（Channel ID）',
  `product_id` int NULL DEFAULT NULL COMMENT '关联的产品ID（可选，用于关联产品）',
  `client_id` int NULL DEFAULT NULL COMMENT '关联的客户ID（可选，用于关联客户）',
  `raw_data` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '原始回调数据（JSON格式，保存完整回调数据以便后续分析）',
  `created_at` datetime NOT NULL COMMENT '创建时间（记录回调接收时间）',
  `click_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '关联的Click ID',
  `click_time` datetime NULL DEFAULT NULL COMMENT '点击时间',
  `conversion_status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT 'Pending' COMMENT '转化状态：Approved/Pending',
  `is_deducted` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否已被扣减',
  `deduction_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '扣减类型：volume（扣量）/amount（扣金额）/both（两者）',
  `original_volume` int NULL DEFAULT 1 COMMENT '原始转化数量',
  `deducted_volume` int NULL DEFAULT 0 COMMENT '扣减的转化数量',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_postback_platform_conversion_event`(`platform` ASC, `conversion_id` ASC, `event_name` ASC) USING BTREE COMMENT '防止同一平台的同一转化ID和事件名称重复处理',
  INDEX `idx_postback_platform_conversion`(`platform` ASC, `conversion_id` ASC) USING BTREE COMMENT '平台和转化ID复合索引（优化平台查询）',
  INDEX `idx_postback_product`(`product_id` ASC) USING BTREE COMMENT '产品ID索引（优化产品关联查询）',
  INDEX `idx_postback_client`(`client_id` ASC) USING BTREE COMMENT '客户ID索引（优化客户关联查询）',
  INDEX `idx_postback_created_at`(`created_at` ASC) USING BTREE COMMENT '创建时间索引（优化时间范围查询）',
  INDEX `idx_postback_platform_event`(`platform` ASC, `event_name` ASC) USING BTREE COMMENT '平台和事件名称复合索引（优化事件统计查询）',
  INDEX `idx_click_id`(`click_id` ASC) USING BTREE,
  INDEX `idx_conversion_status`(`conversion_status` ASC) USING BTREE,
  INDEX `idx_postback_click_id`(`click_id` ASC) USING BTREE,
  INDEX `idx_postback_conversion_status`(`conversion_status` ASC) USING BTREE,
  INDEX `idx_is_deducted`(`is_deducted` ASC) USING BTREE,
  INDEX `idx_deduction_type`(`deduction_type` ASC) USING BTREE,
  CONSTRAINT `postback_conversions_ibfk_1` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `postback_conversions_ibfk_2` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'Postback转化事件表，统一存储所有平台的postback回调数据' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for postback_forward_logs
-- ----------------------------
DROP TABLE IF EXISTS `postback_forward_logs`;
CREATE TABLE `postback_forward_logs`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '转发日志ID',
  `conversion_id` int NOT NULL COMMENT '关联的转化记录ID',
  `product_id` int NULL DEFAULT NULL COMMENT '产品ID',
  `publisher_id` int NULL DEFAULT NULL COMMENT '渠道ID（转发到渠道时使用）',
  `downstream_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '下游URL',
  `request_method` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '请求方式：GET 或 POST',
  `request_data` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '请求数据（JSON格式，用于POST请求）',
  `request_params` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '请求参数（URL参数，用于GET请求）',
  `response_status` int NULL DEFAULT NULL COMMENT '响应状态码',
  `response_body` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '响应内容',
  `success` tinyint(1) NULL DEFAULT NULL COMMENT '是否转发成功',
  `error_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '错误信息（如果转发失败）',
  `retry_count` int NULL DEFAULT NULL COMMENT '重试次数',
  `created_at` datetime NOT NULL COMMENT '创建时间',
  `completed_at` datetime NULL DEFAULT NULL COMMENT '完成时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `ix_postback_forward_logs_publisher_id`(`publisher_id` ASC) USING BTREE,
  INDEX `idx_forward_log_product`(`product_id` ASC) USING BTREE,
  INDEX `ix_postback_forward_logs_success`(`success` ASC) USING BTREE,
  INDEX `idx_forward_log_conversion`(`conversion_id` ASC) USING BTREE,
  INDEX `idx_forward_log_success`(`success` ASC) USING BTREE,
  INDEX `ix_postback_forward_logs_product_id`(`product_id` ASC) USING BTREE,
  INDEX `ix_postback_forward_logs_id`(`id` ASC) USING BTREE,
  INDEX `idx_forward_log_created_at`(`created_at` ASC) USING BTREE,
  INDEX `ix_postback_forward_logs_created_at`(`created_at` ASC) USING BTREE,
  INDEX `idx_forward_log_publisher`(`publisher_id` ASC) USING BTREE,
  INDEX `ix_postback_forward_logs_conversion_id`(`conversion_id` ASC) USING BTREE,
  CONSTRAINT `postback_forward_logs_ibfk_1` FOREIGN KEY (`conversion_id`) REFERENCES `postback_conversions` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `postback_forward_logs_ibfk_2` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `postback_forward_logs_ibfk_3` FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for postback_forward_queue
-- ----------------------------
DROP TABLE IF EXISTS `postback_forward_queue`;
CREATE TABLE `postback_forward_queue`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '队列ID',
  `conversion_id` int NOT NULL COMMENT '关联的转化记录ID',
  `product_id` int NOT NULL COMMENT '产品ID',
  `downstream_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '下游URL',
  `request_method` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '请求方式：GET 或 POST',
  `request_data` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '请求数据（JSON格式，用于POST请求）',
  `request_params` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '请求参数（URL参数，用于GET请求）',
  `retry_count` int NULL DEFAULT NULL COMMENT '已重试次数',
  `next_retry_time` datetime NOT NULL COMMENT '下次重试时间',
  `created_at` datetime NOT NULL COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_forward_queue_time`(`next_retry_time` ASC) USING BTREE,
  INDEX `ix_postback_forward_queue_id`(`id` ASC) USING BTREE,
  INDEX `ix_postback_forward_queue_conversion_id`(`conversion_id` ASC) USING BTREE,
  INDEX `ix_postback_forward_queue_next_retry_time`(`next_retry_time` ASC) USING BTREE,
  INDEX `idx_forward_queue_conversion`(`conversion_id` ASC) USING BTREE,
  INDEX `ix_postback_forward_queue_product_id`(`product_id` ASC) USING BTREE,
  INDEX `ix_postback_forward_queue_created_at`(`created_at` ASC) USING BTREE,
  CONSTRAINT `postback_forward_queue_ibfk_1` FOREIGN KEY (`conversion_id`) REFERENCES `postback_conversions` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `postback_forward_queue_ibfk_2` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for postback_ip_whitelist
-- ----------------------------
DROP TABLE IF EXISTS `postback_ip_whitelist`;
CREATE TABLE `postback_ip_whitelist`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '白名单ID',
  `ip_address` varchar(45) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'IP地址（支持IPv4和IPv6）',
  `description` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT 'IP地址描述/备注',
  `is_active` tinyint(1) NOT NULL COMMENT '是否启用',
  `created_at` datetime NOT NULL COMMENT '创建时间',
  `updated_at` datetime NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `ix_postback_ip_whitelist_ip_address`(`ip_address` ASC) USING BTREE,
  INDEX `ix_postback_ip_whitelist_id`(`id` ASC) USING BTREE,
  INDEX `ix_postback_ip_whitelist_is_active`(`is_active` ASC) USING BTREE,
  INDEX `idx_is_active`(`is_active` ASC) USING BTREE,
  INDEX `idx_ip_address`(`ip_address` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 17 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for postback_notifications
-- ----------------------------
DROP TABLE IF EXISTS `postback_notifications`;
CREATE TABLE `postback_notifications`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '通知记录ID',
  `conversion_id` int NULL DEFAULT NULL COMMENT '转化记录ID（汇总通知时为NULL）',
  `client_id` int NULL DEFAULT NULL COMMENT '客户ID',
  `product_id` int NULL DEFAULT NULL COMMENT '产品ID',
  `publisher_id` int NULL DEFAULT NULL COMMENT '渠道ID（转发通知时使用）',
  `notification_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '通知类型：conversion, high_value, error, forward, summary_hourly, summary_daily',
  `notification_channel` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '通知渠道：telegram, email, sms, webhook',
  `notification_status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '通知状态：sent, failed, pending',
  `notification_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '通知消息内容',
  `error_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '错误信息（如果失败）',
  `auto_notify` tinyint(1) NULL DEFAULT NULL COMMENT '是否自动通知（True=自动通知，False=手动通知）',
  `postback_url` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT 'Postback URL（转发通知时使用）',
  `created_at` datetime NOT NULL COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `ix_postback_notifications_publisher_id`(`publisher_id` ASC) USING BTREE,
  INDEX `idx_postback_notification_publisher`(`publisher_id` ASC) USING BTREE,
  INDEX `idx_postback_notification_conversion`(`conversion_id` ASC) USING BTREE,
  INDEX `ix_postback_notifications_conversion_id`(`conversion_id` ASC) USING BTREE,
  INDEX `ix_postback_notifications_auto_notify`(`auto_notify` ASC) USING BTREE,
  INDEX `idx_postback_notification_product`(`product_id` ASC) USING BTREE,
  INDEX `ix_postback_notifications_product_id`(`product_id` ASC) USING BTREE,
  INDEX `idx_postback_notification_created_at`(`created_at` ASC) USING BTREE,
  INDEX `ix_postback_notifications_id`(`id` ASC) USING BTREE,
  INDEX `idx_postback_notification_client`(`client_id` ASC) USING BTREE,
  INDEX `ix_postback_notifications_created_at`(`created_at` ASC) USING BTREE,
  INDEX `idx_postback_notification_auto_notify`(`auto_notify` ASC) USING BTREE,
  INDEX `ix_postback_notifications_notification_status`(`notification_status` ASC) USING BTREE,
  INDEX `idx_postback_notification_status`(`notification_status` ASC) USING BTREE,
  INDEX `ix_postback_notifications_client_id`(`client_id` ASC) USING BTREE,
  CONSTRAINT `postback_notifications_ibfk_1` FOREIGN KEY (`conversion_id`) REFERENCES `postback_conversions` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `postback_notifications_ibfk_2` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `postback_notifications_ibfk_3` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `postback_notifications_ibfk_4` FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for product_assignments
-- ----------------------------
DROP TABLE IF EXISTS `product_assignments`;
CREATE TABLE `product_assignments`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '分配记录ID',
  `product_id` int NOT NULL COMMENT '产品ID',
  `client_id` int NOT NULL COMMENT '客户ID',
  `start_date` date NOT NULL COMMENT '分配开始日期',
  `end_date` date NULL DEFAULT NULL COMMENT '分配结束日期（NULL表示当前有效）',
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_product_assignments_product`(`product_id` ASC) USING BTREE,
  INDEX `idx_product_assignments_client`(`client_id` ASC) USING BTREE,
  INDEX `idx_product_assignments_date`(`product_id` ASC, `start_date` ASC, `end_date` ASC) USING BTREE,
  INDEX `idx_product_assignments_active`(`product_id` ASC, `end_date` ASC) USING BTREE,
  CONSTRAINT `fk_product_assignments_client` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `fk_product_assignments_product` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '产品分配历史表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for product_notification_configs
-- ----------------------------
DROP TABLE IF EXISTS `product_notification_configs`;
CREATE TABLE `product_notification_configs`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '通知配置ID',
  `product_id` int NOT NULL COMMENT '产品ID',
  `notification_enabled` tinyint(1) NULL DEFAULT NULL COMMENT '是否启用通知',
  `notify_on_conversion` tinyint(1) NULL DEFAULT NULL COMMENT '转化时通知',
  `notify_on_high_value` tinyint(1) NULL DEFAULT NULL COMMENT '高价值转化通知',
  `high_value_threshold` float NULL DEFAULT NULL COMMENT '高价值阈值',
  `notify_channels` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '通知渠道（JSON格式：[\"telegram\", \"email\", \"sms\"]）',
  `telegram_chat_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT 'Telegram Chat ID',
  `email_address` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '邮箱地址',
  `phone_number` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '手机号',
  `notification_frequency` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '通知频率：realtime, hourly, daily',
  `created_at` datetime NULL DEFAULT NULL COMMENT '创建时间',
  `updated_at` datetime NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `ix_product_notification_configs_product_id`(`product_id` ASC) USING BTREE,
  INDEX `idx_product_notification_config_product`(`product_id` ASC) USING BTREE,
  INDEX `idx_product_notification_config_enabled`(`notification_enabled` ASC) USING BTREE,
  INDEX `ix_product_notification_configs_id`(`id` ASC) USING BTREE,
  CONSTRAINT `product_notification_configs_ibfk_1` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for products
-- ----------------------------
DROP TABLE IF EXISTS `products`;
CREATE TABLE `products`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '产品ID',
  `client_id` int NOT NULL COMMENT '客户ID',
  `name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '产品名称',
  `ecpm_deduct_ratio` float NOT NULL DEFAULT 0 COMMENT 'eCPM减扣比例',
  `revenue_deduct_ratio` float NOT NULL DEFAULT 0 COMMENT '收益减扣比例',
  `cplpo_deduct_ratio` float NOT NULL DEFAULT 0 COMMENT 'CPL PO减扣比例 ',
  `is_active` tinyint(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
  `notification_address` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '通知地址（Telegram Chat ID、邮箱地址、Webhook URL等，用于接收转化通知）',
  `downstream_postback_method` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT 'GET' COMMENT '下游 Postback 请求方式：GET 或 POST（默认GET）',
  `downstream_postback_success_check` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '产品下游 Postback 转发成功检查配置（JSON格式，用于检查产品下游 Postback URL 的响应内容是否表示成功）',
  `downstream_postback_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '下游 Postback URL（可选，配置后将自动转发转化数据）',
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_product_client`(`client_id` ASC) USING BTREE,
  INDEX `idx_product_name`(`name` ASC) USING BTREE,
  FULLTEXT INDEX `ft_products_name`(`name`) WITH PARSER `ngram`,
  FULLTEXT INDEX `ft_name`(`name`),
  CONSTRAINT `fk_products_client` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '产品表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for publishers
-- ----------------------------
DROP TABLE IF EXISTS `publishers`;
CREATE TABLE `publishers`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '渠道ID',
  `publisher_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '渠道名称',
  `email` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '邮箱（可选）',
  `price_discount` decimal(5, 2) NULL DEFAULT 0.00 COMMENT '渠道级别的价格扣量比例（0-100）',
  `postback_url` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT 'Postback URL（渠道的Postback配置）',
  `postback_method` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT 'GET' COMMENT 'Postback请求方式：GET/POST',
  `postback_success_check` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '渠道 Postback 转发成功检查配置（JSON格式，用于检查渠道 Postback URL 的响应内容是否表示成功）',
  `active_advertiser_count` int NULL DEFAULT 0 COMMENT '活跃的广告主数量',
  `client_id` int NULL DEFAULT NULL COMMENT '关联的客户ID',
  `is_active` tinyint(1) NULL DEFAULT 1 COMMENT '是否激活',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_publisher_name`(`publisher_name` ASC) USING BTREE,
  INDEX `idx_is_active`(`is_active` ASC) USING BTREE,
  INDEX `idx_client_id`(`client_id` ASC) USING BTREE,
  CONSTRAINT `fk_publishers_client_id` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '渠道表（下游）' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for scheduled_tasks
-- ----------------------------
DROP TABLE IF EXISTS `scheduled_tasks`;
CREATE TABLE `scheduled_tasks`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '定时任务ID',
  `task_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '任务名称（唯一）',
  `last_run_time` datetime(6) NULL DEFAULT NULL COMMENT '上次执行时间',
  `is_running` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否正在执行',
  `last_run_pid` int NULL DEFAULT NULL COMMENT '上次执行的进程ID',
  `last_run_host` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '上次执行的服务器主机名',
  `run_count` int NOT NULL DEFAULT 0 COMMENT '执行次数',
  `success_count` int NOT NULL DEFAULT 0 COMMENT '成功次数',
  `error_count` int NOT NULL DEFAULT 0 COMMENT '失败次数',
  `last_error` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '最后一次错误信息',
  `is_active` tinyint(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  `cron_expression` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT 'Cron表达式',
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '任务描述',
  `function_path` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '执行函数路径（例如：app.scheduler_module.tasks.simple_task.simple_info_task）',
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_scheduled_tasks_task_name`(`task_name` ASC) USING BTREE,
  INDEX `idx_scheduled_task_name`(`task_name` ASC) USING BTREE,
  INDEX `idx_scheduled_task_is_running`(`is_running` ASC) USING BTREE,
  INDEX `idx_scheduled_task_is_active`(`is_active` ASC) USING BTREE,
  FULLTEXT INDEX `ft_tasks_search`(`task_name`, `description`) WITH PARSER `ngram`
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '定时任务执行记录表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for short_links
-- ----------------------------
DROP TABLE IF EXISTS `short_links`;
CREATE TABLE `short_links`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '短链接ID',
  `short_code` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '短链接代码（唯一）',
  `original_url` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '原始URL',
  `title` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '短链接标题（可选）',
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '短链接描述（可选）',
  `created_by` int NULL DEFAULT NULL COMMENT '创建者用户ID',
  `offer_id` int NULL DEFAULT NULL COMMENT '关联的Offer ID',
  `channel_id` int NULL DEFAULT NULL COMMENT '关联的渠道ID（Publisher ID）',
  `show_count` int NOT NULL DEFAULT 0 COMMENT '展示次数',
  `click_count` int NOT NULL DEFAULT 0 COMMENT '点击次数',
  `is_active` tinyint(1) NULL DEFAULT 1 COMMENT '是否激活',
  `expires_at` datetime NULL DEFAULT NULL COMMENT '过期时间（可选）',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `short_code`(`short_code` ASC) USING BTREE,
  INDEX `idx_short_link_created_by`(`created_by` ASC) USING BTREE,
  INDEX `idx_short_link_active`(`is_active` ASC) USING BTREE,
  INDEX `idx_short_link_created_at`(`created_at` ASC) USING BTREE,
  INDEX `idx_short_link_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_short_link_channel_id`(`channel_id` ASC) USING BTREE,
  INDEX `idx_short_links_created_by_active_created`(`created_by` ASC, `is_active` ASC, `created_at` DESC) USING BTREE,
  INDEX `idx_short_links_offer_channel`(`offer_id` ASC, `channel_id` ASC) USING BTREE,
  INDEX `idx_short_link_code`(`short_code` ASC) USING BTREE,
  FULLTEXT INDEX `ft_title`(`title`),
  FULLTEXT INDEX `ft_description`(`description`),
  CONSTRAINT `short_links_ibfk_1` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `short_links_ibfk_channel` FOREIGN KEY (`channel_id`) REFERENCES `publishers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `short_links_ibfk_offer` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '短链接表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for tb_search_data
-- ----------------------------
DROP TABLE IF EXISTS `tb_search_data`;
CREATE TABLE `tb_search_data`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `date` datetime NOT NULL COMMENT '日期',
  `product_id` int NOT NULL COMMENT '产品ID',
  `country_code` varchar(2) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '国家代码',
  `redirects` int NULL DEFAULT NULL COMMENT 'REDIRECTS',
  `searches` int NULL DEFAULT NULL COMMENT 'SEARCHES',
  `monetized` int NULL DEFAULT NULL COMMENT 'MONETIZED',
  `clicks` int NULL DEFAULT NULL COMMENT 'CLICKS',
  `revenue` float NULL DEFAULT NULL COMMENT 'REVENUE（扣减后）',
  `rpm` float NULL DEFAULT NULL COMMENT 'RPM（扣减后）',
  `revenue_before_deduct` float NULL DEFAULT NULL COMMENT 'REVENUE（扣减前）',
  `rpm_before_deduct` float NULL DEFAULT NULL COMMENT 'RPM（扣减前）',
  `created_at` datetime NULL DEFAULT NULL COMMENT '创建时间',
  `updated_at` datetime NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_tb_search_data_date_product_country`(`date` ASC, `product_id` ASC, `country_code` ASC) USING BTREE,
  INDEX `country_code`(`country_code` ASC) USING BTREE,
  INDEX `idx_tb_search_data_date_product`(`date` ASC, `product_id` ASC) USING BTREE,
  INDEX `idx_tb_search_data_product`(`product_id` ASC) USING BTREE,
  INDEX `idx_tb_search_data_date`(`date` ASC) USING BTREE,
  INDEX `ix_tb_search_data_id`(`id` ASC) USING BTREE,
  CONSTRAINT `tb_search_data_ibfk_1` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `tb_search_data_ibfk_2` FOREIGN KEY (`country_code`) REFERENCES `countries` (`alpha_2_code`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'TB收索数据' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for third_party_report_logs
-- ----------------------------
DROP TABLE IF EXISTS `third_party_report_logs`;
CREATE TABLE `third_party_report_logs`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '日志ID',
  `source` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '上报来源：short_link/斗篷点击, postback/转化回调',
  `adsid` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '广告事件ID',
  `event` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '事件类型：viewWebpage, finishPayment',
  `use_hash` tinyint(1) NOT NULL DEFAULT 1 COMMENT '是否对email、ip、phone进行哈希处理：True=哈希，False=不哈希',
  `email` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '邮箱（原始值）',
  `ip` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT 'IP地址（原始值）',
  `phone` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '手机号（原始值）',
  `ua` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT '用户代理',
  `report_params` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT '完整上报参数（JSON格式）',
  `status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '上报状态：pending, success, failed',
  `attempt_count` int NULL DEFAULT 0 COMMENT '尝试次数',
  `max_attempts` int NULL DEFAULT 3 COMMENT '最大尝试次数',
  `response_status` int NULL DEFAULT NULL COMMENT '响应状态码',
  `response_body` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT '响应内容',
  `log_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '第三方返回的logId',
  `error_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT '错误信息（如果失败）',
  `created_at` datetime NOT NULL COMMENT '创建时间',
  `report_start_time` datetime NULL DEFAULT NULL COMMENT '上报开始时间',
  `report_success_time` datetime NULL DEFAULT NULL COMMENT '上报成功时间',
  `completed_at` datetime NULL DEFAULT NULL COMMENT '完成时间',
  `conversion_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '转化ID',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `unique_source_adsid`(`source` ASC, `adsid` ASC) USING BTREE,
  INDEX `idx_third_party_source`(`source` ASC) USING BTREE,
  INDEX `idx_third_party_adsid`(`adsid` ASC) USING BTREE,
  INDEX `idx_third_party_event`(`event` ASC) USING BTREE,
  INDEX `idx_third_party_status`(`status` ASC) USING BTREE,
  INDEX `idx_third_party_created_at`(`created_at` ASC) USING BTREE,
  INDEX `idx_third_party_status_created`(`status` ASC, `created_at` ASC) USING BTREE,
  INDEX `idx_conversion_id`(`conversion_id` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '第三方上报日志表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for token_blacklist
-- ----------------------------
DROP TABLE IF EXISTS `token_blacklist`;
CREATE TABLE `token_blacklist`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '黑名单ID',
  `token_jti` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'JWT令牌ID（jti）',
  `user_id` int NOT NULL COMMENT '用户ID',
  `revoked_at` datetime NOT NULL COMMENT '撤销时间',
  `expires_at` datetime NOT NULL COMMENT 'Token过期时间',
  `reason` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '撤销原因（用户退出、强制退出等）',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `ix_token_blacklist_token_jti`(`token_jti` ASC) USING BTREE,
  INDEX `ix_token_blacklist_revoked_at`(`revoked_at` ASC) USING BTREE,
  INDEX `ix_token_blacklist_user_id`(`user_id` ASC) USING BTREE,
  INDEX `idx_blacklist_user`(`user_id` ASC) USING BTREE,
  INDEX `idx_blacklist_expires`(`expires_at` ASC) USING BTREE,
  INDEX `ix_token_blacklist_id`(`id` ASC) USING BTREE,
  INDEX `ix_token_blacklist_expires_at`(`expires_at` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for user_audit_logs
-- ----------------------------
DROP TABLE IF EXISTS `user_audit_logs`;
CREATE TABLE `user_audit_logs`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '日志ID',
  `user_id` int NULL DEFAULT NULL COMMENT '用户ID（可为空，记录未登录访问）',
  `username` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '用户名（冗余字段，便于查询）',
  `action_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '操作类型：LOGIN, LOGOUT, CREATE, UPDATE, DELETE, VIEW, ACCESS等',
  `resource_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '资源类型：USER, CLIENT, PRODUCT, AD_DATA, SCHEDULED_TASK等',
  `resource_id` int NULL DEFAULT NULL COMMENT '资源ID',
  `resource_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '资源名称（冗余字段，便于查询）',
  `ip_address` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT 'IP地址',
  `user_agent` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '用户代理（浏览器信息）',
  `request_method` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT 'HTTP请求方法',
  `request_path` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '请求路径',
  `request_params` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '请求参数（JSON格式，不包含敏感信息）',
  `status_code` int NULL DEFAULT NULL COMMENT 'HTTP状态码',
  `success` tinyint(1) NOT NULL DEFAULT 1 COMMENT '操作是否成功',
  `error_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '错误信息（如果失败）',
  `details` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '详细信息（JSON格式）',
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
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
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '用户操作日志表（审计日志）' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for user_sessions
-- ----------------------------
DROP TABLE IF EXISTS `user_sessions`;
CREATE TABLE `user_sessions`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '会话ID',
  `user_id` int NOT NULL COMMENT '用户ID',
  `token_jti` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'JWT令牌ID（jti）',
  `ip_address` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '登录IP地址',
  `user_agent` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '用户代理（浏览器信息）',
  `device_info` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '设备信息（移动端/桌面端）',
  `location` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '登录位置（可选，通过IP解析）',
  `is_active` tinyint(1) NOT NULL DEFAULT 1 COMMENT '是否活跃',
  `last_activity` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '最后活动时间',
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间（登录时间）',
  `expires_at` datetime(6) NOT NULL COMMENT '过期时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_user_sessions_token_jti`(`token_jti` ASC) USING BTREE,
  INDEX `idx_session_user_active`(`user_id` ASC, `is_active` ASC) USING BTREE,
  INDEX `idx_session_expires`(`expires_at` ASC) USING BTREE,
  INDEX `idx_user_id`(`user_id` ASC) USING BTREE,
  INDEX `idx_token_jti`(`token_jti` ASC) USING BTREE,
  INDEX `idx_ip_address`(`ip_address` ASC) USING BTREE,
  INDEX `idx_is_active`(`is_active` ASC) USING BTREE,
  INDEX `idx_last_activity`(`last_activity` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '用户会话表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for users
-- ----------------------------
DROP TABLE IF EXISTS `users`;
CREATE TABLE `users`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '用户ID',
  `username` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '用户名称(登录名称)',
  `hashed_password` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '用户Hash密码',
  `full_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '用户全名',
  `email` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '用户邮箱',
  `role` enum('admin','client') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'client' COMMENT '用户角色(ADMIN 管理员 / CLIENT 客户)',
  `is_active` tinyint(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
  `login_restricted` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否限制登录',
  `login_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '登录提示消息',
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_users_username`(`username` ASC) USING BTREE,
  UNIQUE INDEX `uq_users_email`(`email` ASC) USING BTREE,
  INDEX `idx_username`(`username` ASC) USING BTREE,
  INDEX `idx_email`(`email` ASC) USING BTREE,
  FULLTEXT INDEX `ft_users_search`(`username`, `full_name`, `email`) WITH PARSER `ngram`
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '用户表' ROW_FORMAT = DYNAMIC;

SET FOREIGN_KEY_CHECKS = 1;
