# Scheduler 第一批持久化账本候选任务源码核查

- 日期：2026-11-23
- 基线：main `0aab3350be663d1cde07a1ca3c7f51d8bc81207d`
- 关联：Issue #159；设计基线 `docs/adr/20261123_scheduler_execution_ledger.md`
- 状态：源码核查记录；不代表已批准接入或自动重试
- 安全边界：仅基于仓库源码静态核查；未连接生产数据库、Redis、第三方 API 或服务器。

## 1. 结论摘要

本轮核对了 `task_config.py` 中的日志/会话清理和归档任务，以及对应任务实现。当前没有任何任务仅凭本轮静态审查即可直接启用通用账本自动重试。

首批候选应从**无外部副作用、可按稳定主键分批、重复执行语义明确**的任务开始。建议优先进一步完善“清理敏感路径拦截日志”，但在实现分批删除、并发边界、行数上限与索引验证前，只能列为候选，不能接入重试 Worker。

## 2. 逐项源码核查

### 2.1 清理敏感路径拦截日志

源码：`app/scheduler_module/tasks/cleanup_sensitive_path_probes.py`

当前行为：
- 使用 `SENSITIVE_PATH_PROBE_RETENTION_DAYS` 作为保留天数；参数 `retention_days` 可覆盖。
- 以应用时区当前时间减保留天数作为 cutoff。
- 单条 DELETE 删除所有 `created_at < cutoff` 记录，随后提交。
- 删除/提交异常会 rollback 并重新抛出；没有外部 API 调用。

风险与结论：
- 对固定 cutoff 重复执行具备删除幂等性；但当前 cutoff 每次按当前时间重算，任务执行意图并非固定快照。
- 单次 DELETE 没有 LIMIT/主键游标，历史积压较大时可能产生长事务、锁等待和复制延迟。
- 必须确认 `SensitivePathProbeLog.created_at` 索引存在且被 MySQL 使用。
- 建议先改为按主键有序分批删除，每批独立提交；固定本轮 cutoff，设置最大批次数/运行时限，并对删除量和剩余量提供摘要。
- 接入通用账本后，恢复时可重新执行相同 retention policy，但不得绕过租约 fencing 或无限重试。

接入建议：**第一批候选（需先完成分批化和隔离 MySQL 验证）**。允许有限自动重试的前提是每批 DELETE 按固定 cutoff 可重复执行，且不会删除 cutoff 之后的新日志。

### 2.2 清理过期会话和 Token 黑名单

源码：`app/scheduler_module/tasks/cleanup_expired_sessions.py`

当前行为：
- 同一数据库事务中删除过期超过 30 天的会话与 TokenBlacklist。
- 同一事务中将超过 7 天未活动的活跃会话更新为非活跃。
- 执行后提交；异常重新抛出。

风险与结论：
- UPDATE/DELETE 条件具有重复执行的幂等特征，但三个操作均为不设批次上限的集合操作。
- 需核实 expires_at、last_activity 的索引、表规模和外键/级联行为。
- “删除过期超过 30 天”与“expires_at < now”不是同一规则，必须保留当前 30 天缓冲语义，不可擅自简化。
- 同一事务意味着大批量数据可能延长锁持有时间；应先测量并评估按主键分批后是否需要拆分事务。

接入建议：**第二批候选（先完成容量/索引/分批审查）**。执行参数无用户输入；重试仍须有次数上限和退避。

### 2.3 清理旧用户审计日志

源码：`app/scheduler_module/tasks/cleanup_old_logs.py`

当前行为：
- 默认保留 90 天；支持 archive 模式。
- archive 模式会在任务运行期间通过 `CREATE TABLE` 动态创建 `user_audit_logs_archive`，并执行 `INSERT IGNORE ... SELECT` 后删除源记录。
- 删除使用单条 DELETE，没有 LIMIT。
- 归档表创建后单独 commit，后续归档/删除再提交。

风险与结论：
- 运行时 DDL 与项目受控 Migration Runner/manifest 流程不一致；任务账号若无 DDL 权限会失败，若有权限则扩大运行时权限面。
- 动态建表与业务清理混合，失败窗口跨越多个事务；不能把整次任务视为原子操作。
- 大范围 INSERT/DELETE 可能产生长锁、复制延迟和较高 undo/redo 压力。
- `INSERT IGNORE` 可能掩盖归档表数据冲突；需核对归档唯一键与源数据一致性。
- 当前默认 archive=False，但仍应消除或隔离运行时建表路径。

