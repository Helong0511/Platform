# Cap Reservation 持久化账本与崩溃恢复设计

> 状态：实现与验收记录（2026-11-11）。Cap Reservation 账本、Postback 接入和恢复 Worker 已在后续章节落地；是否具备部署条件，以最新 SHA 的 CI、故障注入结果及部署手册为准。  
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

早期审计基线：当时尚未发现独立的 Cap reservation 持久化账本或崩溃恢复调度任务。该问题已在第 13、14 节记录后续实现；本段仅保留问题发现时的历史描述。

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

- 本设计早期阶段尚未实现；后续实现及部署约束见第 13–16 节和 `docs/DEPLOYMENT_READINESS_RUNBOOK_2026-11.md`。
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


## 12. 已核实的模型、迁移与任务注册机制（2026-11-11）

### ORM 与会话

- ORM 基类为 `app.models.base.Base`；`app.models.models` 聚合导入各模型模块。
- `app.core.database.AsyncSessionLocal` 是当前异步会话工厂，可创建独立账本会话；它使用同一配置数据库引擎/连接池，不是独立数据库。
- `create_tables()` 只调用 `Base.metadata.create_all`。它可以创建缺失的新表，但不会为已有表自动增加/修改列和索引。
- 因此新增 Reservation 模型仍必须配套显式 SQL migration；不能以应用启动的 create_all 代替迁移。
- 当前仓库已有手工 SQL migration 目录 `sql/migrations/`，脚本注释要求先隔离环境演练、生产备份审批，并明确 MySQL DDL 隐式提交及独立回退步骤。此次审计和 CI 不执行生产迁移。

### Scheduler 注册

- 任务配置来源是 `app/scheduler_module/task_config.py`；启动初始化会将配置同步到 `scheduled_tasks`，注册器按 task_config 动态加载函数。
- 新增恢复任务必须同步 task_config、任务函数、任务结果存储和测试；若新增任务名常量，还要检查 `task_names.py` 的映射/ALL_TASK_NAMES 清单一致性。
- 账本恢复任务不能只靠单进程内存锁；需要数据库行锁/租约与条件状态更新，确保多 worker 或调度重叠时只由一个 worker 处理同一条记录。
- 恢复任务必须有独立的失败/积压指标：PREPARED/RESERVED 超时数量、最老未解决年龄、Redis UNKNOWN 数量、回滚失败数量。任何 UNKNOWN 均不得被自动当成 ABSENT。

### 推荐实现顺序（确认后再逐阶段落代码）

1. 新增 ORM `CapReservation` 并从统一模型模块导出；建立 migration（唯一键、状态/时间索引、必要外键策略）。
2. 设计独立 ledger service：PREPARED 先 commit；Redis 操作成功后标记 RESERVED；主业务转化 commit 后标记 COMMITTED。
3. 让 Cap manager 接收由账本产生的稳定 token；重试必须复用 token。现有随机 UUID 只能作为无账本兼容路径，不能继续用于可恢复 reservation。
4. 增加 Redis token 三态查询（PRESENT / ABSENT / UNKNOWN），必须避免 Redis 不可用、key 缺失、token 缺失三者混为一谈。
5. 增加恢复任务：先用正式事件唯一键查询转化；存在则 COMMITTED；明确不存在且 token PRESENT 才原子回滚；Redis UNKNOWN 保持待处理并告警。
6. 处理跨日 Daily key、Total 永久 key、Redis 整体数据丢失及 DB 基线恢复；Redis key 缺失不能直接按 0 初始化。
7. 完成故障注入和并发测试后，再做隔离 MySQL/Redis CI 全量回归。

### 当前实现边界

以上是早期架构核验和实施约束。账本、恢复 Worker、三态查询及 migration 的后续实现状态见第 13、14 节；最终部署门槛以第 15、16 节及部署手册为准。


## 13. 账本基础结构与服务已落地（2026-11-11 后续提交）

以下内容已实际提交到审计分支；它们属于基础设施阶段，不应误报为完整恢复闭环：

