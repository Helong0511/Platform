/*
 Navicat Premium Dump SQL

 Source Server         : TigerPay
 Source Server Type    : MySQL
 Source Server Version : 80043 (8.0.43-0ubuntu0.22.04.2)
 Source Host           : 159.138.133.34:3306
 Source Schema         : platform

 Target Server Type    : MySQL
 Target Server Version : 80043 (8.0.43-0ubuntu0.22.04.2)
 File Encoding         : 65001

 Date: 18/11/2025 17:55:35
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

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
  `chat_id` bigint NULL DEFAULT NULL COMMENT '15位聊天ID',
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_clients_key`(`key` ASC) USING BTREE,
  UNIQUE INDEX `chat_id`(`chat_id` ASC) USING BTREE,
  INDEX `idx_client_user`(`user_id` ASC) USING BTREE,
  INDEX `idx_clients_key`(`key` ASC) USING BTREE,
  FULLTEXT INDEX `ft_clients_search`(`company_name`, `contact_person`) WITH PARSER `ngram`,
  CONSTRAINT `fk_clients_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1010 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '客户表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Records of clients
-- ----------------------------
INSERT INTO `clients` VALUES (1, 2, '默认客户（导入数据）', NULL, NULL, NULL, NULL, '8bc85bd7-c69b-4dc8-8728-f1b7be669ec5', 1, 0, 0, NULL, '2025-11-17 14:24:56.215279', '2025-11-17 14:24:56.215279');
INSERT INTO `clients` VALUES (1000, 3, 'yipaijihe Company', NULL, NULL, NULL, NULL, 'a8117b66-acda-4c18-9ef4-f4b796c9debf', 1, 0, 0, NULL, '2025-10-22 04:00:11.000000', '2025-11-17 06:39:48.756641');
INSERT INTO `clients` VALUES (1001, 4, 'Ecovital Company', NULL, NULL, NULL, NULL, '30e12f23-0da1-4b73-a576-522c1e9a3fc4', 1, 0, 0, NULL, '2025-10-24 03:25:14.000000', '2025-11-17 06:39:54.029623');
INSERT INTO `clients` VALUES (1002, 5, 'mengting1 Company', NULL, NULL, NULL, NULL, '2cc33ab6-4eb0-4892-a865-8b2e7a290caf', 1, 0, 0, NULL, '2025-10-29 09:51:13.000000', '2025-11-17 06:39:56.864246');
INSERT INTO `clients` VALUES (1003, 6, 'hehemobi Company', NULL, NULL, NULL, NULL, 'cccbc495-a08b-4b5a-9139-5df4e950c52a', 1, 0, 0, NULL, '2025-10-30 03:13:09.000000', '2025-11-17 06:40:07.848892');
INSERT INTO `clients` VALUES (1004, 7, 'mengting2 Company', NULL, NULL, NULL, NULL, '369489b5-5604-47a3-909f-2c546985bbfc', 1, 0, 0, NULL, '2025-11-06 02:11:56.000000', '2025-11-17 06:40:13.398902');
INSERT INTO `clients` VALUES (1005, 8, 'leadwin Company', NULL, NULL, NULL, NULL, 'fd4f24a6-b4d8-4082-853b-aee2d047ff72', 1, 0, 0, NULL, '2025-11-07 03:03:56.000000', '2025-11-17 06:40:18.368692');
INSERT INTO `clients` VALUES (1006, 9, 'mengting3 Company', NULL, NULL, NULL, NULL, '3de8da55-343c-422f-a888-24492f5defc0', 1, 0, 0, NULL, '2025-11-07 03:20:12.000000', '2025-11-17 06:40:28.787060');
INSERT INTO `clients` VALUES (1007, 10, 'mengting4 Company', NULL, NULL, NULL, NULL, 'ec5875f0-d100-4e1f-8304-4903121f5560', 1, 0, 0, NULL, '2025-11-07 09:33:09.000000', '2025-11-17 06:40:32.841480');
INSERT INTO `clients` VALUES (1008, 11, 'fulong Company', NULL, NULL, NULL, NULL, 'd34c76dc-fd6c-40f7-80f9-bfd83ea5662f', 1, 0, 0, NULL, '2025-11-13 02:03:47.792130', '2025-11-13 02:04:17.780575');
INSERT INTO `clients` VALUES (1009, 12, 'mengting5 Company', NULL, NULL, NULL, NULL, '1a409436-774b-41b4-b475-8e72b6a360a7', 1, 0, 0, NULL, '2025-11-14 07:37:11.305785', '2025-11-14 07:37:22.916155');

SET FOREIGN_KEY_CHECKS = 1;
