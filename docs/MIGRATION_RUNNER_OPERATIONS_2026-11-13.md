# Migration Runner 操作说明（2026-11-13）

## 1. 当前功能

仓库提供以下命令：

```bash
python -m app.db.migrations validate
python -m app.db.migrations status
python -m app.db.migrations apply
```

- `validate`：离线校验 manifest、文件 SHA-256 和 SQL 分句，不连接数据库。
- `status`：只读查询 `platform_schema_migrations`，不创建表、不执行 DDL。
- `apply`：通过专用 MySQL 迁移账号执行待应用的增量 migration。

## 2. 运行前提

1. MySQL 版本至少 8.0.16。
2. 连接字符集为 utf8mb4。
3. `MIGRATION_DATABASE_URL` 必须显式设置为 `mysql+aiomysql` DSN。
4. 应用数据库也必须为 MySQL，且与迁移 DSN 指向同一数据库名、同一服务器端点（TCP 主机/端口或 Unix Socket）；迁移账号用户名必须不同于应用运行账号。CLI 会从应用设置读取 `SQLALCHEMY_DATABASE_URI` 并在任何不匹配时 fail closed。
5. 目标数据库必须由受控 provisioning 预先创建并选定。完整基线导入时使用 MySQL 客户端显式指定目标库，例如 `mysql --default-character-set=utf8mb4 --database=<目标库> < sql/platform.sql`；基线文件不再自行 CREATE DATABASE 或 USE。Runner 只执行 `app/db/migrations/manifest.py` 登记的增量 migration，不会导入 `sql/platform.sql`。

示例仅展示变量形式，不要把真实密码提交到仓库或写入命令历史：

```bash
export MIGRATION_DATABASE_URL='mysql+aiomysql://<migration_user>:<password>@<db-host>:3306/platform?charset=utf8mb4'
python -m app.db.migrations validate
python -m app.db.migrations status
python -m app.db.migrations apply
```

## 3. 执行语义

- Runner 使用单个物理 MySQL connection，从 `GET_LOCK` 到 `RELEASE_LOCK` 不切换连接。
- 每个 revision 在执行 SQL 前先写入 `running`。
- 所有语句按顺序执行；每条语句结果集会被消费并关闭。
- 全部成功后写入 `applied`。
- 明确失败写入 `failed`；连接中断时可能保留 `running`。
- MySQL DDL 会隐式提交，不能假设整份 migration 可以事务回滚。
- 出现 `running` 或 `failed` 时，Runner 会停止，不会自动重跑；先检查 schema 实际状态、DDL 已完成边界和 checksum，再制定单独 forward-fix。
- `status` 返回非零阻断码时，不得忽略后启动部署。

## 4. 基线文件安全边界

`sql/platform.sql` 是完整 schema 快照，含 `DROP TABLE IF EXISTS` 和客户端 DELIMITER / routine 定义；当前快照不包含 `CREATE DATABASE` 或 `USE`，由 provisioning 预先创建目标库，并通过 MySQL 客户端 `--database=<目标库>` 显式选择。它不是增量 migration，也不是 Runner 的输入。

- 只允许在全新或可丢弃数据库上使用经过审核的初始化流程。
- 当前 manifest 共 12 条 revision；执行前必须先运行 `validate`，并核对 `status` 与目标环境基线版本。
- 绝不能把它用于已有数据库升级。
- 不要把“ORM 表名覆盖测试通过”误认为所有列、索引、外键、CHECK 和字符集都已完成物理结构核验。

## 5. MySQL DDL 在线变更风险

当前 migration 中的部分 `ALTER TABLE ... ADD COLUMN ... AFTER ...` 未显式指定 `ALGORITHM`。MySQL 8.0 会优先使用受支持的 `INSTANT`，但当操作不满足 `INSTANT` 条件时，可能退回 `INPLACE` 或 `COPY`；后两者的表重建/并发访问特性不同。尤其当前 Runner 最低版本是 8.0.16，而 `INSTANT ADD COLUMN` 在 8.0.29 之前只允许追加到列尾，当前 migration 使用 `AFTER` 指定列位置，因此不能仅凭版本号推断会采用 INSTANT。

上线前必须在与目标环境相同的 MySQL 小版本、表结构、行数和索引规模的隔离副本上演练每条 DDL，记录实际算法、耗时、metadata lock 等待、复制延迟和写入影响。未完成演练前，不得在大表上直接执行这些 migration。后续应根据正式支持的 MySQL 最低版本，决定是否统一要求 `ALGORITHM=INSTANT`（不支持时立即失败）或采用受控在线变更工具；不得让 MySQL 静默退回高影响算法。

参考：
- MySQL 8.0 `ALTER TABLE` 算法说明：https://dev.mysql.com/doc/refman/8.0/en/alter-table.html
- MySQL 8.0 InnoDB Online DDL 限制：https://dev.mysql.com/doc/refman/8.0/en/innodb-online-ddl-operations.html