- ORM：`app/models/cap_reservation.py`，包含稳定唯一键、正式事件字段、Cap scope、Redis counter/token key 快照、`redis_reserved` 标志、状态、尝试次数、租约字段及恢复索引。`redis_reserved=false + COMMITTED` 可明确表达 fail-open 下没有 Redis token、但 DB Cap 快照随业务事务提交的路径。
- 模型聚合：`app/models/models.py` 与 `app/models/__init__.py` 均导出 `CapReservation`，使共享 `Base.metadata` 能发现新表。
- SQL migration：`sql/migrations/20261111_cap_reservation_ledger.sql`，字段类型与 ORM 对齐；迁移文件只供发布评审，CI 不执行生产迁移。
- 独立服务：`app/services/cap_reservation_ledger.py` 使用 `AsyncSessionLocal`，提供稳定身份生成、独立会话 PREPARED 创建、RESERVED 标记、COMMITTED/ROLLED_BACK 终态确认和 NEEDS_RECONCILIATION 标记。
- 测试：`tests/test_cap_reservation_model.py` 验证 metadata 注册和索引；`tests/test_cap_reservation_ledger_identity.py` 验证稳定键、publisher NULL scope、Daily 日期、cap kind 和非法输入。

### 第 13 节编写时仍未完成的事项（历史状态，已由第 14 节后续实现覆盖）

以下 1–6 项是第 13 节编写时的历史状态；第 14 节记录了后续代码接入和恢复 Worker 实现，不得将这些旧描述当作当前代码状态。

1. `CapReservationLedger.prepare()` 尚未接入 `increment_cap_count()`；当时 Redis reservation 仍由 cap_manager 生成随机 UUID。
2. `mark_reserved/finalize` 尚未接入 Postback 预留、DB commit、rollback 与 commit reconciliation 生命周期。
3. Redis token 三态核验尚未实现；Redis UNKNOWN、counter key missing、token ABSENT 尚无统一恢复语义。
4. 恢复 Worker、数据库 lease 抢占、条件状态更新、任务配置与积压监控尚未实现。
5. Daily 48 小时 key/token 生命周期、Total 长期 token 保留、Redis 整体数据丢失、历史基线恢复尚未完成设计验证与故障注入。
6. 当前新增测试仅验证模型与稳定身份规则，不覆盖跨存储事务恢复，不代表孤儿 reservation 风险已消除。

当时下一步需要明确 fail-open 的账本状态语义；该语义及其后续实现见第 14 节。无论如何，Redis 结果 UNKNOWN 时都不得误标 ROLLED_BACK。


## 14. Postback 接入与恢复任务实现（2026-11-11）

### 已落地的运行时链路

- Postback 将标准化后的 `platform + conversion_id + event_name` 传入 Cap Manager。
- 每个实际 Redis scope 的 Daily / Total 计数器预留前，账本服务使用独立 `AsyncSessionLocal` 提交 PREPARED，并通过数据库行锁 + 5 分钟 lease claim 防止同一事件并发请求复用同一 token。
- Redis reservation token 使用账本 SHA-256 稳定键；同一事件重试不会生成随机新 token。
- Redis Lua 成功后独立标记 RESERVED；若 Redis 预留成功但标记失败，会按同一 token 补偿，无法确认时进入 NEEDS_RECONCILIATION。
- Fail-open 没有真实 Redis token 时，账本保持 `redis_reserved=false`，但仍随 Postback 业务提交/回滚完成终态，避免恢复任务误 DECR。
- Postback DB COMMIT 前续租；DB commit 成功后将账本标记 COMMITTED；保存失败/明确未提交时按原始 token 回滚并标记 ROLLED_BACK。
- COMMIT 响应不确定时仍以正式转化事件键核验；正式事件存在则保留计数并完成 COMMITTED；未知结果保留账本待恢复。
- Daily 与 Total 活动 token 不使用固定 TTL；终态后清理 token。COMMITTED token 清理失败会记录 `redis_token_cleaned=false`，恢复任务后续重试。

### 恢复 Worker

