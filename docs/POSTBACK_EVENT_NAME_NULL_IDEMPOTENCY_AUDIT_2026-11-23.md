# Postback event_name NULL 幂等边界修复记录（2026-11-23）

## 本次确认的真实风险

正式表 `postback_conversions.event_name` 与待审批表 `pending_postback_conversions.event_name` 在 ORM 和 `sql/platform.sql` 中都允许 NULL。正式表唯一键为：

```sql
UNIQUE (platform, conversion_id, event_name)
```

MySQL UNIQUE 索引允许同一组合中包含 NULL 的多行，因此不能依靠该索引保证 NULL 事件名的幂等性。

本次进一步确认了两个历史待审批转正式记录路径：

- `PostbackPendingService._pending_conversion_exists/_create_conversion_from_pending`
- Telegram `process_pending_conversion`

两条路径此前都直接使用 `pending.event_name` 做查重并写入正式记录。即使新入队流程已将缺失事件名规范成 `default`，历史待审批记录仍可能携带 NULL/空白并被重新写入正式表。

## 本次代码修复

新增轻量独立模块 `app/core/postback_event_name.py` 提供统一函数 `normalize_event_name(value)`。该模块不导入 `app.core.postback`，避免待审批入队服务提前触发 Postback 包初始化和处理器注册。规范规则：

- NULL、空字符串、纯空白统一为 `default`；
- 非空值去除首尾空白；
- DataNormalizer、待审批入队、DuplicateChecker 共用同一规范；
- Web/IP 白名单审批和 Telegram 审批在查重前先规范历史 pending 行，并将规范值回写 pending 行；
- 正式记录创建时使用规范后的值。

这样，历史 pending NULL 记录批准时会先按 `default` 查询正式记录；如果正式记录已存在，将走 already_exists，不会再创建 NULL 事件名的正式记录。

## 本次测试

新增/更新测试覆盖：

- NULL、空字符串、空白、正常事件名规范化；
- DataNormalizer 不再输出 NULL/空白 event_name；
- DuplicateChecker 对缺失事件名按 `default` 查询；
- Web/IP 批准路径在查重和正式写入前规范历史 NULL；
- Telegram 批准历史 NULL pending 时正式记录写入 `default`。

## 仍未完成：生产数据核查与 NOT NULL schema 迁移

本次没有连接生产数据库，也没有将 ORM/DDL 改为 NOT NULL。原因是尚未确认正式表和待审批表的历史 NULL/空白数量及重复组；直接 ALTER NOT NULL 或把 NULL 批量改成 default 可能将多条历史记录合并到同一个幂等键，必须先人工确认重复记录的业务归属。

生产只读预检 SQL：

```sql
SELECT 'postback_conversions' AS table_name,
       SUM(event_name IS NULL) AS null_count,
       SUM(event_name = '') AS empty_count,
       SUM(TRIM(event_name) = '') AS blank_count
FROM postback_conversions
UNION ALL
SELECT 'pending_postback_conversions',
       SUM(event_name IS NULL),
       SUM(event_name = ''),
       SUM(TRIM(event_name) = '')
FROM pending_postback_conversions;

SELECT platform, conversion_id,
       COALESCE(NULLIF(TRIM(event_name), ''), 'default') AS normalized_event_name,
       COUNT(*) AS row_count,
       GROUP_CONCAT(id ORDER BY id) AS record_ids
FROM postback_conversions
GROUP BY platform, conversion_id,
         COALESCE(NULLIF(TRIM(event_name), ''), 'default')
HAVING COUNT(*) > 1;

SELECT platform, conversion_id,
       COALESCE(NULLIF(TRIM(event_name), ''), 'default') AS normalized_event_name,
       COUNT(*) AS row_count,
       GROUP_CONCAT(id ORDER BY id) AS pending_ids
FROM pending_postback_conversions
WHERE status = 'pending'
GROUP BY platform, conversion_id,
         COALESCE(NULLIF(TRIM(event_name), ''), 'default')
HAVING COUNT(*) > 1;
```

正式表与待审批表之间的跨表重复也必须预检：

```sql
SELECT p.platform,
       p.conversion_id,
       COALESCE(NULLIF(TRIM(p.event_name), ''), 'default') AS normalized_event_name,
       p.id AS pending_id,
       c.id AS conversion_id
FROM pending_postback_conversions AS p
JOIN postback_conversions AS c
  ON c.platform = p.platform
 AND c.conversion_id = p.conversion_id
 AND COALESCE(NULLIF(TRIM(c.event_name), ''), 'default')
     = COALESCE(NULLIF(TRIM(p.event_name), ''), 'default')
WHERE p.status = 'pending'
ORDER BY p.platform, p.conversion_id, p.id, c.id;
```

执行前应在生产只读副本或只读账号下运行；不得先执行 UPDATE/ALTER。以上查询中的规范化表达式仅用于发现潜在冲突，不会修改任何记录。

只有在历史 NULL/空白和规范化后重复组已核实、处置并备份后，才可准备迁移：
1. 对规范化后会冲突的历史组逐条业务确认；
2. 明确 NULL/空白记录应归入 `default` 还是其它事件；
3. 先更新历史数据并复查重复组；
4. 再将两张表的 event_name 改为 NOT NULL；
5. 同步 ORM、`sql/platform.sql`、schema contract/迁移清单和 MySQL schema drift 测试；
6. 验证迁移重跑、备份恢复和回滚预案。

**Issue #146 保持开放**，直到生产数据预检和安全 schema 迁移验收完成。