接入建议：**暂不纳入**。先将归档表 DDL 移入正式 migration，明确归档唯一键、批次游标、每批插入/核对/删除事务和失败恢复，再重新评审。

### 2.4 清理文件日志

源码：`app/scheduler_module/tasks/cleanup_file_logs.py`，底层 `app/core/log_file_cleanup.py`

当前行为：
- 调用本机文件系统清理服务，涉及轮转备份、archive gzip、Gunicorn 溢出轮转和磁盘守卫。
- 任务执行结果可能包含 skipped、errors、hard_limit_hit 等业务结果。

风险与结论：
- 文件系统状态是本机/挂载卷事实源，不是通用 SQL 账本可独立恢复的对象。
- 多主机、多 Worker 对不同日志目录的作用域必须明确。
- 压缩、移动、删除等步骤可能在部分完成后进程退出；需验证每一步可重复执行及临时文件恢复。
- 返回 errors/hard_limit_hit 时目前可能只记录 warning，不一定抛异常；执行账本不能简单将函数正常 return 等同于全部清理成功。

接入建议：**暂不纳入第一批**。先为底层文件操作定义可恢复步骤和结构化结果状态。

### 2.5 广告数据归档

源码：`app/scheduler_module/tasks/archive_old_data.py`

当前行为：
- 计算 6 个月前的月份阈值。
- 检查归档表存在性；若不存在会失败。
- 运行期间检查并尝试 ALTER TABLE 修复外键约束。
- 使用 `INSERT IGNORE ... SELECT` 将数据写入归档表，再按日期删除主表数据并提交。

风险与结论：
- 运行时 ALTER TABLE 不应由普通调度任务承担；结构变更必须进入 migration。
- 归档与删除的唯一键、外键、行数核对和 COMMIT 结果不确定性需要单独验证。
- 按日期一次性归档/删除，未见稳定主键分批边界，可能产生大事务。
- INSERT IGNORE 不能代替数据一致性校验。

接入建议：**暂不纳入**。先清除运行时 DDL，设计稳定主键批次、每批校验和归档后核对。

## 3. 第一批接入门槛

“清理敏感路径拦截日志”只有满足以下全部条件，才可进入账本第一批实现：

- [ ] 确认 MySQL 表结构、主键、索引和实际执行计划。
- [ ] 将单次全表范围 DELETE 改为主键稳定排序的有界批次。
- [ ] 每轮固定 cutoff，且执行参数仅允许受控的 retention policy。
- [ ] 设置最大批次数、最长运行时间和每批行数上限。
- [ ] 每批提交后可安全续跑；明确 COMMIT 响应超时后的核对策略。
- [ ] 两个 Worker 并发运行时不会造成重复副作用或锁竞争失控。
- [ ] 测试 DB 断连、死锁、lock wait timeout、连接池耗尽和进程在批次提交前/后崩溃。
- [ ] 执行账本记录只保存安全参数和脱敏摘要，不记录请求头、凭据、PII 或 SQL 参数。
- [ ] 明确任务失败、部分完成、无工作、租约过期和 dead-letter 的状态语义。

## 4. 禁止事项

1. 不允许对所有 Cron 任务统一启用失败自动重试。
2. 不允许将业务 Outbox、Cap Reservation、Pending Postback、点击队列复制到通用执行账本并形成第二事实源。
3. 不允许对外部发送结果未知的通知/上报任务直接自动重放。
4. 不允许把任务函数正常返回一律视为业务成功；必须核查结构化结果中的 errors、skipped、partial 等字段。
5. 不允许由普通任务运行时创建/修改生产数据库结构。
6. 不允许使用本轮静态审查替代隔离 MySQL 的并发、锁和崩溃故障注入。

## 5. 下一步

1. 先完成敏感路径日志清理的分批删除设计与索引核查。
2. 再完成第一批候选任务的 migration/schema/API/lease/repository 设计评审。
3. 在隔离 MySQL 中完成并发领取、租约 fencing、提交结果不确定和崩溃恢复测试。
4. 仅在上述通过后实现账本，并只接入明确批准的任务。
5. 持续更新 `docs/adr/20261123_scheduler_execution_ledger.md` 的任务矩阵；ADR 未转 Accepted 前，不将设计标记为已实现。
