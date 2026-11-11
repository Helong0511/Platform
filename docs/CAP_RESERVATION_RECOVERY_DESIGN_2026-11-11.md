# Cap Reservation 持久化账本与崩溃恢复设计

> 状态：审计设计稿，尚未实现，不代表当前系统已具备恢复能力。  
> 适用范围：Postback 的 Daily / Total Cap Redis 预留。  
> 安全边界：仅允许隔离 CI MySQL、隔离 Redis、合成数据和 mock；禁止连接生产环境。

## 1. 当前问题与证据

当前 `increment_cap_count()` 的顺序是：

1. 锁定相关 `offer_caps` 行。
2. 调用 Redis Lua 原子增加 Daily / Total counter，并写入 reservation token。
3. 更新 ORM 中的 `current_daily_count/current_total_count`。
4. Postback 将 Cap、转化、短链和转发队列放在同一 DB 事务提交。
5. 正常异常路径使用 token 回滚 Redis。

该流程能处理 Python 异常和 COMMIT 响应不确定，但不能处理进程被强制终止、主机重启或容器被直接杀死：进程不会执行 `except/finally`，Redis reservation 可能保留，而 DB 转化事务回滚。Total counter 没有 TTL，可能永久占用名额。现有 Cap 同步任务会将 Redis 计数同步回 DB，因此孤儿计数还可能被固化到 DB 快照。

当前没有发现独立的 Cap reservation 持久化账本或崩溃恢复调度任务。现有 Redis token 只保留 30 天，不足以作为长期恢复依据。

## 2. 设计目标

- 每次 Redis 预留在发生前，都有独立 DB 已提交的持久化 PREPARED 记录。
- 同一个 Postback 事件、同一个 Cap scope、同一种计数类型只能对应一个 reservation。
- Redis 响应丢失、进程在任意步骤退出、DB COMMIT 响应不确定时均可恢复。
- 恢复任务不得把未知状态当作未预留；不得使用无 token 的 DECR。
- 已提交转化绝不能因恢复任务而减少 Redis 计数。
- 未提交转化的 Redis 预留最多撤销一次。
- Daily 与 Total 分开处理；Daily 的业务日期必须固定在 reservation 创建时。
- 现有历史计数必须有明确基线，不能因新增账本把旧计数清零。

## 3. 持久化模型建议

新增 `cap_reservations`，建议字段：

| 字段 | 用途 |
|---|---|
| id | 自增主键 |
| reservation_key | 稳定幂等键，唯一索引 |
| token | Redis reservation UUID，唯一索引 |
| platform | Postback 平台 |
| conversion_id | 原始转化 ID |
| event_name | 事件名（空值先规范化为稳定空字符串） |
| offer_id / publisher_id | 预留 scope 快照；publisher 可空 |
| cap_kind | daily / total |
| business_date | Daily 预留日期；Total 可空 |
| status | PREPARED / RESERVED / COMMITTED / ROLLED_BACK / DENIED / NEEDS_RECONCILIATION |
| conversion_db_id | 已知时保存正式转化记录 ID |
| attempts / last_error | 恢复次数及脱敏错误摘要 |
| created_at / updated_at / resolved_at | 生命周期时间 |

约束：

- `reservation_key` 唯一，按平台、转化 ID、事件名、Offer、Publisher、计数类型和业务日期生成稳定摘要。
- `token` 唯一；token 必须在 Redis 预留前持久化。
- 不建议对历史转化记录建立级联删除外键；账本必须能在 Cap 配置删除、重建后保留审计证据。
- 对 `status, updated_at` 建索引，恢复任务按批次分页并锁行。
- 所有时间使用应用业务时区对应的 naive datetime 约定，迁移与 ORM 必须一致。

如果 Postback 没有稳定的 `conversion_id`，必须使用已持久化且跨重试稳定的 request idempotency key；不能每次重试都生成新 UUID。无法获得稳定事件身份时，应拒绝自动创建可恢复 reservation，不能声称幂等。

## 4. 状态机

```text
PREPARED
  ├─ Redis 原子预留成功 ─────────> RESERVED
  ├─ Redis 明确超限 ────────────> DENIED
  └─ Redis 状态/网络不确定 ─────> NEEDS_RECONCILIATION

RESERVED
  ├─ 转化及业务事务已提交 ──────> COMMITTED
  ├─ 转化明确未提交且 token 回滚成功 -> ROLLED_BACK
  └─ DB / Redis 状态无法确认 ───> NEEDS_RECONCILIATION

NEEDS_RECONCILIATION
  ├─ 找到正式转化记录 ──────────> COMMITTED
  ├─ 确认无正式转化且 token 存在，回滚成功 -> ROLLED_BACK
  ├─ 确认无正式转化且 token 不存在 -> ROLLED_BACK（需记录判断证据）
  └─ 仍无法确认 ───────────────> 保持 NEEDS_RECONCILIATION 并告警
```