- 新增 `app/services/cap_reservation_recovery.py`。
- 新增调度任务 `Cap Reservation 崩溃恢复`，每分钟执行，任务配置在 `task_config.py`。
- 通过 MySQL `FOR UPDATE SKIP LOCKED` + lease 领取到期 PREPARED / RESERVED 和待清理的 COMMITTED 记录，多 Worker 不会同时处理同一行。
- 恢复顺序：先按正式唯一事件键查转化；存在则 COMMITTED；不存在时检查 Redis token 三态。
- token PRESENT：只按账本保存的 counter key + token key 调用原子 rollback。
- PREPARED 且 `redis_reserved=false`、token ABSENT：可安全终结 ROLLED_BACK。
- `redis_reserved=true` 但 token ABSENT，或 Redis UNKNOWN、token 存在但 counter 丢失：进入 NEEDS_RECONCILIATION，绝不猜测性 DECR。
- COMMITTED token 清理失败单独重试，不回退已提交计数。

### 新增测试

- Postback stable token 注入、Fail-open 无 token、RESERVED 状态标记、同事件租约竞争拒绝。
- DB commit 前续租、commit 后终态确认。
- Redis token PRESENT / ABSENT / UNKNOWN 与原始 key 原子回滚。
- 崩溃发生在 Redis Lua 成功后、账本 RESERVED 标记前的恢复。
- Redis token ABSENT 时不做猜测性 DECR。
- 已提交账本 token 清理失败后的重试路径。
- ORM 与 SQL migration 包含 `redis_reserved`、`redis_token_cleaned` 两个标志字段。

### 上线前仍必须完成

1. 在隔离 MySQL 8.0 实际执行 migration 并核对 `SHOW CREATE TABLE`、索引、字段类型和字符集；当前 CI 的 SQLite 单测不能替代 MySQL DDL 演练。
2. 补齐故障注入矩阵：PREPARED 后 kill、Redis Lua 执行后响应丢失、RESERVED 更新响应丢失、主 DB flush/commit 前后 kill、commit 响应丢失、Redis flush、Daily 跨日、Total 长期计数、多个恢复 Worker 竞争、恢复期间 Postback 重试。
3. 验证 Cap 同步任务在账本待处理/NEEDS_RECONCILIATION 状态下不会将不确定计数固化成 DB 基线；必要时在缺 key 且同 scope 有未决账本时 fail-closed。
4. 验证 Scheduler 多实例配置、任务启停、失败告警与积压监控；不能仅凭 task_config 有配置就认定生产调度器已经执行。
5. 完成迁移发布顺序、备份、回滚、应用版本兼容及观察指标手册。
6. 最新 HEAD 的 Backend、Frontend、Playwright Mock API E2E 必须全部通过；任何旧 SHA 的成功结果都不能替代最新 SHA。
7. PR #1 在以上事项全部验收前必须保持 Draft，不得合并 main；严禁连接生产服务。



## 15. 当前 CI 验收与历史失败复核（2026-11-11）

### 最新 HEAD 验收

- Run #755：SHA `01faeda301c9df4b9997abd2fa63282da8b266a1`。
- Backend / Frontend / Playwright Mock API E2E 全部成功。
- Backend：286 passed、1 skipped、1 warning、0 failed。
- 新增 MySQL 8.0 隔离迁移集成测试实际执行 Cap Reservation migration 两次，验证幂等性、已插入账本数据保留、字段类型、NULL 语义、索引和 utf8mb4_unicode_ci。
- 1 skipped 是仓库既有本地核对脚本未检出提示，不是 Cap Reservation 测试跳过。
- 链接：https://github.com/Helong0511/Platform/actions/runs/42962433620

### 历史失败归因

对分支近期历史失败记录进行日志抽查，发现它们来自不同旧 SHA，主要包括：

- Publisher 转发队列测试 FakeDB 未模拟新增的转化行锁查询结果；后续修正测试夹具并在后续 SHA 通过。
- 前端日汇总文件的 ESLint 无用赋值；后续代码修复并在最新 lint/build 通过。
- 第三方上报手动重试测试假设 SQL 将状态字面量内联，实际 SQLAlchemy 使用绑定参数；后续测试改为验证绑定参数语义。
- Cap scope 测试 FakeDB 未模拟新增的 Offer 行锁查询；后续夹具更新并在后续全量测试通过。
- 短链点击刷盘的提交响应不确定、ACK 失败和重放测试曾失败；后续实现修复并通过全量测试。
- pytest-asyncio session fixture 与 function loop 的作用域冲突；后续统一异步资源清理/loop 作用域。
- 本轮 Run #750 的新提交测试没有隔离租约续期操作；已修正测试 mock，Run #751 通过。
 
