# 敏感路径探测日志分批清理运行说明

## 行为与事务边界

`cleanup_sensitive_path_probe_logs()` 在任务开始时只计算一次应用时区 cutoff，并在本轮所有批次中复用。每批按主键升序选择有限数量的过期记录，使用 MySQL 8 `FOR UPDATE` 锁定当前批次，再按主键和固定 cutoff 删除。这里刻意不使用 `SKIP LOCKED`：被其它清理实例锁住的记录不能被误当作“没有剩余记录”；并发实例可以等待锁释放，单批等待受总运行预算约束。

每批独立提交。外部注入的 `AsyncSession` 仍由调用方负责关闭，但提交行为与旧实现一致；提交粒度从整轮一次变为每批一次。因此调用方不得把其它需要原子提交的业务写入混入该 Session 后再调用清理任务。

批次提交失败时只回滚当前事务。异常 `SensitivePathProbeCleanupError` 的 `deleted_count` / `batch_count` 只统计已确认提交的批次；超时发生在提交过程中时，数据库端是否完成提交可能未知，不能把该次未知批次计入已确认数量，也不能自动重试未知状态。

## 配置

| 环境变量 | 默认值 | 允许范围 | 说明 |
|---|---:|---:|---|
| `SENSITIVE_PATH_PROBE_RETENTION_DAYS` | 90 | 1–36500 | 保留天数；0、负数、bool 等无效值不会被当成默认值 |
| `SENSITIVE_PATH_PROBE_CLEANUP_BATCH_SIZE` | 500 | 1–5000 | 每批最多选择和删除的记录数 |
| `SENSITIVE_PATH_PROBE_CLEANUP_MAX_BATCHES` | 20 | 1–1000 | 单轮最大批次数 |
| `SENSITIVE_PATH_PROBE_CLEANUP_MAX_RUNTIME_SECONDS` | 20 | 1–300 | 单轮总运行预算；单批查询、删除和提交共享剩余预算 |

达到批次数或运行预算时返回 `complete=false`、`remaining_possible=true`，并将任务结果记录为“清理未完成”，不能显示为成功完成。下一次正常 Cron 运行会继续处理仍符合固定保留策略的记录；任务不执行即时自动重试。

## MySQL 验收

Full Audit CI 使用隔离的本机 MySQL 8 / `platform_ci` 数据库运行 `tests/test_mysql_sensitive_path_probe_cleanup.py`。该测试文件在非 CI 环境默认跳过；若在 GitHub Actions 中检测到非 loopback 主机、非 `platform_ci` 数据库或缺少显式破坏性测试许可，会直接拒绝运行。

验收覆盖：
- 真实 MySQL 8 的 `EXPLAIN` 检查，确认按 `created_at` 过滤时使用 `idx_sensitive_probe_created_at`；
- 每批删除上限、固定 cutoff 边界与部分完成状态；
- 第二批提交失败时第一批仍保留已提交结果，当前批次回滚；
- SQLite 单测只验证业务逻辑，不替代 MySQL 锁、事务和执行计划验证。

本次实现未修改表结构，因此不新增 SQL Migration，也不对生产环境执行索引删除或数据清理。生产部署后如需确认现有表索引，请在维护窗口只读执行 `SHOW INDEX FROM sensitive_path_probe_logs` 并核对 `idx_sensitive_probe_created_at`；不得仅凭 ORM 变更执行 `DROP INDEX`。
