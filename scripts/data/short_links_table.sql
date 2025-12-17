-- 短链接服务数据表
-- 用于实现类似 Bitly 的短链接功能
USE `platform`;

DROP TABLE IF EXISTS short_links;
CREATE TABLE IF NOT EXISTS short_links (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '短链接ID',
    short_code VARCHAR(20) NOT NULL UNIQUE COMMENT '短链接代码（唯一）',
    original_url TEXT NOT NULL COMMENT '原始URL',
    title VARCHAR(200) NULL COMMENT '短链接标题（可选）',
    description TEXT NULL COMMENT '短链接描述（可选）',
    created_by INT NULL COMMENT '创建者用户ID',
    click_count INT DEFAULT 0 COMMENT '点击次数',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',
    expires_at DATETIME NULL COMMENT '过期时间（可选）',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    -- 外键约束
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
    
    -- 索引
    INDEX idx_short_link_code (short_code),
    INDEX idx_short_link_created_by (created_by),
    INDEX idx_short_link_active (is_active),
    INDEX idx_short_link_created_at (created_at)
) COMMENT='短链接表';

-- 使用说明：
-- 1. short_code: 短链接代码，自动生成或自定义（唯一）
-- 2. original_url: 原始URL，必须包含协议（http://或https://）
-- 3. title: 短链接标题，用于管理界面显示
-- 4. description: 短链接描述，用于备注
-- 5. created_by: 创建者用户ID，用于权限控制
-- 6. click_count: 点击次数，每次访问自动增加
-- 7. is_active: 是否激活，禁用后无法访问
-- 8. expires_at: 过期时间，过期后无法访问
--
-- 短链接访问格式：
-- https://yourdomain.com/s/{short_code}
--
-- 示例：
-- INSERT INTO short_links (short_code, original_url, title, created_by) 
-- VALUES ('abc123', 'https://example.com/very/long/url', '示例链接', 1);

