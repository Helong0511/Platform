# Scheduler 持久化执行账本 ADR（第二阶段设计基线）

- 状态：Proposed（待评审；不是已实施功能）
- 日期：2026-11-23
- 范围：`Helong0511/Platform` 的 APScheduler、内部 TaskQueue 与手动任务触发
- 关联：Issue #159；第一阶段队列背压与关闭行为已由 PR #162 合并
- 安全边界：只允许隔离 CI、合成数据和 Mock；本 ADR 不连接生产数据库、Redis、第三方 API 或生产服务器。

## 1. 背景与已确认事实

当前主线已经具备有界内存任务队列和关闭时停止接收/等待排空能力，但这不等于持久化队列：

1. `app/scheduler_module/task_queue.py` 的待执行项、运行中 Task 跟踪均位于进程内存；进程被强制终止、主机故障或断电时，尚未完成的工作可能丢失。
2. `app/scheduler_module/task_result_store.py` 使用模块级字典，仅在当前进程可见，进程重启后丢失；它是最近结果摘要缓存，不是执行历史。
3. `app/scheduler_module/task_result_registry.py` 是结果读取函数注册表，不是持久化记录。
4. `ScheduledTask` 表描述任务配置及最近执行状态，不代表每次触发对应一条独立执行记录。
5. 手动触发路径已经等待队列确认接收，但当前“接收”仍是内存队列接收，不代表数据库持久化提交。
6. 项目已有多个业务级持久化队列/账本，例如 Postback Forward Queue、Third-party Report Outbox、Cap Reservation Ledger、Pending Postback Queue Guard。它们各自拥有业务状态、幂等身份、租约/恢复语义，不能再复制一套通用执行状态作为第二事实源。
7. 项目迁移机制不是简单 ORM create_all：SQL 文件必须进入 `sql/migrations/`，在 `app/db/migrations/manifest.py` 显式登记 revision、依赖和 SHA-256，并通过独立 Migration Runner、隔离 MySQL 测试与启动 revision gate。

## 2. 决策

采用“**通用调度执行账本 + 业务专属队列继续作为事实源**”的分层方案。先完成任务分类、幂等性契约和 API 语义设计，再实施 schema、migration 和运行时接入。不得把所有 APScheduler 回调机械包装成自动重试任务。

通用账本只负责记录被明确纳入范围的执行意图、领取、租约、最终状态和可审计摘要；它不替代业务数据表、Outbox、Cap Reservation 或第三方投递队列。

### 2.1 第一阶段目标范围

优先纳入：
- 明确需要人工触发、要求重启后可恢复、且任务函数能够定义幂等边界的任务。
- 经过逐项评审、可稳定计算计划触发身份的 Cron 执行。
- 需要审计执行人、参数白名单、重试策略和执行历史的管理任务。

暂不自动纳入：
- 已由独立业务账本/队列持久化并负责恢复的任务。
- 具有不可逆外部副作用、无法核实外部结果或没有可靠幂等键的任务。
- 参数包含凭据、令牌、完整连接串、个人信息或任意 Python 对象的任务。
- 单纯刷新内存缓存、展示最近结果等不需要持久化执行历史的轻量回调。

## 3. 任务分类基线

以下分类来自当前 `app/scheduler_module/task_config.py` 与对应业务模块的职责描述，是接入评审起点，不表示已完成每个函数的源码级幂等验证。

| 任务/类别 | 当前可见的业务事实源 | 通用账本接入建议 | 重试/恢复约束 |
|---|---|---|---|
| 第三方 Report Outbox 投递 | `third_party_report_logs` Outbox 状态、租约及事件身份锁 | 不建立第二条可投递队列；可选记录调度器运行摘要，但不作为投递事实 | 沿用 Outbox 自身退避、租约 fencing、幂等身份和人工重试预算 |
| Cap Reservation Recovery | Cap Reservation Ledger、Redis token/恢复状态 | 不复制 reservation 状态 | 只按现有恢复规则执行；未知状态进入人工对账，不盲目重放 |
| Pending Postback 消费/恢复 | Pending Postback 记录及 Queue Guard | 不复制 pending 队列 | 沿用事件去重、队列守卫和恢复规则 |
| 短链接点击队列批处理 | 点击队列、批次/同步幂等记录 | 需先核实队列确认、批次提交与重放边界，再决定 | 只有确认批次幂等、失败可重入后才允许自动恢复 |
| 短链接点击计数同步 | Redis 计数与数据库同步状态 | 候选；先核对 Redis 清零/DB 提交的原子边界 | 必须证明重复同步不会重复计数或丢失增量 |
| 上游广告报表拉取（GAM、TQT、Skymobi、TBSJ、Addermobi、Huguang、ZhiSuo、Pomiad、H5 Deer、Aya、FlyMobi、LeiYang 等） | 各上游导入表及业务唯一键 | 分供应商核验后分批纳入 | 拉取请求、分页游标、导入 upsert、日期窗口和账号隔离分别定义；失败不得导致重复累加 |
| 数据归档/点击归档 | 主表、归档表及归档任务自身进度 | 候选，需确认分批游标与双写/删除顺序 | 必须有稳定主键游标、分批事务、重复执行安全性和归档后核对 |
| 日志/会话/敏感路径记录清理 | 对应业务表和保留策略 | 可作为低风险候选，但仍需定义批次边界 | 只允许按明确保留策略删除；需支持 dry-run/计数核对，不得泛化重试 |
| Cap 重置/Cap 计数同步 | Cap 业务表及 Redis 计数 | 暂缓纳入自动恢复 | 日切时区、重复执行和 Redis/DB 对账语义必须先明确 |
| 通知汇总及其它外部通知 | 通知业务记录/外部发送方 | 逐任务评估 | 外部发送成功但本地未记成功可能重复；必须有对端幂等或发送结果核对 |

