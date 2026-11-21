-- 单例行用于串行化所有待审批入队容量检查，避免并发 COUNT 后同时 INSERT 超过上限。
-- 所有 enqueue 必须在读取 pending COUNT 前锁定 id=1 行，并持锁直到同一事务提交。
CREATE TABLE IF NOT EXISTS `postback_pending_queue_guard` (
    `id` TINYINT UNSIGNED NOT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    CONSTRAINT `chk_postback_pending_queue_guard_singleton` CHECK (`id` = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO `postback_pending_queue_guard` (`id`) VALUES (1);
