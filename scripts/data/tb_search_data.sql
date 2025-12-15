/*
 Navicat Premium Dump SQL

 Source Server         : 广告平台
 Source Server Type    : MySQL
 Source Server Version : 80043 (8.0.43-0ubuntu0.22.04.2)
 Source Host           : 43.156.101.243:3306
 Source Schema         : platform

 Target Server Type    : MySQL
 Target Server Version : 80043 (8.0.43-0ubuntu0.22.04.2)
 File Encoding         : 65001

 Date: 15/12/2025 14:28:00
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

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
) ENGINE = InnoDB AUTO_INCREMENT = 3 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = Dynamic;

SET FOREIGN_KEY_CHECKS = 1;
