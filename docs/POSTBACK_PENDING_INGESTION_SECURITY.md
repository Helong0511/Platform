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

## 尚未完成的上线前事项

1. `pending_postback_conversions.request_ip` 保存服务端来源 IP，`ip` 保存回调用户/点击 IP；二者用途不同，均需按业务、审计和合规要求确定保留期限。
2. `postback_conversions.raw_data/ip/devad_id` 与 `pending_postback_conversions.raw_data/ip/request_ip` 的统一 PII 生命周期仍需单独设计。当前没有自动清理这些字段，不应自行设置期限或删除历史数据。
3. 10,000 条积压保护已改为单例 guard 行锁串行化容量检查；仍需在隔离 MySQL/InnoDB 环境验证多连接并发入队、锁等待超时、死锁回滚与事务释放。
4. 应在部署环境验证可信代理配置，确保 `get_client_ip()` 只信任受控代理传入的来源 IP，不能直接信任任意客户端可伪造的转发头。
5. 本次变更的真实 MySQL 迁移、Redis Lua 和端到端测试以 PR CI 结果为准；合并后还需在隔离环境进行部署验收。
