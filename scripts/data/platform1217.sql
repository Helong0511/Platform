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
CREATE DATABASE IF NOT EXISTS `platform` DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_unicode_ci;

USE `platform`;

-- ----------------------------
-- Table structure for ad_data
-- ----------------------------
DROP TABLE IF EXISTS `ad_data`;
CREATE TABLE IF NOT EXISTS `ad_data`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '广告数据ID',
  `date` datetime NOT NULL COMMENT '数据日期',
  `country_code` varchar(5) NULL DEFAULT 'ZZ' COMMENT '国家代码（ISO 3166-1 二字母代码）',
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
CREATE TABLE IF NOT EXISTS `ad_data_archive`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '广告数据ID',
  `date` datetime NOT NULL COMMENT '数据日期',
  `country_code` varchar(5) NULL DEFAULT 'ZZ' COMMENT '国家代码（ISO 3166-1 二字母代码）',
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
  PRIMARY KEY (`id`) USING BTREE  -- 这里修改为 USING BTREE 或直接删除 USING 子句
) ENGINE = ARCHIVE CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '广告数据归档表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for client_notification_configs
-- ----------------------------
DROP TABLE IF EXISTS `client_notification_configs`;
CREATE TABLE IF NOT EXISTS `client_notification_configs`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '通知配置ID',
  `client_id` int NOT NULL COMMENT '客户ID',
  `notification_enabled` tinyint(1) NULL DEFAULT 1 COMMENT '是否启用通知',
  `notify_on_conversion` tinyint(1) NULL DEFAULT 1 COMMENT '转化时通知',
  `notify_on_high_value` tinyint(1) NULL DEFAULT 0 COMMENT '高价值转化通知',
  `high_value_threshold` decimal(10, 2) NULL DEFAULT NULL COMMENT '高价值阈值',
  `notify_channels` text NULL COMMENT '通知渠道（JSON格式：[\"telegram\", \"email\", \"sms\"]）',
  `telegram_chat_id` varchar(100) NULL DEFAULT NULL COMMENT 'Telegram Chat ID',
  `email_address` varchar(255) NULL DEFAULT NULL COMMENT '邮箱地址',
  `phone_number` varchar(20) NULL DEFAULT NULL COMMENT '手机号',
  `notification_frequency` varchar(20) NULL DEFAULT 'realtime' COMMENT '通知频率：realtime, hourly, daily',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `client_id`(`client_id` ASC) USING BTREE,
  INDEX `idx_client_notification_config_client`(`client_id` ASC) USING BTREE,
  INDEX `idx_client_notification_config_enabled`(`notification_enabled` ASC) USING BTREE,
  CONSTRAINT `client_notification_configs_ibfk_1` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '客户通知配置表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for clients