这些历史 Run 保留为审计证据；不能把旧 SHA 的失败直接算作最新 HEAD 的失败，也不能用最新绿色 CI 声称旧 Run 本身被改写。后续任何提交仍必须重新核验最新 SHA。


## 16. 跨存储集成、租约竞争与运行监控补充

- 新增 `tests/test_cap_reservation_mysql_redis_integration.py`：每次测试创建独立临时 MySQL database，执行账本 migration，建立最小正式事件表；使用 CI Redis DB14 执行真实 Lua reservation / rollback。
- 覆盖真实崩溃场景：Redis Lua 已成功但进程在 RESERVED 标记前退出；恢复 Worker 按稳定 token 回滚。
- 覆盖正式转化已提交：恢复 Worker 保留 counter、删除 token、确认 COMMITTED。
- 覆盖并发首次 claim：两个请求竞争相同稳定键，只允许一个 lease owner；对 MySQL 1205/1213 死锁/锁等待竞争回滚后重新读取赢家，网络错误仍向上抛出。
- 覆盖两个恢复 Worker 同时领取：依赖 `FOR UPDATE SKIP LOCKED` 与 lease，只能有一个 worker 回滚同一条记录。
- 新增恢复积压状态查询：PREPARED / RESERVED / NEEDS_RECONCILIATION 数量、COMMITTED token cleanup pending 数量、最老待处理年龄；调度任务将这些指标写入任务结果并在异常/积压时告警。
- Redis Lua 对现存 counter、DB baseline、Cap limit 都校验为非负/正整数；回滚前先校验计数格式，损坏时返回未知状态并保留 token，不先删除证据再执行 DECR。
- Daily token 与 Total token 在账本终态前不设置固定 TTL。Daily 业务日已过去至少两天且 48h counter key 已不存在时，恢复任务仅清理历史 token，不对已过期 counter 执行 DECR。
- 新增 `sql/platform.sql` 的完整建表定义，保证新数据库初始化和增量 migration 都包含 Cap Reservation 表。
- 新增 `docs/DEPLOYMENT_READINESS_RUNBOOK_2026-11.md`，明确旧版本随机 token 切换风险、MySQL migration 顺序、独立 Scheduler 服务启用顺序、观察指标与回滚边界。

### 最新跨存储验收证据

Run #783 / SHA `042026e6c654753ec91b2ec72748c85d94b11f61`：Backend、Frontend、Playwright Mock API E2E 全绿，293 passed、1 skipped。此 SHA 已覆盖真实隔离 MySQL + Redis 的崩溃恢复、提交保留、并发 claim 和双恢复 Worker 测试。后续任何代码提交仍须重新验收最新 SHA。


### 14. 租约与 Redis token 丢失边界补充（2026-11-11）

- 重复 Postback 不得仅因 PREPARED/RESERVED 租约过期就接管活动账本。旧 Worker 可能只是长时间暂停，并未死亡；若新请求复用同一 Redis token，旧请求随后恢复并回滚，可能撤销新请求已提交的名额。现已改为：PREPARED/RESERVED 对业务重试始终返回处理中；只有恢复 Worker 在核验正式转化与 Redis token 后才能接管。
- Redis token ABSENT 不等于没有发生过 INCR。allkeys 淘汰策略、人工删除或部分 Redis 数据丢失可能只删除 token 而保留 counter。恢复逻辑现要求同时检查 counter key：只有 token ABSENT 且 counter key 明确不存在，才可结束为 ROLLED_BACK；counter 仍存在或无法确认存在性时进入 NEEDS_RECONCILIATION，不执行 DECR。
- 对应新增隔离 MySQL 集成测试：过期租约不得被重复 Postback 抢占；新增恢复单测：token 丢失但 counter 仍存在时必须转人工对账。


### 15. 数据库约束加固（2026-11-11）

