-- ============================================
-- 添加日志清理定时任务
-- ============================================
-- 说明：此脚本用于在数据库中创建日志清理定时任务
-- 执行前请确保：
-- 1. 已配置 AUDIT_LOG_RETENTION_DAYS 环境变量（默认90天）
-- 2. 已配置 AUDIT_LOG_ARCHIVE 环境变量（默认false，直接删除）
-- 
-- 执行方式：
-- mysql -u root -p platform < scripts/add_cleanup_logs_task.sql
-- ============================================

-- 检查任务是否已存在
SET @task_exists = (
    SELECT COUNT(*) 
    FROM `scheduled_tasks` 
    WHERE `task_name` = '清理旧日志'
);

-- 如果任务不存在，则创建
INSERT INTO `scheduled_tasks` (
    `task_name`,
    `last_run_time`,
    `is_running`,
    `run_count`,
    `success_count`,
    `fail_count`,
    `last_error`,
    `is_active`,
    `cron_expression`,
    `description`,
    `function_path`,
    `created_at`,
    `updated_at`
)
SELECT 
    '清理旧日志' AS `task_name`,
    NULL AS `last_run_time`,
    0 AS `is_running`,
    0 AS `run_count`,
    0 AS `success_count`,
    0 AS `fail_count`,
    NULL AS `last_error`,
    1 AS `is_active`,  -- 默认启用
    '0 2 1 * *' AS `cron_expression`,  -- 每月1号凌晨2点执行
    '清理90天前的用户操作日志，减少日志表数据量，提升查询性能。可通过环境变量 AUDIT_LOG_RETENTION_DAYS 配置保留天数（默认90天），AUDIT_LOG_ARCHIVE 配置是否归档（默认false，直接删除）' AS `description`,
    'app.scheduler_module.tasks.cleanup_old_logs.cleanup_old_audit_logs' AS `function_path`,
    NOW() AS `created_at`,
    NOW() AS `updated_at`
WHERE @task_exists = 0;

-- 显示结果
SELECT 
    CASE 
        WHEN @task_exists > 0 THEN '任务已存在，未创建新任务'
        ELSE '任务创建成功'
    END AS `result`,
    `task_name`,
    `cron_expression`,
    `description`,
    `is_active`
FROM `scheduled_tasks`
WHERE `task_name` = '清理旧日志';

