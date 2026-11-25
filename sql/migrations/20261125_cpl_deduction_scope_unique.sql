-- 为每个 scope 建立数据库级激活唯一约束，并拒绝零/多重 scope 历史记录。
-- 历史数据存在异常时必须先人工核实；本迁移绝不自动删除或合并配置。

SET @cpl_invalid_scope_count = (
    SELECT COUNT(*)
    FROM conversion_deduction_configs
    WHERE is_active IS NULL OR
        (advertiser_id IS NOT NULL) +
        (offer_id IS NOT NULL) +
        (publisher_id IS NOT NULL) <> 1
);
SET @cpl_duplicate_active_count = (
    SELECT
        (SELECT COUNT(*) FROM (
            SELECT advertiser_id
            FROM conversion_deduction_configs
            WHERE is_active = 1 AND advertiser_id IS NOT NULL
            GROUP BY advertiser_id
            HAVING COUNT(*) > 1
        ) AS duplicate_advertiser_scopes)
        +
        (SELECT COUNT(*) FROM (
            SELECT offer_id
            FROM conversion_deduction_configs
            WHERE is_active = 1 AND offer_id IS NOT NULL
            GROUP BY offer_id
            HAVING COUNT(*) > 1
        ) AS duplicate_offer_scopes)
        +
        (SELECT COUNT(*) FROM (
            SELECT publisher_id
            FROM conversion_deduction_configs
            WHERE is_active = 1 AND publisher_id IS NOT NULL
            GROUP BY publisher_id
            HAVING COUNT(*) > 1
        ) AS duplicate_publisher_scopes)
);
SET @cpl_scope_unique_validation_sql = IF(
    @cpl_invalid_scope_count = 0 AND @cpl_duplicate_active_count = 0,
    'SELECT 1',
    'SELECT * FROM __cpl_deduction_scope_history_conflict__'
);
PREPARE cpl_scope_unique_validation FROM @cpl_scope_unique_validation_sql;
EXECUTE cpl_scope_unique_validation;
DEALLOCATE PREPARE cpl_scope_unique_validation;

ALTER TABLE conversion_deduction_configs
    MODIFY COLUMN is_active TINYINT(1) NOT NULL DEFAULT 1,
    ADD COLUMN active_advertiser_id INT
        GENERATED ALWAYS AS (
            CASE WHEN is_active = 1 THEN advertiser_id ELSE NULL END
        ) STORED,
    ADD COLUMN active_offer_id INT
        GENERATED ALWAYS AS (
            CASE WHEN is_active = 1 THEN offer_id ELSE NULL END
        ) STORED,
    ADD COLUMN active_publisher_id INT
        GENERATED ALWAYS AS (
            CASE WHEN is_active = 1 THEN publisher_id ELSE NULL END
        ) STORED,
    ADD UNIQUE KEY uq_cpl_active_advertiser (active_advertiser_id),
    ADD UNIQUE KEY uq_cpl_active_offer (active_offer_id),
    ADD UNIQUE KEY uq_cpl_active_publisher (active_publisher_id),
    ADD CONSTRAINT chk_cpl_deduction_exactly_one_scope
        CHECK (
            (advertiser_id IS NOT NULL) +
            (offer_id IS NOT NULL) +
            (publisher_id IS NOT NULL) = 1
        );

-- 验收：三列、三条唯一索引与 CHECK 约束必须同时存在。
SET @cpl_scope_unique_schema_valid = (
    (SELECT COUNT(*) FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME = 'conversion_deduction_configs'
       AND COLUMN_NAME IN (
           'active_advertiser_id', 'active_offer_id', 'active_publisher_id'
       )
       AND EXTRA LIKE '%STORED GENERATED%') = 3
    AND
    (SELECT COUNT(*) FROM information_schema.STATISTICS
     WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME = 'conversion_deduction_configs'
       AND INDEX_NAME IN (
           'uq_cpl_active_advertiser',
           'uq_cpl_active_offer',
           'uq_cpl_active_publisher'
       )
       AND NON_UNIQUE = 0) = 3
    AND
    EXISTS (
        SELECT 1 FROM information_schema.TABLE_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
          AND TABLE_NAME = 'conversion_deduction_configs'
          AND CONSTRAINT_NAME = 'chk_cpl_deduction_exactly_one_scope'
          AND CONSTRAINT_TYPE = 'CHECK'
    )
);
SET @cpl_scope_unique_schema_sql = IF(
    @cpl_scope_unique_schema_valid,
    'SELECT 1',
    'SELECT * FROM __cpl_deduction_scope_unique_schema_mismatch__'
);
PREPARE cpl_scope_unique_schema_check FROM @cpl_scope_unique_schema_sql;
EXECUTE cpl_scope_unique_schema_check;
DEALLOCATE PREPARE cpl_scope_unique_schema_check;
