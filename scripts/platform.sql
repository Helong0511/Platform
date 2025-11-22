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

-- ============================================
-- 删除已存在的表（按依赖顺序，避免外键约束错误）
-- ============================================
DROP TABLE IF EXISTS `token_blacklist`;
DROP TABLE IF EXISTS `user_sessions`;
DROP TABLE IF EXISTS `user_audit_logs`;
DROP TABLE IF EXISTS `product_assignments`;
DROP TABLE IF EXISTS `ad_data`;
DROP TABLE IF EXISTS `scheduled_tasks`;
DROP TABLE IF EXISTS `products`;
DROP TABLE IF EXISTS `clients`;
DROP TABLE IF EXISTS `users`;

-- ============================================
-- 1. 用户表 (users)
-- ============================================
-- 字段检查：
--   id: Integer -> INT(11) ✓
--   username: String(50) -> VARCHAR(50) ✓
--   hashed_password: String(191) -> VARCHAR(191) ✓
--   full_name: String(100) -> VARCHAR(100) ✓
--   email: String(100) -> VARCHAR(100) ✓ (注意：模型定义是100，但实际使用中可能需要191，这里按模型定义)
--   role: Enum('admin','client') -> ENUM('admin','client') ✓
--   is_active: Boolean -> TINYINT(1) ✓
--   login_restricted: Boolean -> TINYINT(1) ✓
--   login_message: Text -> TEXT ✓
--   created_at: DateTime -> DATETIME(6) ✓
--   updated_at: DateTime -> DATETIME(6) ✓
CREATE TABLE IF NOT EXISTS `users` (
    `id` INT(11) NOT NULL AUTO_INCREMENT COMMENT '用户ID',
    `username` VARCHAR(50) NOT NULL COMMENT '用户名称(登录名称)',
    `hashed_password` VARCHAR(191) NOT NULL COMMENT '用户Hash密码',
    `full_name` VARCHAR(100) DEFAULT NULL COMMENT '用户全名',
    `email` VARCHAR(100) DEFAULT NULL COMMENT '用户邮箱',
    `role` ENUM('admin', 'client') NOT NULL DEFAULT 'client' COMMENT '用户角色(ADMIN 管理员 / CLIENT 客户)',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
    `login_restricted` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否限制登录',
    `login_message` TEXT DEFAULT NULL COMMENT '登录提示消息',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
    PRIMARY KEY (`id`) USING BTREE,
    UNIQUE INDEX `uq_users_username` (`username`) USING BTREE,
    UNIQUE INDEX `uq_users_email` (`email`) USING BTREE,
    INDEX `idx_username` (`username`),
    INDEX `idx_email` (`email`),
    -- 全文索引：支持中文搜索（username, full_name, email）
    FULLTEXT INDEX `ft_users_search` (`username`, `full_name`, `email`) WITH PARSER `ngram`
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表' ROW_FORMAT=Dynamic;

-- ============================================
-- 2. 客户表 (clients)
-- ============================================
-- 字段检查：
--   id: Integer -> INT(11) ✓
--   user_id: Integer, ForeignKey -> INT(11) ✓
--   key: String(36) -> VARCHAR(36) ✓
--   company_name: String(100) -> VARCHAR(100) ✓
--   contact_person: String(50) -> VARCHAR(50) ✓
--   phone: String(20) -> VARCHAR(20) ✓
--   address: Text -> TEXT ✓
--   allowed_ips: Text -> TEXT ✓
--   is_active: Boolean -> TINYINT(1) ✓
--   api_enabled: Boolean -> TINYINT(1) ✓
--   password_change_enabled: Boolean -> TINYINT(1) ✓
--   created_at: DateTime -> DATETIME(6) ✓
--   updated_at: DateTime -> DATETIME(6) ✓
CREATE TABLE IF NOT EXISTS `clients` (
    `id` INT(11) NOT NULL AUTO_INCREMENT COMMENT '客户ID',
    `user_id` INT(11) NOT NULL COMMENT '用户ID',
    `company_name` VARCHAR(100) NOT NULL COMMENT '公司名称',
    `contact_person` VARCHAR(50) DEFAULT NULL COMMENT '联系人',
    `phone` VARCHAR(20) DEFAULT NULL COMMENT '联系电话',
    `address` TEXT DEFAULT NULL COMMENT '公司地址',
    `allowed_ips` TEXT DEFAULT NULL COMMENT 'IP白名单，多个IP用逗号分隔，为空则不限制',
    `key` VARCHAR(36) NOT NULL COMMENT '客户API密钥',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
    `api_enabled` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否允许API访问（开启后允许客户通过API查询产品和广告数据，并显示API对接菜单）',
    `password_change_enabled` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否允许客户修改密码（开启后客户可以修改自己的密码）',
    `chat_id` BIGINT NULL UNIQUE COMMENT 'Telegram Chat Id',
    `notify_url` VARCHAR(200) NULL COMMENT '客户广告数据通知地址',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
    PRIMARY KEY (`id`) USING BTREE,
    UNIQUE INDEX `uq_clients_key` (`key`) USING BTREE,
    INDEX `idx_client_user` (`user_id`),
    INDEX `idx_clients_key` (`key`),
    -- 全文索引：支持中文搜索（company_name, contact_person）
    FULLTEXT INDEX `ft_clients_search` (`company_name`, `contact_person`) WITH PARSER `ngram`,
    CONSTRAINT `fk_clients_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT = 1000 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客户表' ROW_FORMAT=Dynamic;

-- ============================================
-- 3. 产品表 (products)
-- ============================================
-- 字段检查：
--   id: Integer -> INT(11) ✓
--   client_id: Integer, ForeignKey -> INT(11) ✓
--   name: String(100) -> VARCHAR(100) ✓
--   ecpm_deduct_ratio: Float -> FLOAT ✓
--   revenue_deduct_ratio: Float -> FLOAT ✓
--   is_active: Boolean -> TINYINT(1) ✓
--   created_at: DateTime -> DATETIME(6) ✓
--   updated_at: DateTime -> DATETIME(6) ✓
CREATE TABLE IF NOT EXISTS `products` (
    `id` INT(11) NOT NULL AUTO_INCREMENT COMMENT '产品ID',
    `client_id` INT(11) NOT NULL COMMENT '客户ID',
    `name` VARCHAR(100) NOT NULL COMMENT '产品名称',
    `ecpm_deduct_ratio` FLOAT NOT NULL DEFAULT 0.0 COMMENT 'eCPM减扣比例',
    `revenue_deduct_ratio` FLOAT NOT NULL DEFAULT 0.0 COMMENT '收益减扣比例',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
    PRIMARY KEY (`id`) USING BTREE,
    INDEX `idx_product_client` (`client_id`),
    INDEX `idx_product_name` (`name`),
    -- 全文索引：支持中文搜索（name）
    FULLTEXT INDEX `ft_products_name` (`name`) WITH PARSER `ngram`,
    CONSTRAINT `fk_products_client` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='产品表' ROW_FORMAT=Dynamic;

-- ============================================
-- 4. 广告数据表 (ad_data)
-- ============================================
-- 字段检查：
--   id: Integer -> INT(11) ✓
--   date: DateTime -> DATETIME ✓
--   product_id: Integer, ForeignKey -> INT(11) ✓
--   request_count: Integer -> INT(11) ✓
--   match_count: Integer -> INT(11) ✓
--   display_count: Integer -> INT(11) ✓
--   click_count: Integer -> INT(11) ✓
--   ecpm_before_deduct: Float -> FLOAT ✓
--   ecpm_after_deduct: Float -> FLOAT ✓
--   revenue_before_deduct: Float -> FLOAT ✓
--   revenue_after_deduct: Float -> FLOAT ✓
--   created_at: DateTime -> DATETIME(6) ✓
--   updated_at: DateTime -> DATETIME(6) ✓
CREATE TABLE IF NOT EXISTS `ad_data` (
    `id` INT(11) NOT NULL AUTO_INCREMENT COMMENT '广告数据ID',
    `date` DATETIME NOT NULL COMMENT '数据日期',
    `product_id` INT(11) NOT NULL COMMENT '产品ID',
    `request_count` INT(11) NOT NULL DEFAULT 0 COMMENT '请求数',
    `match_count` INT(11) NOT NULL DEFAULT 0 COMMENT '匹配数',
    `display_count` INT(11) NOT NULL DEFAULT 0 COMMENT '展示数',
    `click_count` INT(11) NOT NULL DEFAULT 0 COMMENT '点击数',
    `ecpm_before_deduct` FLOAT NOT NULL DEFAULT 0.0 COMMENT 'eCPM未减扣',
    `ecpm_after_deduct` FLOAT NOT NULL DEFAULT 0.0 COMMENT 'eCPM已减扣',
    `revenue_before_deduct` FLOAT NOT NULL DEFAULT 0.0 COMMENT '收益未减扣',
    `revenue_after_deduct` FLOAT NOT NULL DEFAULT 0.0 COMMENT '收益已减扣',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
    PRIMARY KEY (`id`) USING BTREE,
    UNIQUE INDEX `uq_ad_data_date_product` (`date`, `product_id`) USING BTREE,
    INDEX `idx_ad_data_date` (`date`),
    INDEX `idx_ad_data_product` (`product_id`),
    INDEX `idx_ad_data_date_product` (`date`, `product_id`),
    CONSTRAINT `fk_ad_data_product` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='广告数据表' ROW_FORMAT=Dynamic;

-- ============================================
-- 5. 产品分配历史表 (product_assignments)
-- ============================================
-- 字段检查：
--   id: Integer -> INT(11) ✓
--   product_id: Integer, ForeignKey -> INT(11) ✓
--   client_id: Integer, ForeignKey -> INT(11) ✓
--   start_date: Date -> DATE ✓
--   end_date: Date -> DATE ✓
--   created_at: DateTime -> DATETIME(6) ✓
--   updated_at: DateTime -> DATETIME(6) ✓
CREATE TABLE IF NOT EXISTS `product_assignments` (
    `id` INT(11) NOT NULL AUTO_INCREMENT COMMENT '分配记录ID',
    `product_id` INT(11) NOT NULL COMMENT '产品ID',
    `client_id` INT(11) NOT NULL COMMENT '客户ID',
    `start_date` DATE NOT NULL COMMENT '分配开始日期',
    `end_date` DATE DEFAULT NULL COMMENT '分配结束日期（NULL表示当前有效）',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
    PRIMARY KEY (`id`) USING BTREE,
    INDEX `idx_product_assignments_product` (`product_id`),
    INDEX `idx_product_assignments_client` (`client_id`),
    INDEX `idx_product_assignments_date` (`product_id`, `start_date`, `end_date`),
    INDEX `idx_product_assignments_active` (`product_id`, `end_date`),
    CONSTRAINT `fk_product_assignments_product` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_product_assignments_client` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='产品分配历史表' ROW_FORMAT=Dynamic;

-- ============================================
-- 6. 定时任务执行记录表 (scheduled_tasks)
-- ============================================
-- 字段检查：
--   id: Integer -> INT(11) ✓
--   task_name: String(100) -> VARCHAR(100) ✓
--   last_run_time: DateTime -> DATETIME(6) ✓
--   is_running: Boolean -> TINYINT(1) ✓
--   last_run_pid: Integer -> INT(11) ✓
--   last_run_host: String(100) -> VARCHAR(100) ✓
--   run_count: Integer -> INT(11) ✓
--   success_count: Integer -> INT(11) ✓
--   error_count: Integer -> INT(11) ✓
--   last_error: Text -> TEXT ✓
--   is_active: Boolean -> TINYINT(1) ✓
--   cron_expression: String(100) -> VARCHAR(100) ✓
--   description: Text -> TEXT ✓
--   function_path: String(255) -> VARCHAR(255) ✓
--   created_at: DateTime -> DATETIME(6) ✓
--   updated_at: DateTime -> DATETIME(6) ✓
CREATE TABLE IF NOT EXISTS `scheduled_tasks` (
    `id` INT(11) NOT NULL AUTO_INCREMENT COMMENT '定时任务ID',
    `task_name` VARCHAR(100) NOT NULL COMMENT '任务名称（唯一）',
    `last_run_time` DATETIME(6) DEFAULT NULL COMMENT '上次执行时间',
    `is_running` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否正在执行',
    `last_run_pid` INT(11) DEFAULT NULL COMMENT '上次执行的进程ID',
    `last_run_host` VARCHAR(100) DEFAULT NULL COMMENT '上次执行的服务器主机名',
    `run_count` INT(11) NOT NULL DEFAULT 0 COMMENT '执行次数',
    `success_count` INT(11) NOT NULL DEFAULT 0 COMMENT '成功次数',
    `error_count` INT(11) NOT NULL DEFAULT 0 COMMENT '失败次数',
    `last_error` TEXT DEFAULT NULL COMMENT '最后一次错误信息',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
    `cron_expression` VARCHAR(100) DEFAULT NULL COMMENT 'Cron表达式',
    `description` TEXT DEFAULT NULL COMMENT '任务描述',
    `function_path` VARCHAR(255) DEFAULT NULL COMMENT '执行函数路径（例如：app.scheduler_module.tasks.simple_task.simple_info_task）',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
    PRIMARY KEY (`id`) USING BTREE,
    UNIQUE INDEX `uq_scheduled_tasks_task_name` (`task_name`) USING BTREE,
    INDEX `idx_scheduled_task_name` (`task_name`),
    INDEX `idx_scheduled_task_is_running` (`is_running`),
    INDEX `idx_scheduled_task_is_active` (`is_active`),
    -- 全文索引：支持中文搜索（task_name, description）
    FULLTEXT INDEX `ft_tasks_search` (`task_name`, `description`) WITH PARSER `ngram`
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='定时任务执行记录表' ROW_FORMAT=Dynamic;

-- ============================================
-- 7. 用户操作日志表 (user_audit_logs)
-- ============================================
-- 字段检查：
--   id: Integer -> INT(11) ✓
--   user_id: Integer, ForeignKey, nullable -> INT(11) ✓
--   username: String(50) -> VARCHAR(50) ✓
--   action_type: String(50) -> VARCHAR(50) ✓
--   resource_type: String(50) -> VARCHAR(50) ✓
--   resource_id: Integer -> INT(11) ✓
--   resource_name: String(255) -> VARCHAR(255) ✓
--   ip_address: String(50) -> VARCHAR(50) ✓
--   user_agent: String(500) -> VARCHAR(500) ✓
--   request_method: String(10) -> VARCHAR(10) ✓
--   request_path: String(500) -> VARCHAR(500) ✓
--   request_params: Text -> TEXT ✓
--   status_code: Integer -> INT(11) ✓
--   success: Boolean -> TINYINT(1) ✓
--   error_message: Text -> TEXT ✓
--   details: Text -> TEXT ✓
--   created_at: DateTime -> DATETIME(6) ✓
CREATE TABLE IF NOT EXISTS `user_audit_logs` (
    `id` INT(11) NOT NULL AUTO_INCREMENT COMMENT '日志ID',
    `user_id` INT(11) DEFAULT NULL COMMENT '用户ID（可为空，记录未登录访问）',
    `username` VARCHAR(50) DEFAULT NULL COMMENT '用户名（冗余字段，便于查询）',
    `action_type` VARCHAR(50) NOT NULL COMMENT '操作类型：LOGIN, LOGOUT, CREATE, UPDATE, DELETE, VIEW, ACCESS等',
    `resource_type` VARCHAR(50) DEFAULT NULL COMMENT '资源类型：USER, CLIENT, PRODUCT, AD_DATA, SCHEDULED_TASK等',
    `resource_id` INT(11) DEFAULT NULL COMMENT '资源ID',
    `resource_name` VARCHAR(255) DEFAULT NULL COMMENT '资源名称（冗余字段，便于查询）',
    `ip_address` VARCHAR(50) DEFAULT NULL COMMENT 'IP地址',
    `user_agent` VARCHAR(500) DEFAULT NULL COMMENT '用户代理（浏览器信息）',
    `request_method` VARCHAR(10) DEFAULT NULL COMMENT 'HTTP请求方法',
    `request_path` VARCHAR(500) DEFAULT NULL COMMENT '请求路径',
    `request_params` TEXT DEFAULT NULL COMMENT '请求参数（JSON格式，不包含敏感信息）',
    `status_code` INT(11) DEFAULT NULL COMMENT 'HTTP状态码',
    `success` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '操作是否成功',
    `error_message` TEXT DEFAULT NULL COMMENT '错误信息（如果失败）',
    `details` TEXT DEFAULT NULL COMMENT '详细信息（JSON格式）',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    PRIMARY KEY (`id`) USING BTREE,
    INDEX `idx_audit_log_user_id` (`user_id`),
    INDEX `idx_audit_log_username` (`username`),
    INDEX `idx_audit_log_action_type` (`action_type`),
    INDEX `idx_audit_log_resource_type` (`resource_type`),
    INDEX `idx_audit_log_ip_address` (`ip_address`),
    INDEX `idx_audit_log_request_path` (`request_path`),
    INDEX `idx_audit_log_success` (`success`),
    INDEX `idx_audit_log_created_at` (`created_at`),
    INDEX `idx_audit_log_user_action` (`user_id`, `action_type`),
    INDEX `idx_audit_log_resource` (`resource_type`, `resource_id`),
    CONSTRAINT `fk_user_audit_logs_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户操作日志表（审计日志）' ROW_FORMAT=Dynamic;

-- ============================================
-- 8. 用户会话表 (user_sessions)
-- ============================================
-- 字段检查：
--   id: Integer -> INT(11) ✓
--   user_id: Integer -> INT(11) ✓
--   token_jti: String(64) -> VARCHAR(64) ✓
--   ip_address: String(50) -> VARCHAR(50) ✓
--   user_agent: String(500) -> VARCHAR(500) ✓
--   device_info: String(200) -> VARCHAR(200) ✓
--   location: String(200) -> VARCHAR(200) ✓
--   is_active: Boolean -> TINYINT(1) ✓
--   last_activity: DateTime -> DATETIME(6) ✓
--   created_at: DateTime -> DATETIME(6) ✓
--   expires_at: DateTime -> DATETIME(6) ✓
CREATE TABLE IF NOT EXISTS `user_sessions` (
    `id` INT(11) NOT NULL AUTO_INCREMENT COMMENT '会话ID',
    `user_id` INT(11) NOT NULL COMMENT '用户ID',
    `token_jti` VARCHAR(64) NOT NULL COMMENT 'JWT令牌ID（jti）',
    `ip_address` VARCHAR(50) DEFAULT NULL COMMENT '登录IP地址',
    `user_agent` VARCHAR(500) DEFAULT NULL COMMENT '用户代理（浏览器信息）',
    `device_info` VARCHAR(200) DEFAULT NULL COMMENT '设备信息（移动端/桌面端）',
    `location` VARCHAR(200) DEFAULT NULL COMMENT '登录位置（可选，通过IP解析）',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否活跃',
    `last_activity` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '最后活动时间',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间（登录时间）',
    `expires_at` DATETIME(6) NOT NULL COMMENT '过期时间',
    PRIMARY KEY (`id`) USING BTREE,
    UNIQUE INDEX `uq_user_sessions_token_jti` (`token_jti`) USING BTREE,
    INDEX `idx_session_user_active` (`user_id`, `is_active`),
    INDEX `idx_session_expires` (`expires_at`),
    INDEX `idx_user_id` (`user_id`),
    INDEX `idx_token_jti` (`token_jti`),
    INDEX `idx_ip_address` (`ip_address`),
    INDEX `idx_is_active` (`is_active`),
    INDEX `idx_last_activity` (`last_activity`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户会话表' ROW_FORMAT=Dynamic;

-- ============================================
-- 9. Token黑名单表 (token_blacklist)
-- ============================================
-- 字段检查：
--   id: Integer -> INT(11) ✓
--   token_jti: String(64) -> VARCHAR(64) ✓
--   user_id: Integer -> INT(11) ✓
--   revoked_at: DateTime -> DATETIME(6) ✓
--   expires_at: DateTime -> DATETIME(6) ✓
--   reason: String(200) -> VARCHAR(200) ✓
CREATE TABLE IF NOT EXISTS `token_blacklist` (
    `id` INT(11) NOT NULL AUTO_INCREMENT COMMENT '黑名单ID',
    `token_jti` VARCHAR(64) NOT NULL COMMENT 'JWT令牌ID（jti）',
    `user_id` INT(11) NOT NULL COMMENT '用户ID',
    `revoked_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '撤销时间',
    `expires_at` DATETIME(6) NOT NULL COMMENT 'Token过期时间',
    `reason` VARCHAR(200) DEFAULT NULL COMMENT '撤销原因（用户退出、强制退出等）',
    PRIMARY KEY (`id`) USING BTREE,
    UNIQUE INDEX `uq_token_blacklist_token_jti` (`token_jti`) USING BTREE,
    INDEX `idx_blacklist_user` (`user_id`),
    INDEX `idx_blacklist_expires` (`expires_at`),
    INDEX `idx_token_jti` (`token_jti`),
    INDEX `idx_revoked_at` (`revoked_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Token黑名单表' ROW_FORMAT=Dynamic;

-- ============================================
-- 恢复外键检查
-- ============================================
SET FOREIGN_KEY_CHECKS = 1;

-- 添加数据
-- 添加管理员：[admin]密码：[admin123]
INSERT INTO `users` VALUES 
(1, 'admin', '$2b$12$BOHTtubZePvpDN.Sls7EbO3ANHMwjouG104GVdfdKcyPxM6wR/gYy', '管理员', 'admin@btfrx.online', 'admin', 1, 0, NULL, '2025-11-14 17:32:33.000000', '2025-11-14 17:32:33.000000'),
(2, 'data', '$2b$12$BOHTtubZePvpDN.Sls7EbO3ANHMwjouG104GVdfdKcyPxM6wR/gYy', '数据挂靠', 'data@btfrx.online', 'admin', 0, 0, NULL, '2025-11-14 17:32:33.000000', '2025-11-14 17:32:33.000000');


INSERT INTO `clients` (`id`,`user_id`,`key`,`company_name`) VALUES 
(1, 2, '8bc85bd7-c69b-4dc8-8728-f1b7be669ec5', '默认客户（导入数据）');


-- ============================================
-- 插入默认定时任务
-- ============================================
-- 1. 清理过期会话和黑名单（每天凌晨2点执行）
INSERT INTO `scheduled_tasks` (`task_name`, `description`, `cron_expression`, `function_path`, `is_active`, `run_count`, `success_count`, `error_count`, `last_run_time`, `is_running`, `last_run_pid`, `last_run_host`, `last_error`, `created_at`, `updated_at`) VALUES 
('数据归档任务', '归档6个月前的数据', '0 1 1 * *', 'app.scheduler_module.tasks.archive_old_data.archive_old_ad_data', 1, 0, 0, 0, NULL, 0, NULL, NULL, NULL, NOW(), NOW()),
('清理过期会话和黑名单', '清理过期超过30天的会话记录和黑名单记录，标记超过7天未活动的会话为非活跃', '0 2 * * *', 'app.scheduler_module.tasks.cleanup_expired_sessions.cleanup_expired_sessions', 1, 0, 0, 0, NULL, 0, NULL, NULL, NULL, NOW(), NOW()),
('TQT API获取数据', '每隔30分钟执行一次，从TQT API获取广告数据并导入到数据库', '*/30 * * * *', 'app.scheduler_module.tasks.tqt_task.tqt_api_task', 1, 0, 0, 0, NULL, 0, NULL, NULL, NULL, NOW(), NOW());