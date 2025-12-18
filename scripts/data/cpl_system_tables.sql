-- CPL 系统数据表创建脚本
-- 数据模型选择：选项 A（完全重构）
-- 保留现有的 clients 和 products 表

USE `platform`;

-- ==================== 1. 广告主表 ====================
DROP TABLE IF EXISTS advertisers;
CREATE TABLE advertisers (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '广告主ID',
    advertiser_id VARCHAR(50) UNIQUE NOT NULL COMMENT '广告主ID（系统生成，唯一标识）',
    advertiser_name VARCHAR(100) NOT NULL COMMENT '广告主名称',
    email VARCHAR(255) COMMENT '邮箱（可选）',
    mobile VARCHAR(20) COMMENT '手机号',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    INDEX idx_advertiser_id (advertiser_id),
    INDEX idx_advertiser_name (advertiser_name),
    INDEX idx_is_active (is_active)
) COMMENT='广告主表（上游）';

-- ==================== 2. 渠道表 ====================
DROP TABLE IF EXISTS publishers;
CREATE TABLE publishers (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '渠道ID',
    publisher_id VARCHAR(50) UNIQUE NOT NULL COMMENT '渠道ID（系统生成，唯一标识）',
    publisher_name VARCHAR(100) NOT NULL COMMENT '渠道名称',
    email VARCHAR(255) COMMENT '邮箱（可选）',
    price_discount DECIMAL(5,2) DEFAULT 0.00 COMMENT '渠道级别的价格扣量比例（0-100）',
    active_advertiser_count INT DEFAULT 0 COMMENT '活跃的广告主数量',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    INDEX idx_publisher_id (publisher_id),
    INDEX idx_publisher_name (publisher_name),
    INDEX idx_is_active (is_active)
) COMMENT='渠道表（下游）';

-- ==================== 3. Offer表（单子表） ====================
DROP TABLE IF EXISTS offers;
CREATE TABLE offers (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT 'Offer ID（主键）',
    offer_id VARCHAR(50) UNIQUE NOT NULL COMMENT 'Offer ID（系统生成的唯一标识）',
    offer_name VARCHAR(200) NOT NULL COMMENT 'Offer名称',
    advertiser_offer_id VARCHAR(100) COMMENT '上游系统中的Offer ID（ADV Offer ID）',
    advertiser_id INT NOT NULL COMMENT '关联的广告主ID',
    preview_link TEXT COMMENT '预览链接',
    payout DECIMAL(10,2) COMMENT '上游支付金额（PO）',
    affiliate_payout DECIMAL(10,2) COMMENT '扣价后给渠道的金额（PO扣价后）',
    country VARCHAR(50) COMMENT '国家',
    category VARCHAR(50) COMMENT '分类',
    type VARCHAR(50) COMMENT '类型',
    status VARCHAR(20) DEFAULT 'Active' COMMENT '状态：Active/Inactive',
    upstream_cap INT COMMENT '上游转化上限',
    downstream_cap INT COMMENT '下游转化上限',
    advertiser_tracklink TEXT COMMENT '上游的Tracklink（不显示给下游，建立单子时配置我们的参数）',
    downstream_tracklink TEXT COMMENT '生成给下游的Tracklink',
    postback_url TEXT COMMENT 'Postback URL（配置我们的参数）',
    postback_method VARCHAR(10) DEFAULT 'GET' COMMENT 'Postback请求方式：GET/POST',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    FOREIGN KEY (advertiser_id) REFERENCES advertisers(id) ON DELETE RESTRICT,
    INDEX idx_offer_id (offer_id),
    INDEX idx_advertiser_id (advertiser_id),
    INDEX idx_status (status),
    INDEX idx_is_active (is_active),
    INDEX idx_country (country)
) COMMENT='Offer表（单子表）';

