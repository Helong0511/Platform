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
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '广告数据ID',
  `date` DATETIME NOT NULL COMMENT '数据日期',
  `country_code` VARCHAR(5) NULL DEFAULT 'ZZ' COMMENT '国家代码（ISO 3166-1 二字母代码）',
  `product_id` INT NOT NULL COMMENT '产品ID',
  `request_count` INT NOT NULL DEFAULT 0 COMMENT '请求数',
  `match_count` INT NOT NULL DEFAULT 0 COMMENT '匹配数',
  `coverage_rate` FLOAT NULL DEFAULT 0 COMMENT '覆盖率',
  `display_count` INT NOT NULL DEFAULT 0 COMMENT '展示数',
  `display_rate` FLOAT NULL DEFAULT 0 COMMENT '展示率',
  `click_count` INT NOT NULL DEFAULT 0 COMMENT '点击数',
  `click_rate` FLOAT NULL DEFAULT 0 COMMENT '点击率',
  `viewability_rate` FLOAT NULL DEFAULT 0 COMMENT '可见率',
  `cpc` FLOAT NULL DEFAULT 0 COMMENT 'CPC',
  `pageviews` INT NULL DEFAULT 0 COMMENT 'PageViews',
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
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '广告数据表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for ad_data_archive
-- ----------------------------
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS `ad_data_archive`;
CREATE TABLE IF NOT EXISTS `ad_data_archive`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '广告数据ID',
  `date` DATETIME NOT NULL COMMENT '数据日期',
  `country_code` VARCHAR(5) NULL DEFAULT 'ZZ' COMMENT '国家代码（ISO 3166-1 二字母代码）',
  `product_id` INT NOT NULL COMMENT '产品ID',
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
  PRIMARY KEY (`id`) USING SE_SPECIFIC
) ENGINE = ARCHIVE CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '广告数据归档表' ROW_FORMAT = DYNAMIC;
SET FOREIGN_KEY_CHECKS = 1;
-- ----------------------------
-- Table structure for advertiser_tests
-- ----------------------------
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS `advertiser_tests`;
CREATE TABLE IF NOT EXISTS `advertiser_tests`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '测试记录ID',
  `advertiser_id` INT NOT NULL COMMENT '广告主ID',
  `advertiser_name` VARCHAR(100) NULL DEFAULT NULL COMMENT '广告主名称',
  `advertiser_offer_id` VARCHAR(100) NULL DEFAULT NULL COMMENT '上游系统中的Offer ID',
  `offer_id` INT NOT NULL COMMENT '平台内的Offer ID',
  `offer_name` VARCHAR(200) NULL DEFAULT NULL COMMENT 'Offer名称',
  `price` DECIMAL(10, 2) NULL DEFAULT NULL COMMENT '价格',
  `country` VARCHAR(50) NULL DEFAULT NULL COMMENT '国家',
  `click_id` VARCHAR(255) NULL DEFAULT NULL COMMENT '测试生成的Click ID',
  `click_url` TEXT NULL COMMENT '测试生成的Click Url',
  `test_time` DATETIME NULL DEFAULT NULL COMMENT '测试时间',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_advertiser_id`(`advertiser_id` ASC) USING BTREE,
  INDEX `idx_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_test_time`(`test_time` ASC) USING BTREE,
  CONSTRAINT `advertiser_tests_ibfk_1` FOREIGN KEY (`advertiser_id`) REFERENCES `advertisers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `advertiser_tests_ibfk_2` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '上游测试记录表' ROW_FORMAT = Dynamic;