账本模型和 MySQL migration 已增加同名 CHECK 约束，防止绕过 Service 的写入破坏恢复依据：

- SHA-256 reservation_key 必须为 64 字符。
- offer_id 必须为正数；publisher_id 只能为 NULL 或正数。
- attempts 不得为负数。
- Daily 必须有 business_date；Total 必须没有 business_date。
- state 只能为状态机定义的五种状态。

MySQL 目标版本为 8.0.16+（CHECK 约束实际执行版本）。隔离 CI 的 migration 集成测试负责校验建表和实际 ORM 写入；正式数据库仍未连接、迁移仍未执行。
## 17. Token 缺失回滚歧义与数据库级约束补充（2026-11-11）

### Token ABSENT 不等于回滚成功

复核 Redis 回滚 Lua 时发现旧返回值 `0` 同时表达“token 已不存在”和“重复回滚未扣减”。调用方将 `0` 视为成功，可能在 token 被独立淘汰、但 counter 仍存在时，把活动账本错误终结为 ROLLED_BACK。

修复后约定：

- `_ROLLBACK_RESERVATION_LUA` 在 token 不存在时返回 `-3`，不执行 DECR，也不删除或改写任何其它 token。
- 调用方将 `-3` 视为状态不确定，活动账本转入 NEEDS_RECONCILIATION；不得把它当作成功。
- 已完成的第一次回滚仍只扣减一次；后续重复调用会得到 `-3`，并要求调用方结合持久化账本状态判断，避免把“token 消失”错误解释成“回滚已确认”。
- 新增单测、Postback 回滚状态测试和隔离 Redis 集成测试覆盖该行为。

### 数据库层不变量

CapReservation ORM、migration 和 `sql/platform.sql` 统一增加 CHECK 约束，数据库直接拒绝非法 Reservation key 长度、非正 Offer/Publisher ID、负 attempts、错误的 Daily/Total 日期组合及未知状态。

这些 CHECK 约束必须由 MySQL 实际强制执行，因此部署最低版本明确为 MySQL 8.0.16+。CI migration 测试需查询 `information_schema.TABLE_CONSTRAINTS` 并尝试插入非法 Daily 日期组合，确认约束不是仅存在于 ORM metadata 中。

### 验收边界

以上修改已提交修复分支；必须以包含这些变更的最新 SHA 重新运行 Backend、MySQL 8.0 隔离迁移、Redis DB14 集成、Frontend lint/build 和 Playwright Mock API E2E。历史 Run #783 不能代替新提交验收。

## 18. 2026-11-11 Postback 第三方事件上报崩溃窗口（待修复）

### 发现

当前 `PostbackProcessor.process()` 的顺序是：先提交转化记录与下游转发队列事务，再调用 `_send_third_party_report_if_needed()`。而 `send_third_party_report()` 在被调用后才创建 `ThirdPartyReportLog` 并持久化事件幂等键。

因此存在一个明确的进程崩溃窗口：数据库已提交转化，但进程在创建第三方上报日志之前退出。上游重试时，重复转化检查会提前返回“重复转化”，不会重新执行第三方上报。该事件可能永久漏报。现有第三方事件日志的幂等和租约机制只能保护“日志已创建之后”的发送阶段，不能覆盖“转化提交成功、日志尚未创建”的窗口。

### 修复要求（不得连接生产环境）

1. 将第三方上报任务改为事务性 Outbox：在转化记录事务中创建待发送事件记录，转化与 Outbox 必须同一 DB transaction commit。
2. Outbox 必须保存稳定事件身份、可恢复的非凭据请求参数、状态、尝试次数、租约与下次重试时间；不得把 access token 等凭据写入 Outbox。
3. 后台 worker 以原子条件更新认领任务；租约过期可恢复，成功/失败状态必须持久化。
4. Worker 从受控配置源解析像素配置与凭据；配置缺失/不可用时保留可重试状态，不得伪装发送成功。
5. 重复 Postback 不应再次创建相同事件，但必须允许已有待发送 Outbox 继续被 worker 处理。
6. 覆盖“转化事务提交后立即崩溃”“Outbox worker 发送前崩溃”“远端成功但本地状态更新失败”“并发 worker 竞争”“凭据配置暂时不可用”等故障注入测试。
7. 使用隔离 DB、模拟 HTTP 和合成数据验收；不得访问生产数据库、Redis、队列或第三方接口。