-- ==================== 4. Offer-渠道分配表 ====================
DROP TABLE IF EXISTS offer_publisher_assignments;
CREATE TABLE offer_publisher_assignments (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '分配ID',
    offer_id INT NOT NULL COMMENT 'Offer ID',
    publisher_id INT NOT NULL COMMENT '渠道ID',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    UNIQUE KEY uk_offer_publisher (offer_id, publisher_id),
    FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE CASCADE,
    FOREIGN KEY (publisher_id) REFERENCES publishers(id) ON DELETE CASCADE,
    INDEX idx_offer_id (offer_id),
    INDEX idx_publisher_id (publisher_id),
    INDEX idx_is_active (is_active)
) COMMENT='Offer-渠道分配表';

-- ==================== 5. 点击记录表 ====================
DROP TABLE IF EXISTS clicks;
CREATE TABLE clicks (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '点击记录ID',
    click_id VARCHAR(255) UNIQUE NOT NULL COMMENT '点击ID（系统生成，唯一标识）',
    offer_id INT COMMENT '关联的Offer ID',
    publisher_id INT COMMENT '关联的渠道ID',
    advertiser_id INT COMMENT '关联的广告主ID',
    click_time DATETIME NOT NULL COMMENT '点击时间',
    ip VARCHAR(50) COMMENT '点击IP地址',
    device VARCHAR(100) COMMENT '设备信息',
    country VARCHAR(50) COMMENT '国家',
    user_agent TEXT COMMENT 'User Agent',
    referer TEXT COMMENT '来源页面',
    conversion_id INT COMMENT '关联的转化ID（如果已转化）',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    
    FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE SET NULL,
    FOREIGN KEY (publisher_id) REFERENCES publishers(id) ON DELETE SET NULL,
    FOREIGN KEY (advertiser_id) REFERENCES advertisers(id) ON DELETE SET NULL,
    INDEX idx_click_id (click_id),
    INDEX idx_offer_id (offer_id),
    INDEX idx_publisher_id (publisher_id),
    INDEX idx_advertiser_id (advertiser_id),
    INDEX idx_click_time (click_time),
    INDEX idx_conversion_id (conversion_id)
) COMMENT='点击记录表';

-- ==================== 6. Cap配置表 ====================
DROP TABLE IF EXISTS offer_caps;
CREATE TABLE offer_caps (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT 'Cap配置ID',
    cap_type VARCHAR(50) NOT NULL COMMENT 'Cap类型：advertiser_offer/offer',
    advertiser_id INT COMMENT '广告主ID（如果是advertiser_offer类型）',
    offer_id INT NOT NULL COMMENT 'Offer ID',
    publisher_id INT COMMENT '渠道ID（如果为空，表示所有渠道）',
    daily_cap INT COMMENT '每日Cap',
    total_cap INT COMMENT '总Cap',
    current_daily_count INT DEFAULT 0 COMMENT '当前每日计数',
    current_total_count INT DEFAULT 0 COMMENT '当前总计数',
    cap_start_date DATETIME COMMENT 'Cap开始日期（用于Total Cap）',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE CASCADE,
    FOREIGN KEY (advertiser_id) REFERENCES advertisers(id) ON DELETE CASCADE,
    FOREIGN KEY (publisher_id) REFERENCES publishers(id) ON DELETE CASCADE,
    INDEX idx_cap_type (cap_type),
    INDEX idx_offer_id (offer_id),
    INDEX idx_advertiser_id (advertiser_id),
    INDEX idx_publisher_id (publisher_id),
    INDEX idx_is_active (is_active)
) COMMENT='Cap配置表';

