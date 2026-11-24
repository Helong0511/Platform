-- 用户统计缓存独立 Generation；依赖 cache_namespace_generations / Outbox 基础表。
-- 业务数据、user_stats Generation 与 Outbox 必须在同一 InnoDB 事务提交。
-- utf8mb4 继承基础表结构；重复执行不重置现有 Generation。

INSERT IGNORE INTO cache_namespace_generations (namespace, generation)
VALUES ('user_stats', 1);

-- 缺失或非法版本必须让迁移失败，禁止带着不完整命名空间上线。
SET @user_stats_generation_valid = (
    SELECT COUNT(*)
    FROM cache_namespace_generations
    WHERE namespace = 'user_stats' AND generation > 0
);
SET @ddl = IF(
    @user_stats_generation_valid = 1,
    'SELECT 1',
    'SELECT * FROM __user_stats_cache_generation_schema_mismatch__'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SELECT namespace, generation
FROM cache_namespace_generations
WHERE namespace = 'user_stats' AND generation > 0;
