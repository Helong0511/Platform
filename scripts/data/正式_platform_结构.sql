-- 设置数据库字符集
SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================================
-- 删除数据库（如果存在）
-- ============================================
DROP DATABASE IF EXISTS `platform`;

-- ============================================
-- 创建数据库
-- ============================================
CREATE DATABASE IF NOT EXISTS `platform` 
    DEFAULT CHARACTER SET utf8mb4 
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE `platform`;

-- ----------------------------
-- Table structure for ad_data
-- ----------------------------
DROP TABLE IF EXISTS `ad_data`;
CREATE TABLE `ad_data`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '广告数据ID',
  `date` DATETIME NOT NULL COMMENT '数据日期',
  `country_code` VARCHAR(5) NULL DEFAULT 'ZZ' COMMENT '国家代码（ISO 3166-1 二字母代码）',
  `product_id` INT NOT NULL COMMENT '产品ID',
  `request_count` INT NOT NULL DEFAULT 0 COMMENT '请求数',
  `match_count` INT NOT NULL DEFAULT 0 COMMENT '匹配数',
  `display_count` INT NOT NULL DEFAULT 0 COMMENT '展示数',
  `click_count` INT NOT NULL DEFAULT 0 COMMENT '点击数',
  `ecpm_before_deduct` float NOT NULL DEFAULT 0 COMMENT 'eCPM未减扣',
  `ecpm_after_deduct` float NOT NULL DEFAULT 0 COMMENT 'eCPM已减扣',
  `revenue_before_deduct` float NOT NULL DEFAULT 0 COMMENT '收益未减扣',
  `revenue_after_deduct` float NOT NULL DEFAULT 0 COMMENT '收益已减扣',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_ad_data_date_product_country`(`date` ASC, `product_id` ASC, `country_code` ASC) USING BTREE,
  INDEX `idx_ad_data_date`(`date` ASC) USING BTREE,
  INDEX `idx_ad_data_product`(`product_id` ASC) USING BTREE,
  INDEX `idx_ad_data_date_product`(`date` ASC, `product_id` ASC) USING BTREE,
  INDEX `idx_ad_data_country_code`(`country_code` ASC) USING BTREE,
  CONSTRAINT `fk_ad_data_product` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 0 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = DYNAMIC COMMENT = '广告数据表';

-- ----------------------------
-- Table structure for ad_data_archive
-- ----------------------------
DROP TABLE IF EXISTS `ad_data_archive`;
CREATE TABLE `ad_data_archive`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '广告数据ID',
  `date` DATETIME NOT NULL COMMENT '数据日期',
  `product_id` INT NOT NULL COMMENT '产品ID',
  `request_count` INT NOT NULL DEFAULT 0 COMMENT '请求数',
  `match_count` INT NOT NULL DEFAULT 0 COMMENT '匹配数',
  `display_count` INT NOT NULL DEFAULT 0 COMMENT '展示数',
  `click_count` INT NOT NULL DEFAULT 0 COMMENT '点击数',
  `ecpm_before_deduct` float NOT NULL DEFAULT 0 COMMENT 'eCPM未减扣',
  `ecpm_after_deduct` float NOT NULL DEFAULT 0 COMMENT 'eCPM已减扣',
  `revenue_before_deduct` float NOT NULL DEFAULT 0 COMMENT '收益未减扣',
  `revenue_after_deduct` float NOT NULL DEFAULT 0 COMMENT '收益已减扣',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  PRIMARY KEY (`id`) USING SE_SPECIFIC
) ENGINE = ARCHIVE CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = DYNAMIC COMMENT = '广告数据归档表';

-- ----------------------------
-- Table structure for clients
-- ----------------------------
DROP TABLE IF EXISTS `clients`;
CREATE TABLE `clients`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '客户ID',
  `user_id` INT NOT NULL COMMENT '用户ID',
  `company_name` VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '公司名称',
  `contact_person` VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '联系人',
  `phone` VARCHAR(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '联系电话',
  `address` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '公司地址',
  `allowed_ips` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT 'IP白名单，多个IP用逗号分隔，为空则不限制',
  `key` VARCHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '客户唯一标识UUID',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
  `api_enabled` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否允许API访问（开启后允许客户通过API查询产品和广告数据，并显示API对接菜单）',
  `password_change_enabled` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否允许客户修改密码（开启后客户可以修改自己的密码）',
  `chat_id` bigint NULL DEFAULT NULL COMMENT '15位聊天ID',
  `notify_url` VARCHAR(200) NULL COMMENT '客户广告数据通知地址',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_clients_key`(`key` ASC) USING BTREE,
  UNIQUE INDEX `chat_id`(`chat_id` ASC) USING BTREE,
  INDEX `idx_client_user`(`user_id` ASC) USING BTREE,
  INDEX `idx_clients_key`(`key` ASC) USING BTREE,
  FULLTEXT INDEX `ft_clients_search`(`company_name`, `contact_person`) WITH PARSER `ngram`,
  CONSTRAINT `fk_clients_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1012 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = DYNAMIC COMMENT = '客户表';

-- ----------------------------
-- Table structure for product_assignments
-- ----------------------------
DROP TABLE IF EXISTS `product_assignments`;
CREATE TABLE `product_assignments`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '分配记录ID',
  `product_id` INT NOT NULL COMMENT '产品ID',
  `client_id` INT NOT NULL COMMENT '客户ID',
  `start_date` DATE NOT NULL COMMENT '分配开始日期',
  `end_date` DATE NULL DEFAULT NULL COMMENT '分配结束日期（NULL表示当前有效）',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_product_assignments_product`(`product_id` ASC) USING BTREE,
  INDEX `idx_product_assignments_client`(`client_id` ASC) USING BTREE,
  INDEX `idx_product_assignments_date`(`product_id` ASC, `start_date` ASC, `end_date` ASC) USING BTREE,
  INDEX `idx_product_assignments_active`(`product_id` ASC, `end_date` ASC) USING BTREE,
  CONSTRAINT `fk_product_assignments_client` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `fk_product_assignments_product` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 45 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = DYNAMIC COMMENT = '产品分配历史表';

