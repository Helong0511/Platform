/*
 Navicat Premium Dump SQL

 Source Server         : 广告数据
 Source Server Type    : MySQL
 Source Server Version : 80043 (8.0.43-0ubuntu0.22.04.2)
 Source Host           : 43.156.101.243:3306
 Source Schema         : platform

 Target Server Type    : MySQL
 Target Server Version : 80043 (8.0.43-0ubuntu0.22.04.2)
 File Encoding         : 65001

 Date: 22/11/2025 16:55:13
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

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
) ENGINE = InnoDB AUTO_INCREMENT = 15 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '用户表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Records of users
-- ----------------------------
INSERT INTO `users` VALUES (1, 'admin', '$2b$12$VsqK4/DVKDDp14UqNabPvOBPQhSW7amZL/Jnu/WrbPRZQehYV8gja', '管理员', 'admin@btfrx.online', 'admin', 1, 0, NULL, '2025-11-14 17:32:33.000000', '2025-11-19 10:00:41.163304');
INSERT INTO `users` VALUES (2, 'data', '$2b$12$BOHTtubZePvpDN.Sls7EbO3ANHMwjouG104GVdfdKcyPxM6wR/gYy', '数据挂靠', 'data@btfrx.online', 'admin', 0, 0, NULL, '2025-11-14 17:32:33.000000', '2025-11-14 17:32:33.000000');
INSERT INTO `users` VALUES (3, 'yipaijihe', '$2b$12$F3EWj6vrp2ZzmaMPbV4ZwexOOCGBDKEbKU6bsCDEWlN3/lapQFtnu', 'yipaijihe', 'yipaijihe@btfrx.online', 'client', 1, 0, NULL, '2025-10-22 04:00:11.000000', '2025-10-22 04:00:11.000000');
INSERT INTO `users` VALUES (4, 'ecovital', '$2b$12$uwZQuAY37wLO3vxmLC9kLuGgKEWmwMT5YeMGXBNwTtXFrc3slHnua', 'ev', 'ev@btfrx.online', 'client', 1, 0, NULL, '2025-10-24 03:25:14.000000', '2025-11-13 06:34:04.334620');
INSERT INTO `users` VALUES (5, 'mengting1', '$2b$12$zmK8cr0h1RWv67b5foPAvuP7Gn4ruuq97CSdVR.l8ObngXGSqwo1C', 'mengting1', 'mengting1@btfrx.online', 'client', 1, 0, NULL, '2025-10-29 09:51:13.000000', '2025-10-29 09:51:13.000000');
INSERT INTO `users` VALUES (6, 'hehemobi', '$2b$12$B1A4hdGELolxcUECzdzMMOl8suqprIKUVMeUiOL7W93khv7d1Z6Sq', 'hehemobi', 'hehemobi@btfrx.online', 'client', 1, 0, NULL, '2025-10-30 03:13:09.000000', '2025-10-30 03:13:09.000000');
INSERT INTO `users` VALUES (7, 'mengting2', '$2b$12$lpE.1kXqXinEmwTAOoefBusXZzIP1fmAGt5jFLatGtUhnaB.eA/te', 'mengting2', 'mengting2@btfrx.online', 'client', 1, 0, NULL, '2025-11-06 02:11:56.000000', '2025-11-06 02:11:56.000000');
INSERT INTO `users` VALUES (8, 'leadwin', '$2b$12$YeuwoLi5rJWLdLcvnY1iG.kt5vjl2.yGHOs2WwDNekZ12NOGLdi7K', 'leadwin', 'leadwin@btfrx.online', 'client', 1, 0, NULL, '2025-11-07 03:03:56.000000', '2025-11-19 08:15:03.165646');
INSERT INTO `users` VALUES (9, 'mengting3', '$2b$12$ZomV536j03hKrG7JWGq...iVY9mB5I7ffn8zrwV7u/RG5nYiwXfjm', 'mengting3', 'mengting3@btfrx.online', 'client', 1, 0, NULL, '2025-11-07 03:20:12.000000', '2025-11-07 03:20:12.000000');
INSERT INTO `users` VALUES (10, 'mengting4', '$2b$12$w7.kiIgUgC.yBcCqXzLGVeWnKGeEk9k8JGhuAoWUDm/Y5UxefOv8u', 'mengting4', 'mengting4@btfrx.online', 'client', 1, 0, NULL, '2025-11-07 09:33:09.000000', '2025-11-07 09:33:09.000000');
INSERT INTO `users` VALUES (11, 'fulong', '$2b$12$HZqrcI/SMAsygsBACO7o4OTHkHvhiu1qekVAxvm51FWk5NEhV4JOS', 'fulong', 'moobai@outlook.com', 'client', 1, 0, NULL, '2025-11-13 02:03:47.787808', '2025-11-13 02:03:47.787813');
INSERT INTO `users` VALUES (12, 'mengting5', '$2b$12$Nt9FHDt806cQxKtYe4N7pOrUEi.1uF6zC9idGIWOHY4foiak7Ecqa', 'mengting5', 'mengting5@btfrx.online', 'client', 1, 0, NULL, '2025-11-14 07:37:11.300670', '2025-11-14 07:37:22.839605');
INSERT INTO `users` VALUES (13, 'zhuzhouyiya', '$2b$12$lcj4bGqw4o/4S709JjEbrusqkyoXfvTFmGxB06A2rxx9b/cVT8AQC', 'zhuzhouyiya', '1914442009@qq.com', 'client', 1, 0, NULL, '2025-11-19 09:48:27.784731', '2025-11-19 09:48:27.784736');
INSERT INTO `users` VALUES (14, 'winner', '$2b$12$lanvDaMNEdMoz9GLAAO2y.O5LI8Gj31YRMGY6fqO9zVj1T38NsuNq', 'winner', 'winner@btfrx.online', 'client', 1, 0, NULL, '2025-11-20 04:09:27.851443', '2025-11-20 04:09:27.851448');

SET FOREIGN_KEY_CHECKS = 1;
