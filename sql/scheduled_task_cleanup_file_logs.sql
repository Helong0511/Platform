-- 定时任务：清理文件日志（logs/ 磁盘文件超期归档/删除）
-- 由 task_init 也可自动写入；本脚本供手工补库或对照核对。
-- 默认每天 03:30 执行；与「清理旧日志」(DB 审计)、「清理敏感路径拦截日志」相互独立。

INSERT INTO `scheduled_tasks` (
  `task_name`,
  `cron_expression`,
  `description`,
  `function_path`,
  `is_active`,
  `status`,
  `is_running`,
  `retry_count`,
  `created_at`,
  `updated_at`
) VALUES (
  '清理文件日志',
  '30 3 * * *',
  '清理超期文件日志：轮转备份归档/删除、archive 超期清理、gunicorn 溢出轮转与磁盘守卫',
  'app.scheduler_module.tasks.cleanup_file_logs.cleanup_file_logs',
  1,
  'idle',
  0,
  0,
  NOW(6),
  NOW(6)
) ON DUPLICATE KEY UPDATE
  `cron_expression` = VALUES(`cron_expression`),
  `description` = VALUES(`description`),
  `function_path` = VALUES(`function_path`),
  `updated_at` = NOW(6);
