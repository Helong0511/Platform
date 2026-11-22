# Migration Runner 锁等待超时审计（2026-11-22）

## 发现

Migration Runner 已使用 MySQL GET_LOCK 串行化迁移进程，并为获取该命名锁设置 60 秒上限。但 GET_LOCK 不等于表级 metadata lock，也不限制 InnoDB 行锁等待。

MySQL 的 SESSION lock_wait_timeout 默认值可能长达 31536000 秒。若 ALTER TABLE 等 DDL 遇到长事务持有的 metadata lock，迁移连接可能长时间等待；在发布窗口中会拖延部署，并可能形成连接占用和运维误判。

## 修复

- 在获取 GET_LOCK 后、执行 ledger 或业务 DDL 前，设置 SESSION lock_wait_timeout=30。
- 同时设置 SESSION innodb_lock_wait_timeout=30，限制迁移 DML/探测语句的 InnoDB 行锁等待。
- 通过 SELECT @@SESSION 读取两个变量并核验确实生效；无法确认时 fail-closed，不继续 DDL。
- 设置作用于 Runner 当前独占的物理连接；该连接在 GET_LOCK 到 RELEASE_LOCK 期间保持不变，连接结束后 Session 设置不会污染应用连接池。
- 超时只限制等待锁的时间，不限制 DDL 已获得锁后的执行时长；大表 DDL 算法、耗时、磁盘峰值和复制延迟仍须在生产等价副本演练。

## 测试

新增 tests/test_migration_runner_lock_timeouts.py，覆盖设置语句、读取核验和配置未生效时拒绝继续执行。

## 风险边界

本次不连接或修改生产 MySQL，不执行生产 DDL。30 秒为迁移锁等待预算；若特定受控迁移确实需要更长等待，应经审查后显式调整常量并同步测试与运维手册，不能恢复为 MySQL 的超长默认值。

## 验收

等待 PR Backend 全量测试、Migration Runner MySQL 集成测试、Frontend 和 Security CI 全部成功后再合并。