-- ==================== 7. 扣量配置表 ====================
DROP TABLE IF EXISTS offer_discounts;
CREATE TABLE offer_discounts (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '扣量配置ID',
    discount_type VARCHAR(50) NOT NULL COMMENT '扣量类型：offer/channel',
    offer_id INT COMMENT 'Offer ID（如果是offer类型）',
    publisher_id INT NOT NULL COMMENT '渠道ID',
    discount_ratio DECIMAL(5,2) NOT NULL COMMENT '扣量比例（0-100）',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE CASCADE,
    FOREIGN KEY (publisher_id) REFERENCES publishers(id) ON DELETE CASCADE,
    INDEX idx_discount_type (discount_type),
    INDEX idx_offer_id (offer_id),
    INDEX idx_publisher_id (publisher_id),
    INDEX idx_is_active (is_active)
) COMMENT='扣量配置表';

-- ==================== 8. 上游测试记录表 ====================
DROP TABLE IF EXISTS advertiser_tests;
CREATE TABLE advertiser_tests (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '测试记录ID',
    advertiser_id INT NOT NULL COMMENT '广告主ID',
    advertiser_name VARCHAR(100) COMMENT '广告主名称',
    advertiser_offer_id VARCHAR(100) COMMENT '上游系统中的Offer ID',
    offer_id INT NOT NULL COMMENT '平台内的Offer ID',
    offer_name VARCHAR(200) COMMENT 'Offer名称',
    price DECIMAL(10,2) COMMENT '价格',
    country VARCHAR(50) COMMENT '国家',
    click_id VARCHAR(255) COMMENT '测试生成的Click ID',
    click_url TEXT COMMENT '测试生成的Click Url',
    test_time DATETIME COMMENT '测试时间',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    
    FOREIGN KEY (advertiser_id) REFERENCES advertisers(id) ON DELETE CASCADE,
    FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE CASCADE,
    INDEX idx_advertiser_id (advertiser_id),
    INDEX idx_offer_id (offer_id),
    INDEX idx_test_time (test_time)
) COMMENT='上游测试记录表';

-- ==================== 9. 下游测试记录表 ====================
DROP TABLE IF EXISTS affiliate_tests;
CREATE TABLE affiliate_tests (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '测试记录ID',
    publisher_id INT NOT NULL COMMENT '渠道ID',
    click_id VARCHAR(255) NOT NULL COMMENT '下游提供的Click ID',
    offer_id INT NOT NULL COMMENT 'Offer ID',
    offer_name VARCHAR(200) COMMENT 'Offer名称',
    price DECIMAL(10,2) COMMENT '价格',
    country VARCHAR(50) COMMENT '国家',
    platform VARCHAR(50) COMMENT '平台',
    postback_time DATETIME COMMENT 'Postback发送时间',
    status VARCHAR(50) COMMENT '发送状态：Send Success/Failed',
    affiliate_return_content TEXT COMMENT '渠道返回内容',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    
    FOREIGN KEY (publisher_id) REFERENCES publishers(id) ON DELETE CASCADE,
    FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE CASCADE,
    INDEX idx_publisher_id (publisher_id),
    INDEX idx_offer_id (offer_id),
    INDEX idx_click_id (click_id),
    INDEX idx_status (status),
    INDEX idx_postback_time (postback_time)
) COMMENT='下游测试记录表';

-- ==================== 10. 修改 postback_conversions 表 ====================
-- 添加 click_id, click_time, conversion_status 字段
ALTER TABLE postback_conversions 
ADD COLUMN click_id VARCHAR(255) COMMENT '关联的Click ID',
ADD COLUMN click_time DATETIME COMMENT '点击时间',
ADD COLUMN conversion_status VARCHAR(20) DEFAULT 'Pending' COMMENT '转化状态：Approved/Pending',
ADD INDEX idx_click_id (click_id),
ADD INDEX idx_conversion_status (conversion_status);

-- ==================== 使用说明 ====================
-- 1. 执行此脚本前，请确保已备份数据库
-- 2. 此脚本会创建新的表，不会删除现有的 clients 和 products 表
-- 3. 新的 CPL 系统使用新的表结构，与现有系统并行运行
-- 4. 如果需要建立映射关系，可以后续添加映射表

