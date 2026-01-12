-- ============================================
-- 迁移脚本：创建管理员通知配置表
-- 创建时间：2026-01-12
-- 说明：管理员通知配置表，单例模式（只有一条记录，id=1）
-- ============================================

-- 创建管理员通知配置表
CREATE TABLE IF NOT EXISTS `admin_notification_configs` (
  `id` INT NOT NULL DEFAULT 1 COMMENT '配置ID（固定为1，单例模式）',
  `telegram_enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用 Telegram 通知',
  `telegram_chat_id` VARCHAR(100) NULL DEFAULT NULL COMMENT '管理员 Telegram Chat ID',
  `notify_all_conversions` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '通知所有转化',
  `notify_forward_failure` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '通知转发失败',
  `notify_forward_success` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '通知转发成功（可选）',
  `notify_system_errors` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '通知系统异常',
  `notify_statistics` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '定时统计通知',
  `statistics_frequency` VARCHAR(20) NOT NULL DEFAULT 'hourly' COMMENT '统计频率：hourly, daily',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  CONSTRAINT `check_single_record` CHECK (`id` = 1)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '管理员通知配置表（单例模式）' ROW_FORMAT = DYNAMIC;

-- 插入默认配置（如果不存在）
INSERT INTO `admin_notification_configs` (
  `id`,
  `telegram_enabled`,
  `telegram_chat_id`,
  `notify_all_conversions`,
  `notify_forward_failure`,
  `notify_forward_success`,
  `notify_system_errors`,
  `notify_statistics`,
  `statistics_frequency`
) VALUES (
  1,
  1,
  NULL,
  1,
  1,
  0,
  1,
  0,
  'hourly'
) ON DUPLICATE KEY UPDATE `id` = `id`;

-- 验证表是否创建成功
SELECT 
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    COLUMN_COMMENT
FROM 
    INFORMATION_SCHEMA.COLUMNS
WHERE 
    TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'admin_notification_configs'
ORDER BY 
    ORDINAL_POSITION;
