# Migration Runner 设计决策与实施门槛（2026-11-12）

> 状态：设计基线，尚未实现 Runner。本文不授权生产执行，不替代发布审批。
> 适用仓库：`Helong0511/Platform`。
> 安全边界：设计、代码和 CI 只允许使用 GitHub Actions 临时 MySQL/Redis、合成数据和 Mock；禁止连接生产服务器、数据库、缓存、队列或真实第三方接口。

## 1. 当前实现边界

当前代码已经具备：

- `app/db/migrations/manifest.py`：显式 revision 清单、路径绑定、SHA-256、依赖顺序和文件集合校验。
- `app/db/migrations/planner.py`：未知 revision、checksum 漂移、非连续 ledger 前缀和依赖缺失时 fail closed。
- `app/db/migrations/sql_parser.py`：受限 MySQL SQL 语句切分，支持常见引号和注释，拒绝 `DELIMITER`。
- `python -m app.db.migrations validate`：离线校验 manifest 和 SQL 语句边界，不创建数据库连接、不执行 SQL。

当前仍未实现：

- Migration ledger 数据表及其 schema 校验。
- 独立迁移 DSN / engine / 数据库账号。
- 数据库级迁移锁、Runner、执行状态持久化。
- 中断后状态核验与人工恢复命令。
- 应用启动只读 revision gate。
- 自动安装 / 旧库升级 / 并发 / 故障恢复的完整隔离 MySQL 测试。

## 2. 不直接采用 Alembic 的原因

当前五份迁移脚本包含 MySQL information_schema 检查、session user variables、PREPARE/EXECUTE、动态 DDL、SHOW/SELECT 验证语句。直接把这些脚本机械转换为 Alembic revision，或让 Alembic 的默认事务假设包裹它们，都不能自动解决 MySQL DDL 隐式提交、部分成功和恢复状态问题。

本阶段先保留现有 SQL migration 格式，完成显式 Runner 与故障模型验证。后续可单独评估 Alembic；不得仅为“看起来标准”而引入依赖，也不得假设 Alembic 会自动提供本项目需要的恢复语义。

## 3. Ledger 最小数据模型

建议首版使用独立表 `schema_migration_ledger`，由显式安装/迁移命令创建并校验：

| 字段 | 建议类型 | 语义 |
|---|---|---|
| `execution_order` | BIGINT AUTO_INCREMENT PRIMARY KEY | 数据库确认的应用顺序；不可用 SELECT 默认顺序代替 |
| `revision` | VARCHAR(128) UNIQUE NOT NULL | manifest revision |
| `checksum` | CHAR(64) NOT NULL | 执行前验证的 SHA-256 |
| `status` | VARCHAR(16) NOT NULL | running / applied / failed |
| `attempts` | INT UNSIGNED NOT NULL | 开始执行次数 |
| `runner_id` | VARCHAR(64) NULL | 本次执行实例标识，不包含凭据 |
| `started_at` | DATETIME(6) NULL | 本次尝试开始时间 |
| `applied_at` | DATETIME(6) NULL | 所有语句成功后的完成时间 |
| `failed_at` | DATETIME(6) NULL | 明确失败时间 |
| `error_summary` | VARCHAR(1000) NULL | 脱敏错误摘要，不写 SQL 参数、DSN 或秘密 |

约束：

1. `revision` 唯一；同一 revision 只能有一条当前状态记录。
2. `execution_order` 由数据库分配，读取 ledger 时必须 `ORDER BY execution_order ASC`。
3. 应用历史必须是 manifest 的连续前缀；不得跳过早期 revision 直接应用后续 revision。
4. `applied` 记录的 checksum 必须与 manifest 完全一致；已应用文件被修改即拒绝继续。
5. `running` / `failed` 都是阻断状态。不得自动重置为 pending 或自动重跑。
6. 状态变更和 DDL 不能假设处于同一可回滚事务；MySQL DDL 隐式提交会打破该假设。

Ledger 自身也必须校验字段类型、长度、NULL、默认值、主键、唯一键、索引、字符集和排序规则。发现同名错误表时 fail closed，不自动 DROP/ALTER。

## 4. Runner 生命周期

所有锁和迁移 SQL 必须使用同一个专用物理 MySQL connection/session：

