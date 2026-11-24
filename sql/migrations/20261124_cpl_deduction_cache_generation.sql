-- CPL 扣量配置使用独立数据库 Generation，防止旧配置缓存回填影响扣量计算。
-- Generation 更新与扣量配置变更、通用 CacheInvalidationOutbox 事件必须同事务提交。
-- 依赖 20261123_ad_data_cache_generation_outbox 创建的基础表；重复执行不会重置版本。

INSERT IGNORE INTO cache_namespace_generations (namespace, generation)
VALUES ('cpl:deduction_config', 1);

-- 缺失或非法版本必须让迁移失败，禁止带着不完整命名空间上线。
SET @deduction_generation_valid = (
    SELECT COUNT(*)
    FROM cache_namespace_generations
    WHERE namespace = 'cpl:deduction_config' AND generation > 0
);
SET @ddl = IF(
    @deduction_generation_valid = 1,
    'SELECT 1',
    'SELECT * FROM __cpl_deduction_cache_generation_schema_mismatch__'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SELECT namespace, generation
FROM cache_namespace_generations
WHERE namespace = 'cpl:deduction_config' AND generation > 0;