任务清单必须随每个任务的源码审查更新，不能仅凭任务名称或 Cron 表达式批准接入。

## 4. 执行记录数据契约（待 schema 评审）

建议每次执行独立一行，最终表名待评审，不在本 ADR 中锁定。

必需语义字段：

- `execution_id`：UUID/ULID，唯一且不可复用。
- `task_name`：对应受控任务注册表，不允许用户提交任意模块/函数路径。
- `trigger_source`：限定为 `cron`、`manual`、`recovery`。
- `idempotency_key`：同一业务执行意图唯一；数据库唯一约束兜底。
- `status`：状态机见下节。
- `created_at`、`accepted_at`、`started_at`、`finished_at`：统一使用数据库时间；明确 DATETIME(6) 与应用时区转换策略。
- `attempt_count`、`max_attempts`、`next_retry_at`：重试预算与退避。
- `lease_owner`、`lease_token`、`lease_expires_at`：多 Worker 领取和 fencing。
- `triggered_by_user_id`：人工触发时的审计主体；Cron/恢复触发为空或使用明确系统主体，不能伪造用户。
- `safe_parameters_json`：只允许任务 schema 白名单字段，限制字节数/深度/类型；拒绝凭据、令牌、DSN、任意对象和不必要的 PII。
- `error_type`、`error_summary`：仅保存异常类型和脱敏摘要，不存 traceback、请求头、响应原文、SQL 参数或密钥。
- 可选 `scheduled_for`：Cron 计划触发时间，用于稳定构造计划执行身份。

所有字符串字段须明确长度、字符集、排序规则；身份键使用确定的二进制比较规则，避免大小写/尾随空格导致唯一性语义漂移。时间精度、UTC/业务时区和 DST 策略必须在 schema/代码/测试中一致。

## 5. 状态机与并发领取

建议状态：

```text
accepted -> running -> succeeded
                    -> failed
                    -> retryable -> running
                    -> dead_letter
accepted -> cancelled
retryable -> cancelled
```

约束：
1. `accepted` 只在执行记录事务成功提交后返回“已持久化接收”。
2. Worker 领取时使用短事务锁定待执行记录；确认 MySQL 最低版本及驱动支持后，优先评估 `SELECT ... FOR UPDATE SKIP LOCKED`。
3. 领取事务写入随机高熵 `lease_token`、owner、过期时间和 attempt，然后提交；不得在执行任务期间持有数据库行锁。
4. 所有状态回写必须同时匹配 `execution_id + lease_token + expected_state`。旧 Worker 租约失效后即使迟到完成，也不能覆盖新 Worker 状态。
5. 长任务需 heartbeat/续租；续租失败后 Worker 应停止继续产生可控副作用，但不能假设任意外部调用都可中断。
6. Recovery Worker 仅回收明确过期租约；对外部副作用结果未知的任务进入 reconciliation/dead_letter，不得默认自动重放。
7. 任务执行历史保留策略、脱敏和访问权限独立定义；不得无限保存个人信息或第三方响应内容。

## 6. 幂等键规则

- Manual：客户端提供稳定 Idempotency-Key（长度/字符集/有效期受限），或服务端生成并返回 execution_id；同一用户/任务/请求键重复提交返回原执行记录，不产生第二次执行。
- Cron：使用 `task_name + scheduled_for(UTC instant)` 构造唯一计划执行身份。不得只用 task_name，否则永久只能执行一次；也不能用 Worker 当前时间，否则多 Worker 会产生不同键。
- Recovery：沿用原 execution_id，不创建新的业务执行身份；每次领取仅增加 attempt/lease。
- 幂等键唯一作用域需评估是否包含租户/客户 ID；只有任务确实按租户隔离时才加入。不可用用户 ID 代替业务幂等身份。
- 参数摘要可用于审计/冲突检测，但不能用未经规范化的 JSON 字符串直接作为唯一键。

## 7. 至少一次语义，不承诺 exactly-once

执行账本只能提供持久化接收、竞争领取、租约 fencing 和可恢复状态。它无法单独保证外部副作用恰好执行一次。