1. 加载并校验 manifest 与全部 SQL 文件 checksum。
2. 加载独立迁移连接配置；禁止导入 Web Worker 默认 engine 或使用应用运行账号。
3. 建立连接，读取 MySQL 版本、当前 schema、`@@SESSION.sql_mode`、连接字符集和排序规则。
4. 校验 MySQL 版本满足当前脚本要求（现有迁移至少要求 MySQL 8.0；Cap CHECK 约束脚本要求 8.0.16+）。
5. 在该连接执行 `SELECT GET_LOCK(...)`；返回值必须严格为 1。0、NULL、异常均终止。
6. 校验 ledger 结构，按 `execution_order` 读取历史，使用 planner 生成待执行计划。
7. 对每个 revision：先持久化 `running` 和 attempts，再提交 ledger 状态；之后才开始执行 SQL。
8. SQL parser 按读取到的 `@@SESSION.sql_mode` 配置反斜杠规则；每条语句在同一 session 顺序执行。每条语句结果集必须消费/关闭，不能遗留未读结果。
9. 全部语句成功后，再持久化 `applied` 与 `applied_at`。
10. 明确失败时尽力持久化 `failed` 和脱敏摘要；若连接已断开，原 ledger 行保留 `running`，不得谎报为 failed 或 applied。
11. 释放锁必须在原连接上调用 `RELEASE_LOCK`；若连接丢失，锁由 MySQL session 结束释放，但本次结果视为状态不确定。
12. 关闭连接并返回明确退出码。

必须使用单一连接的原因：当前 SQL migration 使用 `SET @...`、`PREPARE`、`EXECUTE` 和 `DEALLOCATE PREPARE`，这些状态依赖 MySQL session。每条语句重新建连接会破坏脚本语义。

## 5. 状态机与恢复

允许的正常路径：

```text
未登记 -> running -> applied
                  -> failed
```

异常恢复原则：

- 进程崩溃、机器重启、连接断开或 DDL 中途失败后，revision 可能仍为 `running`；这表示 schema 状态不确定，不等于 SQL 全部失败。
- `running` / `failed` 状态下 Runner 必须停止，不得自动重跑。
- 恢复命令先只读检查目标表、列、索引、约束、数据回填结果和当前 checksum，输出差异报告。
- 只有显式人工确认当前 schema 已达到该 revision 的完整目标状态，才能将 ledger 标记为 applied；若部分完成，则由单独、可审计的 forward-fix 修复。
- 不实现虚假的通用 down migration。回退依赖已演练的 forward-fix 或备份恢复方案。

## 6. SQL 执行语法边界

首版 Runner 只支持当前解析器能够可靠切分的 SQL 子集：

- 单/双引号字符串、反引号标识符、重复引号、SQL_MODE 对应的反斜杠转义。
- `--`、`#` 行注释、普通块注释和 MySQL 可执行注释。
- 单条语句分号终止；同一 session 执行。
- 拒绝 `DELIMITER`、存储过程/触发器定义、无法识别的客户端命令和不受支持的语法。
- 解析器只做语句边界切分，不是 MySQL 语法校验器。CI 必须在真实隔离 MySQL 上执行脚本，静态 validate 不能代替。

当前离线 CLI 默认按常见反斜杠转义模式检查边界；正式 Runner 必须先读取 session SQL_MODE，再传递 `backslash_escapes`。SQL_MODE 不符合已测试组合时应拒绝执行，而不是猜测。

## 7. 大表数据回填专门要求

`20261110_third_party_report_event_idempotency.sql` 当前有全表 `UPDATE ... WHERE event_key IS NULL`。在没有代表性规模的隔离演练前，不得直接用于生产。

后续必须先评估并实施可恢复批处理：

- 按稳定主键游标分批，不用 OFFSET。
- 每批限制行数、事务大小和执行速率。
- 记录最后处理主键、完成量、失败摘要和运行耗时。
- 每批完成后可安全续跑；重算必须保证幂等。
- 回填前后分别核对 NULL、空字符串、重复键和事件键算法。
- 新唯一索引建立成功并验证后，才允许移除旧唯一索引。
- 使用合成大数据量测试锁等待、redo/undo、执行时长、磁盘增长和复制延迟（如适用）。

## 8. 启动期数据库职责拆分

当前实际启动行为尚未改造：

- `app/bootstrap/lifespan.py` 在应用启动时调用 `create_database()`，随后在 advisory lock 下执行 `Base.metadata.create_all()`。
- `app/core/database.py::create_tables()` 还保留第二个 `Base.metadata.create_all()` 入口；本轮未完成全仓库所有调用点的穷尽性静态搜索。
- `init_db()` 会在启动时确保默认管理员存在。
- `init_scheduled_tasks_in_db()` 会在每个 Worker 启动时同步任务配置，且当前失败会记录 warning 后继续启动。

