# 点击归档有界批处理与并发安全审计（2026-11-22）

## 1. 审计结论

此前 `archive_old_clicks()` 在一个事务内执行全量 `INSERT ... SELECT` 与范围 `DELETE`。当历史点击积压较大时，事务持续时间、锁持有行数、undo/redo 量和锁等待均没有上界；调度器普通任务锁预算只有 300 秒，可能在任务仍运行时被其他 Worker 视为过期。

本次改为**固定高水位 + 有界行锁批次 + 每批独立事务**；令牌模式下仅用 `SELECT 1 ... LIMIT 1` 判断主表是否有数据，不再为跳过任务执行全表 `COUNT(*)`：

1. 捕获本轮主表最大 `id` 作为 `high_water_id`，固定本轮扫描边界。
2. 使用 `click_time < cutoff AND id <= high_water_id`，按 `click_time, id` 排序，最多选择 1000 条。
3. 使用 `SELECT ... FOR UPDATE` 锁定当前批次的源行。
4. 按明确的 ID 列表执行普通 `INSERT ... SELECT`，核对写入数。
5. 按相同 ID 列表删除源行，核对删除数。
6. 两项数量完全一致才提交当前批次；失败时仅回滚当前批次，之前已提交批次保持完整。
7. MySQL 死锁（1213）和锁等待超时（1205）最多额外重试 3 次，退避为 100/200/400 毫秒。

默认批次大小为 1000，允许 1–10000；保留期天数必须是正整数。调度器为“点击记录归档”配置 900 秒 MySQL 锁预算，Redis 锁 TTL 为 960 秒。

## 2. 并发与事务边界

- 每批的源行在 `SELECT ... FOR UPDATE` 后保持锁定，直到该批 commit/rollback。
- 归档写入与源表删除处于同一个事务；唯一键冲突、字段错误、写入数量不一致、删除数量不一致都会回滚当前批次。
- 进程在批次中途崩溃时，MySQL 连接关闭后未提交事务回滚；之前已提交批次不受影响。
- 再次运行时，已完成批次的源记录已经删除，任务从剩余的主表记录继续，不需要维护额外的偏移量或游标。
- 多 Worker 同时执行时，普通 `FOR UPDATE` 会等待其他事务释放行锁；获得锁后按当前可见记录继续处理。没有使用 `SKIP LOCKED`，避免把跳过锁定行的非一致结果当成全量扫描完成。

## 3. 高水位语义与边界

`high_water_id` 用于固定本轮扫描的最大 ID，防止归档期间持续产生的点击让本轮任务无限追赶。

- 本轮开始后新分配且大于高水位的 ID 留给下一轮归档。
- 并发写入尚未提交的延迟点击可能在本轮扫描经过后才变为可见；不能承诺本轮一定包含所有迟到记录，下一轮会再次按时间阈值扫描主表。
- 任务总耗时仍取决于历史积压量和数据库吞吐量；900 秒是调度租约预算，不是整个归档任务的硬截止时间。
- 若任务超过调度租约，多个 Worker 可能同时参与剩余批次；批次级行锁与事务核对保护数据正确性，但仍可能产生额外竞争和重复扫描开销。
- 高水位之后的新数据不会被本轮归档；监控应关注主表过期点击积压是否持续下降。

## 4. 索引与锁策略

当前 `clicks` 主表已有 `idx_click_time(click_time)`。批次查询按 `click_time, id` 排序；InnoDB 二级索引叶子记录包含主键值，当前不额外创建重复索引。上线后仍应在目标数据分布上运行 `EXPLAIN`，确认优化器使用 `idx_click_time`，并观察实际扫描行数。

本次不使用表锁。锁定范围限定在每批命中的行及 InnoDB 为范围扫描维护的必要索引/gap 锁；批次提交后立即释放。

## 5. 自动重试策略

仅重试 MySQL 错误码：

- 1205：Lock wait timeout exceeded
- 1213：Deadlock found

最多 3 次额外重试，间隔 100/200/400 毫秒；每次重试前先 rollback，重新选择并锁定当前批次。重复键 1062、schema 错误、数据异常和数量不匹配不重试，直接 fail closed，避免掩盖永久性错误。

## 6. 测试覆盖

- 单元测试：多批提交、源/目标 URL 字段映射、归档写入失败、写入数量不一致、删除数量不一致、前批提交后后批失败可续跑、无源数据、无效天数/批次大小、1205/1213 重试。
- MySQL 集成测试：真实 MySQL + SQLAlchemy AsyncSession 验证多批归档、URL 字段完整性、近期记录不被归档，以及两个 Worker 并发运行时不重复归档、不丢失源记录。
- CI 使用本机临时 `platform_ci` 数据库；测试模块强制 loopback 地址与显式破坏性测试开关，不允许连接生产/远程数据库。
- 本文和测试不代表已经完成生产数据规模压测或线上故障演练。

## 7. 上线观测建议

- 监控每轮 `batch_count`、`archived_count`、`deleted_count`、`high_water_id` 和总耗时。
- 观察归档前后 `clicks` 过期数据积压、MySQL 慢查询、`data_lock_waits`、死锁次数、undo history 与连接池等待。
- 任务失败时确认失败批次是否回滚、之前批次是否已提交；允许安全重跑，不要人工直接删除主表记录。
- 在真实数据量下确认 1000 行批次的耗时和锁等待；若需调整批次大小，应同步更新上限、测试和运行预算。
- 点击归档仍是每月任务；若某轮失败，应告警并安排重跑，不应等到下一个月才发现积压未下降。

## 8. 官方依据

- MySQL 8.0 [Locking Reads](https://dev.mysql.com/doc/refman/8.0/en/innodb-locking-reads.html)：`SELECT ... FOR UPDATE` 的行锁语义、锁在 commit/rollback 释放；`SKIP LOCKED` 会返回不一致视图。
- MySQL 8.0 [Locks Set by Different SQL Statements](https://dev.mysql.com/doc/refman/8.0/en/innodb-locks-set.html)：范围扫描、索引选择与 gap/next-key 锁行为。
- MySQL 8.0 [Deadlock Handling](https://dev.mysql.com/doc/refman/8.0/en/innodb-deadlocks-handling.html)：保持访问顺序一致、使用合适索引、减少锁范围并处理死锁。
- MySQL 8.0 [Consistent Nonlocking Reads](https://dev.mysql.com/doc/refman/8.0/en/innodb-consistent-read.html)：`INSERT ... SELECT` 的源表读取锁行为与隔离级别相关；本实现先显式锁定 ID 批次，再按 ID 完成复制与删除。
