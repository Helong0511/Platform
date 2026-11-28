-- 防止删除广告主、Offer、渠道时通过 ON DELETE CASCADE 绕过扣量配置 scope 锁。
-- 已有 RESTRICT 约束保持不动；仅将仍为 CASCADE 的外键改为 RESTRICT。
-- 该迁移不删除、不迁移任何业务配置数据。

-- 在修改约束前，拒绝同一目标表上列映射错误的外键；不能误删其它业务约束。
SET @cpl_fk_mapping_mismatch_count = (
    SELECT COUNT(DISTINCT CONCAT(k.TABLE_NAME, ':', k.CONSTRAINT_NAME))
    FROM information_schema.KEY_COLUMN_USAGE k
    WHERE k.CONSTRAINT_SCHEMA = DATABASE()
      AND k.TABLE_NAME = 'conversion_deduction_configs'
      AND k.REFERENCED_TABLE_NAME IN ('advertisers', 'offers', 'publishers')
      AND (
          k.COLUMN_NAME <> CASE k.REFERENCED_TABLE_NAME
              WHEN 'advertisers' THEN 'advertiser_id'
              WHEN 'offers' THEN 'offer_id'
              WHEN 'publishers' THEN 'publisher_id'
          END
          OR k.REFERENCED_COLUMN_NAME <> 'id'
      )
);
SET @cpl_fk_mapping_validation_sql = IF(
    @cpl_fk_mapping_mismatch_count = 0,
    'SELECT 1',
    'SELECT * FROM __cpl_deduction_scope_fk_column_mapping_mismatch__'
);
PREPARE cpl_fk_mapping_validation FROM @cpl_fk_mapping_validation_sql;
EXECUTE cpl_fk_mapping_validation;
DEALLOCATE PREPARE cpl_fk_mapping_validation;

SET @cpl_adv_fk = (
    SELECT CONSTRAINT_NAME
    FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'conversion_deduction_configs'
      AND REFERENCED_TABLE_NAME = 'advertisers'
      AND DELETE_RULE = 'CASCADE'
    LIMIT 1
);
SET @cpl_adv_ddl = IF(
    @cpl_adv_fk IS NULL,
    'SELECT 1',
    CONCAT(
        'ALTER TABLE conversion_deduction_configs DROP FOREIGN KEY `',
        REPLACE(@cpl_adv_fk, '`', '``'),
        '`'
    )
);
PREPARE cpl_adv_drop_fk FROM @cpl_adv_ddl;
EXECUTE cpl_adv_drop_fk;
DEALLOCATE PREPARE cpl_adv_drop_fk;
SET @cpl_adv_restrict_exists = (
    SELECT COUNT(*)
    FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'conversion_deduction_configs'
      AND REFERENCED_TABLE_NAME = 'advertisers'
      AND DELETE_RULE = 'RESTRICT'
);
SET @cpl_adv_add_ddl = IF(
    @cpl_adv_restrict_exists > 0,
    'SELECT 1',
    'ALTER TABLE conversion_deduction_configs ADD CONSTRAINT fk_cpl_deduction_advertiser_restrict FOREIGN KEY (advertiser_id) REFERENCES advertisers(id) ON DELETE RESTRICT ON UPDATE RESTRICT'
);
PREPARE cpl_adv_add_fk FROM @cpl_adv_add_ddl;
EXECUTE cpl_adv_add_fk;
DEALLOCATE PREPARE cpl_adv_add_fk;

