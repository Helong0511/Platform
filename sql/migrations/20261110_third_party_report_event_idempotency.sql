-- 第三方上报日志事件级幂等迁移（MySQL 8.0）
--
-- 目的：
-- 1. 同一 adsid 的 ViewContent 与 Purchase 必须分别留痕。
-- 2. 同一 source/adsid/event/conversion_id 的重试复用同一日志和稳定 event_id。
-- 3. 替换过宽的 unique_source_adsid 唯一约束。
--
-- 安全要求：
-- - 本脚本只定义迁移步骤；禁止在生产环境未经备份、审批和维护窗口直接执行。
-- - 先在隔离数据库完整演练，并核对行数、唯一键与历史日志。
-- - MySQL DDL 会隐式提交，不能依赖事务整体回滚。
--
-- 迁移前检查：
-- SHOW INDEX FROM third_party_report_logs;
-- SELECT COUNT(*) FROM third_party_report_logs;
--
-- 1. 先允许为空，兼容历史数据回填。
ALTER TABLE third_party_report_logs
    ADD COLUMN event_key VARCHAR(64) NULL
    COMMENT '事件幂等键：source、adsid、event、conversion_id 的 SHA-256'
    AFTER event;

-- 2. 与 app/core/third_party_report.py 的长度前缀算法保持一致。
UPDATE third_party_report_logs
SET event_key = SHA2(
    CONCAT(
        CHAR_LENGTH(source), ':', source,
        CHAR_LENGTH(adsid), ':', adsid,
        CHAR_LENGTH(event), ':', event,
        CHAR_LENGTH(COALESCE(conversion_id, '')), ':', COALESCE(conversion_id, '')
    ),
    256
)
WHERE event_key IS NULL;

-- 3. 必须先确认没有空值或碰撞，再继续添加唯一约束。
SELECT COUNT(*) AS missing_event_keys
FROM third_party_report_logs
WHERE event_key IS NULL OR event_key = '';

SELECT event_key, COUNT(*) AS duplicate_count
FROM third_party_report_logs
GROUP BY event_key
HAVING COUNT(*) > 1;

-- 4. 删除旧的过宽唯一索引，改为事件级唯一键。
ALTER TABLE third_party_report_logs
    DROP INDEX unique_source_adsid,
    MODIFY COLUMN event_key VARCHAR(64) NOT NULL
        COMMENT '事件幂等键：source、adsid、event、conversion_id 的 SHA-256',
    ADD UNIQUE INDEX unique_event_key (event_key);

-- 5. 迁移后验证。
SHOW INDEX FROM third_party_report_logs;
SELECT COUNT(*) AS rows_without_event_key
FROM third_party_report_logs
WHERE event_key IS NULL OR event_key = '';