### 当前验收状态

**代码修复已接入分支，验收仍阻断。** 后续提交已新增 `enqueue_postback_report()`，并由 `PostbackProcessor` 在转化主事务提交前调用；Outbox 行与转化、下游转发队列共同提交。提交后仅做低延迟 worker 触发，真正恢复由持久化调度任务负责。当前仍须通过最新 CI 和隔离故障注入，不能据代码存在就认定可靠投递已验收。


## 19. 第三方上报重试链路与恢复任务缺失（2026-11-11）

### 已核实的问题

1. `retry_report_log()` 从 `ThirdPartyReportLog` 读取事件后调用 `send_third_party_report()`，但没有传入必需的 `facebook_pixel_id` 和 `facebook_access_token`。发送函数会在入口因凭据缺失返回 `missing_facebook_credentials`，因此当前人工重试路径不能完成实际重发。
2. `send_third_party_report()` 创建的日志状态为 `pending`。当前调度任务注册配置中能找到 Postback 转发队列恢复任务，但没有找到第三方上报 pending/过期租约扫描恢复任务。若进程在认领后崩溃，租约过期本身不会自动触发再次发送。
3. 当前 `retry_report_log()` 通过 `asyncio.create_task()` 发起发送，没有持久化任务队列；进程在任务调度与执行之间退出时，没有独立的持久化调度器保证重新投递。

### 修复要求

- 以事务性 Outbox/持久化队列作为唯一待发送来源，写入必须与转化事务同提交。
- 不得将 access token 明文写入事件表、Outbox、日志或任务参数。Worker 必须按可信关联（click_id/short_link_id/斗篷配置）在执行时重新解析当前有效配置；缺少配置时记录明确的可重试/不可重试原因，不得假报成功。
- 增加周期性恢复 Worker：扫描 pending 且未认领、租约过期的任务；以原子条件 UPDATE 认领；限制每轮批量与并发；记录下次重试时间、最大尝试次数、终态及告警。
- 人工重试必须调用同一持久化入队/认领路径，不能直接 create_task 绕开队列。
- 测试必须覆盖缺少配置、配置轮换、worker 崩溃、租约过期、任务提交与调度间崩溃、远端成功但本地 ACK 失败、并发人工重试和幂等键稳定性。

### 当前验收状态

**实现状态：核心链路已接入，仍需验收。** 当前分支已新增第三方 Report Outbox 服务：转化事务内写入待发送事件；worker 发送时按短链/斗篷配置引用重新解析凭据，不将 access token 写入 Outbox；新增每分钟调度任务；人工重试改为将失败的 Outbox 行原子重置为 pending 并等待同一 worker 消费，不再依赖进程内 `asyncio.create_task()`。另修复 `create_report_log()` 引用未定义 `event_key` 的运行时错误。新增 Outbox 入队、配置动态解析、发送结果归一化和调度注册测试。

仍未通过最新 CI 和完整故障注入验收。必须继续验证：转化事务提交/回滚边界、并发相同事件唯一键冲突、worker 多实例竞争、远端成功但本地状态更新失败、配置轮换/缺失、重试预算耗尽、人工重试并发，以及旧版非 Outbox 日志的处理提示。CI 结果未完成前本节仍为合并阻断项。


## 20. Outbox 实现接入记录与待验收事项（2026-11-11）

- 已新增 `app/services/third_party_report_outbox.py`：转化事务入队、短链/斗篷配置引用解析、单条发送、批量扫描。
- `PostbackProcessor` 在 conversion commit 前调用 `_enqueue_third_party_report_if_needed()`；Outbox 与 conversion、下游转发队列同事务提交。
- 新增 `app/scheduler_module/tasks/third_party_report_tasks.py`，并在 task_names/task_config 注册每分钟恢复任务。
- `retry_report_log()` 现在只对 `outbox_enqueued=true` 且失败的行做条件 UPDATE，写入立即可重试时间；不再创建进程内后台任务。非 Outbox 旧日志不允许伪装为已成功重试。
- 发送函数成功路径可能返回 None，Outbox worker 已在调用后回读持久化状态，避免把已成功事件误计为 worker 失败。
- 新增 Outbox 服务单测和 scheduler registration 契约测试；第三方日志创建、人工重试测试也已更新。
- 上述仅为代码提交记录。不得将测试文件存在等同于测试通过；必须以最新 head 的 CI 结果及隔离 MySQL/Redis/mock HTTP 故障注入结果作为验收证据。