目标拆分：

| 职责 | 目标执行者 | 应用运行账号权限 |
|---|---|---|
| 创建数据库/schema | 独立 provisioning | 无需 CREATE DATABASE |
| 建表/DDL migration | 显式 migration job | 无 CREATE/ALTER |
| schema revision/drift gate | 每个应用 Worker，只读 | SELECT / 必需只读元数据权限 |
| 默认管理员初始化 | 显式、幂等 bootstrap 流程 | 最小业务表 DML |
| 定时任务配置同步 | 单一协调者/leader，具备审计与重试 | 仅相关表 DML |

不能在 Runner 和空库安装路径验证完成前直接移除现有 `create_database` / `create_all`，否则会破坏首次安装。

## 9. 必须通过的隔离 CI 验收

1. 空库：显式初始化 ledger、执行全部迁移、重复执行无副作用。
2. 旧库：构造代表性旧 schema 与合成历史数据，升级到最新 revision。
3. 完整性：checksum 漂移、未知 revision、非连续历史、错误 ledger 结构全部拒绝。
4. 并发：两个 Runner 同时启动，只有一个取得锁；另一个安全等待或失败。
5. Session：验证 SET/PREPARE/EXECUTE 在单连接中正常运行；断开连接后锁释放。
6. 故障注入：在每个 DDL 边界前后中断，状态必须可诊断，Runner 不得盲目重跑。
7. SQL_MODE：默认模式和 `NO_BACKSLASH_ESCAPES` 分别验证；未支持模式拒绝。
8. 结构冲突：错误同名表/索引/约束必须 fail closed。
9. 数据安全：重复事件键、NULL 回填、PII 清理标记与 outbox 状态符合预期。
10. 权限边界：应用运行账号无 CREATE DATABASE / CREATE TABLE / ALTER 权限时，已迁移 schema 仍可启动；schema 落后时只读 gate 拒绝启动。
11. 字符集：数据库、表、列、连接字符集和中文注释/数据均验证 utf8mb4。
12. 备份恢复：至少演练隔离库备份恢复及 forward-fix；不把自动 down migration 作为验收条件。

CI 只能连接 GitHub Actions 创建的 loopback 临时 MySQL/Redis，所有数据均为合成数据；禁止从 secrets 读取生产 DSN。

## 10. 当前结论

- Run #1461 对 HEAD `f35ca5063e14a9de0e22ab6b17b4cbc8b75e0f0c` 的 Backend / Frontend 均成功；它验证 manifest/planner/parser/离线 CLI 及现有 CI，不代表 Runner 已实现。
- 本文是 Runner 的实施约束和验收基线，不代表任何数据库迁移已执行。
- PR #1 继续 Open / Draft；不合并 main、不部署。
- 凭据安全专项仍按用户要求暂缓。
- 未连接生产服务器、数据库、Redis、队列或真实第三方接口。

## 2026-11-13 启动入口与部署单元复核

本次复核基于分支 `fix/non-credential-hardening-2026-11` 当前 HEAD `90bf1c65eb5479ac30db3ea7d82d479f9859669f`，读取了以下文件：

- `app/bootstrap/lifespan.py`
- `app/db/database.py`
- `app/core/database.py`
- `.github/workflows/ci.yml`
- `systemd/Platform-backend.service`
- `systemd/Platform-scheduler.service`
- `tests/test_database_init.py`
- `tests/test_mysql_migrations.py`

### 已直接确认的启动行为