-- ----------------------------
-- Table structure for products
-- ----------------------------
DROP TABLE IF EXISTS `products`;
CREATE TABLE `products`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '产品ID',
  `client_id` INT NOT NULL COMMENT '客户ID',
  `name` VARCHAR(100) NOT NULL COMMENT '产品名称',
  `ecpm_deduct_ratio` float NOT NULL DEFAULT 0 COMMENT 'eCPM减扣比例',
  `revenue_deduct_ratio` float NOT NULL DEFAULT 0 COMMENT '收益减扣比例',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_product_client`(`client_id` ASC) USING BTREE,
  INDEX `idx_product_name`(`name` ASC) USING BTREE,
  FULLTEXT INDEX `ft_products_name`(`name`) WITH PARSER `ngram`,
  CONSTRAINT `fk_products_client` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 53 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = DYNAMIC COMMENT = '产品表';

-- ----------------------------
-- Table structure for scheduled_tasks
-- ----------------------------
DROP TABLE IF EXISTS `scheduled_tasks`;
CREATE TABLE `scheduled_tasks`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '定时任务ID',
  `task_name` VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '任务名称（唯一）',
  `last_run_time` DATETIME(6) NULL DEFAULT NULL COMMENT '上次执行时间',
  `is_running` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否正在执行',
  `last_run_pid` INT NULL DEFAULT NULL COMMENT '上次执行的进程ID',
  `last_run_host` VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '上次执行的服务器主机名',
  `run_count` INT NOT NULL DEFAULT 0 COMMENT '执行次数',
  `success_count` INT NOT NULL DEFAULT 0 COMMENT '成功次数',
  `error_count` INT NOT NULL DEFAULT 0 COMMENT '失败次数',
  `last_error` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '最后一次错误信息',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  `cron_expression` VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT 'Cron表达式',
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '任务描述',
  `function_path` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '执行函数路径（例如：app.scheduler_module.tasks.simple_task.simple_info_task）',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_scheduled_tasks_task_name`(`task_name` ASC) USING BTREE,
  INDEX `idx_scheduled_task_name`(`task_name` ASC) USING BTREE,
  INDEX `idx_scheduled_task_is_running`(`is_running` ASC) USING BTREE,
  INDEX `idx_scheduled_task_is_active`(`is_active` ASC) USING BTREE,
  FULLTEXT INDEX `ft_tasks_search`(`task_name`, `description`) WITH PARSER `ngram`
) ENGINE = InnoDB AUTO_INCREMENT = 4 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = DYNAMIC COMMENT = '定时任务执行记录表';