## 21. 第三方 Report Outbox 最新 CI 与二次审查（2026-11-11）

### 最新 CI 证据

- 最新已完成 CI：Run #860，commit `ccab5706fb6937b7d749674a814fb36ad397b721`，结论 `success`。
- Backend：依赖安装、Python compile、unit tests 全部成功，**310 passed、1 skipped、1 warning**。唯一 skipped 是仓库既有本地核对脚本未检出提示；不是 MySQL migration 测试跳过。
- Frontend：`npm ci`、lint、build 全部成功。
- Playwright：隔离前端服务 + Mock API 浏览器 E2E 全部成功。
- CI Backend 明确注入 `MYSQL_INTEGRATION_HOST=127.0.0.1` 和 CI 专用数据库 `platform_ci`；MySQL migration 集成测试已运行。新增两个独立 MySQL 连接竞争同一 Outbox 行的租约测试随该测试执行并通过。
- CI 使用隔离 MySQL/Redis 容器和 mock API；没有连接生产服务器、生产数据库、生产缓存、生产队列或真实 Meta 接口。
- Run #860 只证明该提交在现有自动化覆盖范围内通过，不代表真实第三方网络、生产数据或发布迁移已验收。

### 本轮二次代码审查核实

- Outbox 发送前由 `_claim_report_log()` 使用条件 UPDATE 认领，状态、租约过期时间和下次重试时间均参与仲裁；多 worker 扫描同一批 ID 时，只有取得租约的一方能进入发送路径。
- 失败发送按累计 attempt_count 与 max_attempts 计算退避；达到预算后不再自动进入 due scan，管理员可通过人工重试显式重置预算。
- 缺少当前像素凭据时，不调用第三方接口；记录失败原因并设置后续重试时间，允许配置恢复后重新发送。
- 成功事件的稳定 event_id 来自持久化 event_key；远端响应成功后本地状态更新失败时，当前代码会在租约过期后重新尝试同一 event_id，而不是创建新事件身份。
- 调度任务每分钟执行，单轮 batch_size=20；批量扫描上限为 100。调度任务结果记录 selected/success/retryable/failed 与耗时。

### 仍然阻断最终合并的验证缺口

1. 现有 `test_report_log_claim_is_atomic_for_concurrent_senders` 是模拟数据库条件 UPDATE 的并发单测；尚需补充隔离 MySQL 上两个独立 session/worker 真实争抢同一行的集成测试，验证实际事务隔离、行锁和 rowcount。
2. 需要故障注入覆盖「第三方已接收事件、应用在写 success 状态前退出」以及「success UPDATE commit 响应丢失」；验证租约过期后的恢复结果，并记录外部平台 event_id 去重的边界，不得假设外部系统一定提供 exactly-once。
3. 需要覆盖 attempt_count 达到 max_attempts、人工重试并发、配置恢复、短链被删除、斗篷配置被禁用等完整状态转换；检查管理端能否清楚区分自动重试中、自动重试耗尽、配置缺失和人工重新排队。
4. 需要在隔离 MySQL 上实际执行第三方 Outbox 两个 migration，核对已有表兼容、索引、唯一键、字符集、字段默认值及独立回滚方案。CI 的单元测试不能替代 DDL 发布演练。
5. 必须检查 report_params 的持久化内容与保留周期；哈希发送失败后的非哈希 fallback 会改变上报参数敏感度，需确认业务授权、访问权限、日志展示和清理策略。此项不是凭据专项，不得因凭据安全排除而跳过。

**结论：Run #860 全绿；真实 MySQL 双连接租约竞争已通过。Outbox 核心代码已接入，但远端成功/本地 ACK 崩溃注入、管理端状态可见性和完整 migration 发布/回滚演练仍未验收。PR 继续保持 Draft，禁止合并 main。**