状态只能单向终结；COMMITTED / ROLLED_BACK / DENIED 不得被普通恢复任务重新打开。

## 5. 强制执行顺序

1. 在主 Postback 事务之外，通过独立 `AsyncSessionLocal` 插入或获取 PREPARED 账本行并提交。必须先持久化 token、scope 和事件身份。
2. 调用 Redis Lua。Lua 继续以 token 幂等：同 token 重试不得重复 INCR。
3. Redis 明确成功后，独立 DB session 将记录更新为 RESERVED；若进程在此更新前退出，PREPARED 记录仍足以让恢复任务检查 Redis token。
4. 将 Cap DB 快照、正式转化、短链状态和转发队列写入原业务事务。
5. 正式转化事务提交成功后，用独立 DB session 将 reservation 更新为 COMMITTED。若此步骤失败，恢复任务根据正式转化自然唯一键核对并补记 COMMITTED。
6. 若转化明确未提交，按 token 原子回滚 Redis，再把账本更新为 ROLLED_BACK。
7. 任意无法确认的情况保留 reservation，不得为了释放名额而盲目 DECR。

账本状态更新必须使用条件更新或行锁，避免两个恢复 worker 同时处理同一记录。Redis 回滚 Lua 必须保持 token 检查与 DECR 原子完成。

## 6. Redis token 生命周期

- Total counter 继续永久保留。
- 对处于 PREPARED / RESERVED / NEEDS_RECONCILIATION 的 Total token，不得设置短于恢复 SLA 的 TTL；推荐在终结前持久保留。
- 终结 token 的清理必须与账本状态策略一起设计；不能在账本仍可能恢复时删除 token。
- Daily counter 仍可按业务策略过期；账本保留原 business_date。恢复过期日期时不得误操作当天 Daily key。
- 增加 Lua 查询 token 状态接口，返回明确的 PRESENT / ABSENT；Redis 不可用或读取错误必须返回 UNKNOWN，而不是 ABSENT。
- Redis 整体数据丢失时，所有 scope 进入 NEEDS_RECONCILIATION。不能只凭 token ABSENT 推断原先从未预留；必须结合 DB 账本、正式转化和可信 DB 计数基线重建。

## 7. 历史计数基线与配置生命周期

新账本上线前，`offer_caps.current_total_count` 是已有 DB 快照，但可能不是 Redis 最新值。上线迁移/切换必须：

1. 在维护窗口确定 Cap 写入/预留切换策略，避免旧代码与新代码混跑。
2. 为每个当前有效 scope 记录基线快照，保留 Offer、Publisher、Total / Daily 类型和业务日期。
3. 对同一 Redis scope 下多个 Cap 配置，沿用当前逻辑取 DB 最大计数、限制取最小值。
4. 对已删除后重建的 scope，不得用新行的 0 覆盖历史 Total 基线。
5. 基线不完整或 Redis/DB 差异无法解释时停止自动恢复并告警，不能猜测。

## 8. 恢复任务

新增独立周期任务（建议每分钟执行，实际频率经压测确定）：

- 只扫描超过安全宽限期的 PREPARED / RESERVED / NEEDS_RECONCILIATION。
- 用 `SELECT ... FOR UPDATE SKIP LOCKED`（确认目标 MySQL 版本支持后）或等价租约机制并发领取。
- 先按稳定事件键查询 `postback_conversions(platform, conversion_id, event_name)`。
- 找到转化：标记 COMMITTED，不做 Redis 回滚。
- 未找到转化：查询 Redis token 状态；PRESENT 时执行 token 级原子回滚；ABSENT 时结合 Redis counter 和 DB 账本记录判断；UNKNOWN 时保持待核对并告警。
- 对每次处理保存 attempts、最后错误、处理 worker 和时间；超过阈值转人工告警。
- 每批设置数量上限、执行时限和退避，避免恢复任务挤占正常 Postback 连接池。
- 恢复任务不得调用真实第三方接口。

## 9. 故障注入测试矩阵

必须在隔离 MySQL + 隔离 Redis 中覆盖：

1. PREPARED 提交后、Redis 调用前进程退出。
2. Redis Lua 已执行，但响应丢失。
3. Redis 成功后、账本 RESERVED 更新前进程退出。
4. RESERVED 后、转化 INSERT 前退出。
5. 转化 INSERT/flush 后、主事务 COMMIT 前退出。
6. DB 已提交但 COMMIT 响应丢失。
7. DB 已提交、账本 COMMITTED 更新前退出。
8. Redis 回滚成功、账本 ROLLED_BACK 更新前退出。
9. Redis 回滚响应丢失后恢复重试，不得重复 DECR。
10. 两个恢复 worker 同时领取同一 reservation。
11. 相同 Postback 并发重试，唯一账本键和 Redis token 不重复计数。
12. 同一事件 Daily + Total、多个 Cap 配置共享 scope 时各计数只增加一次。
13. 午夜跨日后恢复前一日 Daily reservation。
14. Total token 长时间待恢复，不得因 TTL 消失。
15. Redis 整体数据丢失、部分 key 缺失、token 与 counter 不匹配。
16. Cap 删除重建后，历史 Total 不得回退。
17. 恢复任务 DB/Redis 不可用、超时、进程再次退出。
18. 迁移重复执行、唯一索引、utf8mb4 中文内容和回滚演练。