-- ----------------------------
-- Table structure for token_blacklist
-- ----------------------------
DROP TABLE IF EXISTS `token_blacklist`;
CREATE TABLE `token_blacklist`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '黑名单ID',
  `token_jti` VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'JWT令牌ID（jti）',
  `user_id` INT NOT NULL COMMENT '用户ID',
  `revoked_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '撤销时间',
  `expires_at` DATETIME(6) NOT NULL COMMENT 'Token过期时间',
  `reason` VARCHAR(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '撤销原因（用户退出、强制退出等）',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_token_blacklist_token_jti`(`token_jti` ASC) USING BTREE,
  INDEX `idx_blacklist_user`(`user_id` ASC) USING BTREE,
  INDEX `idx_blacklist_expires`(`expires_at` ASC) USING BTREE,
  INDEX `idx_token_jti`(`token_jti` ASC) USING BTREE,
  INDEX `idx_revoked_at`(`revoked_at` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = DYNAMIC COMMENT = 'Token黑名单表';

-- ----------------------------
-- Table structure for user_audit_logs
-- ----------------------------
DROP TABLE IF EXISTS `user_audit_logs`;
CREATE TABLE `user_audit_logs`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '日志ID',
  `user_id` INT NULL DEFAULT NULL COMMENT '用户ID（可为空，记录未登录访问）',
  `username` VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '用户名（冗余字段，便于查询）',
  `action_type` VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '操作类型：LOGIN, LOGOUT, CREATE, UPDATE, DELETE, VIEW, ACCESS等',
  `resource_type` VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '资源类型：USER, CLIENT, PRODUCT, AD_DATA, SCHEDULED_TASK等',
  `resource_id` INT NULL DEFAULT NULL COMMENT '资源ID',
  `resource_name` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '资源名称（冗余字段，便于查询）',
  `ip_address` VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT 'IP地址',
  `user_agent` VARCHAR(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '用户代理（浏览器信息）',
  `request_method` VARCHAR(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT 'HTTP请求方法',
  `request_path` VARCHAR(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '请求路径',
  `request_params` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '请求参数（JSON格式，不包含敏感信息）',
  `status_code` INT NULL DEFAULT NULL COMMENT 'HTTP状态码',
  `success` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '操作是否成功',
  `error_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '错误信息（如果失败）',
  `details` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '详细信息（JSON格式）',
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
) ENGINE = InnoDB AUTO_INCREMENT = 876 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = DYNAMIC COMMENT = '用户操作日志表（审计日志）';

-- ----------------------------
-- Table structure for user_sessions
-- ----------------------------
DROP TABLE IF EXISTS `user_sessions`;
CREATE TABLE `user_sessions`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '会话ID',
  `user_id` INT NOT NULL COMMENT '用户ID',
  `token_jti` VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'JWT令牌ID（jti）',
  `ip_address` VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '登录IP地址',
  `user_agent` VARCHAR(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '用户代理（浏览器信息）',
  `device_info` VARCHAR(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '设备信息（移动端/桌面端）',
  `location` VARCHAR(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '登录位置（可选，通过IP解析）',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否活跃',
  `last_activity` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '最后活动时间',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间（登录时间）',
  `expires_at` DATETIME(6) NOT NULL COMMENT '过期时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_user_sessions_token_jti`(`token_jti` ASC) USING BTREE,
  INDEX `idx_session_user_active`(`user_id` ASC, `is_active` ASC) USING BTREE,
  INDEX `idx_session_expires`(`expires_at` ASC) USING BTREE,
  INDEX `idx_user_id`(`user_id` ASC) USING BTREE,
  INDEX `idx_token_jti`(`token_jti` ASC) USING BTREE,
  INDEX `idx_ip_address`(`ip_address` ASC) USING BTREE,
  INDEX `idx_is_active`(`is_active` ASC) USING BTREE,
  INDEX `idx_last_activity`(`last_activity` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 153 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = DYNAMIC COMMENT = '用户会话表';

-- ----------------------------
-- Table structure for users
-- ----------------------------
DROP TABLE IF EXISTS `users`;
CREATE TABLE `users`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '用户ID',
  `username` VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '用户名称(登录名称)',
  `hashed_password` VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '用户Hash密码',
  `full_name` VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '用户全名',
  `email` VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '用户邮箱',
  `role` ENUM('admin','client') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'client' COMMENT '用户角色(ADMIN 管理员 / CLIENT 客户)',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
  `login_restricted` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否限制登录',
  `login_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '登录提示消息',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_users_username`(`username` ASC) USING BTREE,
  UNIQUE INDEX `uq_users_email`(`email` ASC) USING BTREE,
  INDEX `idx_username`(`username` ASC) USING BTREE,
  INDEX `idx_email`(`email` ASC) USING BTREE,
  FULLTEXT INDEX `ft_users_search`(`username`, `full_name`, `email`) WITH PARSER `ngram`
) ENGINE = InnoDB AUTO_INCREMENT = 15 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = DYNAMIC COMMENT = '用户表';

SET FOREIGN_KEY_CHECKS = 1;