## 22. 第三方上报日志管理 API 的个人信息暴露修复（2026-11-11）

### 已修复

- 列表接口原先直接截取 `report_params` 原始 JSON 前 120 字符作为预览，可能把 email、phone、IP、UA 明文返回给管理端页面。
- 详情接口原先直接序列化 ORM 日志字段，包含原始 email、phone、IP、UA 和完整 `report_params`。
- 现在列表预览和详情响应统一递归脱敏：邮箱保留首字符和域名，手机号只保留首三位/末四位，IPv4 只保留前两段，IPv6 仅保留首段，UA 隐藏；无法解析的参数 JSON 不返回原文。
- 新增 API 脱敏单测，覆盖单字段、嵌套 JSON、非法 JSON 和空值。
- 此项属于个人信息最小暴露，不属于凭据安全专项，因此纳入本次修复范围。

### 尚待验收

- 最新分支 CI 必须覆盖新增脱敏单测；再增加 API 层响应模型测试，确认 FastAPI/Pydantic 序列化后不会重新暴露原始字段。
- 应检查前端页面是否依赖原始 report_params/UA/email/phone/IP 明文；若依赖，需同步调整页面展示和排障文档，不能通过新增旁路接口绕过脱敏。
- 仍需确定原始 PII 在数据库中的保留期限、清理机制、访问审计与合法业务目的；API 脱敏不等于数据库已完成数据最小化。

## 23. 第三方已接收但本地成功 ACK 丢失的恢复验证（2026-11-11）

### 故障窗口与预期语义

1. worker 使用稳定的 `event_key` 作为 Meta `event_id` 发起请求。
2. Meta 返回 `events_received > 0`，表示远端已接收。
3. 本地更新 `status=success` 的数据库提交失败或响应丢失；现有日志更新函数可能吞掉该异常，因此本地仍显示 pending/failed。
4. 发送租约到期后 worker 再次发送；必须复用同一条日志、同一 `event_key`、同一 `event_id`，不能重新创建业务事件身份。
5. Meta 侧是否将相同 event_id 去重由 Meta 的事件去重语义决定；本系统只能保证重试身份稳定，不能宣称跨网络 exactly-once。

### 新增自动化覆盖

- Outbox worker 层测试模拟远端已接收、本地 ACK 未确认，第二次读取状态成功；两次调用携带完全相同的 event_id。
- 发送函数层测试执行真实 `send_third_party_report` 控制流，模拟 success ACK 持久化失败但日志更新函数吞掉异常；确认重试仍携带原始 event_id。
- 以上均为 mock HTTP 和隔离测试，不访问真实 Meta API 或生产数据库。

### 验收限制

- 该故障注入验证的是应用层状态机与稳定事件身份，不是 MySQL 实际断连/COMMIT 响应丢失的端到端演练。
- 仍需 CI 通过，并在隔离 MySQL 环境增加提交响应丢失/连接中断测试；生产发布前另行执行备份、迁移和回滚演练。

## 24. ViewContent 事件身份与 Purchase 关联字段隔离（2026-11-11）

- 复核发现：Purchase 发送时会给历史 ViewContent 日志补写 `conversion_id`，但 ViewContent 原事件的 event_key 已在创建时生成；若把后补 conversion_id 纳入重算，会改变已发送事件身份并破坏重试去重。
- 修正原则：ViewContent 的幂等键只由 source、adsid、event（以及存在时的平台维度）决定；后补 conversion_id 仅作为关联元数据，不参与 ViewContent 身份。Purchase 等转化事件仍使用 conversion_id 区分事件。
- `build_event_idempotency_key()` 已按上述规则规范化；事件幂等键迁移回填 SQL 同步对 ViewContent 忽略 conversion_id，保持历史数据与新代码一致。
- 新增回归断言：同一 ViewContent 在 conversion_id 为空和后补 Purchase conversion_id 时生成相同 event_key，且与 Purchase event_key 不同。
- 该修正仍需最新 CI 的后端全量测试和 MySQL migration 测试通过；不代表真实生产数据已完成迁移或核对。