典型故障：Worker 已成功调用上游/发送通知/写入第三方系统，但在本地写入 `succeeded` 前崩溃。恢复后无法仅凭本地状态判断外部动作是否已成功。

因此：
- 优先依赖业务唯一键、数据库 upsert、Outbox、对端幂等键或可查询的外部操作 ID。
- 对不可幂等且结果未知的副作用，进入人工核对，不自动重试。
- 每个任务必须有独立的 `retry_safe` 声明、最大次数、指数退避/抖动、超时、是否允许人工重放和 dead-letter 处理方式。
- 不允许一个全局“失败自动重试”策略覆盖所有任务。

## 8. API 与权限语义

- 手动触发 API 只有在 execution record 事务提交后才能返回持久化 accepted；数据库不可用时必须返回失败，不得退回内存队列后仍报告持久化成功。
- 响应应包含 `execution_id`、当前状态和是否为幂等重复请求；不能将“已接收”表述为“已执行成功”。
- 查询执行历史必须沿用现有管理员权限和租户/客户数据范围；执行记录中的参数、错误摘要按敏感数据处理。
- 取消只对尚未开始或任务明确支持协作取消的状态生效；不能承诺强制终止正在运行的线程/外部请求。
- 手动重放必须创建新的审计动作并遵守原任务的重放策略；不应直接把终态记录改回 accepted。

## 9. Migration 与部署门槛

本项目必须沿用现有 migration runner，不使用 `Base.metadata.create_all()` 偷偷创建生产表。

新增数据库对象前必须：
1. 评审表名、字段、索引、唯一键、外键策略、行大小、保留期、字符集和排序规则。
2. 核查 MySQL 最低版本、InnoDB、`SKIP LOCKED` 行为和隔离级别；在隔离 MySQL 上验证锁范围、死锁和索引命中。
3. 编写 `sql/migrations/YYYYMMDD_*.sql`，加入 manifest，计算 SHA-256 并登记依赖。
4. 验证 DDL 可在每个语句边界中断后诊断；Runner 对普通 running/failed migration fail closed。
5. 按“向后兼容 schema → 兼容代码 → 验证 → 启用写入/Worker → 清理旧路径”的顺序部署。
6. 验证应用运行账号无 DDL 权限时仍能运行；Migration Runner 使用独立账号。
7. 只有隔离 CI/演练全通过后才允许进入生产变更审批。

## 10. 必须具备的测试与故障注入

- 同一 manual idempotency key 并发重复提交，只产生一条执行记录。
- 不同用户/租户作用域符合权限和唯一键设计，不发生跨租户读取。
- 多 Worker 同时领取时同一 execution 只有一个有效 lease。
- 旧 lease 过期后旧 Worker 迟到写回被 fencing 拒绝。
- Worker 在领取后、任务开始前崩溃；执行中崩溃；外部副作用后、succeeded 写入前 kill；数据库断连。
- retryable 退避、最大次数、dead-letter、人工重放审计。
- 任务参数非法类型、超深 JSON、超大 payload、凭据字段和 PII 被拒绝/脱敏。
- Cron 夏令时跳变、重复本地时间、UTC 计划时间唯一性。
- shutdown 开始后并发提交；持久化 accepted 记录在重启后可恢复。
- DB 不可用时 API 不得谎报持久化接收；Redis 不可用不得影响数据库账本正确性。
- MySQL 死锁、锁等待超时、连接池耗尽和主从切换期间的安全行为。
- 中文任务名/错误摘要、utf8mb4、排序规则、DATETIME(6) 精度均正确。

## 11. 明确不在本 ADR 中批准的事项

- 不创建 migration、不改 ORM model、不改 API、不启用自动重试。
- 不把现有 Outbox/Cap Reservation/Pending Postback 等业务队列迁移到通用账本。
- 不承诺 exactly-once，不保证 SIGKILL 后所有外部副作用自动安全重放。
- 不改变生产 Cron 频率、任务优先级、任务参数或现有部署服务。
- 不自动删除旧的内存队列；只有持久化接入逐任务完成、灰度验证和回滚方案通过后才评估替换。

## 12. 评审清单与后续实施顺序

- [ ] 逐个任务核对实现、业务唯一键、外部副作用、失败语义和最大执行时间。
- [ ] 输出任务级幂等/重试安全矩阵，标记可自动恢复、仅人工恢复、禁止重放。
- [ ] 评审 schema、索引、租约期限、heartbeat 和保留期。
- [ ] 评审 API Idempotency-Key、权限范围和执行历史查询。
- [ ] 完成隔离 MySQL 并发/崩溃/恢复测试。
- [ ] 再实现 migration、repository/service、worker 和 API。
- [ ] 逐类任务接入，先选纯 DB 幂等任务，再逐步处理外部 API/通知类任务。
- [ ] 更新部署 runbook、README、监控告警和运维恢复手册。

**当前结论：** PR #162 解决的是进程内队列容量和正常关闭排空，不解决进程崩溃后的持久化恢复。Issue #159 继续保持 open，直到上述设计评审、实现、隔离测试和运维验收完成。