SET FOREIGN_KEY_CHECKS = 1;
-- ----------------------------
-- Table structure for advertisers
-- ----------------------------
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS `advertisers`;
CREATE TABLE IF NOT EXISTS `advertisers`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '广告主ID',
  `advertiser_id` VARCHAR(50) NOT NULL COMMENT '广告主ID（系统生成，唯一标识）',
  `advertiser_name` VARCHAR(100) NOT NULL COMMENT '广告主名称',
  `email` VARCHAR(255) NULL DEFAULT NULL COMMENT '邮箱（可选）',
  `mobile` VARCHAR(20) NULL DEFAULT NULL COMMENT '手机号',
  `is_active` TINYINT(1) NULL DEFAULT 1 COMMENT '是否激活',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `advertiser_id`(`advertiser_id` ASC) USING BTREE,
  INDEX `idx_advertiser_id`(`advertiser_id` ASC) USING BTREE,
  INDEX `idx_advertiser_name`(`advertiser_name` ASC) USING BTREE,
  INDEX `idx_is_active`(`is_active` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '广告主表（上游）' ROW_FORMAT = Dynamic;
SET FOREIGN_KEY_CHECKS = 1;
-- ----------------------------
-- Table structure for affiliate_tests
-- ----------------------------
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS `affiliate_tests`;
CREATE TABLE IF NOT EXISTS `affiliate_tests`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '测试记录ID',
  `publisher_id` INT NOT NULL COMMENT '渠道ID',
  `click_id` VARCHAR(255) NOT NULL COMMENT '下游提供的Click ID',
  `offer_id` INT NOT NULL COMMENT 'Offer ID',
  `offer_name` VARCHAR(200) NULL DEFAULT NULL COMMENT 'Offer名称',
  `price` DECIMAL(10, 2) NULL DEFAULT NULL COMMENT '价格',
  `country` VARCHAR(50) NULL DEFAULT NULL COMMENT '国家',
  `platform` VARCHAR(50) NULL DEFAULT NULL COMMENT '平台',
  `postback_time` DATETIME NULL DEFAULT NULL COMMENT 'Postback发送时间',
  `status` VARCHAR(50) NULL DEFAULT NULL COMMENT '发送状态：Send Success/Failed',
  `affiliate_return_content` TEXT NULL COMMENT '渠道返回内容',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_publisher_id`(`publisher_id` ASC) USING BTREE,
  INDEX `idx_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_click_id`(`click_id` ASC) USING BTREE,
  INDEX `idx_status`(`status` ASC) USING BTREE,
  INDEX `idx_postback_time`(`postback_time` ASC) USING BTREE,
  CONSTRAINT `affiliate_tests_ibfk_1` FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `affiliate_tests_ibfk_2` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '下游测试记录表' ROW_FORMAT = Dynamic;
SET FOREIGN_KEY_CHECKS = 1;
-- ----------------------------
-- Table structure for clicks
-- ----------------------------
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS `clicks`;
CREATE TABLE IF NOT EXISTS `clicks`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '点击记录ID',
  `click_id` VARCHAR(255) NOT NULL COMMENT '点击ID（系统生成，唯一标识）',
  `offer_id` INT NULL DEFAULT NULL COMMENT '关联的Offer ID',
  `publisher_id` INT NULL DEFAULT NULL COMMENT '关联的渠道ID',
  `advertiser_id` INT NULL DEFAULT NULL COMMENT '关联的广告主ID',
  `click_time` DATETIME NOT NULL COMMENT '点击时间',
  `ip` VARCHAR(50) NULL DEFAULT NULL COMMENT '点击IP地址',
  `device` VARCHAR(100) NULL DEFAULT NULL COMMENT '设备信息',
  `country` VARCHAR(50) NULL DEFAULT NULL COMMENT '国家',
  `user_agent` TEXT NULL COMMENT 'User Agent',
  `referer` TEXT NULL COMMENT '来源页面',
  `conversion_id` INT NULL DEFAULT NULL COMMENT '关联的转化ID（如果已转化）',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `click_id`(`click_id` ASC) USING BTREE,
  INDEX `idx_click_id`(`click_id` ASC) USING BTREE,
  INDEX `idx_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_publisher_id`(`publisher_id` ASC) USING BTREE,
  INDEX `idx_advertiser_id`(`advertiser_id` ASC) USING BTREE,
  INDEX `idx_click_time`(`click_time` ASC) USING BTREE,
  INDEX `idx_conversion_id`(`conversion_id` ASC) USING BTREE,
  CONSTRAINT `clicks_ibfk_1` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `clicks_ibfk_2` FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `clicks_ibfk_3` FOREIGN KEY (`advertiser_id`) REFERENCES `advertisers` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '点击记录表' ROW_FORMAT = Dynamic;
SET FOREIGN_KEY_CHECKS = 1;
-- ----------------------------
-- Table structure for client_notification_configs
-- ----------------------------
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS `client_notification_configs`;
CREATE TABLE IF NOT EXISTS `client_notification_configs`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '通知配置ID',
  `client_id` INT NOT NULL COMMENT '客户ID',
  `notification_enabled` TINYINT(1) NULL DEFAULT 1 COMMENT '是否启用通知',
  `notify_on_conversion` TINYINT(1) NULL DEFAULT 1 COMMENT '转化时通知',
  `notify_on_high_value` TINYINT(1) NULL DEFAULT 0 COMMENT '高价值转化通知',
  `high_value_threshold` DECIMAL(10, 2) NULL DEFAULT NULL COMMENT '高价值阈值',
  `notify_channels` TEXT NULL COMMENT '通知渠道（JSON格式：[\"telegram\", \"email\", \"sms\"]）',
  `telegram_chat_id` VARCHAR(100) NULL DEFAULT NULL COMMENT 'Telegram Chat ID',
  `email_address` VARCHAR(255) NULL DEFAULT NULL COMMENT '邮箱地址',
  `phone_number` VARCHAR(20) NULL DEFAULT NULL COMMENT '手机号',
  `notification_frequency` VARCHAR(20) NULL DEFAULT 'realtime' COMMENT '通知频率：realtime, hourly, daily',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `client_id`(`client_id` ASC) USING BTREE,
  INDEX `idx_client_notification_config_client`(`client_id` ASC) USING BTREE,
  INDEX `idx_client_notification_config_enabled`(`notification_enabled` ASC) USING BTREE,
  CONSTRAINT `client_notification_configs_ibfk_1` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '客户通知配置表' ROW_FORMAT = Dynamic;
SET FOREIGN_KEY_CHECKS = 1;
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
  INDEX `idx_clients_key`(`key` ASC) USING BTREE,
  FULLTEXT INDEX `ft_clients_search`(`company_name`, `contact_person`) WITH PARSER `ngram`,
  CONSTRAINT `fk_clients_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '客户表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for countries
-- ----------------------------
DROP TABLE IF EXISTS `countries`;
CREATE TABLE IF NOT EXISTS `countries`  (
  `id` INT NOT NULL AUTO_INCREMENT,
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
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'ISO 3166-1国家代码表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Records of countries
-- ----------------------------
INSERT INTO `countries` VALUES (1, 'AA', 'AAA', '000', '未知区域', 'unknown', '未知区域', 'unknown', 1, '全球', '任意地区');
INSERT INTO `countries` VALUES (2, 'AF', 'AFG', '004', '阿富汗', 'Afghanistan', '阿富汗伊斯兰共和国', 'Islamic Republic of Afghanistan', 1, '亚洲', '中亚');
INSERT INTO `countries` VALUES (3, 'AX', 'ALA', '248', '奥兰群岛', 'Åland Islands', NULL, NULL, 0, '欧洲', '北欧');
INSERT INTO `countries` VALUES (4, 'AL', 'ALB', '008', '阿尔巴尼亚', 'Albania', '阿尔巴尼亚共和国', 'Republic of Albania', 1, '欧洲', '南欧');
INSERT INTO `countries` VALUES (5, 'DZ', 'DZA', '012', '阿尔及利亚', 'Algeria', '阿尔及利亚人民民主共和国', 'People\'s Democratic Republic of Algeria', 1, '非洲', '北非');
INSERT INTO `countries` VALUES (6, 'AS', 'ASM', '016', '美属萨摩亚', 'American Samoa', NULL, NULL, 0, '大洋洲', '波利尼西亚');
INSERT INTO `countries` VALUES (7, 'AD', 'AND', '020', '安道尔', 'Andorra', '安道尔公国', 'Principality of Andorra', 1, '欧洲', '南欧');
INSERT INTO `countries` VALUES (8, 'AO', 'AGO', '024', '安哥拉', 'Angola', '安哥拉共和国', 'Republic of Angola', 1, '非洲', '中非');
INSERT INTO `countries` VALUES (9, 'AI', 'AIA', '660', '安圭拉', 'Anguilla', NULL, NULL, 0, '美洲', '加勒比');
INSERT INTO `countries` VALUES (10, 'AQ', 'ATA', '010', '南极洲', 'Antarctica', NULL, NULL, 0, '南极洲', NULL);
INSERT INTO `countries` VALUES (11, 'AG', 'ATG', '028', '安提瓜和巴布达', 'Antigua and Barbuda', NULL, NULL, 1, '美洲', '加勒比');
INSERT INTO `countries` VALUES (12, 'AR', 'ARG', '032', '阿根廷', 'Argentina', '阿根廷共和国', 'Argentine Republic', 1, '美洲', '南美洲');
INSERT INTO `countries` VALUES (13, 'AM', 'ARM', '051', '亚美尼亚', 'Armenia', '亚美尼亚共和国', 'Republic of Armenia', 1, '亚洲', '西亚');
INSERT INTO `countries` VALUES (14, 'AW', 'ABW', '533', '阿鲁巴', 'Aruba', NULL, NULL, 0, '美洲', '加勒比');
INSERT INTO `countries` VALUES (15, 'AU', 'AUS', '036', '澳大利亚', 'Australia', '澳大利亚联邦', 'Commonwealth of Australia', 1, '大洋洲', '澳大利亚和新西兰');
INSERT INTO `countries` VALUES (16, 'AT', 'AUT', '040', '奥地利', 'Austria', '奥地利共和国', 'Republic of Austria', 1, '欧洲', '中欧');
INSERT INTO `countries` VALUES (17, 'AZ', 'AZE', '031', '阿塞拜疆', 'Azerbaijan', '阿塞拜疆共和国', 'Republic of Azerbaijan', 1, '亚洲', '西亚');
INSERT INTO `countries` VALUES (18, 'BS', 'BHS', '044', '巴哈马', 'Bahamas', '巴哈马联邦', 'Commonwealth of the Bahamas', 1, '美洲', '加勒比');
INSERT INTO `countries` VALUES (19, 'BH', 'BHR', '048', '巴林', 'Bahrain', '巴林王国', 'Kingdom of Bahrain', 1, '亚洲', '西亚');
INSERT INTO `countries` VALUES (20, 'BD', 'BGD', '050', '孟加拉国', 'Bangladesh', '孟加拉人民共和国', 'People\'s Republic of Bangladesh', 1, '亚洲', '南亚');
INSERT INTO `countries` VALUES (21, 'BB', 'BRB', '052', '巴巴多斯', 'Barbados', NULL, NULL, 1, '美洲', '加勒比');
INSERT INTO `countries` VALUES (22, 'BY', 'BLR', '112', '白俄罗斯', 'Belarus', '白俄罗斯共和国', 'Republic of Belarus', 1, '欧洲', '东欧');
INSERT INTO `countries` VALUES (23, 'BE', 'BEL', '056', '比利时', 'Belgium', '比利时王国', 'Kingdom of Belgium', 1, '欧洲', '西欧');
INSERT INTO `countries` VALUES (24, 'BZ', 'BLZ', '084', '伯利兹', 'Belize', NULL, NULL, 1, '美洲', '中美洲');
INSERT INTO `countries` VALUES (25, 'BJ', 'BEN', '204', '贝宁', 'Benin', '贝宁共和国', 'Republic of Benin', 1, '非洲', '西非');
INSERT INTO `countries` VALUES (26, 'BM', 'BMU', '060', '百慕大', 'Bermuda', NULL, NULL, 0, '美洲', '北大西洋');
INSERT INTO `countries` VALUES (27, 'BT', 'BTN', '064', '不丹', 'Bhutan', '不丹王国', 'Kingdom of Bhutan', 1, '亚洲', '南亚');
INSERT INTO `countries` VALUES (28, 'BO', 'BOL', '068', '玻利维亚', 'Bolivia', '多民族玻利维亚国', 'Plurinational State of Bolivia', 1, '美洲', '南美洲');
INSERT INTO `countries` VALUES (29, 'BQ', 'BES', '535', '荷兰加勒比区', 'Bonaire, Sint Eustatius and Saba', NULL, NULL, 0, '美洲', '加勒比');
INSERT INTO `countries` VALUES (30, 'BA', 'BIH', '070', '波黑', 'Bosnia and Herzegovina', '波斯尼亚和黑塞哥维那', 'Bosnia and Herzegovina', 1, '欧洲', '南欧');
INSERT INTO `countries` VALUES (31, 'BW', 'BWA', '072', '博茨瓦纳', 'Botswana', '博茨瓦纳共和国', 'Republic of Botswana', 1, '非洲', '南非');
INSERT INTO `countries` VALUES (32, 'BV', 'BVT', '074', '布韦岛', 'Bouvet Island', NULL, NULL, 0, '南极洲', NULL);
INSERT INTO `countries` VALUES (33, 'BR', 'BRA', '076', '巴西', 'Brazil', '巴西联邦共和国', 'Federative Republic of Brazil', 1, '美洲', '南美洲');
INSERT INTO `countries` VALUES (34, 'IO', 'IOT', '086', '英属印度洋领地', 'British Indian Ocean Territory', NULL, NULL, 0, '亚洲', '印度洋');
INSERT INTO `countries` VALUES (35, 'BN', 'BRN', '096', '文莱', 'Brunei Darussalam', '文莱达鲁萨兰国', 'Nation of Brunei, the Abode of Peace', 1, '亚洲', '东南亚');
INSERT INTO `countries` VALUES (36, 'BG', 'BGR', '100', '保加利亚', 'Bulgaria', '保加利亚共和国', 'Republic of Bulgaria', 1, '欧洲', '东欧');
INSERT INTO `countries` VALUES (37, 'BF', 'BFA', '854', '布基纳法索', 'Burkina Faso', NULL, NULL, 1, '非洲', '西非');
INSERT INTO `countries` VALUES (38, 'BI', 'BDI', '108', '布隆迪', 'Burundi', '布隆迪共和国', 'Republic of Burundi', 1, '非洲', '东非');
INSERT INTO `countries` VALUES (39, 'CV', 'CPV', '132', '佛得角', 'Cabo Verde', '佛得角共和国', 'Republic of Cabo Verde', 1, '非洲', '西非');
INSERT INTO `countries` VALUES (40, 'KH', 'KHM', '116', '柬埔寨', 'Cambodia', '柬埔寨王国', 'Kingdom of Cambodia', 1, '亚洲', '东南亚');
INSERT INTO `countries` VALUES (41, 'CM', 'CMR', '120', '喀麦隆', 'Cameroon', '喀麦隆共和国', 'Republic of Cameroon', 1, '非洲', '中非');
INSERT INTO `countries` VALUES (42, 'CA', 'CAN', '124', '加拿大', 'Canada', NULL, NULL, 1, '美洲', '北美洲');
INSERT INTO `countries` VALUES (43, 'KY', 'CYM', '136', '开曼群岛', 'Cayman Islands', NULL, NULL, 0, '美洲', '加勒比');
INSERT INTO `countries` VALUES (44, 'CF', 'CAF', '140', '中非', 'Central African Republic', '中非共和国', 'Central African Republic', 1, '非洲', '中非');
INSERT INTO `countries` VALUES (45, 'TD', 'TCD', '148', '乍得', 'Chad', '乍得共和国', 'Republic of Chad', 1, '非洲', '中非');
INSERT INTO `countries` VALUES (46, 'CL', 'CHL', '152', '智利', 'Chile', '智利共和国', 'Republic of Chile', 1, '美洲', '南美洲');
INSERT INTO `countries` VALUES (47, 'CN', 'CHN', '156', '中国', 'China', '中华人民共和国', 'People\'s Republic of China', 1, '亚洲', '东亚');
INSERT INTO `countries` VALUES (48, 'CX', 'CXR', '162', '圣诞岛', 'Christmas Island', NULL, NULL, 0, '亚洲', '印度洋');
INSERT INTO `countries` VALUES (49, 'CC', 'CCK', '166', '科科斯（基林）群岛', 'Cocos (Keeling) Islands', NULL, NULL, 0, '亚洲', '印度洋');
INSERT INTO `countries` VALUES (50, 'CO', 'COL', '170', '哥伦比亚', 'Colombia', '哥伦比亚共和国', 'Republic of Colombia', 1, '美洲', '南美洲');
INSERT INTO `countries` VALUES (51, 'KM', 'COM', '174', '科摩罗', 'Comoros', '科摩罗联盟', 'Union of the Comoros', 1, '非洲', '东非');
INSERT INTO `countries` VALUES (52, 'CG', 'COG', '178', '刚果（布）', 'Congo', '刚果共和国', 'Republic of the Congo', 1, '非洲', '中非');
INSERT INTO `countries` VALUES (53, 'CD', 'COD', '180', '刚果（金）', 'Congo, Democratic Republic of the', '刚果民主共和国', 'Democratic Republic of the Congo', 1, '非洲', '中非');
INSERT INTO `countries` VALUES (54, 'CK', 'COK', '184', '库克群岛', 'Cook Islands', NULL, NULL, 0, '大洋洲', '波利尼西亚');
INSERT INTO `countries` VALUES (55, 'CR', 'CRI', '188', '哥斯达黎加', 'Costa Rica', '哥斯达黎加共和国', 'Republic of Costa Rica', 1, '美洲', '中美洲');
INSERT INTO `countries` VALUES (56, 'CI', 'CIV', '384', '科特迪瓦', 'Côte d\'Ivoire', '科特迪瓦共和国', 'Republic of Côte d\'Ivoire', 1, '非洲', '西非');
INSERT INTO `countries` VALUES (57, 'HR', 'HRV', '191', '克罗地亚', 'Croatia', '克罗地亚共和国', 'Republic of Croatia', 1, '欧洲', '南欧');
INSERT INTO `countries` VALUES (58, 'CU', 'CUB', '192', '古巴', 'Cuba', '古巴共和国', 'Republic of Cuba', 1, '美洲', '加勒比');
INSERT INTO `countries` VALUES (59, 'CW', 'CUW', '531', '库拉索', 'Curaçao', NULL, NULL, 0, '美洲', '加勒比');
INSERT INTO `countries` VALUES (60, 'CY', 'CYP', '196', '塞浦路斯', 'Cyprus', '塞浦路斯共和国', 'Republic of Cyprus', 1, '亚洲', '西亚');
INSERT INTO `countries` VALUES (61, 'CZ', 'CZE', '203', '捷克', 'Czechia', '捷克共和国', 'Czech Republic', 1, '欧洲', '中欧');
INSERT INTO `countries` VALUES (62, 'DK', 'DNK', '208', '丹麦', 'Denmark', '丹麦王国', 'Kingdom of Denmark', 1, '欧洲', '北欧');
INSERT INTO `countries` VALUES (63, 'DJ', 'DJI', '262', '吉布提', 'Djibouti', '吉布提共和国', 'Republic of Djibouti', 1, '非洲', '东非');
INSERT INTO `countries` VALUES (64, 'DM', 'DMA', '212', '多米尼克', 'Dominica', '多米尼克国', 'Commonwealth of Dominica', 1, '美洲', '加勒比');
INSERT INTO `countries` VALUES (65, 'DO', 'DOM', '214', '多米尼加', 'Dominican Republic', '多米尼加共和国', 'Dominican Republic', 1, '美洲', '加勒比');
INSERT INTO `countries` VALUES (66, 'EC', 'ECU', '218', '厄瓜多尔', 'Ecuador', '厄瓜多尔共和国', 'Republic of Ecuador', 1, '美洲', '南美洲');
INSERT INTO `countries` VALUES (67, 'EG', 'EGY', '818', '埃及', 'Egypt', '阿拉伯埃及共和国', 'Arab Republic of Egypt', 1, '非洲', '北非');
INSERT INTO `countries` VALUES (68, 'SV', 'SLV', '222', '萨尔瓦多', 'El Salvador', '萨尔瓦多共和国', 'Republic of El Salvador', 1, '美洲', '中美洲');
INSERT INTO `countries` VALUES (69, 'GQ', 'GNQ', '226', '赤道几内亚', 'Equatorial Guinea', '赤道几内亚共和国', 'Republic of Equatorial Guinea', 1, '非洲', '中非');
INSERT INTO `countries` VALUES (70, 'ER', 'ERI', '232', '厄立特里亚', 'Eritrea', '厄立特里亚国', 'State of Eritrea', 1, '非洲', '东非');
INSERT INTO `countries` VALUES (71, 'EE', 'EST', '233', '爱沙尼亚', 'Estonia', '爱沙尼亚共和国', 'Republic of Estonia', 1, '欧洲', '北欧');
INSERT INTO `countries` VALUES (72, 'SZ', 'SWZ', '748', '斯威士兰', 'Eswatini', '斯威士兰王国', 'Kingdom of Eswatini', 1, '非洲', '南非');
INSERT INTO `countries` VALUES (73, 'ET', 'ETH', '231', '埃塞俄比亚', 'Ethiopia', '埃塞俄比亚联邦民主共和国', 'Federal Democratic Republic of Ethiopia', 1, '非洲', '东非');
INSERT INTO `countries` VALUES (74, 'FK', 'FLK', '238', '福克兰群岛（马尔维纳斯）', 'Falkland Islands (Malvinas)', NULL, NULL, 0, '美洲', '南美洲');
INSERT INTO `countries` VALUES (75, 'FO', 'FRO', '234', '法罗群岛', 'Faroe Islands', NULL, NULL, 0, '欧洲', '北欧');
INSERT INTO `countries` VALUES (76, 'FJ', 'FJI', '242', '斐济', 'Fiji', '斐济共和国', 'Republic of Fiji', 1, '大洋洲', '美拉尼西亚');
INSERT INTO `countries` VALUES (77, 'FI', 'FIN', '246', '芬兰', 'Finland', '芬兰共和国', 'Republic of Finland', 1, '欧洲', '北欧');
INSERT INTO `countries` VALUES (78, 'FR', 'FRA', '250', '法国', 'France', '法兰西共和国', 'French Republic', 1, '欧洲', '西欧');
INSERT INTO `countries` VALUES (79, 'GF', 'GUF', '254', '法属圭亚那', 'French Guiana', NULL, NULL, 0, '美洲', '南美洲');
INSERT INTO `countries` VALUES (80, 'PF', 'PYF', '258', '法属波利尼西亚', 'French Polynesia', NULL, NULL, 0, '大洋洲', '波利尼西亚');
INSERT INTO `countries` VALUES (81, 'TF', 'ATF', '260', '法属南部领地', 'French Southern Territories', NULL, NULL, 0, '南极洲', NULL);
INSERT INTO `countries` VALUES (82, 'GA', 'GAB', '266', '加蓬', 'Gabon', '加蓬共和国', 'Gabonese Republic', 1, '非洲', '中非');
INSERT INTO `countries` VALUES (83, 'GM', 'GMB', '270', '冈比亚', 'Gambia', '冈比亚共和国', 'Republic of the Gambia', 1, '非洲', '西非');
INSERT INTO `countries` VALUES (84, 'GE', 'GEO', '268', '格鲁吉亚', 'Georgia', NULL, NULL, 1, '亚洲', '西亚');
INSERT INTO `countries` VALUES (85, 'DE', 'DEU', '276', '德国', 'Germany', '德意志联邦共和国', 'Federal Republic of Germany', 1, '欧洲', '中欧');
INSERT INTO `countries` VALUES (86, 'GH', 'GHA', '288', '加纳', 'Ghana', '加纳共和国', 'Republic of Ghana', 1, '非洲', '西非');
INSERT INTO `countries` VALUES (87, 'GI', 'GIB', '292', '直布罗陀', 'Gibraltar', NULL, NULL, 0, '欧洲', '南欧');
INSERT INTO `countries` VALUES (88, 'GR', 'GRC', '300', '希腊', 'Greece', '希腊共和国', 'Hellenic Republic', 1, '欧洲', '南欧');
INSERT INTO `countries` VALUES (89, 'GL', 'GRL', '304', '格陵兰', 'Greenland', NULL, NULL, 0, '美洲', '北美洲');
INSERT INTO `countries` VALUES (90, 'GD', 'GRD', '308', '格林纳达', 'Grenada', NULL, NULL, 1, '美洲', '加勒比');
INSERT INTO `countries` VALUES (91, 'GP', 'GLP', '312', '瓜德罗普', 'Guadeloupe', NULL, NULL, 0, '美洲', '加勒比');
INSERT INTO `countries` VALUES (92, 'GU', 'GUM', '316', '关岛', 'Guam', NULL, NULL, 0, '大洋洲', '密克罗尼西亚');
INSERT INTO `countries` VALUES (93, 'GT', 'GTM', '320', '危地马拉', 'Guatemala', '危地马拉共和国', 'Republic of Guatemala', 1, '美洲', '中美洲');
INSERT INTO `countries` VALUES (94, 'GG', 'GGY', '831', '根西', 'Guernsey', NULL, NULL, 0, '欧洲', '北欧');
INSERT INTO `countries` VALUES (95, 'GN', 'GIN', '324', '几内亚', 'Guinea', '几内亚共和国', 'Republic of Guinea', 1, '非洲', '西非');
INSERT INTO `countries` VALUES (96, 'GW', 'GNB', '624', '几内亚比绍', 'Guinea-Bissau', '几内亚比绍共和国', 'Republic of Guinea-Bissau', 1, '非洲', '西非');
INSERT INTO `countries` VALUES (97, 'GY', 'GUY', '328', '圭亚那', 'Guyana', '圭亚那合作共和国', 'Co-operative Republic of Guyana', 1, '美洲', '南美洲');
INSERT INTO `countries` VALUES (98, 'HT', 'HTI', '332', '海地', 'Haiti', '海地共和国', 'Republic of Haiti', 1, '美洲', '加勒比');
INSERT INTO `countries` VALUES (99, 'HM', 'HMD', '334', '赫德岛和麦克唐纳群岛', 'Heard Island and McDonald Islands', NULL, NULL, 0, '南极洲', NULL);
INSERT INTO `countries` VALUES (100, 'VA', 'VAT', '336', '梵蒂冈', 'Holy See', '梵蒂冈城国', 'Vatican City State', 1, '欧洲', '南欧');
INSERT INTO `countries` VALUES (101, 'HN', 'HND', '340', '洪都拉斯', 'Honduras', '洪都拉斯共和国', 'Republic of Honduras', 1, '美洲', '中美洲');
INSERT INTO `countries` VALUES (102, 'HK', 'HKG', '344', '香港', 'Hong Kong', '中华人民共和国香港特别行政区', 'Hong Kong Special Administrative Region of China', 0, '亚洲', '东亚');
INSERT INTO `countries` VALUES (103, 'HU', 'HUN', '348', '匈牙利', 'Hungary', NULL, NULL, 1, '欧洲', '东欧');
INSERT INTO `countries` VALUES (104, 'IS', 'ISL', '352', '冰岛', 'Iceland', '冰岛共和国', 'Republic of Iceland', 1, '欧洲', '北欧');
INSERT INTO `countries` VALUES (105, 'IN', 'IND', '356', '印度', 'India', '印度共和国', 'Republic of India', 1, '亚洲', '南亚');
INSERT INTO `countries` VALUES (106, 'ID', 'IDN', '360', '印度尼西亚', 'Indonesia', '印度尼西亚共和国', 'Republic of Indonesia', 1, '亚洲', '东南亚');
INSERT INTO `countries` VALUES (107, 'IR', 'IRN', '364', '伊朗', 'Iran', '伊朗伊斯兰共和国', 'Islamic Republic of Iran', 1, '亚洲', '西亚');
INSERT INTO `countries` VALUES (108, 'IQ', 'IRQ', '368', '伊拉克', 'Iraq', '伊拉克共和国', 'Republic of Iraq', 1, '亚洲', '西亚');
INSERT INTO `countries` VALUES (109, 'IE', 'IRL', '372', '爱尔兰', 'Ireland', NULL, NULL, 1, '欧洲', '西欧');
INSERT INTO `countries` VALUES (110, 'IM', 'IMN', '833', '马恩岛', 'Isle of Man', NULL, NULL, 0, '欧洲', '北欧');
INSERT INTO `countries` VALUES (111, 'IL', 'ISR', '376', '以色列', 'Israel', '以色列国', 'State of Israel', 1, '亚洲', '西亚');
INSERT INTO `countries` VALUES (112, 'IT', 'ITA', '380', '意大利', 'Italy', '意大利共和国', 'Italian Republic', 1, '欧洲', '南欧');
INSERT INTO `countries` VALUES (113, 'JM', 'JAM', '388', '牙买加', 'Jamaica', NULL, NULL, 1, '美洲', '加勒比');
INSERT INTO `countries` VALUES (114, 'JP', 'JPN', '392', '日本', 'Japan', NULL, NULL, 1, '亚洲', '东亚');
INSERT INTO `countries` VALUES (115, 'JE', 'JEY', '832', '泽西', 'Jersey', NULL, NULL, 0, '欧洲', '北欧');
INSERT INTO `countries` VALUES (116, 'JO', 'JOR', '400', '约旦', 'Jordan', '约旦哈希姆王国', 'Hashemite Kingdom of Jordan', 1, '亚洲', '西亚');
INSERT INTO `countries` VALUES (117, 'KZ', 'KAZ', '398', '哈萨克斯坦', 'Kazakhstan', '哈萨克斯坦共和国', 'Republic of Kazakhstan', 1, '亚洲', '中亚');
INSERT INTO `countries` VALUES (118, 'KE', 'KEN', '404', '肯尼亚', 'Kenya', '肯尼亚共和国', 'Republic of Kenya', 1, '非洲', '东非');
INSERT INTO `countries` VALUES (119, 'KI', 'KIR', '296', '基里巴斯', 'Kiribati', '基里巴斯共和国', 'Republic of Kiribati', 1, '大洋洲', '密克罗尼西亚');
INSERT INTO `countries` VALUES (120, 'KP', 'PRK', '408', '朝鲜', 'Korea (Democratic People\'s Republic of)', '朝鲜民主主义人民共和国', 'Democratic People\'s Republic of Korea', 1, '亚洲', '东亚');
INSERT INTO `countries` VALUES (121, 'KR', 'KOR', '410', '韩国', 'Korea, Republic of', '大韩民国', 'Republic of Korea', 1, '亚洲', '东亚');
INSERT INTO `countries` VALUES (122, 'KW', 'KWT', '414', '科威特', 'Kuwait', '科威特国', 'State of Kuwait', 1, '亚洲', '西亚');
INSERT INTO `countries` VALUES (123, 'KG', 'KGZ', '417', '吉尔吉斯斯坦', 'Kyrgyzstan', '吉尔吉斯共和国', 'Kyrgyz Republic', 1, '亚洲', '中亚');
INSERT INTO `countries` VALUES (124, 'LA', 'LAO', '418', '老挝', 'Lao People\'s Democratic Republic', '老挝人民民主共和国', 'Lao People\'s Democratic Republic', 1, '亚洲', '东南亚');
INSERT INTO `countries` VALUES (125, 'LV', 'LVA', '428', '拉脱维亚', 'Latvia', '拉脱维亚共和国', 'Republic of Latvia', 1, '欧洲', '北欧');
INSERT INTO `countries` VALUES (126, 'LB', 'LBN', '422', '黎巴嫩', 'Lebanon', '黎巴嫩共和国', 'Republic of Lebanon', 1, '亚洲', '西亚');
INSERT INTO `countries` VALUES (127, 'LS', 'LSO', '426', '莱索托', 'Lesotho', '莱索托王国', 'Kingdom of Lesotho', 1, '非洲', '南非');
INSERT INTO `countries` VALUES (128, 'LR', 'LBR', '430', '利比里亚', 'Liberia', '利比里亚共和国', 'Republic of Liberia', 1, '非洲', '西非');
INSERT INTO `countries` VALUES (129, 'LY', 'LBY', '434', '利比亚', 'Libya', '利比亚国', 'State of Libya', 1, '非洲', '北非');
INSERT INTO `countries` VALUES (130, 'LI', 'LIE', '438', '列支敦士登', 'Liechtenstein', '列支敦士登公国', 'Principality of Liechtenstein', 1, '欧洲', '中欧');
INSERT INTO `countries` VALUES (131, 'LT', 'LTU', '440', '立陶宛', 'Lithuania', '立陶宛共和国', 'Republic of Lithuania', 1, '欧洲', '北欧');
INSERT INTO `countries` VALUES (132, 'LU', 'LUX', '442', '卢森堡', 'Luxembourg', '卢森堡大公国', 'Grand Duchy of Luxembourg', 1, '欧洲', '西欧');
INSERT INTO `countries` VALUES (133, 'MO', 'MAC', '446', '澳门', 'Macao', '中华人民共和国澳门特别行政区', 'Macao Special Administrative Region of China', 0, '亚洲', '东亚');
INSERT INTO `countries` VALUES (134, 'MG', 'MDG', '450', '马达加斯加', 'Madagascar', '马达加斯加共和国', 'Republic of Madagascar', 1, '非洲', '东非');
INSERT INTO `countries` VALUES (135, 'MW', 'MWI', '454', '马拉维', 'Malawi', '马拉维共和国', 'Republic of Malawi', 1, '非洲', '东非');
INSERT INTO `countries` VALUES (136, 'MY', 'MYS', '458', '马来西亚', 'Malaysia', NULL, NULL, 1, '亚洲', '东南亚');
INSERT INTO `countries` VALUES (137, 'MV', 'MDV', '462', '马尔代夫', 'Maldives', '马尔代夫共和国', 'Republic of Maldives', 1, '亚洲', '南亚');
INSERT INTO `countries` VALUES (138, 'ML', 'MLI', '466', '马里', 'Mali', '马里共和国', 'Republic of Mali', 1, '非洲', '西非');
INSERT INTO `countries` VALUES (139, 'MT', 'MLT', '470', '马耳他', 'Malta', '马耳他共和国', 'Republic of Malta', 1, '欧洲', '南欧');
INSERT INTO `countries` VALUES (140, 'MH', 'MHL', '584', '马绍尔群岛', 'Marshall Islands', '马绍尔群岛共和国', 'Republic of the Marshall Islands', 1, '大洋洲', '密克罗尼西亚');
INSERT INTO `countries` VALUES (141, 'MQ', 'MTQ', '474', '马提尼克', 'Martinique', NULL, NULL, 0, '美洲', '加勒比');
INSERT INTO `countries` VALUES (142, 'MR', 'MRT', '478', '毛里塔尼亚', 'Mauritania', '毛里塔尼亚伊斯兰共和国', 'Islamic Republic of Mauritania', 1, '非洲', '西非');
INSERT INTO `countries` VALUES (143, 'MU', 'MUS', '480', '毛里求斯', 'Mauritius', '毛里求斯共和国', 'Republic of Mauritius', 1, '非洲', '东非');
INSERT INTO `countries` VALUES (144, 'YT', 'MYT', '175', '马约特', 'Mayotte', NULL, NULL, 0, '非洲', '东非');
INSERT INTO `countries` VALUES (145, 'MX', 'MEX', '484', '墨西哥', 'Mexico', '墨西哥合众国', 'United Mexican States', 1, '美洲', '北美洲');
INSERT INTO `countries` VALUES (146, 'FM', 'FSM', '583', '密克罗尼西亚联邦', 'Micronesia (Federated States of)', '密克罗尼西亚联邦', 'Federated States of Micronesia', 1, '大洋洲', '密克罗尼西亚');
INSERT INTO `countries` VALUES (147, 'MD', 'MDA', '498', '摩尔多瓦', 'Moldova', '摩尔多瓦共和国', 'Republic of Moldova', 1, '欧洲', '东欧');
INSERT INTO `countries` VALUES (148, 'MC', 'MCO', '492', '摩纳哥', 'Monaco', '摩纳哥公国', 'Principality of Monaco', 1, '欧洲', '西欧');
INSERT INTO `countries` VALUES (149, 'MN', 'MNG', '496', '蒙古', 'Mongolia', '蒙古国', 'Mongolia', 1, '亚洲', '东亚');
INSERT INTO `countries` VALUES (150, 'ME', 'MNE', '499', '黑山', 'Montenegro', '黑山', 'Montenegro', 1, '欧洲', '南欧');
INSERT INTO `countries` VALUES (151, 'MS', 'MSR', '500', '蒙特塞拉特', 'Montserrat', NULL, NULL, 0, '美洲', '加勒比');
INSERT INTO `countries` VALUES (152, 'MA', 'MAR', '504', '摩洛哥', 'Morocco', '摩洛哥王国', 'Kingdom of Morocco', 1, '非洲', '北非');
INSERT INTO `countries` VALUES (153, 'MZ', 'MOZ', '508', '莫桑比克', 'Mozambique', '莫桑比克共和国', 'Republic of Mozambique', 1, '非洲', '东非');
INSERT INTO `countries` VALUES (154, 'MM', 'MMR', '104', '缅甸', 'Myanmar', '缅甸联邦共和国', 'Republic of the Union of Myanmar', 1, '亚洲', '东南亚');
INSERT INTO `countries` VALUES (155, 'NA', 'NAM', '516', '纳米比亚', 'Namibia', '纳米比亚共和国', 'Republic of Namibia', 1, '非洲', '南非');
INSERT INTO `countries` VALUES (156, 'NR', 'NRU', '520', '瑙鲁', 'Nauru', '瑙鲁共和国', 'Republic of Nauru', 1, '大洋洲', '密克罗尼西亚');
INSERT INTO `countries` VALUES (157, 'NP', 'NPL', '524', '尼泊尔', 'Nepal', '尼泊尔联邦民主共和国', 'Federal Democratic Republic of Nepal', 1, '亚洲', '南亚');
INSERT INTO `countries` VALUES (158, 'NL', 'NLD', '528', '荷兰', 'Netherlands', '荷兰王国', 'Kingdom of the Netherlands', 1, '欧洲', '西欧');
INSERT INTO `countries` VALUES (159, 'NC', 'NCL', '540', '新喀里多尼亚', 'New Caledonia', NULL, NULL, 0, '大洋洲', '美拉尼西亚');
INSERT INTO `countries` VALUES (160, 'NZ', 'NZL', '554', '新西兰', 'New Zealand', NULL, NULL, 1, '大洋洲', '澳大利亚和新西兰');
INSERT INTO `countries` VALUES (161, 'NI', 'NIC', '558', '尼加拉瓜', 'Nicaragua', '尼加拉瓜共和国', 'Republic of Nicaragua', 1, '美洲', '中美洲');
INSERT INTO `countries` VALUES (162, 'NE', 'NER', '562', '尼日尔', 'Niger', '尼日尔共和国', 'Republic of Niger', 1, '非洲', '西非');
INSERT INTO `countries` VALUES (163, 'NG', 'NGA', '566', '尼日利亚', 'Nigeria', '尼日利亚联邦共和国', 'Federal Republic of Nigeria', 1, '非洲', '西非');
INSERT INTO `countries` VALUES (164, 'NU', 'NIU', '570', '纽埃', 'Niue', NULL, NULL, 0, '大洋洲', '波利尼西亚');
INSERT INTO `countries` VALUES (165, 'NF', 'NFK', '574', '诺福克岛', 'Norfolk Island', NULL, NULL, 0, '大洋洲', '澳大利亚和新西兰');
INSERT INTO `countries` VALUES (166, 'MK', 'MKD', '807', '北马其顿', 'North Macedonia', '北马其顿共和国', 'Republic of North Macedonia', 1, '欧洲', '南欧');
INSERT INTO `countries` VALUES (167, 'MP', 'MNP', '580', '北马里亚纳群岛', 'Northern Mariana Islands', NULL, NULL, 0, '大洋洲', '密克罗尼西亚');
INSERT INTO `countries` VALUES (168, 'NO', 'NOR', '578', '挪威', 'Norway', '挪威王国', 'Kingdom of Norway', 1, '欧洲', '北欧');
INSERT INTO `countries` VALUES (169, 'OM', 'OMN', '512', '阿曼', 'Oman', '阿曼苏丹国', 'Sultanate of Oman', 1, '亚洲', '西亚');
INSERT INTO `countries` VALUES (170, 'PK', 'PAK', '586', '巴基斯坦', 'Pakistan', '巴基斯坦伊斯兰共和国', 'Islamic Republic of Pakistan', 1, '亚洲', '南亚');
INSERT INTO `countries` VALUES (171, 'PW', 'PLW', '585', '帕劳', 'Palau', '帕劳共和国', 'Republic of Palau', 1, '大洋洲', '密克罗尼西亚');
INSERT INTO `countries` VALUES (172, 'PS', 'PSE', '275', '巴勒斯坦', 'Palestine, State of', '巴勒斯坦国', 'State of Palestine', 1, '亚洲', '西亚');
INSERT INTO `countries` VALUES (173, 'PA', 'PAN', '591', '巴拿马', 'Panama', '巴拿马共和国', 'Republic of Panama', 1, '美洲', '中美洲');
INSERT INTO `countries` VALUES (174, 'PG', 'PNG', '598', '巴布亚新几内亚', 'Papua New Guinea', '巴布亚新几内亚独立国', 'Independent State of Papua New Guinea', 1, '大洋洲', '美拉尼西亚');
INSERT INTO `countries` VALUES (175, 'PY', 'PRY', '600', '巴拉圭', 'Paraguay', '巴拉圭共和国', 'Republic of Paraguay', 1, '美洲', '南美洲');
INSERT INTO `countries` VALUES (176, 'PE', 'PER', '604', '秘鲁', 'Peru', '秘鲁共和国', 'Republic of Peru', 1, '美洲', '南美洲');
INSERT INTO `countries` VALUES (177, 'PH', 'PHL', '608', '菲律宾', 'Philippines', '菲律宾共和国', 'Republic of the Philippines', 1, '亚洲', '东南亚');
INSERT INTO `countries` VALUES (178, 'PN', 'PCN', '612', '皮特凯恩群岛', 'Pitcairn', NULL, NULL, 0, '大洋洲', '波利尼西亚');
INSERT INTO `countries` VALUES (179, 'PL', 'POL', '616', '波兰', 'Poland', '波兰共和国', 'Republic of Poland', 1, '欧洲', '东欧');
INSERT INTO `countries` VALUES (180, 'PT', 'PRT', '620', '葡萄牙', 'Portugal', '葡萄牙共和国', 'Portuguese Republic', 1, '欧洲', '南欧');
INSERT INTO `countries` VALUES (181, 'PR', 'PRI', '630', '波多黎各', 'Puerto Rico', NULL, NULL, 0, '美洲', '加勒比');
INSERT INTO `countries` VALUES (182, 'QA', 'QAT', '634', '卡塔尔', 'Qatar', '卡塔尔国', 'State of Qatar', 1, '亚洲', '西亚');
INSERT INTO `countries` VALUES (183, 'RE', 'REU', '638', '留尼汪', 'Réunion', NULL, NULL, 0, '非洲', '东非');
INSERT INTO `countries` VALUES (184, 'RO', 'ROU', '642', '罗马尼亚', 'Romania', NULL, NULL, 1, '欧洲', '东欧');
INSERT INTO `countries` VALUES (185, 'RU', 'RUS', '643', '俄罗斯', 'Russian Federation', '俄罗斯联邦', 'Russian Federation', 1, '欧洲', '东欧');
INSERT INTO `countries` VALUES (186, 'RW', 'RWA', '646', '卢旺达', 'Rwanda', '卢旺达共和国', 'Republic of Rwanda', 1, '非洲', '东非');
INSERT INTO `countries` VALUES (187, 'BL', 'BLM', '652', '圣巴泰勒米', 'Saint Barthélemy', NULL, NULL, 0, '美洲', '加勒比');
INSERT INTO `countries` VALUES (188, 'SH', 'SHN', '654', '圣赫勒拿', 'Saint Helena, Ascension and Tristan da Cunha', NULL, NULL, 0, '非洲', '西非');
INSERT INTO `countries` VALUES (189, 'KN', 'KNA', '659', '圣基茨和尼维斯', 'Saint Kitts and Nevis', '圣基茨和尼维斯联邦', 'Federation of Saint Kitts and Nevis', 1, '美洲', '加勒比');
INSERT INTO `countries` VALUES (190, 'LC', 'LCA', '662', '圣卢西亚', 'Saint Lucia', NULL, NULL, 1, '美洲', '加勒比');
INSERT INTO `countries` VALUES (191, 'MF', 'MAF', '663', '法属圣马丁', 'Saint Martin (French part)', NULL, NULL, 0, '美洲', '加勒比');
INSERT INTO `countries` VALUES (192, 'PM', 'SPM', '666', '圣皮埃尔和密克隆', 'Saint Pierre and Miquelon', NULL, NULL, 0, '美洲', '北美洲');
INSERT INTO `countries` VALUES (193, 'VC', 'VCT', '670', '圣文森特和格林纳丁斯', 'Saint Vincent and the Grenadines', NULL, NULL, 1, '美洲', '加勒比');
INSERT INTO `countries` VALUES (194, 'WS', 'WSM', '882', '萨摩亚', 'Samoa', '萨摩亚独立国', 'Independent State of Samoa', 1, '大洋洲', '波利尼西亚');
INSERT INTO `countries` VALUES (195, 'SM', 'SMR', '674', '圣马力诺', 'San Marino', '圣马力诺共和国', 'Republic of San Marino', 1, '欧洲', '南欧');
INSERT INTO `countries` VALUES (196, 'ST', 'STP', '678', '圣多美和普林西比', 'Sao Tome and Principe', '圣多美和普林西比民主共和国', 'Democratic Republic of Sao Tome and Principe', 1, '非洲', '中非');
INSERT INTO `countries` VALUES (197, 'SA', 'SAU', '682', '沙特阿拉伯', 'Saudi Arabia', '沙特阿拉伯王国', 'Kingdom of Saudi Arabia', 1, '亚洲', '西亚');
INSERT INTO `countries` VALUES (198, 'SN', 'SEN', '686', '塞内加尔', 'Senegal', '塞内加尔共和国', 'Republic of Senegal', 1, '非洲', '西非');
INSERT INTO `countries` VALUES (199, 'RS', 'SRB', '688', '塞尔维亚', 'Serbia', '塞尔维亚共和国', 'Republic of Serbia', 1, '欧洲', '南欧');
INSERT INTO `countries` VALUES (200, 'SC', 'SYC', '690', '塞舌尔', 'Seychelles', '塞舌尔共和国', 'Republic of Seychelles', 1, '非洲', '东非');
INSERT INTO `countries` VALUES (201, 'SL', 'SLE', '694', '塞拉利昂', 'Sierra Leone', '塞拉利昂共和国', 'Republic of Sierra Leone', 1, '非洲', '西非');
INSERT INTO `countries` VALUES (202, 'SG', 'SGP', '702', '新加坡', 'Singapore', '新加坡共和国', 'Republic of Singapore', 1, '亚洲', '东南亚');
INSERT INTO `countries` VALUES (203, 'SX', 'SXM', '534', '荷属圣马丁', 'Sint Maarten (Dutch part)', NULL, NULL, 0, '美洲', '加勒比');
INSERT INTO `countries` VALUES (204, 'SK', 'SVK', '703', '斯洛伐克', 'Slovakia', '斯洛伐克共和国', 'Slovak Republic', 1, '欧洲', '中欧');
INSERT INTO `countries` VALUES (205, 'SI', 'SVN', '705', '斯洛文尼亚', 'Slovenia', '斯洛文尼亚共和国', 'Republic of Slovenia', 1, '欧洲', '南欧');
INSERT INTO `countries` VALUES (206, 'SB', 'SLB', '090', '所罗门群岛', 'Solomon Islands', NULL, NULL, 1, '大洋洲', '美拉尼西亚');
INSERT INTO `countries` VALUES (207, 'SO', 'SOM', '706', '索马里', 'Somalia', '索马里联邦共和国', 'Federal Republic of Somalia', 1, '非洲', '东非');
INSERT INTO `countries` VALUES (208, 'ZA', 'ZAF', '710', '南非', 'South Africa', '南非共和国', 'Republic of South Africa', 1, '非洲', '南非');
INSERT INTO `countries` VALUES (209, 'GS', 'SGS', '239', '南乔治亚和南桑威奇群岛', 'South Georgia and the South Sandwich Islands', NULL, NULL, 0, '南极洲', NULL);
INSERT INTO `countries` VALUES (210, 'SS', 'SSD', '728', '南苏丹', 'South Sudan', '南苏丹共和国', 'Republic of South Sudan', 1, '非洲', '东非');
INSERT INTO `countries` VALUES (211, 'ES', 'ESP', '724', '西班牙', 'Spain', '西班牙王国', 'Kingdom of Spain', 1, '欧洲', '南欧');
INSERT INTO `countries` VALUES (212, 'LK', 'LKA', '144', '斯里兰卡', 'Sri Lanka', '斯里兰卡民主社会主义共和国', 'Democratic Socialist Republic of Sri Lanka', 1, '亚洲', '南亚');
INSERT INTO `countries` VALUES (213, 'SD', 'SDN', '729', '苏丹', 'Sudan', '苏丹共和国', 'Republic of the Sudan', 1, '非洲', '北非');
INSERT INTO `countries` VALUES (214, 'SR', 'SUR', '740', '苏里南', 'Suriname', '苏里南共和国', 'Republic of Suriname', 1, '美洲', '南美洲');
INSERT INTO `countries` VALUES (215, 'SJ', 'SJM', '744', '斯瓦尔巴和扬马延', 'Svalbard and Jan Mayen', NULL, NULL, 0, '欧洲', '北欧');
INSERT INTO `countries` VALUES (216, 'SE', 'SWE', '752', '瑞典', 'Sweden', '瑞典王国', 'Kingdom of Sweden', 1, '欧洲', '北欧');
INSERT INTO `countries` VALUES (217, 'CH', 'CHE', '756', '瑞士', 'Switzerland', '瑞士联邦', 'Swiss Confederation', 1, '欧洲', '中欧');
INSERT INTO `countries` VALUES (218, 'SY', 'SYR', '760', '叙利亚', 'Syrian Arab Republic', '阿拉伯叙利亚共和国', 'Syrian Arab Republic', 1, '亚洲', '西亚');
INSERT INTO `countries` VALUES (219, 'TW', 'TWN', '158', '台湾', 'Taiwan, Province of China', '中国台湾省', 'Taiwan, Province of China', 0, '亚洲', '东亚');
INSERT INTO `countries` VALUES (220, 'TJ', 'TJK', '762', '塔吉克斯坦', 'Tajikistan', '塔吉克斯坦共和国', 'Republic of Tajikistan', 1, '亚洲', '中亚');
INSERT INTO `countries` VALUES (221, 'TZ', 'TZA', '834', '坦桑尼亚', 'Tanzania', '坦桑尼亚联合共和国', 'United Republic of Tanzania', 1, '非洲', '东非');
INSERT INTO `countries` VALUES (222, 'TH', 'THA', '764', '泰国', 'Thailand', '泰王国', 'Kingdom of Thailand', 1, '亚洲', '东南亚');
INSERT INTO `countries` VALUES (223, 'TL', 'TLS', '626', '东帝汶', 'Timor-Leste', '东帝汶民主共和国', 'Democratic Republic of Timor-Leste', 1, '亚洲', '东南亚');
INSERT INTO `countries` VALUES (224, 'TG', 'TGO', '768', '多哥', 'Togo', '多哥共和国', 'Togolese Republic', 1, '非洲', '西非');
INSERT INTO `countries` VALUES (225, 'TK', 'TKL', '772', '托克劳', 'Tokelau', NULL, NULL, 0, '大洋洲', '波利尼西亚');
INSERT INTO `countries` VALUES (226, 'TO', 'TON', '776', '汤加', 'Tonga', '汤加王国', 'Kingdom of Tonga', 1, '大洋洲', '波利尼西亚');
INSERT INTO `countries` VALUES (227, 'TT', 'TTO', '780', '特立尼达和多巴哥', 'Trinidad and Tobago', '特立尼达和多巴哥共和国', 'Republic of Trinidad and Tobago', 1, '美洲', '加勒比');
INSERT INTO `countries` VALUES (228, 'TN', 'TUN', '788', '突尼斯', 'Tunisia', '突尼斯共和国', 'Republic of Tunisia', 1, '非洲', '北非');
INSERT INTO `countries` VALUES (229, 'TR', 'TUR', '792', '土耳其', 'Turkey', '土耳其共和国', 'Republic of Turkey', 1, '亚洲', '西亚');
INSERT INTO `countries` VALUES (230, 'TM', 'TKM', '795', '土库曼斯坦', 'Turkmenistan', '土库曼斯坦', 'Turkmenistan', 1, '亚洲', '中亚');
INSERT INTO `countries` VALUES (231, 'TC', 'TCA', '796', '特克斯和凯科斯群岛', 'Turks and Caicos Islands', NULL, NULL, 0, '美洲', '加勒比');
INSERT INTO `countries` VALUES (232, 'TV', 'TUV', '798', '图瓦卢', 'Tuvalu', NULL, NULL, 1, '大洋洲', '波利尼西亚');
INSERT INTO `countries` VALUES (233, 'UG', 'UGA', '800', '乌干达', 'Uganda', '乌干达共和国', 'Republic of Uganda', 1, '非洲', '东非');
INSERT INTO `countries` VALUES (234, 'UA', 'UKR', '804', '乌克兰', 'Ukraine', NULL, NULL, 1, '欧洲', '东欧');
INSERT INTO `countries` VALUES (235, 'AE', 'ARE', '784', '阿联酋', 'United Arab Emirates', '阿拉伯联合酋长国', 'United Arab Emirates', 1, '亚洲', '西亚');
INSERT INTO `countries` VALUES (236, 'GB', 'GBR', '826', '英国', 'United Kingdom', '大不列颠及北爱尔兰联合王国', 'United Kingdom of Great Britain and Northern Ireland', 1, '欧洲', '西欧');
INSERT INTO `countries` VALUES (237, 'US', 'USA', '840', '美国', 'United States', '美利坚合众国', 'United States of America', 1, '美洲', '北美洲');
INSERT INTO `countries` VALUES (238, 'UM', 'UMI', '581', '美国本土外小岛屿', 'United States Minor Outlying Islands', NULL, NULL, 0, '大洋洲', '密克罗尼西亚');
INSERT INTO `countries` VALUES (239, 'UY', 'URY', '858', '乌拉圭', 'Uruguay', '乌拉圭东岸共和国', 'Oriental Republic of Uruguay', 1, '美洲', '南美洲');
INSERT INTO `countries` VALUES (240, 'UZ', 'UZB', '860', '乌兹别克斯坦', 'Uzbekistan', '乌兹别克斯坦共和国', 'Republic of Uzbekistan', 1, '亚洲', '中亚');
INSERT INTO `countries` VALUES (241, 'VU', 'VUT', '548', '瓦努阿图', 'Vanuatu', '瓦努阿图共和国', 'Republic of Vanuatu', 1, '大洋洲', '美拉尼西亚');
INSERT INTO `countries` VALUES (242, 'VE', 'VEN', '862', '委内瑞拉', 'Venezuela', '委内瑞拉玻利瓦尔共和国', 'Bolivarian Republic of Venezuela', 1, '美洲', '南美洲');
INSERT INTO `countries` VALUES (243, 'VN', 'VNM', '704', '越南', 'Viet Nam', '越南社会主义共和国', 'Socialist Republic of Viet Nam', 1, '亚洲', '东南亚');
INSERT INTO `countries` VALUES (244, 'VG', 'VGB', '092', '英属维尔京群岛', 'Virgin Islands (British)', NULL, NULL, 0, '美洲', '加勒比');
INSERT INTO `countries` VALUES (245, 'VI', 'VIR', '850', '美属维尔京群岛', 'Virgin Islands (U.S.)', NULL, NULL, 0, '美洲', '加勒比');
INSERT INTO `countries` VALUES (246, 'WF', 'WLF', '876', '瓦利斯和富图纳', 'Wallis and Futuna', NULL, NULL, 0, '大洋洲', '波利尼西亚');
INSERT INTO `countries` VALUES (247, 'EH', 'ESH', '732', '西撒哈拉', 'Western Sahara', NULL, NULL, 0, '非洲', '北非');
INSERT INTO `countries` VALUES (248, 'YE', 'YEM', '887', '也门', 'Yemen', '也门共和国', 'Republic of Yemen', 1, '亚洲', '西亚');
INSERT INTO `countries` VALUES (249, 'ZM', 'ZMB', '894', '赞比亚', 'Zambia', '赞比亚共和国', 'Republic of Zambia', 1, '非洲', '东非');
INSERT INTO `countries` VALUES (250, 'ZW', 'ZWE', '716', '津巴布韦', 'Zimbabwe', '津巴布韦共和国', 'Republic of Zimbabwe', 1, '非洲', '东非');
INSERT INTO `countries` VALUES (251, 'ZZ', 'ZZZ', '111', '全部区域', 'All Country', '全部区域', 'All Country', 1, '全球', '全部地区');

-- ----------------------------
-- Table structure for offer_caps
-- ----------------------------
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS `offer_caps`;
CREATE TABLE IF NOT EXISTS `offer_caps`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Cap配置ID',
  `cap_type` VARCHAR(50) NOT NULL COMMENT 'Cap类型：advertiser_offer/offer',
  `advertiser_id` INT NULL DEFAULT NULL COMMENT '广告主ID（如果是advertiser_offer类型）',
  `offer_id` INT NOT NULL COMMENT 'Offer ID',
  `publisher_id` INT NULL DEFAULT NULL COMMENT '渠道ID（如果为空，表示所有渠道）',
  `daily_cap` INT NULL DEFAULT NULL COMMENT '每日Cap',
  `total_cap` INT NULL DEFAULT NULL COMMENT '总Cap',
  `current_daily_count` INT NULL DEFAULT 0 COMMENT '当前每日计数',
  `current_total_count` INT NULL DEFAULT 0 COMMENT '当前总计数',
  `cap_start_date` DATETIME NULL DEFAULT NULL COMMENT 'Cap开始日期（用于Total Cap）',
  `is_active` TINYINT(1) NULL DEFAULT 1 COMMENT '是否激活',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_cap_type`(`cap_type` ASC) USING BTREE,
  INDEX `idx_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_advertiser_id`(`advertiser_id` ASC) USING BTREE,
  INDEX `idx_publisher_id`(`publisher_id` ASC) USING BTREE,
  INDEX `idx_is_active`(`is_active` ASC) USING BTREE,
  CONSTRAINT `offer_caps_ibfk_1` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `offer_caps_ibfk_2` FOREIGN KEY (`advertiser_id`) REFERENCES `advertisers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `offer_caps_ibfk_3` FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'Cap配置表' ROW_FORMAT = Dynamic;
SET FOREIGN_KEY_CHECKS = 1;
-- ----------------------------
-- Table structure for offer_discounts
-- ----------------------------
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS `offer_discounts`;
CREATE TABLE IF NOT EXISTS `offer_discounts`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '扣量配置ID',
  `discount_type` VARCHAR(50) NOT NULL COMMENT '扣量类型：offer/channel',
  `offer_id` INT NULL DEFAULT NULL COMMENT 'Offer ID（如果是offer类型）',
  `publisher_id` INT NOT NULL COMMENT '渠道ID',
  `discount_ratio` DECIMAL(5, 2) NOT NULL COMMENT '扣量比例（0-100）',
  `is_active` TINYINT(1) NULL DEFAULT 1 COMMENT '是否激活',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_discount_type`(`discount_type` ASC) USING BTREE,
  INDEX `idx_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_publisher_id`(`publisher_id` ASC) USING BTREE,
  INDEX `idx_is_active`(`is_active` ASC) USING BTREE,
  CONSTRAINT `offer_discounts_ibfk_1` FOREIGN KEY (`offer_id`) REFERENCES `offers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `offer_discounts_ibfk_2` FOREIGN KEY (`publisher_id`) REFERENCES `publishers` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '扣量配置表' ROW_FORMAT = Dynamic;
SET FOREIGN_KEY_CHECKS = 1;
-- ----------------------------
-- Table structure for offer_publisher_assignments
-- ----------------------------
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS `offer_publisher_assignments`;
CREATE TABLE IF NOT EXISTS `offer_publisher_assignments`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '分配ID',
  `offer_id` INT NOT NULL COMMENT 'Offer ID',
  `publisher_id` INT NOT NULL COMMENT '渠道ID',
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
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'Offer-渠道分配表' ROW_FORMAT = Dynamic;
SET FOREIGN_KEY_CHECKS = 1;
-- ----------------------------
-- Table structure for offers
-- ----------------------------
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS `offers`;
CREATE TABLE IF NOT EXISTS `offers`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Offer ID（主键）',
  `offer_id` VARCHAR(50) NOT NULL COMMENT 'Offer ID（系统生成的唯一标识）',
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
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_offer_id`(`offer_id` ASC) USING BTREE,
  INDEX `idx_advertiser_id`(`advertiser_id` ASC) USING BTREE,
  INDEX `idx_status`(`status` ASC) USING BTREE,
  INDEX `idx_is_active`(`is_active` ASC) USING BTREE,
  INDEX `idx_country`(`country` ASC) USING BTREE,
  CONSTRAINT `offers_ibfk_1` FOREIGN KEY (`advertiser_id`) REFERENCES `advertisers` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'Offer表（单子表）' ROW_FORMAT = Dynamic;
SET FOREIGN_KEY_CHECKS = 1;
-- ----------------------------
-- Table structure for postback_conversions
-- ----------------------------
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS `postback_conversions`;
CREATE TABLE IF NOT EXISTS `postback_conversions`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '转化记录ID',
  `platform` VARCHAR(50) NOT NULL COMMENT '平台名称：macan, addermobi等',
  `conversion_id` VARCHAR(255) NOT NULL COMMENT '转化ID（各平台唯一标识，如Macan的clk_id）',
  `event_name` VARCHAR(100) NULL DEFAULT NULL COMMENT '事件名称（如purchase, install等）',
  `event_value` FLOAT NULL DEFAULT NULL COMMENT '事件价值（购买价格等）',
  `payout` FLOAT NULL DEFAULT NULL COMMENT '支付金额（确认的广告单元价格）',
  `devad_id` VARCHAR(255) NULL DEFAULT NULL COMMENT '设备广告ID（IDFA或GAID）',
  `os` VARCHAR(20) NULL DEFAULT NULL COMMENT '操作系统（IOS或Android）',
  `carrier` VARCHAR(50) NULL DEFAULT NULL COMMENT '用户运营商',
  `ip` VARCHAR(50) NULL DEFAULT NULL COMMENT '点击IP地址',
  `gid` VARCHAR(100) NULL DEFAULT NULL COMMENT '渠道ID（Channel ID）',
  `product_id` INT NULL DEFAULT NULL COMMENT '关联的产品ID（可选，用于关联产品）',
  `client_id` INT NULL DEFAULT NULL COMMENT '关联的客户ID（可选，用于关联客户）',
  `raw_data` TEXT NULL COMMENT '原始回调数据（JSON格式，保存完整回调数据以便后续分析）',
  `created_at` DATETIME NOT NULL COMMENT '创建时间（记录回调接收时间）',
  `click_id` VARCHAR(255) NULL DEFAULT NULL COMMENT '关联的Click ID',
  `click_time` DATETIME NULL DEFAULT NULL COMMENT '点击时间',
  `conversion_status` VARCHAR(20) NULL DEFAULT 'Pending' COMMENT '转化状态：Approved/Pending',
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
  CONSTRAINT `postback_conversions_ibfk_1` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `postback_conversions_ibfk_2` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'Postback转化事件表，统一存储所有平台的postback回调数据' ROW_FORMAT = DYNAMIC;
SET FOREIGN_KEY_CHECKS = 1;
-- ----------------------------
-- Table structure for postback_forward_logs
-- ----------------------------
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS `postback_forward_logs`;
CREATE TABLE IF NOT EXISTS `postback_forward_logs`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '转发日志ID',
  `conversion_id` INT NOT NULL COMMENT '关联的转化记录ID',
  `product_id` INT NULL DEFAULT NULL COMMENT '产品ID',
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
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = DYNAMIC;
SET FOREIGN_KEY_CHECKS = 1;
-- ----------------------------
-- Table structure for postback_notifications
-- ----------------------------
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS `postback_notifications`;
CREATE TABLE IF NOT EXISTS `postback_notifications`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '通知记录ID',
  `conversion_id` INT NOT NULL COMMENT '转化记录ID',
  `client_id` INT NULL DEFAULT NULL COMMENT '客户ID',
  `product_id` INT NULL DEFAULT NULL COMMENT '产品ID',
  `notification_type` VARCHAR(50) NULL DEFAULT NULL COMMENT '通知类型：conversion, high_value, error',
  `notification_channel` VARCHAR(50) NOT NULL COMMENT '通知渠道：telegram, email, sms',
  `notification_status` VARCHAR(20) NULL DEFAULT 'pending' COMMENT '通知状态：sent, failed, pending',
  `notification_message` TEXT NULL COMMENT '通知消息内容',
  `error_message` TEXT NULL COMMENT '错误信息（如果失败）',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_postback_notification_conversion`(`conversion_id` ASC) USING BTREE,
  INDEX `idx_postback_notification_client`(`client_id` ASC) USING BTREE,
  INDEX `idx_postback_notification_product`(`product_id` ASC) USING BTREE,
  INDEX `idx_postback_notification_status`(`notification_status` ASC) USING BTREE,
  INDEX `idx_postback_notification_created_at`(`created_at` ASC) USING BTREE,
  CONSTRAINT `postback_notifications_ibfk_1` FOREIGN KEY (`conversion_id`) REFERENCES `postback_conversions` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `postback_notifications_ibfk_2` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `postback_notifications_ibfk_3` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'Postback通知记录表' ROW_FORMAT = DYNAMIC;
SET FOREIGN_KEY_CHECKS = 1;
-- ----------------------------
-- Table structure for product_assignments
-- ----------------------------
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS `product_assignments`;
CREATE TABLE IF NOT EXISTS `product_assignments`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '分配记录ID',
  `product_id` INT NOT NULL COMMENT '产品ID',
  `client_id` INT NOT NULL COMMENT '客户ID',
  `start_date` date NOT NULL COMMENT '分配开始日期',
  `end_date` date NULL DEFAULT NULL COMMENT '分配结束日期（NULL表示当前有效）',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_product_assignments_product`(`product_id` ASC) USING BTREE,
  INDEX `idx_product_assignments_client`(`client_id` ASC) USING BTREE,
  INDEX `idx_product_assignments_date`(`product_id` ASC, `start_date` ASC, `end_date` ASC) USING BTREE,
  INDEX `idx_product_assignments_active`(`product_id` ASC, `end_date` ASC) USING BTREE,
  CONSTRAINT `fk_product_assignments_client` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `fk_product_assignments_product` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '产品分配历史表' ROW_FORMAT = DYNAMIC;
SET FOREIGN_KEY_CHECKS = 1;
-- ----------------------------
-- Table structure for product_notification_configs
-- ----------------------------
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS `product_notification_configs`;
CREATE TABLE IF NOT EXISTS `product_notification_configs`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '通知配置ID',
  `product_id` INT NOT NULL COMMENT '产品ID',
  `notification_enabled` TINYINT(1) NULL DEFAULT 1 COMMENT '是否启用通知',
  `notify_on_conversion` TINYINT(1) NULL DEFAULT 1 COMMENT '转化时通知',
  `notify_on_high_value` TINYINT(1) NULL DEFAULT 0 COMMENT '高价值转化通知',
  `high_value_threshold` DECIMAL(10, 2) NULL DEFAULT NULL COMMENT '高价值阈值',
  `notify_channels` TEXT NULL COMMENT '通知渠道（JSON格式：[\"telegram\", \"email\", \"sms\"]）',
  `telegram_chat_id` VARCHAR(100) NULL DEFAULT NULL COMMENT 'Telegram Chat ID',
  `email_address` VARCHAR(255) NULL DEFAULT NULL COMMENT '邮箱地址',
  `phone_number` VARCHAR(20) NULL DEFAULT NULL COMMENT '手机号',
  `notification_frequency` VARCHAR(20) NULL DEFAULT 'realtime' COMMENT '通知频率：realtime, hourly, daily',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `product_id`(`product_id` ASC) USING BTREE,
  INDEX `idx_product_notification_config_product`(`product_id` ASC) USING BTREE,
  INDEX `idx_product_notification_config_enabled`(`notification_enabled` ASC) USING BTREE,
  CONSTRAINT `product_notification_configs_ibfk_1` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '产品通知配置表' ROW_FORMAT = Dynamic;
SET FOREIGN_KEY_CHECKS = 1;
-- ----------------------------
-- Table structure for products
-- ----------------------------
DROP TABLE IF EXISTS `products`;
CREATE TABLE IF NOT EXISTS `products`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '产品ID',
  `client_id` INT NOT NULL COMMENT '客户ID',
  `name` VARCHAR(100) NOT NULL COMMENT '产品名称',
  `ecpm_deduct_ratio` FLOAT NOT NULL DEFAULT 0 COMMENT 'eCPM减扣比例',
  `revenue_deduct_ratio` FLOAT NOT NULL DEFAULT 0 COMMENT '收益减扣比例',
  `cplpo_deduct_ratio` FLOAT NOT NULL DEFAULT 0 COMMENT 'CPL PO减扣比例 ',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否激活',
  `notification_address` VARCHAR(500) NULL DEFAULT NULL COMMENT '通知地址（Telegram Chat ID、邮箱地址、Webhook URL等，用于接收转化通知）',
  `downstream_postback_method` VARCHAR(10) NULL DEFAULT 'GET' COMMENT '下游 Postback 请求方式：GET 或 POST（默认GET）',
  `downstream_postback_url` VARCHAR(500) NULL DEFAULT NULL COMMENT '下游 Postback URL（可选，配置后将自动转发转化数据）',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_product_client`(`client_id` ASC) USING BTREE,
  INDEX `idx_product_name`(`name` ASC) USING BTREE,
  FULLTEXT INDEX `ft_products_name`(`name`) WITH PARSER `ngram`,
  CONSTRAINT `fk_products_client` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '产品表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for publishers
-- ----------------------------
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS `publishers`;
CREATE TABLE IF NOT EXISTS `publishers`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '渠道ID',
  `publisher_id` VARCHAR(50) NOT NULL COMMENT '渠道ID（系统生成，唯一标识）',
  `publisher_name` VARCHAR(100) NOT NULL COMMENT '渠道名称',
  `email` VARCHAR(255) NULL DEFAULT NULL COMMENT '邮箱（可选）',
  `price_discount` DECIMAL(5, 2) NULL DEFAULT 0.00 COMMENT '渠道级别的价格扣量比例（0-100）',
  `postback_url` TEXT NULL COMMENT 'Postback URL（渠道的Postback配置）',
  `postback_method` VARCHAR(10) NULL DEFAULT 'GET' COMMENT 'Postback请求方式：GET/POST',
  `active_advertiser_count` INT NULL DEFAULT 0 COMMENT '活跃的广告主数量',
  `is_active` TINYINT(1) NULL DEFAULT 1 COMMENT '是否激活',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `publisher_id`(`publisher_id` ASC) USING BTREE,
  INDEX `idx_publisher_id`(`publisher_id` ASC) USING BTREE,
  INDEX `idx_publisher_name`(`publisher_name` ASC) USING BTREE,
  INDEX `idx_is_active`(`is_active` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '渠道表（下游）' ROW_FORMAT = Dynamic;
SET FOREIGN_KEY_CHECKS = 1;
-- ----------------------------
-- Table structure for scheduled_tasks
-- ----------------------------
DROP TABLE IF EXISTS `scheduled_tasks`;
CREATE TABLE IF NOT EXISTS `scheduled_tasks`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '定时任务ID',
  `task_name` VARCHAR(100) NOT NULL COMMENT '任务名称（唯一）',
  `last_run_time` DATETIME(6) NULL DEFAULT NULL COMMENT '上次执行时间',
  `is_running` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否正在执行',
  `last_run_pid` INT NULL DEFAULT NULL COMMENT '上次执行的进程ID',
  `last_run_host` VARCHAR(100) NULL DEFAULT NULL COMMENT '上次执行的服务器主机名',
  `run_count` INT NOT NULL DEFAULT 0 COMMENT '执行次数',
  `success_count` INT NOT NULL DEFAULT 0 COMMENT '成功次数',
  `error_count` INT NOT NULL DEFAULT 0 COMMENT '失败次数',
  `last_error` TEXT NULL COMMENT '最后一次错误信息',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  `cron_expression` VARCHAR(100) NULL DEFAULT NULL COMMENT 'Cron表达式',
  `description` TEXT NULL COMMENT '任务描述',
  `function_path` VARCHAR(255) NULL DEFAULT NULL COMMENT '执行函数路径（例如：app.scheduler_module.tasks.simple_task.simple_info_task）',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
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
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS `short_links`;
CREATE TABLE IF NOT EXISTS `short_links`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '短链接ID',
  `short_code` VARCHAR(20) NOT NULL COMMENT '短链接代码（唯一）',
  `original_url` TEXT NOT NULL COMMENT '原始URL',
  `title` VARCHAR(200) NULL DEFAULT NULL COMMENT '短链接标题（可选）',
  `description` TEXT NULL COMMENT '短链接描述（可选）',
  `created_by` INT NULL DEFAULT NULL COMMENT '创建者用户ID',
  `click_count` INT NULL DEFAULT 0 COMMENT '点击次数',
  `is_active` TINYINT(1) NULL DEFAULT 1 COMMENT '是否激活',
  `expires_at` DATETIME NULL DEFAULT NULL COMMENT '过期时间（可选）',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `short_code`(`short_code` ASC) USING BTREE,
  INDEX `idx_short_link_code`(`short_code` ASC) USING BTREE,
  INDEX `idx_short_link_created_by`(`created_by` ASC) USING BTREE,
  INDEX `idx_short_link_active`(`is_active` ASC) USING BTREE,
  INDEX `idx_short_link_created_at`(`created_at` ASC) USING BTREE,
  CONSTRAINT `short_links_ibfk_1` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '短链接表' ROW_FORMAT = DYNAMIC;
SET FOREIGN_KEY_CHECKS = 1;
-- ----------------------------
-- Table structure for tb_search_data
-- ----------------------------
DROP TABLE IF EXISTS `tb_search_data`;
CREATE TABLE IF NOT EXISTS `tb_search_data`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `date` DATETIME NOT NULL COMMENT '日期',
  `product_id` INT NOT NULL COMMENT '产品ID',
  `country_code` VARCHAR(2) NULL DEFAULT NULL COMMENT '国家代码',
  `redirects` INT NULL DEFAULT NULL COMMENT 'REDIRECTS',
  `searches` INT NULL DEFAULT NULL COMMENT 'SEARCHES',
  `monetized` INT NULL DEFAULT NULL COMMENT 'MONETIZED',
  `clicks` INT NULL DEFAULT NULL COMMENT 'CLICKS',
  `revenue` FLOAT NULL DEFAULT NULL COMMENT 'REVENUE（扣减后）',
  `rpm` FLOAT NULL DEFAULT NULL COMMENT 'RPM（扣减后）',
  `revenue_before_deduct` FLOAT NULL DEFAULT NULL COMMENT 'REVENUE（扣减前）',
  `rpm_before_deduct` FLOAT NULL DEFAULT NULL COMMENT 'RPM（扣减前）',
  `created_at` DATETIME NULL DEFAULT NULL COMMENT '创建时间',
  `updated_at` DATETIME NULL DEFAULT NULL COMMENT '更新时间',
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
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '黑名单ID',
  `token_jti` VARCHAR(64) NOT NULL COMMENT 'JWT令牌ID（jti）',
  `user_id` INT NOT NULL COMMENT '用户ID',
  `revoked_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '撤销时间',
  `expires_at` DATETIME(6) NOT NULL COMMENT 'Token过期时间',
  `reason` VARCHAR(200) NULL DEFAULT NULL COMMENT '撤销原因（用户退出、强制退出等）',
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
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '用户操作日志表（审计日志）' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for user_sessions
-- ----------------------------
DROP TABLE IF EXISTS `user_sessions`;
CREATE TABLE IF NOT EXISTS `user_sessions`  (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '会话ID',
  `user_id` INT NOT NULL COMMENT '用户ID',
  `token_jti` VARCHAR(64) NOT NULL COMMENT 'JWT令牌ID（jti）',
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
  INDEX `idx_username`(`username` ASC) USING BTREE,
  INDEX `idx_email`(`email` ASC) USING BTREE,
  FULLTEXT INDEX `ft_users_search`(`username`, `full_name`, `email`) WITH PARSER `ngram`
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '用户表' ROW_FORMAT = DYNAMIC;

SET FOREIGN_KEY_CHECKS = 1;