1. Backend 与 Scheduler 两个 systemd unit 都以 Gunicorn 启动同一个 `app.main:app`，因此两者都会执行 FastAPI lifespan。
2. 两个服务都继承 `/data/Platform/.env`，并分别覆盖 `GUNICORN_ROLE=api` / `GUNICORN_ROLE=scheduler`。这两个服务都会进入当前 schema bootstrap 路径；不是只有 API 服务执行。
3. 当前 lifespan 顺序为：`create_database()` → `_bootstrap_database_schema()` → `init_db()`。MySQL 场景下前两步分别需要创建数据库权限及当前连接可执行 ORM DDL 的权限。
4. `_bootstrap_database_schema()` 的 MySQL advisory lock 只串行化两个启动者的 `create_all()`，并未将 DDL 移出应用 Worker，也未将权限降为只读。
5. `app/core/database.py::create_tables()` 是另一个可调用的 `Base.metadata.create_all()` 封装。当前已直接确认该函数定义存在，但本轮未完成全仓库所有调用点的穷尽搜索；不得据此断言它没有调用者。
6. `init_db()` 会在每个启动 lifespan 中检查管理员并在不存在时创建默认管理员。唯一键冲突路径有并发重查，但这仍是应用启动时的业务数据写入，不是 schema migration。
7. `init_scheduled_tasks_in_db()` 在 API 与 Scheduler 启动路径都会调用。它是任务配置数据同步，不应混入 schema revision ledger；应由单一协调者或具备幂等/锁/告警的专用同步流程负责。
8. 当前 CI 启动临时 MySQL 8.0 和 Redis 7.4，并执行全量 pytest；迁移 SQL 集成测试直接调用测试辅助执行器。CI 尚未证明存在独立 Migration Runner、专用迁移身份或只读启动 schema gate。

### 当前启动漂移检查的边界

`_schema_metadata_drift()` 仅报告缺表、缺列。它没有核对列类型/长度、NULL 属性、默认值、主键/唯一约束、普通索引、外键、CHECK、字符集或 collation。因此它只能作为最低限度存在性检查，不能被描述为完整 schema drift 检测或 migration 完成证明。

### 本次核查范围限制

GitHub Tree 可确认仓库文件清单，但本轮没有成功取得可用的分支级全仓库代码搜索结果。因此，`create_all`、`create_tables`、`create_database`、`init_db` 的所有间接调用点仍未穷尽。后续必须在可执行的仓库工作区使用类似 `git grep -nE 'create_all|create_tables|create_database|init_db'` 的方式完成全仓库搜索，并检查动态导入、脚本入口、测试夹具和部署命令后，才能关闭此项。

### 下一阶段实施顺序（不可跳步）

1. 完成全仓库调用点搜索和入口清单，先标记哪些入口属于生产运行路径、测试路径、手工运维路径。
2. 实现独立 provisioning / migration 命令与 ledger；不要先删除现有 `create_all`，避免空库初始化路径被破坏。
3. 在隔离 MySQL 中验证空库 provisioning、旧库 migration、checksum drift、未知 revision、非连续 ledger、并发 GET_LOCK、连接中断及 DDL 部分完成后的人工恢复。
4. 增加 schema revision 只读 gate，先以观察/拒绝不兼容启动的方式验证；再将 systemd 发布流程改为先执行 migration job、后启动 API/Scheduler。
5. 确认应用运行身份不再拥有 CREATE DATABASE / CREATE / ALTER / DROP 等 schema 权限；migration 身份与运行身份分离。
6. 最后移除 lifespan 的自动建库/建表行为，并对两个 systemd unit 的启动顺序和失败恢复做隔离演练。

以上结论不授权连接任何生产服务器、数据库、Redis、队列或真实第三方接口。PR 仍保持 Open / Draft，不合并、不部署；凭据安全专项继续暂缓。

## 2026-11-13 MySQL 集成测试执行器一致性修复

复核 `tests/test_mysql_migrations.py` 时发现，MySQL 集成测试原先使用：

- 删除整行 `--` 注释；
- 再用 Python `split(';')` 切分 SQL；
- DDL 中断故障注入辅助函数也独立复制了同一套简单切分逻辑。

这意味着离线 Migration SQL Parser 与真正执行迁移集成测试的执行路径并不一致。若未来迁移 SQL 在字符串中出现分号、块注释或更复杂的转义内容，CI 可能按错误边界执行，不能证明正式 Runner 将正确处理这些脚本。

本次已修复提交 `133180239a2c8e79d00aa4975542d44204b1fece`：

- 正常 MySQL 集成迁移测试改为调用 `app.db.migrations.sql_parser.split_mysql_statements()`。
- DDL 边界中断/恢复测试也改为调用同一个解析器。
- 移除两处重复的 `split(';')` 实现。
- SQL 文件仍以 UTF-8 读取；CI 仍只连接 workflow 创建的 loopback 临时 MySQL，且破坏性测试继续要求显式隔离开关。

这次修改让现有 MySQL 迁移集成测试与离线解析器共享语句边界逻辑，但不等于正式 Migration Runner 已实现。当前测试辅助执行器仍然只是测试代码，不得作为生产迁移入口使用。正式 Runner 仍须在同一物理 Session 中取得 advisory lock、读取 SQL_MODE、持久化 ledger 状态、执行语句并处理结果集。