-- ----------------------------
DROP TABLE IF EXISTS `clients`;
CREATE TABLE IF NOT EXISTS `clients`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '客户ID',
  `user_id` int NOT NULL COMMENT '用户ID',
  `company_name` varchar(100) NOT NULL COMMENT '公司名称',
  `contact_person` varchar(50) NULL DEFAULT NULL COMMENT '联系人',
  `phone` varchar(20) NULL DEFAULT NULL COMMENT '联系电话',
  `address` TEXT NULL COMMENT '公司地址',
  `allowed_ips` TEXT NULL COMMENT 'IP白名单，多个IP用逗号分隔，为空则不限制',
  `key` varchar(36) NOT NULL COMMENT '客户唯一标识UUID',
  `is_active` tinyint(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
  `api_enabled` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否允许API访问（开启后允许客户通过API查询产品和广告数据，并显示API对接菜单）',
  `password_change_enabled` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否允许客户修改密码（开启后客户可以修改自己的密码）',
  `chat_id` varchar(20) NULL DEFAULT NULL COMMENT '15位聊天ID',
  `notify_url` varchar(200) NULL DEFAULT NULL COMMENT '客户广告数据通知地址',
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
-- Table structure for countries
-- ----------------------------
DROP TABLE IF EXISTS `countries`;
CREATE TABLE IF NOT EXISTS `countries`  (
  `id` int NOT NULL AUTO_INCREMENT,
  `alpha_2_code` char(2) NOT NULL COMMENT '国家二字代码',
  `alpha_3_code` char(3) NOT NULL COMMENT '国家三字代码',
  `numeric_code` char(3) NOT NULL COMMENT '国家数字代码',
  `country_name_zh` varchar(100) NOT NULL COMMENT '国家中文名称',
  `country_name_en` varchar(100) NOT NULL COMMENT '国家英文名称',
  `official_name_zh` varchar(150) NULL DEFAULT NULL COMMENT '官方中文名称',
  `official_name_en` varchar(150) NULL DEFAULT NULL COMMENT '官方英文名称',
  `independent_status` tinyint(1) NULL DEFAULT 1 COMMENT '是否独立国家',
  `continent` varchar(50) NULL DEFAULT NULL COMMENT '所属大洲',
  `subregion` varchar(50) NULL DEFAULT NULL COMMENT '所属地区',
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
-- Table structure for postback_conversions
-- ----------------------------
-- SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS `postback_conversions`;
CREATE TABLE IF NOT EXISTS `postback_conversions`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '转化记录ID',
  `platform` varchar(50) NOT NULL COMMENT '平台名称：macan, addermobi等',
  `conversion_id` varchar(255) NOT NULL COMMENT '转化ID（各平台唯一标识，如Macan的clk_id）',
  `event_name` varchar(100) NULL DEFAULT NULL COMMENT '事件名称（如purchase, install等）',
  `event_value` float NULL DEFAULT NULL COMMENT '事件价值（购买价格等）',
  `payout` float NULL DEFAULT NULL COMMENT '支付金额（确认的广告单元价格）',
  `devad_id` varchar(255) NULL DEFAULT NULL COMMENT '设备广告ID（IDFA或GAID）',
  `os` varchar(20) NULL DEFAULT NULL COMMENT '操作系统（IOS或Android）',
  `carrier` varchar(50) NULL DEFAULT NULL COMMENT '用户运营商',
  `ip` varchar(50) NULL DEFAULT NULL COMMENT '点击IP地址',
  `gid` varchar(100) NULL DEFAULT NULL COMMENT '渠道ID（Channel ID）',
  `product_id` int NULL DEFAULT NULL COMMENT '关联的产品ID（可选，用于关联产品）',
  `client_id` int NULL DEFAULT NULL COMMENT '关联的客户ID（可选，用于关联客户）',
  `raw_data` TEXT NULL COMMENT '原始回调数据（JSON格式，保存完整回调数据以便后续分析）',
  `created_at` datetime NOT NULL COMMENT '创建时间（记录回调接收时间）',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_postback_platform_conversion_event`(`platform` ASC, `conversion_id` ASC, `event_name` ASC) USING BTREE COMMENT '防止同一平台的同一转化ID和事件名称重复处理',
  INDEX `idx_postback_platform_conversion`(`platform` ASC, `conversion_id` ASC) USING BTREE COMMENT '平台和转化ID复合索引（优化平台查询）',
  INDEX `idx_postback_product`(`product_id` ASC) USING BTREE COMMENT '产品ID索引（优化产品关联查询）',
  INDEX `idx_postback_client`(`client_id` ASC) USING BTREE COMMENT '客户ID索引（优化客户关联查询）',
  INDEX `idx_postback_created_at`(`created_at` ASC) USING BTREE COMMENT '创建时间索引（优化时间范围查询）',
  INDEX `idx_postback_platform_event`(`platform` ASC, `event_name` ASC) USING BTREE COMMENT '平台和事件名称复合索引（优化事件统计查询）',
  CONSTRAINT `postback_conversions_ibfk_1` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `postback_conversions_ibfk_2` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'Postback转化事件表，统一存储所有平台的postback回调数据' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for postback_forward_logs
-- ----------------------------
DROP TABLE IF EXISTS `postback_forward_logs`;
CREATE TABLE IF NOT EXISTS `postback_forward_logs`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '转发日志ID',
  `conversion_id` int NOT NULL COMMENT '关联的转化记录ID',
  `product_id` int NULL DEFAULT NULL COMMENT '产品ID',
  `downstream_url` varchar(500) NOT NULL COMMENT '下游URL',
  `request_method` varchar(10) NOT NULL COMMENT '请求方式：GET 或 POST',
  `request_data` TEXT NULL COMMENT '请求数据（JSON格式，用于POST请求）',
  `request_params` TEXT NULL COMMENT '请求参数（URL参数，用于GET请求）',
  `response_status` int NULL DEFAULT NULL COMMENT '响应状态码',
  `response_body` TEXT NULL COMMENT '响应内容',
  `success` tinyint(1) NULL DEFAULT NULL COMMENT '是否转发成功',
  `error_message` TEXT NULL COMMENT '错误信息（如果转发失败）',
  `retry_count` int NULL DEFAULT NULL COMMENT '重试次数',
  `created_at` datetime NOT NULL COMMENT '创建时间',
  `completed_at` datetime NULL DEFAULT NULL COMMENT '完成时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_forward_log_product`(`product_id` ASC) USING BTREE,
  INDEX `ix_postback_forward_logs_id`(`id` ASC) USING BTREE,
  INDEX `ix_postback_forward_logs_created_at`(`created_at` ASC) USING BTREE,
  INDEX `ix_postback_forward_logs_conversion_id`(`conversion_id` ASC) USING BTREE,
  INDEX `idx_forward_log_conversion`(`conversion_id` ASC) USING BTREE,
  INDEX `idx_forward_log_success`(`success` ASC) USING BTREE,
  INDEX `idx_forward_log_created_at`(`created_at` ASC) USING BTREE,
  INDEX `ix_postback_forward_logs_product_id`(`product_id` ASC) USING BTREE,
  INDEX `ix_postback_forward_logs_success`(`success` ASC) USING BTREE,
  CONSTRAINT `postback_forward_logs_ibfk_1` FOREIGN KEY (`conversion_id`) REFERENCES `postback_conversions` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `postback_forward_logs_ibfk_2` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for postback_notifications
-- ----------------------------
DROP TABLE IF EXISTS `postback_notifications`;
CREATE TABLE IF NOT EXISTS `postback_notifications`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '通知记录ID',
  `conversion_id` int NOT NULL COMMENT '转化记录ID',
  `client_id` int NULL DEFAULT NULL COMMENT '客户ID',
  `product_id` int NULL DEFAULT NULL COMMENT '产品ID',
  `notification_type` varchar(50) NULL DEFAULT NULL COMMENT '通知类型：conversion, high_value, error',
  `notification_channel` varchar(50) NOT NULL COMMENT '通知渠道：telegram, email, sms',
  `notification_status` varchar(20) NULL DEFAULT 'pending' COMMENT '通知状态：sent, failed, pending',
  `notification_message` TEXT NULL COMMENT '通知消息内容',
  `error_message` TEXT NULL COMMENT '错误信息（如果失败）',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_postback_notification_conversion`(`conversion_id` ASC) USING BTREE,
  INDEX `idx_postback_notification_client`(`client_id` ASC) USING BTREE,
  INDEX `idx_postback_notification_product`(`product_id` ASC) USING BTREE,
  INDEX `idx_postback_notification_status`(`notification_status` ASC) USING BTREE,
  INDEX `idx_postback_notification_created_at`(`created_at` ASC) USING BTREE,
  CONSTRAINT `postback_notifications_ibfk_1` FOREIGN KEY (`conversion_id`) REFERENCES `postback_conversions` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `postback_notifications_ibfk_2` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `postback_notifications_ibfk_3` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'Postback通知记录表' ROW_FORMAT = Dynamic;
-- SET FOREIGN_KEY_CHECKS = 1;
-- ----------------------------
-- Table structure for product_assignments
-- ----------------------------
DROP TABLE IF EXISTS `product_assignments`;
CREATE TABLE IF NOT EXISTS `product_assignments`  (
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
CREATE TABLE IF NOT EXISTS `product_notification_configs`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '通知配置ID',
  `product_id` int NOT NULL COMMENT '产品ID',
  `notification_enabled` tinyint(1) NULL DEFAULT 1 COMMENT '是否启用通知',
  `notify_on_conversion` tinyint(1) NULL DEFAULT 1 COMMENT '转化时通知',
  `notify_on_high_value` tinyint(1) NULL DEFAULT 0 COMMENT '高价值转化通知',
  `high_value_threshold` decimal(10, 2) NULL DEFAULT NULL COMMENT '高价值阈值',
  `notify_channels` TEXT NULL COMMENT '通知渠道（JSON格式：[\"telegram\", \"email\", \"sms\"]）',
  `telegram_chat_id` varchar(100) NULL DEFAULT NULL COMMENT 'Telegram Chat ID',
  `email_address` varchar(255) NULL DEFAULT NULL COMMENT '邮箱地址',
  `phone_number` varchar(20) NULL DEFAULT NULL COMMENT '手机号',
  `notification_frequency` varchar(20) NULL DEFAULT 'realtime' COMMENT '通知频率：realtime, hourly, daily',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `product_id`(`product_id` ASC) USING BTREE,
  INDEX `idx_product_notification_config_product`(`product_id` ASC) USING BTREE,
  INDEX `idx_product_notification_config_enabled`(`notification_enabled` ASC) USING BTREE,
  CONSTRAINT `product_notification_configs_ibfk_1` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '产品通知配置表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for products
-- ----------------------------
DROP TABLE IF EXISTS `products`;
CREATE TABLE IF NOT EXISTS `products`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '产品ID',
  `client_id` int NOT NULL COMMENT '客户ID',
  `name` varchar(100) NOT NULL COMMENT '产品名称',
  `ecpm_deduct_ratio` float NOT NULL DEFAULT 0 COMMENT 'eCPM减扣比例',
  `revenue_deduct_ratio` float NOT NULL DEFAULT 0 COMMENT '收益减扣比例',
  `cplpo_deduct_ratio` float NOT NULL DEFAULT 0 COMMENT 'CPL PO减扣比例',
  `is_active` tinyint(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
  `notification_address` varchar(500) NULL DEFAULT NULL COMMENT '通知地址（Telegram Chat ID、邮箱地址、Webhook URL等，用于接收转化通知）',
  `downstream_postback_method` varchar(10) NULL DEFAULT 'GET' COMMENT '下游 Postback 请求方式：GET 或 POST（默认GET）',
  `downstream_postback_url` varchar(500) NULL DEFAULT NULL COMMENT '下游 Postback URL（可选，配置后将自动转发转化数据）',
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_product_client`(`client_id` ASC) USING BTREE,
  INDEX `idx_product_name`(`name` ASC) USING BTREE,
  FULLTEXT INDEX `ft_products_name`(`name`) WITH PARSER `ngram`,
  CONSTRAINT `fk_products_client` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '产品表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for scheduled_tasks
-- ----------------------------
DROP TABLE IF EXISTS `scheduled_tasks`;
CREATE TABLE IF NOT EXISTS `scheduled_tasks`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '定时任务ID',
  `task_name` varchar(100) NOT NULL COMMENT '任务名称（唯一）',
  `last_run_time` datetime(6) NULL DEFAULT NULL COMMENT '上次执行时间',
  `is_running` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否正在执行',
  `last_run_pid` int NULL DEFAULT NULL COMMENT '上次执行的进程ID',
  `last_run_host` varchar(100) NULL DEFAULT NULL COMMENT '上次执行的服务器主机名',
  `run_count` int NOT NULL DEFAULT 0 COMMENT '执行次数',
  `success_count` int NOT NULL DEFAULT 0 COMMENT '成功次数',
  `error_count` int NOT NULL DEFAULT 0 COMMENT '失败次数',
  `last_error` TEXT NULL COMMENT '最后一次错误信息',
  `is_active` tinyint(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  `cron_expression` varchar(100) NULL DEFAULT NULL COMMENT 'Cron表达式',
  `description` TEXT NULL COMMENT '任务描述',
  `function_path` varchar(255) NULL DEFAULT NULL COMMENT '执行函数路径（例如：app.scheduler_module.tasks.simple_task.simple_info_task）',
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
CREATE TABLE IF NOT EXISTS `short_links`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '短链接ID',
  `short_code` varchar(20) NOT NULL COMMENT '短链接代码（唯一）',
  `original_url` TEXT NOT NULL COMMENT '原始URL',
  `title` varchar(200) NULL DEFAULT NULL COMMENT '短链接标题（可选）',
  `description` TEXT NULL COMMENT '短链接描述（可选）',
  `created_by` int NULL DEFAULT NULL COMMENT '创建者用户ID',
  `click_count` int NULL DEFAULT 0 COMMENT '点击次数',
  `is_active` tinyint(1) NULL DEFAULT 1 COMMENT '是否激活',
  `expires_at` datetime NULL DEFAULT NULL COMMENT '过期时间（可选）',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `short_code`(`short_code` ASC) USING BTREE,
  INDEX `idx_short_link_code`(`short_code` ASC) USING BTREE,
  INDEX `idx_short_link_created_by`(`created_by` ASC) USING BTREE,
  INDEX `idx_short_link_active`(`is_active` ASC) USING BTREE,
  INDEX `idx_short_link_created_at`(`created_at` ASC) USING BTREE,
  CONSTRAINT `short_links_ibfk_1` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '短链接表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for tb_search_data
-- ----------------------------
DROP TABLE IF EXISTS `tb_search_data`;
CREATE TABLE IF NOT EXISTS `tb_search_data`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `date` datetime NOT NULL COMMENT '日期',
  `product_id` int NOT NULL COMMENT '产品ID',
  `country_code` varchar(2) NULL DEFAULT NULL COMMENT '国家代码',
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
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for token_blacklist
-- ----------------------------
DROP TABLE IF EXISTS `token_blacklist`;
CREATE TABLE IF NOT EXISTS `token_blacklist`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '黑名单ID',
  `token_jti` varchar(64) NOT NULL COMMENT 'JWT令牌ID（jti）',
  `user_id` int NOT NULL COMMENT '用户ID',
  `revoked_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '撤销时间',
  `expires_at` datetime(6) NOT NULL COMMENT 'Token过期时间',
  `reason` varchar(200) NULL DEFAULT NULL COMMENT '撤销原因（用户退出、强制退出等）',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uq_token_blacklist_token_jti`(`token_jti` ASC) USING BTREE,
  INDEX `idx_blacklist_user`(`user_id` ASC) USING BTREE,
  INDEX `idx_blacklist_expires`(`expires_at` ASC) USING BTREE,
  INDEX `idx_token_jti`(`token_jti` ASC) USING BTREE,
  INDEX `idx_revoked_at`(`revoked_at` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'Token黑名单表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for user_audit_logs
-- ----------------------------
DROP TABLE IF EXISTS `user_audit_logs`;
CREATE TABLE IF NOT EXISTS `user_audit_logs`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '日志ID',
  `user_id` int NULL DEFAULT NULL COMMENT '用户ID（可为空，记录未登录访问）',
  `username` varchar(50) NULL DEFAULT NULL COMMENT '用户名（冗余字段，便于查询）',
  `action_type` varchar(50) NOT NULL COMMENT '操作类型：LOGIN, LOGOUT, CREATE, UPDATE, DELETE, VIEW, ACCESS等',
  `resource_type` varchar(50) NULL DEFAULT NULL COMMENT '资源类型：USER, CLIENT, PRODUCT, AD_DATA, SCHEDULED_TASK等',
  `resource_id` int NULL DEFAULT NULL COMMENT '资源ID',
  `resource_name` varchar(255) NULL DEFAULT NULL COMMENT '资源名称（冗余字段，便于查询）',
  `ip_address` varchar(50) NULL DEFAULT NULL COMMENT 'IP地址',
  `user_agent` varchar(500) NULL DEFAULT NULL COMMENT '用户代理（浏览器信息）',
  `request_method` varchar(10) NULL DEFAULT NULL COMMENT 'HTTP请求方法',
  `request_path` varchar(500) NULL DEFAULT NULL COMMENT '请求路径',
  `request_params` TEXT NULL COMMENT '请求参数（JSON格式，不包含敏感信息）',
  `status_code` int NULL DEFAULT NULL COMMENT 'HTTP状态码',
  `success` tinyint(1) NOT NULL DEFAULT 1 COMMENT '操作是否成功',
  `error_message` TEXT NULL COMMENT '错误信息（如果失败）',
  `details` TEXT NULL COMMENT '详细信息（JSON格式）',
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
CREATE TABLE IF NOT EXISTS `user_sessions`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '会话ID',
  `user_id` int NOT NULL COMMENT '用户ID',
  `token_jti` varchar(64) NOT NULL COMMENT 'JWT令牌ID（jti）',
  `ip_address` varchar(50) NULL DEFAULT NULL COMMENT '登录IP地址',
  `user_agent` varchar(500) NULL DEFAULT NULL COMMENT '用户代理（浏览器信息）',
  `device_info` varchar(200) NULL DEFAULT NULL COMMENT '设备信息（移动端/桌面端）',
  `location` varchar(200) NULL DEFAULT NULL COMMENT '登录位置（可选，通过IP解析）',
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
CREATE TABLE IF NOT EXISTS `users`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '用户ID',
  `username` varchar(50) NOT NULL COMMENT '用户名称(登录名称)',
  `hashed_password` varchar(191) NOT NULL COMMENT '用户Hash密码',
  `full_name` varchar(100) NULL DEFAULT NULL COMMENT '用户全名',
  `email` varchar(100) NULL DEFAULT NULL COMMENT '用户邮箱',
  `role` enum('admin','client') NOT NULL DEFAULT 'client' COMMENT '用户角色(ADMIN 管理员 / CLIENT 客户)',
  `is_active` tinyint(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
  `login_restricted` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否限制登录',
  `login_message` TEXT NULL COMMENT '登录提示消息',
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