SET @cpl_offer_fk = (
    SELECT CONSTRAINT_NAME
    FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'conversion_deduction_configs'
      AND REFERENCED_TABLE_NAME = 'offers'
      AND DELETE_RULE = 'CASCADE'
    LIMIT 1
);
SET @cpl_offer_ddl = IF(
    @cpl_offer_fk IS NULL,
    'SELECT 1',
    CONCAT(
        'ALTER TABLE conversion_deduction_configs DROP FOREIGN KEY `',
        REPLACE(@cpl_offer_fk, '`', '``'),
        '`'
    )
);
PREPARE cpl_offer_drop_fk FROM @cpl_offer_ddl;
EXECUTE cpl_offer_drop_fk;
DEALLOCATE PREPARE cpl_offer_drop_fk;
SET @cpl_offer_restrict_exists = (
    SELECT COUNT(*)
    FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'conversion_deduction_configs'
      AND REFERENCED_TABLE_NAME = 'offers'
      AND DELETE_RULE = 'RESTRICT'
);
SET @cpl_offer_add_ddl = IF(
    @cpl_offer_restrict_exists > 0,
    'SELECT 1',
    'ALTER TABLE conversion_deduction_configs ADD CONSTRAINT fk_cpl_deduction_offer_restrict FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE RESTRICT ON UPDATE RESTRICT'
);
PREPARE cpl_offer_add_fk FROM @cpl_offer_add_ddl;
EXECUTE cpl_offer_add_fk;
DEALLOCATE PREPARE cpl_offer_add_fk;

SET @cpl_pub_fk = (
    SELECT CONSTRAINT_NAME
    FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'conversion_deduction_configs'
      AND REFERENCED_TABLE_NAME = 'publishers'
      AND DELETE_RULE = 'CASCADE'
    LIMIT 1
);
SET @cpl_pub_ddl = IF(
    @cpl_pub_fk IS NULL,
    'SELECT 1',
    CONCAT(
        'ALTER TABLE conversion_deduction_configs DROP FOREIGN KEY `',
        REPLACE(@cpl_pub_fk, '`', '``'),
        '`'
    )
);
PREPARE cpl_pub_drop_fk FROM @cpl_pub_ddl;
EXECUTE cpl_pub_drop_fk;
DEALLOCATE PREPARE cpl_pub_drop_fk;
SET @cpl_pub_restrict_exists = (
    SELECT COUNT(*)
    FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'conversion_deduction_configs'
      AND REFERENCED_TABLE_NAME = 'publishers'
      AND DELETE_RULE = 'RESTRICT'
);
SET @cpl_pub_add_ddl = IF(
    @cpl_pub_restrict_exists > 0,
    'SELECT 1',
    'ALTER TABLE conversion_deduction_configs ADD CONSTRAINT fk_cpl_deduction_publisher_restrict FOREIGN KEY (publisher_id) REFERENCES publishers(id) ON DELETE RESTRICT ON UPDATE RESTRICT'
);
PREPARE cpl_pub_add_fk FROM @cpl_pub_add_ddl;
EXECUTE cpl_pub_add_fk;
DEALLOCATE PREPARE cpl_pub_add_fk;

-- 验收：三条 scope 外键必须全部为 RESTRICT。
SET @cpl_restrict_count = (
    SELECT COUNT(DISTINCT k.REFERENCED_TABLE_NAME)
    FROM information_schema.KEY_COLUMN_USAGE k
    JOIN information_schema.REFERENTIAL_CONSTRAINTS r
      ON r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA
     AND r.CONSTRAINT_NAME = k.CONSTRAINT_NAME
     AND r.TABLE_NAME = k.TABLE_NAME
    WHERE k.CONSTRAINT_SCHEMA = DATABASE()
      AND k.TABLE_NAME = 'conversion_deduction_configs'
      AND (
          (k.COLUMN_NAME = 'advertiser_id' AND k.REFERENCED_TABLE_NAME = 'advertisers' AND k.REFERENCED_COLUMN_NAME = 'id')
          OR (k.COLUMN_NAME = 'offer_id' AND k.REFERENCED_TABLE_NAME = 'offers' AND k.REFERENCED_COLUMN_NAME = 'id')
          OR (k.COLUMN_NAME = 'publisher_id' AND k.REFERENCED_TABLE_NAME = 'publishers' AND k.REFERENCED_COLUMN_NAME = 'id')
      )
      AND r.DELETE_RULE = 'RESTRICT'
      AND r.UPDATE_RULE = 'RESTRICT'
);
SET @cpl_restrict_validation_sql = IF(
    @cpl_restrict_count = 3,
    'SELECT 1',
    'SELECT * FROM __cpl_deduction_scope_foreign_key_mismatch__'
);
PREPARE cpl_restrict_validation FROM @cpl_restrict_validation_sql;
EXECUTE cpl_restrict_validation;
DEALLOCATE PREPARE cpl_restrict_validation;