每个用例必须断言：Redis counter、token、DB Cap 快照、正式转化行、账本状态五者的最终关系。不能只断言函数返回值。

## 10. 上线与回滚约束

- 本设计尚未实现；不得据此部署。
- 新表迁移必须先在隔离 MySQL 8.0 演练，验证重复执行、索引、字符集和备份恢复。
- 生产迁移需单独备份、审批和维护窗口；当前审计/CI 禁止连接生产数据库。
- 迁移前后需明确新旧应用混跑策略；不允许一部分 worker 写账本、另一部分 worker 不写账本却共同修改同一 Redis Cap counter。
- 回滚应用版本前，必须先停止新恢复 worker，并制定账本与 Redis token 的保留策略；禁止直接删表或清空 Redis token。
- PR 必须在实现、故障注入、隔离 CI 全绿及发布/回滚手册完成前保持 Draft。


## 11. 已核实的现有 Postback 幂等约束（2026-11-11 代码核对补充）

本节是对上文事件身份设计的代码核验补充：

- `PostbackConversion` 模型确实定义了数据库唯一约束 `uq_postback_platform_conversion_event(platform, conversion_id, event_name)`。因此正式转化的主事件键不是推测出来的，而是现有数据库约束。
- `DataNormalizer.normalize()` 将缺失或空白 `event_name` 统一为非空字符串 `default`，并将 conversion_id 标准化为字符串；`DuplicateChecker` 在保存前按 platform + conversion_id + event_name 预查。
- `PostbackConversion.event_name` ORM 列目前仍声明 nullable=True，但正常标准化路径会提供 `default`。历史数据或绕过标准化的写入仍可能写入 NULL；MySQL UNIQUE 对 NULL 的处理不能保证 NULL 事件键唯一。新增 Reservation 不能把历史 NULL 与字符串 default 默认为同一事件，必须按正式业务规则确定兼容处理。
- `conversion_id` 在模型层 NOT NULL，但标准化后可能是空字符串；在 Reservation 开始前必须确认验证器是否拒绝空字符串。若没有拒绝，应在同一改造中 fail-closed 拒绝无稳定事件 ID 的 Postback，不能给空 ID 自动生成每次请求不同的幂等键。
- 现有唯一约束可作为最终并发防重保护；预查只是快速路径，不能替代唯一约束。两个并发请求同时通过 DuplicateChecker 时，后续唯一约束冲突分支必须回滚各自 reservation。
- `transaction_id` 和 `request_id` 是独立的 nullable unique 字段，不应在没有上游语义证明前拿其中任一字段替代三元组事件身份。

### Reservation 唯一键建议（以现有数据库业务键为基础）

每个 Redis scope 的每一种计数类型独立一条账本记录。稳定唯一键建议由以下规范化字段构成，再进行 SHA-256：

`platform | conversion_id | event_name | offer_id | publisher_scope | cap_kind | business_date`

其中：

- `platform`、`conversion_id`、`event_name` 使用与正式转化保存完全一致的标准化值。
- `publisher_scope` 必须明确区分全局 NULL 与具体 publisher ID；不能把 NULL 转为空字符串后与其他业务字段产生歧义。
- `cap_kind` 为 daily / total；Daily 必须包含固定业务日期，Total 日期使用固定空值标记。
- Redis token 应由账本行稳定生成并先提交，再执行 Redis Lua；重试同一事件/同一 scope/type 必须复用同一 token。
- 现有 cap_manager 对相同 `(offer_id, publisher_id)` 下多个 Cap 配置只预留一次 Daily、一次 Total。因此账本也按 Redis 实际计数 scope 建记录，不能按 OfferCap ORM 行数创建重复预留。

### 还需在实现前完成的验证

1. 检查 `DataValidator` 是否拒绝空 `conversion_id`，并检查所有 Postback 入口是否统一经过 DataNormalizer。
2. 在隔离 MySQL 中验证现有唯一约束实际存在、列字符集/排序规则与大小写比较语义；不能只依赖 ORM 定义。
3. 检查历史正式转化表是否存在 NULL/空 conversion_id 或 NULL event_name；只读统计应在隔离数据快照上执行，生产数据不得由本审计连接。
4. 检查现有唯一约束冲突分支是否只在真正的事件重复时触发；不能把其他唯一字段冲突一律报告为重复事件。
5. 对历史 NULL event_name 的转换规则必须由业务语义决定，迁移不得静默将 NULL 改成 default。
