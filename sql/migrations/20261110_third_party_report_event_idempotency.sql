-- 第三方上报日志事件级幂等迁移（MySQL 8.0）
--
-- 目的：
-- 1. 同一 adsid 的 ViewContent 与 Purchase 必须分别留痕。
-- 2. 同一 source/adsid/event/conversion_id 的重试复用同一日志和稳定 event_id。
-- 3. 替换过宽的 unique_source_adsid 唯一约束。
--
-- 发布顺序（强制）：
-- 1. 先在隔离数据库演练并验证本迁移；生产发布时先完成数据库备份与审批。
-- 2. 在维护窗口先执行并验证本迁移，再部署包含 event_key 写入逻辑的新应用版本。
-- 3. 迁移未完成前禁止部署新应用版本，否则 ORM INSERT 会因缺少 event_key 失败。
-- 4. 本脚本仅定义迁移步骤；禁止本次审计或 CI 连接/执行生产数据库。
-- 5. MySQL DDL 会隐式提交，不能依赖事务整体回滚；回滚需按独立回退方案处理。
--
-- 迁移前检查：
-- SHOW INDEX FROM third_party_report_logs;
-- SELECT COUNT(*) FROM third_party_report_logs;
--
-- 1. 先允许为空，兼容历史数据回填。
ALTER TABLE third_party_report_logs
    ADD COLUMN event_key VARCHAR(64) NULL
    COMMENT '事件幂等键：稳定事件身份字段的 SHA-256（ViewContent 不含后补 conversion_id）'
    AFTER event;

-- 2. 与 app/core/third_party_report.py 的长度前缀算法保持一致；ViewContent 的后补 conversion_id 是关联元数据，不参与事件身份。
UPDATE third_party_report_logs
SET event_key = SHA2(
    CONCAT(
        CHAR_LENGTH(source), ':', source,
        CHAR_LENGTH(adsid), ':', adsid,
        CHAR_LENGTH(event), ':', event,
        CHAR_LENGTH(CASE WHEN event = 'ViewContent' THEN '' ELSE COALESCE(conversion_id, '') END), ':',
        CASE WHEN event = 'ViewContent' THEN '' ELSE COALESCE(conversion_id, '') END
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
        COMMENT '事件幂等键：稳定事件身份字段的 SHA-256（ViewContent 不含后补 conversion_id）',
    ADD UNIQUE INDEX unique_event_key (event_key);

-- 5. 迁移后验证。
SHOW INDEX FROM third_party_report_logs;
SELECT COUNT(*) AS rows_without_event_key
FROM third_party_report_logs
WHERE event_key IS NULL OR event_key = '';