## 6. 当前尚未达到生产使用条件

- API/Scheduler lifespan 已移除 `create_database()` 与 `Base.metadata.create_all()`，启动时只读检查 migration revision 和 ORM 表/列是否存在。
- 旧的 `create_tables()` / `create_database()` helper 尚待全仓调用点核查与禁用/迁移。
- Runner 尚未成为 systemd 部署的唯一 schema 变更入口；仍需演练 migration job 先于 API/Scheduler 启动。
- 新库基线导入、旧库升级、备份恢复、worker pause/resume 和失败人工恢复演练仍未完成。

因此：当前命令和 CI 仅证明隔离测试环境中的 Runner 与只读启动 gate 行为；未完成真实新库/旧库部署演练前，不能在生产执行，也不能宣称上线就绪。


## 7. 当前隔离验收记录

- PR HEAD：`6394f63976a79ffdbfe414dc46060db4f7773b76`。
- GitHub Actions Run #43398657923：Backend 669 passed、1 skipped、1 warning；Frontend 依赖审计、Lint、Build、Playwright Mock API E2E 全部通过。
- 该结果只覆盖 GitHub Actions 临时 MySQL/Redis 与合成数据；不代表空库完整导入、旧库真实规模升级、备份恢复或生产 DDL 风险演练已经完成。
- PR #1 仍为 Open / Draft；不合并、不部署。


## 8. 第三方上报平台标识二进制排序规则迁移（2026-11-14）

新增 revision：`20261114_third_party_report_platform_binary_collation`。

- ORM 模型与基线 schema 将 `third_party_report_logs.platform` 明确设为 `utf8mb4_bin`，确保数据库平台标识比较与应用层精确字符串身份一致。
- 增量 SQL 将既有列调整为 `VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL DEFAULT NULL`；不重写历史 platform 值或 event_key。
- 迁移通过 `information_schema.COLUMNS` 判断目标结构，已符合时跳过 ALTER；执行后再次核验结构，核验失败必须让 migration 失败，不得写入 applied。
- 该 ALTER 可能重建关联索引。正式环境执行前，必须在同版本、同结构、相近数据量和索引规模的隔离副本测量 DDL 算法、耗时、metadata lock、复制延迟、磁盘峰值和业务写入影响；未演练前禁止直接生产执行。
- CI 新增真实 MySQL migration 测试：从旧 `utf8mb4_0900_ai_ci` 列升级，连续执行 migration 两次，并检查精确比较、历史值保留和索引保留。测试只覆盖 CI 临时 MySQL，不代表生产大表在线 DDL 演练或备份恢复已通过。
- 当前 CI 正在对最新 migration 测试修正进行复验；以最新 PR HEAD 的 Backend / Frontend 全部通过结果为准，不能用此前失败 Run 的结果替代。
- PR #1 仍为 Open / Draft；此迁移未经生产副本演练前不得合并部署。

MySQL 官方参考：
- Collation 与大小写敏感比较：https://dev.mysql.com/doc/refman/8.0/en/case-sensitivity.html
- ALTER TABLE 行为与算法：https://dev.mysql.com/doc/refman/8.0/en/alter-table.html
- 字符串类型与字符集/排序规则：https://dev.mysql.com/doc/refman/8.0/en/string-type-syntax.html

## 9. 管理员 Outbox 重试与审计事务一致性（2026-11-14）

管理员手动重试不是直接发送 HTTP 请求，而是将失败 Outbox 事件重新置为待处理。该状态变更与“谁在何时触发了重试”的审计记录必须同生共死。

- API 现在把请求依赖注入的同一个数据库 session 传给 `retry_report_log`。
- 重试 SQL 更新不再在核心函数内提前独立 commit；随后写入的管理员操作审计日志由 API 的统一 commit 一起提交。
- 若审计写入或统一 commit 失败，重试状态变更不会单独落库，避免出现“事件已重新排队但审计日志缺失”。
- 独立调用 `retry_report_log(log_id)` 的兼容路径仍使用自己的 session 并提交；管理 API 必须传入共享 session。
- 新增单元测试验证传入共享 session 时核心函数不会自行 commit。
- 现在每条事件增加独立 `manual_retry_count`，历史记录迁移时默认为 0；管理员重新入队通过条件 UPDATE 原子递增，单条事件整个生命周期最多人工重新入队 3 次。自动 `attempt_count` 仍只表示当前自动重试周期，重置它不会重置人工累计次数。
- 达到 3 次后，API 不再允许人工重新入队；需要进一步处置时应走独立的事件纠错/补偿流程，不得直接改数据库计数或反复重置自动次数。当前上限是保守的代码策略，业务负责人仍需确认是否符合运营要求。
- 重试动作仍与管理员审计日志在同一事务提交；每次成功入队都会产生管理员操作审计记录。审计日志保留、查询/导出权限及不可篡改性仍需专项验收。
