/*
 Navicat Premium Dump SQL

 Source Server         : 香港测试服务器
 Source Server Type    : MySQL
 Source Server Version : 80043 (8.0.43-0ubuntu0.22.04.2)
 Source Host           : 159.138.133.34:3306
 Source Schema         : platform

 Target Server Type    : MySQL
 Target Server Version : 80043 (8.0.43-0ubuntu0.22.04.2)
 File Encoding         : 65001

 Date: 21/11/2025 20:37:25
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for ad_data
-- ----------------------------
DROP TABLE IF EXISTS `ad_data`;
CREATE TABLE IF NOT EXISTS `ad_data` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '广告数据ID',
  `date` DATETIME NOT NULL COMMENT '数据日期',
  `product_id` INT NOT NULL COMMENT '产品ID',
  `country_code` VARCHAR(5) NULL DEFAULT 'ZZ' COMMENT '国家代码（ISO 3166-1 二字母代码）',
  `request_count` INT NOT NULL DEFAULT 0 COMMENT '请求数',
  `match_count` INT NOT NULL DEFAULT 0 COMMENT '匹配数',
  `display_count` INT NOT NULL DEFAULT 0 COMMENT '展示数',
  `click_count` INT NOT NULL DEFAULT 0 COMMENT '点击数',
  `ecpm_before_deduct` FLOAT NOT NULL DEFAULT 0 COMMENT 'eCPM未减扣',
  `ecpm_after_deduct` FLOAT NOT NULL DEFAULT 0 COMMENT 'eCPM已减扣',
  `revenue_before_deduct` FLOAT NOT NULL DEFAULT 0 COMMENT '收益未减扣',
  `revenue_after_deduct` FLOAT NOT NULL DEFAULT 0 COMMENT '收益已减扣',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_ad_data_date_product_country`(`date` ASC, `product_id` ASC, `country_code` ASC) USING BTREE,
  INDEX `idx_ad_data_date`(`date` ASC) USING BTREE,
  INDEX `idx_ad_data_product`(`product_id` ASC) USING BTREE,
  INDEX `idx_ad_data_date_product`(`date` ASC, `product_id` ASC) USING BTREE,
  INDEX `idx_ad_data_country_code`(`country_code` ASC) USING BTREE,
  CONSTRAINT `fk_ad_data_product` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = DYNAMIC COMMENT = '广告数据表';

SET FOREIGN_KEY_CHECKS = 1;
