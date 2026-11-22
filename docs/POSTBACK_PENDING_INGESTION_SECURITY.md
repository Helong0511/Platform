# 非白名单 Postback 待审批入队安全说明

## 业务规则

非白名单来源的 Postback 不再直接静默丢弃。请求通过来源 IP 检查、请求大小限制、字段验证、Redis 限流和脱敏后，写入 `pending_postback_conversions`，状态为 `pending`。

**待审批阶段不会：**
- 创建 `postback_conversions` 正式转化；
- 扣减或预留 Offer/Publisher/Advertiser Cap；
- 创建下游转发队列；
- 创建第三方 Report Outbox；
- 触发正式转化通知。

管理员通过 Web/Telegram 批准后，既有审批服务才会创建正式转化；拒绝则只变更待审批状态并写审批审计。新增 IP 白名单后，既有自动批准流程仍然有效。

## 接收端保护

| 控制 | 当前策略 |
|---|---|
| 来源 IP | 只使用服务端解析的连接来源 IP；缺失、unknown 或无效 IP 不入队 |
| 平台名称 | 仅允许 1–50 位字母、数字、点、下划线和连字符，首位必须为字母或数字 |
| 请求体 | JSON / URL-encoded；单个 Body 或 Query 最多 64 KiB |
| 字段数量 | Query、Body、合并后的字段数最多 200 |
| 文件上传 | 不接受 multipart/form-data |
| 原始快照 | 入队前递归脱敏；存储上限 32 KiB |
| 敏感字段 | 不在 raw_data 快照中保留邮箱、电话、IP、设备广告标识、UA、凭证等 |
| 入队限流 | Redis Lua 原子计数：每来源 IP 每小时 20 次、每天 100 次；全局每小时 500 次、每天 5,000 次 |
| Redis 故障 | fail-closed，返回可重试 503；不降级为单进程内存计数 |
| 重复回调 | SHA-256 dedupe_key + MySQL 唯一索引，防止并发重复入队 |
| 待审批积压 | 入队前锁定 MySQL 单例 guard 行，再执行 pending COUNT 与 INSERT；并发入队串行化，达到 10,000 条时返回可重试 503 |


## 上游响应与重试语义

- 入队成功和已存在的幂等重复记录返回固定成功响应；重复请求不会再次插入待审批记录。
- Redis 不可用、待审批队列达到容量上限、入队提交失败、来源 IP 缺失/无效，以及入队限流命中，均不得向上游返回 HTTP 200。Processor 返回可重试失败，由接收入口统一返回 HTTP 503，避免上游把未入队的合法转化永久标记为成功。
- 未识别的入队结果也按 fail-closed 处理并返回可重试失败，不能静默当作已接收。
- 限流窗口到期后，上游按其重试策略重新发送；当前通用 503 响应不包含精确的 Retry-After 时间，后续如需精确退避，应扩展 Lua 限流结果以区分小时/日限额并返回对应等待时间。

限流 Redis key 使用来源 IP 的 SHA-256 摘要，不把明文 IP 放入 Redis key；同时使用全局计数，降低攻击者轮换来源 IP 绕过限流的风险。

注意：raw_data 快照会删除 IP、devad_id 和 UA 等敏感键；为保持审批转正后的业务字段完整，经过长度/格式校验的回调用户 IP 与 devad_id 仍分别保存在 `ip`、`devad_id` 专用列中。服务端连接来源 IP 单独保存在 `request_ip`，不使用回调体自报值。接收入口不会把服务端来源 IP 注入回调 `ip` 字段；当回调未提供用户 IP 时，`ip` 保持为空，正式转化可从可信 Click 关联快照取得点击 IP。上述专用字段仍属于 PII，必须纳入后续保留期限设计。

## 数据库迁移

新增迁移：

- `sql/migrations/20261121_postback_pending_dedupe.sql`：为 `pending_postback_conversions` 增加可空 `dedupe_key` 和唯一索引。历史记录保持 NULL，不执行历史数据去重或删除。MySQL 唯一索引允许多条 NULL，因此只约束新入队记录。
- `sql/migrations/20261121_postback_pending_queue_guard.sql`：创建 InnoDB 单例互斥表并初始化 `id=1`。每次入队必须先执行 `SELECT ... FOR UPDATE` 锁定该行，再读取 pending 数量并插入记录；行锁持有到入队事务提交。guard 行缺失或迁移未执行时 fail-closed，不会绕过容量保护。

容量上限依赖 MySQL/InnoDB 行锁语义；不要在 SQLite 或不支持行级锁的数据库上将其视为并发保护。

