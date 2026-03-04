/*
 Navicat Premium Dump SQL

 Source Server         : 本地
 Source Server Type    : MySQL
 Source Server Version : 80033 (8.0.33)
 Source Host           : localhost:3306
 Source Schema         : platform

 Target Server Type    : MySQL
 Target Server Version : 80033 (8.0.33)
 File Encoding         : 65001

 Date: 03/02/2026 11:40:47
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

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
  CONSTRAINT `clicks_ibfk_1` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `clicks_ibfk_2` FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `clicks_ibfk_3` FOREIGN KEY (`advertiser_id`) REFERENCES `advertisers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `clicks_ibfk_short_link` FOREIGN KEY (`short_link_id`) REFERENCES `short_links` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '点击记录表' ROW_FORMAT = DYNAMIC;

SET FOREIGN_KEY_CHECKS = 1;
