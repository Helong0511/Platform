# Outbox 调度锁与单条租约预算复核（2026-11-19）

## 结论

本次按 `main` 当前实现复核了第三方 Postback Report Outbox 的批次上限、HTTP 总时限、重试次数、单条报告租约、MySQL 调度锁与 Redis 调度锁。

**当前代码参数在预设 HTTP 重试路径下具备时间余量，未发现需要立即修改运行逻辑的确定性 TTL 配置错误。** 本次不修改业务代码，仅补充审计记录。该结论不代表生产环境压力/故障演练已经完成。

## 实际预算

| 项目 | 当前实现 | 说明 |
|---|---:|---|
| Outbox 每批上限 | 3 条 | `app/scheduler_module/tasks/third_party_report_tasks.py` |
| 单条 HTTP 总时限 | 60 秒 | `REPORT_HTTP_REQUEST_DEADLINE_SECONDS=60`，且不超过单条租约的一半 |
| 单条自动请求次数 | 最多 3 次/本轮 | `send_third_party_report()` 的 `max_retries=3` |
| 单条重试退避 | 1 秒 + 2 秒 | 指数退避，最多两次等待 |
| 单条 HTTP 网络预算 | 183 秒 | 3 × 60 + 1 + 2 |
| 每批 HTTP 网络预算 | 549 秒 | 3 × 183；不含数据库、凭据解析、通知及调度开销 |
| 单条 Outbox 租约 | 300 秒 | `REPORT_LOG_LEASE_SECONDS`；每次 HTTP 请求前续租/核验 |
| 调度 MySQL 锁超时 | 900 秒 | `_task_lock_timeout_seconds()` 对 Outbox 特别设置 |
| 调度 Redis 锁 TTL | 960 秒 | MySQL 锁预算额外增加 60 秒 |

## 已核实的保护措施

1. 每次 HTTP 请求由 `asyncio.wait_for` 限制总墙钟时间；这弥补了 HTTPX read timeout 只限制相邻数据块等待、无法限制持续慢速回包总时长的问题。
2. 单条报告租约为 300 秒；发送前通过租约令牌和数据库时钟续租/校验。旧 Worker 失去租约后不能继续发起下一次请求，也不能覆盖新 Worker 的持久化结果。
3. 调度器先获取 Redis 锁，再获取 MySQL `scheduled_tasks` 行锁；Redis 锁释放时按 token 比对，避免误删其他 Worker 的锁。
4. Outbox worker 批次大小固定为 3，低于服务函数允许的最大 100 条，避免默认批量参数被误用于定时任务。
5. 发送尝试次数先持久化，再发起 HTTP 请求；累计预算耗尽后不再继续发送。
6. 发送失败、租约丢失和第三方已接收但本地 ACK 未确认等情况仍按幂等键和状态核验处理；不能将其描述为严格 exactly-once。

## 本次发现的文档/测试精度问题

原调度注册测试注释使用 `3 条 × 3 次 × 60 秒 = 540 秒`，没有计入每条事件最多 1+2 秒的指数退避。更准确的**纯 HTTP 网络预算**为：

`3 条 × (3 次 × 60 秒 + 1 秒 + 2 秒) = 549 秒`

549 秒仍低于 900 秒 MySQL 调度锁预算，剩余 351 秒用于数据库操作、配置读取、状态持久化及其他开销。这个余量是配置预算，不是实测上界；数据库锁等待、连接池拥塞、第三方通知或运行时停顿都可能增加任务总耗时。

当前测试 `test_outbox_scheduler_lock_budget_exceeds_bounded_batch_http_budget` 验证了 Outbox 的 MySQL 锁超时为 900 秒、普通任务为 300 秒；`test_http_total_deadline_is_shorter_than_report_lease` 和慢速持续回包取消测试验证 HTTP 总时限受限。现有测试没有直接对 Redis 的 960 秒 TTL 做行为级断言。

## 未覆盖及上线前仍需验证