部署前必须通过项目迁移 Runner 检查并应用迁移；不要跳过迁移直接发布新代码。迁移清单 SHA-256 已登记在 `app/db/migrations/manifest.py`。

## 本地与生产依赖

待审批入队限流依赖 Redis。生产环境必须配置可用的 Redis；Redis 不可用时请求会返回 503，等待上游重试，不能放宽为无保护入队。

Windows 本机如果没有启动 Redis，非白名单请求也会 fail-closed。测试中通过 mock Redis 验证限流，不要求连接真实 Redis。

## 测试范围

- 正常入队与 raw_data 脱敏；
- 缺失、无效来源 IP 不入队；
- 无效字段和超大载荷拒绝；
- Redis 不可用时 fail-closed；
- Redis Lua 原子限流与超限拒绝；
- 已存在 dedupe_key 时重复请求不再插入；
- 待审批容量检查先锁定单例 guard 行，guard 缺失时 fail-closed；
- 队列达到上限时回滚并返回可重试失败，避免向上游返回 200 后丢弃回调；
- 请求体大小、字段数、Content-Type 和 UTF-8 JSON/Form 解析边界；
- Processor 的非白名单路径只创建待审批记录，不进入正式转化流程。

## PII 生命周期与尚未完成的上线前事项

### 待审批记录的终态清理

新增独立配置 `PENDING_POSTBACK_PII_RETENTION_DAYS`，默认 `0`（关闭），与第三方上报/下游转发日志的 `THIRD_PARTY_REPORT_PII_RETENTION_DAYS` 分离，避免不同业务数据被同一保留期限误伤。

- 只允许清理创建时间超过独立保留期限且状态为 `approved` 或 `rejected` 的终态记录。
- `pending` 状态永不由此任务清理，避免自动删除仍等待管理员处理的回调。
- 清除设备广告 ID、操作系统/运营商、用户 IP、渠道 ID、Click ID/时间、原始 JSON、服务端请求 IP、Telegram 消息 ID/Chat ID。
- 保留 `platform`、`conversion_id`、`event_name`、`dedupe_key`、金额/财务字段、状态、时间戳及记录 ID，以维持幂等去重、对账和审批审计关联。
- `request_ip` 是非空列，清理时写空字符串；API/后台展示必须将空值视为“已按策略清理”，不得把空字符串解释为有效来源 IP。
- 使用 `FOR UPDATE SKIP LOCKED`、按 `created_at,id` 排序、每批最多 1,000 条，避免多个 Scheduler Worker 重复争抢同一批记录。该语法会跳过已锁定行，适合队列式并发消费，不应被用于要求完整一致视图的普通业务查询。
- MySQL 官方明确指出 `NOWAIT/SKIP LOCKED` 对 statement-based replication 不安全；若生产启用 binlog/复制，部署前必须核验 `binlog_format=ROW`（或经 DBA 确认安全的 MIXED），不能使用纯 STATEMENT。
- 每日 PII 任务独立执行此清理；第三方 Report 清理开关与待审批记录清理开关互不影响。

新增迁移 `20261122_pending_postback_pii_retention`，只增加 `pii_scrubbed_at` 和 `(pii_scrubbed_at,status,created_at,id)` 索引，不改写历史 PII。全新基线 `sql/platform.sql` 同步包含字段和索引；旧库必须通过 Migration Runner 应用迁移。

### 仍需业务/合规审批或专项设计

1. `PENDING_POSTBACK_PII_RETENTION_DAYS` 与 `THIRD_PARTY_REPORT_PII_RETENTION_DAYS` 继续默认 0；未经业务/合规负责人批准，不得在生产启用任何自动清理期限。
2. `pending` 状态记录没有自动过期策略；需要单独确定审批 SLA、超期拒绝/隔离规则、人工复核和上游重放处理，不得将未决记录直接按终态清理。
3. `postback_conversions.raw_data/ip/devad_id` 正式转化数据仍需独立生命周期设计；待审批终态清理不代表正式业务记录也可清理。
4. 审批通过后数据会复制到正式转化表；应明确两份记录的保留期限、对账要求、访问权限和备份副本保留期。
5. 10,000 条积压保护已改为单例 guard 行锁串行化容量检查；仍需在隔离 MySQL/InnoDB 环境验证多连接并发入队、锁等待超时、死锁回滚与事务释放。
6. 应在部署环境验证可信代理配置，确保 `get_client_ip()` 只信任受控代理传入的来源 IP，不能直接信任任意客户端可伪造的转发头。
7. 本次变更的真实 MySQL 迁移、Redis Lua 和端到端测试以 PR CI 结果为准；合并后还需在隔离环境进行部署验收。
