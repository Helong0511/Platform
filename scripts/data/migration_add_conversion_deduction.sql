-- ============================================
-- CPL扣减系统数据库迁移脚本
-- 创建时间: 2024-01-XX
-- 说明: 添加转化扣减配置表和日志表
-- ============================================

-- 1. 创建扣减配置表
CREATE TABLE IF NOT EXISTS conversion_deduction_configs (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '配置ID',
    
    -- 配置层级（三选一）
    advertiser_id INT NULL COMMENT '广告主ID（如果配置在广告主级别）',
    offer_id INT NULL COMMENT 'Offer ID（如果配置在Offer级别）',
    publisher_id INT NULL COMMENT '渠道ID（如果配置在渠道级别）',
    
    -- 扣减类型配置
    volume_deduction_ratio DECIMAL(5,4) DEFAULT 0.0000 COMMENT '按比例扣量比例（0-1，如0.10表示扣量10%）',
    amount_deduction_ratio DECIMAL(5,4) DEFAULT 0.0000 COMMENT '按比例扣金额比例（0-1，如0.10表示扣金额10%）',
    
    -- 扣减策略配置
    deduction_strategy VARCHAR(50) DEFAULT 'random' COMMENT '扣减策略：random（随机）/proportional（按比例）/round_robin（轮询）',
    enable_volume_deduction BOOLEAN DEFAULT FALSE COMMENT '是否启用按比例扣量',
    enable_amount_deduction BOOLEAN DEFAULT FALSE COMMENT '是否启用按比例扣金额',
    
    -- 优先级配置
    priority INT DEFAULT 0 COMMENT '优先级（数字越大优先级越高）',
    
    -- 状态
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',
    
    -- 时间戳
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    -- 索引
    INDEX idx_advertiser_id (advertiser_id),
    INDEX idx_offer_id (offer_id),
    INDEX idx_publisher_id (publisher_id),
    INDEX idx_is_active (is_active),
    INDEX idx_priority (priority),
    
    -- 外键
    FOREIGN KEY (advertiser_id) REFERENCES advertisers(id) ON DELETE CASCADE,
    FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE CASCADE,
    FOREIGN KEY (publisher_id) REFERENCES publishers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='转化扣减配置表';

-- 2. 创建扣减执行记录表
CREATE TABLE IF NOT EXISTS conversion_deduction_logs (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '记录ID',
    
    -- 关联信息
    conversion_id INT NULL COMMENT '转化记录ID（关联postback_conversions.id，可为NULL因为扣量的转化可能不保存）',
    click_id VARCHAR(255) NULL COMMENT '点击ID',
    advertiser_id INT NULL COMMENT '广告主ID',
    offer_id INT NULL COMMENT 'Offer ID',
    publisher_id INT NULL COMMENT '渠道ID',
    
    -- 扣减前数据
    original_volume INT DEFAULT 1 COMMENT '原始转化数量（通常为1）',
    original_amount DECIMAL(10,2) NOT NULL COMMENT '原始转化金额',
    
    -- 扣减后数据
    deducted_volume INT DEFAULT 0 COMMENT '扣减的转化数量',
    deducted_amount DECIMAL(10,2) DEFAULT 0.00 COMMENT '扣减的转化金额',
    final_volume INT DEFAULT 1 COMMENT '最终转化数量（扣减后）',
    final_amount DECIMAL(10,2) NOT NULL COMMENT '最终转化金额（扣减后）',
    
    -- 扣减配置信息
    deduction_config_id INT NULL COMMENT '使用的扣减配置ID',
    volume_deduction_ratio DECIMAL(5,4) COMMENT '使用的扣量比例',
    amount_deduction_ratio DECIMAL(5,4) COMMENT '使用的扣金额比例',
    deduction_strategy VARCHAR(50) COMMENT '使用的扣减策略',
    
    -- 扣减原因
    deduction_reason TEXT NULL COMMENT '扣减原因说明',
    
    -- 时间戳
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    
    -- 索引
    INDEX idx_conversion_id (conversion_id),
    INDEX idx_click_id (click_id),
    INDEX idx_advertiser_id (advertiser_id),
    INDEX idx_offer_id (offer_id),
    INDEX idx_publisher_id (publisher_id),
    INDEX idx_created_at (created_at),
    INDEX idx_deduction_config_id (deduction_config_id),
    
    -- 外键
    FOREIGN KEY (advertiser_id) REFERENCES advertisers(id) ON DELETE SET NULL,
    FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE SET NULL,
    FOREIGN KEY (publisher_id) REFERENCES publishers(id) ON DELETE SET NULL,
    FOREIGN KEY (deduction_config_id) REFERENCES conversion_deduction_configs(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='转化扣减执行记录表';

-- 3. 修改postback_conversions表，增加扣减相关字段
-- 使用动态SQL检查字段是否存在（兼容MySQL 5.7）

-- 检查并添加 is_deducted 字段
SET @col_exists := (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'postback_conversions'
      AND COLUMN_NAME = 'is_deducted'
);

SET @sql := IF(
    @col_exists = 0,
    'ALTER TABLE postback_conversions ADD COLUMN is_deducted BOOLEAN DEFAULT FALSE COMMENT ''是否已被扣减''',
    'SELECT 1'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 检查并添加 deduction_type 字段
SET @col_exists := (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'postback_conversions'
      AND COLUMN_NAME = 'deduction_type'
);

SET @sql := IF(
    @col_exists = 0,
    'ALTER TABLE postback_conversions ADD COLUMN deduction_type VARCHAR(20) NULL COMMENT ''扣减类型：volume（扣量）/amount（扣金额）/both（两者）''',
    'SELECT 1'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 检查并添加 original_volume 字段
SET @col_exists := (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'postback_conversions'
      AND COLUMN_NAME = 'original_volume'
);

SET @sql := IF(
    @col_exists = 0,
    'ALTER TABLE postback_conversions ADD COLUMN original_volume INT DEFAULT 1 COMMENT ''原始转化数量''',
    'SELECT 1'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 检查并添加 deducted_volume 字段
SET @col_exists := (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'postback_conversions'
      AND COLUMN_NAME = 'deducted_volume'
);

SET @sql := IF(
    @col_exists = 0,
    'ALTER TABLE postback_conversions ADD COLUMN deducted_volume INT DEFAULT 0 COMMENT ''扣减的转化数量''',
    'SELECT 1'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 添加索引（检查索引是否存在）
-- 检查 idx_is_deducted 索引
SET @idx_exists := (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'postback_conversions'
      AND INDEX_NAME = 'idx_is_deducted'
);

SET @sql := IF(
    @idx_exists = 0,
    'CREATE INDEX idx_is_deducted ON postback_conversions(is_deducted)',
    'SELECT 1'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 检查 idx_deduction_type 索引
SET @idx_exists := (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'postback_conversions'
      AND INDEX_NAME = 'idx_deduction_type'
);

SET @sql := IF(
    @idx_exists = 0,
    'CREATE INDEX idx_deduction_type ON postback_conversions(deduction_type)',
    'SELECT 1'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 注意：MySQL 5.7不支持 IF NOT EXISTS，如果报错请手动检查字段是否存在后再执行