- Redis 故障/恢复期间多 Scheduler 实例并发触发的真实集成测试；Redis 不可用时当前实现回退为仅依赖 MySQL 锁。
- 任务执行超过 900/960 秒、Worker 被 SIGKILL、事件循环阻塞、数据库连接池耗尽等故障注入。
- 在目标生产 MySQL/Redis 版本和真实数据规模下验证锁等待、任务时长分布与积压恢复能力。
- 监控任务执行时长 P95/P99、超过 600 秒告警、超过 900 秒严重告警、Redis 锁获取失败、Outbox due backlog、租约过期接管次数及第三方发送失败率。
- 评估是否需要把调度锁改为可续租并带 fencing token 的租约。当前 900/960 秒固定锁不是任意长任务的通用保障；若未来批次大小、请求次数或超时上限增加，必须同步重算预算并更新测试。

## 本次核对的代码与测试

- `app/scheduler_module/tasks/third_party_report_tasks.py`
- `app/scheduler_module/scheduler.py`
- `app/scheduler_module/lock.py`
- `app/services/third_party_report_outbox.py`
- `app/core/third_party_report.py`
- `tests/test_third_party_report_outbox_scheduler_registration.py`
- `tests/test_third_party_report_request_deadline.py`
- `tests/test_third_party_report_outbox_worker_errors.py`

本次为基于 `main` 源码与现有测试的静态复核；没有连接生产环境，没有执行真实 Meta API 请求，也没有声称已完成生产压力测试。


## 38. 2026-11-21：Scheduler 锁释放竞态与数据库时钟统一

### 38.1 发现的问题

- `acquire_task_lock()` 在 `SELECT ... FOR UPDATE` 后提交事务；提交会释放 InnoDB 行锁。任务执行期间并没有一直持有该行锁。
- 旧版 `release_task_lock()` 的注释误以为同一 Session 仍持有抢锁时的行锁，实际释放时只做普通一致性读，没有重新 `FOR UPDATE`。若旧 Worker 超时后新 Worker 已抢占，旧 Worker 可能读到旧快照中的 PID，再把 `is_running` 改成 False，覆盖新 Worker 的锁状态，造成第三个 Worker 提前进入。
- 旧版超时判断和 `last_run_time` 写入使用各 Worker 的本地时钟；多节点时钟偏差可能导致过早抢锁或延迟恢复。

### 38.2 修复

- `release_task_lock()` 现在重新执行 `SELECT ... FOR UPDATE` 并使用 `populate_existing=True` 刷新 SQLAlchemy identity map，在行锁保护下读取数据库中的当前持有者，再校验 PID/Host 和单调递增的 `run_count` 运行代号。仅 PID/Host 不足以识别同一进程超时后重新抢到的下一代任务；旧运行必须携带抢锁时保存的 `run_count`，否则 fail closed，不释放锁。
- `acquire_task_lock()` 在同一锁事务中读取 MySQL 服务端时间表达式 `get_app_now_sql_expression()`，用它判断超时并写入 `last_run_time`。
- `execute_task_with_lock()` 的提前跳过检查也使用 MySQL 服务端时间，避免 Worker 本地时钟造成误判。若无法读取数据库时间，抢锁路径 fail closed。
- 第三方 Report Outbox 单批最坏 HTTP 网络预算为 549 秒（每条最多 3 次、每次 60 秒，退避合计 3 秒；每批 3 条），代码注释已与 900 秒 MySQL 任务超时及 960 秒 Redis TTL 对齐。该预算不包含 DB/凭据/调度开销，不能当作生产实测耗时。

### 38.3 回归测试

- 使用快/慢偏移的模拟 Worker 时钟，验证抢锁与 stale precheck 只使用 DB 时间。
- 验证任务开始时间写入 DB 时间。
- 编译 MySQL 方言 SQL，验证释放锁时确实包含 `FOR UPDATE`。
- 这些测试证明时间源、SQL 行锁、identity map 刷新及同 PID/Host 的旧运行代号不能释放新运行；仍需在真实多 MySQL 会话下做故障注入/长任务演练，不能替代生产级压测。

结论：修复了旧 Worker 使用一致性快照/ORM 缓存误释放新 Worker 锁的竞态；使用 `run_count` 作为同 PID/Host 的运行代号 fencing，并统一锁超时判断时间源。任务超时后旧 Worker 仍可能继续执行其业务函数；各业务任务仍必须具备自己的幂等/租约 fencing，不能把 Scheduler 锁当作外部副作用的 exactly-once 保证。
