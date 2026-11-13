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

## 2026-11-13 迁移启动链路复核与 CI 证据

### 本轮核验范围

复核分支 `fix/non-credential-hardening-2026-11` 当前 HEAD（`006be5d2d39835a5c9ceccad19dd6f9ad66c9827`）中的：

- `app/bootstrap/lifespan.py`：启动调用顺序、schema bootstrap、任务配置同步。
- `app/db/database.py`：MySQL provisioning 连接与 `CREATE DATABASE IF NOT EXISTS`。
- `app/core/database.py`：`create_tables()`、`init_db()`。
- `app/scheduler_module/task_init.py`：任务配置同步的锁、提交、并发冲突与失败策略。
- `systemd/Platform-backend.service`、`systemd/Platform-scheduler.service`：实际启动入口和环境变量覆盖。
- `.github/workflows/ci.yml`、`tests/test_mysql_migrations.py`、`tests/test_schema_metadata_drift.py`：隔离测试边界及验证范围。

### 已确认的启动行为

1. Backend 与 Scheduler systemd unit 都运行 `gunicorn ... app.main:app`，都会进入同一 FastAPI lifespan。
2. 两个 unit 都加载 `/data/Platform/.env`；随后分别覆盖 `GUNICORN_ROLE=api` 与 `GUNICORN_ROLE=scheduler`。Scheduler 额外设置 `ENABLE_SCHEDULER=true`、`SCHEDULER_WORKER=1`、`WORKERS=1`。
3. 每个进入 lifespan 的服务实例都会执行 `create_database()`、`_bootstrap_database_schema()` 和 `init_db()`。因此当前应用运行身份仍需要数据库创建权限及 schema DDL 权限；advisory lock 仅串行化 create_all，不构成独立 migration job 或权限隔离。
4. `_schema_metadata_drift()` 当前只比较 ORM 表是否存在、ORM 列名是否存在。它不核对列类型/长度/NULL/default、主键、唯一键、普通索引、CHECK、字符集或排序规则；测试也只覆盖缺表/缺列与完全存在两类情况。
5. `app/core/database.py::create_tables()` 是第二个 `Base.metadata.create_all()` 封装。当前已确认其定义，但本轮未取得可证明全仓库调用点穷尽的检索结果；不得据此声称它没有调用者。
6. `init_scheduled_tasks_in_db()` 在 schema bootstrap、管理员初始化后每个 API/Scheduler lifespan 都会执行，与 APScheduler 是否启动无关。当前版本已改为整批事务提交，移除 `SKIP LOCKED`，识别唯一键冲突、MySQL 死锁/锁等待超时后整批回滚并有限重试；其它错误回滚后向上传播。lifespan 仍允许 Worker 在记录明确错误后继续启动，因此任务同步失败必须进入监控告警，不能视为同步成功。该函数属于业务配置同步，不属于 schema migration。
7. 当前 CI 使用 GitHub Actions 临时 MySQL 8.0 / Redis 7.4；MySQL 迁移测试要求 GitHub Actions、`UNIT_TEST=1`、显式 destructive flag、loopback host 和固定 `platform_ci` 数据库。迁移 SQL 测试辅助执行器与离线 parser 已统一，但这仍不是生产 Runner。

### 历史 CI 证据（Run #1469）

- Run #1469：https://github.com/Helong0511/Platform/actions/runs/43345544426
- SHA：`006be5d2d39835a5c9ceccad19dd6f9ad66c9827`
- Backend 与 Frontend jobs 均成功；前端包含 Lint、Build 和 Mock API Playwright E2E。
- 该结果只证明该 SHA 的 CI 工作流通过，不证明生产 Migration Runner、最小权限迁移账号、历史数据发布演练或备份恢复能力已经实现。

### 尚未关闭的工程阻断

- 未实现独立 provisioning、Migration Runner、ledger、专用迁移 DSN/账号及应用启动只读 revision gate。
- 尚未完成 `create_tables()`、`create_database()`、`Base.metadata.create_all()`、`init_db()` 等入口的全仓库调用点穷尽检索；当前 GitHub code-search 对目标分支未提供可用结果，不能作为“无调用者”的证据。
- 尚未完成 schema drift 对类型、约束、索引、字符集/排序规则的完整检查。
- 定时任务配置同步仍由每个 API/Scheduler 实例启动时触发；虽然批次原子性和并发冲突重试已有修复，但仍缺少单一协调者、可查询的同步健康状态、失败告警和恢复策略。
- `20261110_third_party_report_event_idempotency.sql` 的全表回填仍未改造成可恢复、按主键分批和限速的流程。不得直接修改已登记 migration 内容或 checksum 来掩盖该风险。
- 旧 schema + 代表性历史数据、逐 DDL 中断恢复、备份恢复、应用兼容回滚、数据/结构 diff 尚未完成隔离演练。

**结论：** 当前 CI 通过，但数据库发布架构仍未达到可上线验收条件。PR #1 继续 Open / Draft；不合并 main、不部署、不连接生产服务器、数据库、Redis、队列或真实第三方接口。凭据安全专项继续按用户要求暂缓。

## 2026-11-13 Gunicorn Worker 级启动行为补充

### 进一步核对 Gunicorn Worker 生命周期

本轮继续读取 `gunicorn.conf.py`、`app/main.py`、两个 systemd unit 和 `app/bootstrap/lifespan.py`：

1. Backend 未显式设置 `WORKERS` 时按 CPU/内存规则计算 Worker 数；配置注释明确 2 核 API 默认 3 Worker。Scheduler 的 `WORKERS=1` 且角色判断固定为 1 Worker。
2. 两个 systemd unit 都以 `app.main:app` 作为 ASGI 应用入口；`app.main` 将 `app.bootstrap.lifespan.lifespan` 注册为 FastAPI lifespan。
3. 每个 Worker 各自创建并运行应用生命周期，因此不能将数据库初始化的执行次数简单描述为“Backend 一次 + Scheduler 一次”。Backend 多 Worker 与 Scheduler Worker 都可能分别触发启动链路。
4. 每个 Worker 的启动链路都执行 `create_database()`、`_bootstrap_database_schema()`、`init_db()`，随后还会调用 `init_scheduled_tasks_in_db()`。因此启动期数据库权限和并发写入影响面覆盖全部 Worker。
5. `_bootstrap_database_schema()` 内部 MySQL advisory lock 只能协调它所保护的 schema bootstrap 临界区，不能替代独立迁移身份，也不能保护管理员初始化、任务配置同步或其他不在该临界区中的写入。
6. 任务同步函数现为整批事务；唯一键/死锁/锁等待超时冲突会整批回滚并有限重试，其它异常向上传播。lifespan 仍采用记录明确错误后继续启动的降级策略，因此失败状态需监控告警，不能把服务启动等同于任务配置同步成功。
7. 因此未来拆分应将 schema provisioning / migration 作为独立、显式、单次运行的部署步骤；API 与 Scheduler Worker 启动时仅执行只读 schema revision/drift gate。管理员 bootstrap 与 scheduled task config sync 应分别设计唯一协调者、幂等、失败告警及恢复机制，不应借用 migration ledger 充当业务数据同步账本。

### 当前结论的边界

- 上述结论由实际入口和配置直接支持。
- 当前分支 Git tree 中有 536 个 Python 文件（app 433、tests 102、其它 1）；尚未完成全量调用点扫描，GitHub 搜索结果为空不能作为无调用者证明。
- `app/core/database.py::create_tables()` 的其它调用者仍待穷尽核验。
- 本补充不修改应用行为，不代表 Runner 已实现或已完成发布演练。

## 2026-11-13 定时任务配置同步原子性修复

### 已确认的问题

- `init_scheduled_tasks_in_db()` 原先对每条任务单独 commit；批次中途发生数据库异常时，前面任务可能已提交，后续任务未同步。
- 多个异常分支仅记录日志并继续，最外层也捕获异常后正常返回；调用方可能把部分同步误认为完整成功。
- 查询使用 `FOR UPDATE SKIP LOCKED`；被其它 Worker 锁住的现有任务可能被暂时视为不存在，随后走 INSERT 并触发唯一键竞争。
- `ScheduledTask.task_name` 在 ORM 中有唯一约束；现有管理员停用状态和运行计数属于运行时数据，配置同步不应重置。

### 本轮修复

- 移除 `skip_locked=True`，不再将被锁定的现有任务当作不存在。
- 将一批 `TASK_CONFIGS` 的 INSERT/UPDATE 合并到单个数据库事务，统一提交；失败时整体 rollback，避免部分批次持久化。
- 对 task_name 为空或配置内重复的情况，在写库前 fail fast。
- 只对识别出的唯一键冲突执行整批 rollback + 重新读取重试，最多 3 次；其它数据库错误回滚后向上传播。
- 配置同步只更新函数路径、Cron 和描述，不重置管理员的 `is_active`、运行计数及最近执行状态。
- lifespan 捕获同步失败后仍允许 Worker 继续启动（避免把任务配置写入短暂故障直接扩大为 API 全面不可用），但现在会明确记录失败状态和异常类型，不再输出原始数据库异常文本；不能再将失败记录为同步成功。
- 新增隔离 SQLite 测试覆盖整批原子回滚、重复同步幂等性、保留管理员停用状态/运行统计、重复 task_name 拒绝及唯一键错误分类。

### 仍需验证 / 限制

- MySQL 多 Worker 并发同步集成测试已在 Run #1479 的 GitHub Actions 临时 MySQL 中真实执行并通过；仍需补充并发批次失败/回滚故障注入测试。
- 当前 lifespan 对同步失败采取“记录明确错误后继续启动”的降级策略；因此部署监控必须能识别该错误，且 Scheduler Worker 启动后应检查数据库中的任务配置完整性。此处尚未实现独立任务同步协调者/健康状态端点。
- 该修复仅处理业务配置同步，不是 schema migration，也不应写入 migration ledger。
- 未连接生产服务器、数据库、Redis、队列或真实第三方接口；PR 仍保持 Open / Draft，不合并、不部署。

### MySQL 并发冲突补充

- InnoDB 在多个 Worker 对尚不存在的唯一键执行 `SELECT ... FOR UPDATE` 时，可能出现 gap/insert-intention 锁竞争；失败不一定表现为 1062 Duplicate entry，也可能是 1213 deadlock 或 1205 lock wait timeout。
- 同步重试分类现覆盖 MySQL 1062 / 1205 / 1213，以及 SQLite 的 locked 状态；每次重试前均先回滚整批事务。非冲突类完整性错误不重试。
- 新增 `tests/test_mysql_scheduled_task_sync.py`：仅在 GitHub Actions loopback 临时 MySQL `platform_ci` 且显式开启 destructive-test flag 时运行；为每次测试创建独立 utf8mb4 临时数据库，两个并发 Worker 同步 8 条合成任务，断言最终无重复且任务齐全，结束后销毁临时库。
- 该 MySQL 测试已在 Run #1479 通过；运行环境仅为 GitHub Actions loopback 临时 MySQL，测试创建并销毁独立 utf8mb4 临时数据库。若测试环境未满足安全条件，CI 应失败关闭而不是连接远程数据库。

### 隔离 CI 验收（Run #1479）

- 最新 PR HEAD `958cf3a9fde223be93bafc5973e66b60d340a1fe` 对应 Run #1479：Backend、Frontend 全部成功。
- Backend：**587 passed、1 skipped、1 warning**；新增 `test_mysql_two_workers_sync_same_task_config_without_duplicates` 在 GitHub Actions 临时 MySQL 中真实执行并通过，两个并发 Worker 同步 8 条合成任务后无重复记录且任务齐全。
- 四个新增单元测试全部通过：整批失败回滚、幂等同步及保留管理员停用状态/运行计数、冲突分类、重复 task_name 预检。
- Frontend：npm ci、依赖 advisory 报告、Lint、Build、Playwright Mock API Browser E2E 全部通过。
- Run #1479：https://github.com/Helong0511/Platform/actions/runs/43347458101
- 1 skipped 仍是本机核对脚本未提交（CI 不依赖）；1 warning 是 passlib/Python 3.11 `crypt` 弃用提示。不得将其描述为零 warning。
- MySQL 集成测试只连接本次 GitHub Actions loopback 临时 MySQL，并创建/销毁独立 utf8mb4 临时数据库；未连接生产数据库或外部服务。

### Schema drift 测试命名纠正

- 复核发现既有 MySQL 测试名称包含 `verifies_full_metadata`，但实际断言只覆盖 ORM 表和列存在性，并不比较列类型、NULL/default、主键、索引、CHECK、字符集或排序规则。
- 已将测试重命名为 `test_mysql_schema_bootstrap_creates_orm_tables_and_checks_table_column_presence`，并修正文档字符串，避免把有限检查误称为完整 metadata 验收。
- 真实 schema drift 检查范围仍需后续设计和兼容性测试；不在本轮贸然扩展到类型/索引/字符集比较，以免对既有生产 schema 产生未经验证的误报或错误阻断。

### 最新 HEAD / CI 状态更新（2026-11-13）

- 当前 PR HEAD：`3ca7e8d5d8a6f5131445bf596bafa1f13529c662`。
- 对应 Run #1482：https://github.com/Helong0511/Platform/actions/runs/43347718738，Backend / Frontend 均成功。
- Run #1482 是 schema drift 测试命名与文档修订后的验证；任务同步 MySQL 并发测试的实际执行证据仍以 Run #1479 为准（587 passed、1 skipped、1 warning）。
- PR #1 仍为 Open / Draft，未合并；mergeable 不代表上线验收完成。


## 2026-11-13 调度 Worker 任务配置同步失败关闭

### 复核发现

- 先前的任务同步修复将所有 Worker 的同步失败都按“记录错误后继续启动”处理。
- 该降级策略对纯 API Worker 可以接受，但对负责运行 APScheduler 的 Worker 不安全：同步失败后仍会继续初始化并启动调度器，可能按数据库中的旧任务配置运行，漏掉新增任务或未应用 Cron/函数路径变更。
- 独立 Scheduler systemd unit 设置 `GUNICORN_ROLE=scheduler`；`settings.should_run_scheduler()` 对该角色始终返回 true，因此可以在启动阶段明确区分必须依赖任务配置的 Worker。

### 本轮修复

- 将启动同步策略提取为 `_sync_scheduled_tasks_for_worker()`，便于独立验证。
- 任务配置同步成功：记录成功状态并继续启动。
- 任务配置同步失败且当前 Worker 将运行 APScheduler：抛出启动异常，拒绝启动调度器，避免以旧配置继续调度。
- 任务配置同步失败且当前 Worker 是纯 API（`should_run_scheduler() == false`）：保留降级启动策略，记录异常类型，不记录数据库原始异常文本。
- 新增 `tests/test_scheduled_task_sync_startup.py`，覆盖 Scheduler fail-closed、纯 API 降级和同步成功三条路径。

### 验收状态与边界

- 代码提交：`c277075`、`df41f91`、`119840a`（完整 SHA 以 GitHub commit 记录为准）。
- 本文档提交后仍须以最新 HEAD 的 GitHub Actions Backend / Frontend 完整 CI 结果作为验收证据；在 CI 完成前不宣称测试通过。
- 该修复没有实现任务同步单一协调者、健康状态端点、告警投递或自动恢复；API Worker 的降级状态仍需后续可观测性方案。
- 不改变生产数据库、不连接生产服务器/Redis/队列/第三方接口；仅在 CI 隔离环境验证。
- PR #1 继续 Open / Draft，不合并 main、不部署；凭据安全专项仍按用户要求暂缓。


## 2026-11-13 调度启动链路进一步失败关闭（最新验收）

### 新发现

- 在任务配置同步失败关闭修复之后，继续沿 lifespan 向下检查发现：即使 `init_scheduled_tasks_in_db()` 成功，原有 `init_scheduled_tasks()` 或 `start_scheduler()` 失败仍会被捕获，随后记录 warning 并让应用继续启动。
- 这会导致 Scheduler Worker 进程存活但 APScheduler 不可用，形成“进程健康、调度失效”的假健康状态。
- 原异常日志还会直接格式化异常对象；本轮改为记录异常类型，避免把驱动/任务异常详情写入通用启动日志。

### 修复

- 新增 `_start_scheduler_for_worker()`，将任务注册和调度器启动作为一个必须成功的启动步骤。
- 任一阶段失败均抛出启动异常，Scheduler Worker 不再继续就绪。
- 仅当任务注册完成后才调用 `start_scheduler()`。
- 新增测试覆盖：
  - 调度配置同步失败时，Scheduler Worker 拒绝启动；
  - 同步失败时，纯 API Worker 保留降级策略；
  - 调度任务注册失败时，不会继续调用启动；
  - 任务注册成功后才启动 APScheduler；
  - 成功日志调用及异常日志脱敏。

### CI 验收

- 修复测试断言方式后的完整最新 SHA：`9ab3f75524e618a09c7740a912cf14b280fcdc2d`。
- Run #1490：https://github.com/Helong0511/Platform/actions/runs/43349369544。
- Backend：592 passed、1 skipped、1 warning。
- Frontend：npm ci、依赖风险报告、Lint、Build、Playwright Mock API E2E 全部成功。
- 前一轮 Run #1488 的唯一失败是成功日志断言使用 caplog 时没有启用 INFO 捕获；已改为直接 mock logger 并验证调用，后续最新 CI 通过。
- Run #1490 对应 SHA 与当时 PR HEAD 一致；后续文档更新会产生新 SHA，必须再以新 SHA 的 CI 验收。

### 未解决边界

- Scheduler fail-closed 仅解决启动阶段配置同步/任务注册/调度器启动失败后错误就绪的问题。
- 尚无独立 scheduler heartbeat、任务最后成功时间/延迟指标、连续失败告警、单一任务同步协调者或自动恢复流程。
- 纯 API Worker 仍允许在任务配置同步失败时降级启动；目前只有日志，管理端缺少可查询的同步状态。后续应设计持久化同步状态和告警，而不是让 API Worker 因非核心调度配置短暂故障全部拒绝服务。
- 数据库 schema bootstrap 仍由每个 API/Scheduler Worker 启动触发，尚未拆分为 provisioning、独立 migration job 与只读 schema gate。
- 不连接生产环境，不部署，不合并 PR；凭据安全专项继续暂缓。


## 2026-11-13 数据库权限边界与最新 CI 复核（Run #1492）

### 最新分支状态

- PR #1 HEAD：`9a9b5030641e48c5278292de2333011923a17110`；PR 仍为 Open / Draft，未合并。
- HEAD 对应 Run #1492：https://github.com/Helong0511/Platform/actions/runs/43349636448；Backend 与 Frontend jobs 均为 success。
- Run #1492 仅证明该 HEAD 的 CI workflow jobs 成功，不代表数据库职责拆分、迁移 Runner、备份恢复或上线演练已完成。

### 本轮重新确认的权限边界

1. `app/core/config.py` 当前仅定义应用主数据库配置 `SQLALCHEMY_DATABASE_URI`（环境变量别名 `DATABASE_URL`）；没有独立 migration DSN、provisioning DSN 或运行账号/迁移账号角色配置。
2. `app/db/database.py::create_database()` 使用同一个 `settings.SQLALCHEMY_DATABASE_URI` 派生不指定 schema 的 server URL，并执行 `CREATE DATABASE IF NOT EXISTS`。这意味着启动应用的数据库身份必须具备建库权限（或该步骤在部署中被人为绕开；当前 systemd unit 未配置绕过开关）。
3. `app/bootstrap/lifespan.py::lifespan()` 在每个 Worker 启动时调用 `create_database()`，随后调用 `_bootstrap_database_schema()`。后者通过应用主 engine 执行 `Base.metadata.create_all()`，因此同一应用数据库身份还需要相应 schema DDL 权限。
4. Backend 与 Scheduler 的 systemd unit 均加载同一 `/data/Platform/.env`，并使用同一 `app.main:app` 入口；它们仅覆盖 `GUNICORN_ROLE`、调度相关环境变量，没有为迁移或 schema provisioning 指定独立数据库身份。
5. Gunicorn 每个 Worker 都运行 FastAPI lifespan，因此上述启动期建库/建表检查不是每个 systemd 服务仅执行一次。MySQL advisory lock 只保护 `_bootstrap_database_schema()` 内的 `create_all()` 临界区；`create_database()` 在锁外执行，且该锁不提供数据库权限隔离。
6. CI workflow 中的 `DATABASE_URL` 使用内存 SQLite；MySQL 集成测试通过独立的 `MYSQL_INTEGRATION_*` 测试参数连接 GitHub Actions loopback 临时 MySQL。测试身份/辅助执行器不构成应用运行时 migration 身份，也不能据此认定生产账号已经最小权限化。
7. `app/core/database.py::create_tables()` 仍是另一个可调用的 `Base.metadata.create_all()` 包装函数。本轮尚未获得可靠的全仓库代码搜索结果，不能断言其没有其它调用者；必须在完整工作区执行 `git grep` 并检查动态导入、CLI、脚本、测试夹具和部署入口后，才可关闭调用点审计。

### 当前风险与处理顺序

- 当前运行身份同时承担运行期 DML、建库和 schema DDL 权限，违反应用运行账号最小权限的目标；但不能在 Runner / provisioning 替代路径完成前直接撤权，否则会破坏现有启动和空库安装流程。
- 下一步应先新增显式 provisioning 命令和独立 migration Runner/ledger，并在隔离 MySQL 验证空库初始化、旧库升级、并发锁、checksum drift、DDL 中断恢复和备份恢复。
- 随后增加 Worker 启动时只读 schema revision/drift gate，并在 systemd 部署流程中明确执行 migration job 后再启动 API/Scheduler。
- 最后将运行身份限制为业务所需 DML 权限，迁移身份才拥有 CREATE/ALTER/DROP 等 schema 权限；必须在隔离环境用运行身份无 DDL 权限的测试证明应用可正常启动。
- 不得仅通过新增环境变量开关跳过建库/建表而宣称完成职责拆分；空库安装、旧库升级、失败恢复和权限边界都必须形成可执行、可验证的发布流程。

### 本轮审计边界

- GitHub Tree 返回完整文件树（未截断），当前分支 Python 文件数为 537；但 GitHub code search 对 `create_database` / `create_tables` 返回空且标记 incomplete，不能视为完整搜索。
- 已读取当前分支的 `app/db/database.py`、`app/core/database.py`、`app/bootstrap/lifespan.py`、`app/core/config.py`、两个 systemd unit、`.github/workflows/ci.yml` 及相关测试。
- 未连接生产服务器、数据库、Redis、队列或真实第三方接口；本轮仅读取 GitHub 文件与 CI 元数据。
- PR #1 继续 Open / Draft；不合并 main、不部署；凭据安全专项继续暂缓。


## 2026-11-13 数据库入口与运行身份二次核查（Run #1493）

### 最新 CI 验收证据

- 当前 HEAD：`acbf915eaaff5c5a78babd71138b8360072ae6f7`。
- Run #1493：https://github.com/Helong0511/Platform/actions/runs/43350109994。
- Backend：**592 passed、1 skipped、1 warning**。
- Frontend：Job 成功，Mock API Playwright E2E 通过（登录校验、认证成功/失败、管理端导航、Outbox 重试详情、退出登录、移动端菜单、客户端 RBAC）。
- 本次 MySQL 临时服务实际执行并通过了 `tests/test_mysql_migrations.py` 中迁移结构、索引冲突拒绝、事件键回填、DDL 边界中断/恢复等用例；`test_mysql_two_workers_sync_same_task_config_without_duplicates` 也通过。
- MySQL 迁移测试使用 GitHub Actions loopback 临时 MySQL，测试辅助连接账号为 CI 注入的 root；因此这些用例不构成“应用运行账号无 DDL 权限仍可启动”的证据。
- 1 skipped：本地核对脚本未纳入 CI；1 warning：passlib/Python 3.11 `crypt` 弃用警告。CI 不能描述为零跳过或零警告。

### 本轮实际代码复核

重新读取当前分支以下文件及相关区段：

- `app/db/database.py`
- `app/core/database.py`
- `app/bootstrap/lifespan.py`
- `app/main.py`
- `app/core/telegram/sync_db.py`
- `tests/test_database_init.py`
- `tests/test_schema_metadata_drift.py`
- `tests/test_database_bootstrap_url.py`
- `systemd/Platform-backend.service`
- `systemd/Platform-scheduler.service`

直接确认：

1. `app/db/database.py::create_database()` 从应用主 `settings.SQLALCHEMY_DATABASE_URI` 派生无默认 schema 的 server URL，并执行 `CREATE DATABASE IF NOT EXISTS`；当前没有单独 provisioning DSN。
2. `app/bootstrap/lifespan.py::lifespan()` 在每个 Worker 启动时显式导入并调用 `create_database()`，之后调用 `_bootstrap_database_schema()`；失败即拒绝启动。
3. `_bootstrap_database_schema()` 使用主 `engine` 执行 `Base.metadata.create_all()`。因此应用运行身份仍需 schema DDL 权限；advisory lock 不会改变 SQL 权限需求。
4. `app/core/database.py::create_tables()` 是第二个 `Base.metadata.create_all()` 包装函数。本轮在该函数定义及其直接文件中确认存在，但全仓库调用点尚未穷尽；不能断言无调用者。
5. `app/core/database.py::init_db()` 每个 Worker 启动时都会查询管理员；不存在时尝试创建默认管理员。当前 `tests/test_database_init.py` 通过 mock session 测试唯一键竞争后的回查及非重复完整性错误传播，不是 MySQL 多 Worker 实际并发集成测试。
6. `app/core/telegram/sync_db.py::get_sync_session_factory()` 也从同一个 `settings.SQLALCHEMY_DATABASE_URI` 构建同步 SQLAlchemy Engine，供 Telegram 独立线程使用；当前没有运行期只读身份或专用身份切换。
7. 两个 systemd unit 都读取同一个 `/data/Platform/.env`，均以 `app.main:app` 启动；没有独立 migration/provisioning service 或执行步骤。
8. `_schema_metadata_drift()` 目前只比对 ORM 所需表和列名。既有测试仅验证缺表/缺列及完整存在两种情况，不能覆盖类型、长度、NULL/default、PK/唯一约束、普通索引、外键、CHECK、charset/collation。
9. `tests/test_mysql_migrations.py` 的危险操作保护要求 GitHub Actions、UNIT_TEST、显式 destructive flag、loopback host 和固定 `platform_ci` 数据库；这项保护有价值，但它隔离的是测试执行目标，不是生产应用账号权限。

### 全仓库调用点审计状态（未关闭）

- 当前 Tree 未截断，仓库 Python 文件数为 537。
- 本轮逐文件复核了上述核心入口、部署文件和数据库测试；尝试通过 GitHub Code Search 查找 `create_database`、`create_tables`、`init_db`、`Base.metadata.create_all` 和 `_bootstrap_database_schema`，返回结果为空且该搜索接口对目标分支未提供可验证的完整性保证。
- 曾尝试通过单次批量读取全部 Python 文件进行调用点扫描，但 GitHub 工具调用次数限制阻止了该批量操作；因此不能把这次失败的批量尝试当作扫描结果。
- 目前已知直接调用点：lifespan 调用 `create_database()`、`_bootstrap_database_schema()`、`init_db()`；`create_tables()` 仅确认定义；`Base.metadata.create_all()` 在 lifespan bootstrap 与 `create_tables()` 中确认。
- 仍需在可执行的完整仓库工作区运行 `git grep -nE 'create_database|create_tables|create_all|init_db|_bootstrap_database_schema|init_scheduled_tasks_in_db' -- '*.py'`，再检查动态导入、脚本、测试夹具和部署入口。未取得该结果前，不关闭全仓库调用点审计。

### 下一步实施门槛

- 不直接在当前启动流程中撤销 DDL 权限。
- 先实现独立 provisioning 和 Migration Runner / ledger；迁移任务与应用运行身份使用独立 DSN/数据库账号。
- 对已完成迁移的临时 MySQL schema，以专用低权限用户验证：只读 schema gate 成功、业务所需 DML 成功、CREATE DATABASE / CREATE TABLE / ALTER / DROP 明确失败。
- 对空库路径另用 provisioning/migration 身份执行初始化；验证失败中断、重复运行、checksum drift、并发锁和人工恢复。
- 在上述测试通过前，systemd 不得改为低权限账号，也不得删除现有自动 bootstrap 代码。
- PR #1 保持 Open / Draft，不合并、不部署；不连接生产服务器、数据库、Redis、队列或真实第三方接口；凭据安全专项继续暂缓。


## 2026-11-13 运行账号 DML-only 与真实 MySQL 并发管理员初始化验收（Run #1498 / #1499）

### 最新 CI 证据

- Run #1498 对应 HEAD：`9f3ab8bb687ea8bc2a47d0296c36a2b5775db72c`，CI 全部成功。
  - Backend：**593 passed、1 skipped、1 warning**。
  - Frontend：依赖安装、advisory 报告、Lint、Build、Playwright Mock API Browser E2E 全部成功。
  - 详情：https://github.com/Helong0511/Platform/actions/runs/43351458980
- Run #1499 对应 HEAD：`80d8375339b3e3c8dead4f852ba7972a2a3694c4`，CI 全部成功。
  - Backend：**593 passed、1 skipped、1 warning**。
  - Frontend：Lint、Build、Playwright Mock API Browser E2E 全部成功。
  - 新增真实 MySQL 权限/并发测试节点 `tests/test_mysql_runtime_privileges.py::test_mysql_runtime_account_can_bootstrap_admin_but_cannot_run_ddl` 明确为 PASSED。
  - 详情：https://github.com/Helong0511/Platform/actions/runs/43351749183
- 1 skipped 仍是本地核对脚本未纳入 CI；1 warning 仍是 passlib/Python 3.11 `crypt` 弃用提示。不能描述为零 skip / 零 warning。
- Run #1497 的一次失败已保留：当时测试错误地使用 DML-only 用户创建测试表，MySQL 按预期返回 1142。修正为测试管理员预置表结构后，Run #1498 通过。该失败是测试准备身份错误，不是放宽权限后绕过失败。

### 新增真实 MySQL 验证内容

新增 `tests/test_mysql_runtime_privileges.py`，仅在 GitHub Actions loopback 临时 MySQL 中运行，并使用独立测试 schema `platform_ci_runtime_privileges` 与临时测试用户：

1. 安全门禁要求 `UNIT_TEST=1`、`GITHUB_ACTIONS=true`、显式 destructive-test flag、loopback host 和固定 CI 数据库名；其它环境拒绝执行破坏性操作。
2. 由隔离测试管理员创建专用 schema、临时用户并授予仅 `SELECT/INSERT/UPDATE/DELETE` 权限。
3. 测试管理员预置 ORM 的 `users` 表；运行账号没有 CREATE/ALTER/DROP 权限。
4. 通过真实 MySQL + SQLAlchemy AsyncSession 执行 `app.core.database.init_db()`。
5. 用两个独立 AsyncSession 和两方屏障，强制两个初始化 Worker 都先查询到“没有管理员”，再并发插入；验证唯一键竞争的一方回滚后能重新查询到胜出 Worker 创建的管理员。
6. 再次执行初始化，确认幂等；查询数据库确认管理员记录只有一条。
7. 使用同一运行账号执行 `CREATE TABLE`，断言 MySQL 错误码 1142，确认 DDL 被拒绝。
8. finally 清理临时数据库、临时用户并释放 Engine/连接。

### 结果能证明什么、不能证明什么

**已证明：**
- `init_db()` 的管理员检查、创建、唯一键竞争回查及重复初始化，在真实 MySQL、独立连接、DML-only 用户下可以成功。
- MySQL 唯一键竞争路径在强制同时读到“无管理员”的真实并发场景下通过。
- 运行账号执行 CREATE TABLE 被数据库拒绝；测试没有通过授予 DDL 权限来绕过错误。

**尚未证明 / 仍是阻断项：**
- 当前 FastAPI lifespan 仍会执行 `create_database()` 和 `Base.metadata.create_all()`；本测试刻意由测试管理员预置表结构，不能证明低权限账号可以启动完整应用。
- 尚无独立 provisioning DSN、正式 Migration Runner / ledger、只读 schema revision gate。
- 尚未覆盖 Telegram 同步 Engine 在专用运行身份下的连接配置；目前仍使用主 `SQLALCHEMY_DATABASE_URI`。
- 尚未验证所有业务表/索引/约束均由迁移身份正确创建，也未完成旧 schema 升级、备份恢复、DDL 中断恢复、checksum drift 和应用兼容回滚。
- 尚未完成全仓库 `create_database/create_tables/create_all/init_db` 调用点清单；537 个 Python 文件的完整调用点审计仍待可执行工作区 `git grep` 与动态入口核查。

### 下一步

- 不因这两次 CI 通过就更改 systemd 数据库账号或撤销现有 DDL 权限。
- 继续完成 Migration Runner / provisioning / read-only schema gate 的实现设计与隔离测试；再验证完整 lifespan 和 Telegram 同步连接都使用 DML-only 身份。
- 继续全仓库调用点清单、schema drift 完整度、迁移恢复与备份演练。
- PR #1 继续 Open / Draft，不合并 main、不部署；生产服务器、生产数据库、Redis、队列及真实第三方接口均未连接；凭据安全专项继续暂缓。


## 2026-11-13 最新 HEAD / Run #1500 与复核补充

### 最新 CI 证据

- 当前 PR HEAD：`0e8ac683a793e095405be12ba6cbb1be4ba0cc24`。
- Run #1500：https://github.com/Helong0511/Platform/actions/runs/43352023944；该 SHA 的 Backend / Frontend jobs 均为 success。
- Backend：**593 passed、1 skipped、1 warning**；Python compile 成功。
- Frontend：`npm ci`、依赖 advisory 报告、Lint、Build、Playwright Mock API Browser E2E 全部成功。
- Skip 是本地核对脚本未纳入 CI；warning 是 passlib 在 Python 3.11 使用 `crypt` 的弃用提示。
- 本次仅使用 GitHub Actions 隔离 MySQL 8.0 / Redis 7.4、合成数据与 Mock API；未连接生产服务或真实第三方接口。

### 对当前实际代码的再次确认

本轮在当前分支重新读取了 `app/db/database.py`、`app/core/database.py`、`app/bootstrap/lifespan.py`、`app/core/telegram/sync_db.py`、迁移 CLI / manifest / planner / parser、两个 systemd unit，以及真实 MySQL 运行账号测试：

1. `lifespan()` 的当前启动路径仍为 `create_database()` → `_bootstrap_database_schema()` → `init_db()`。前两步仍由应用主数据库连接执行建库 / ORM DDL。
2. `create_tables()` 仍保留为第二个 `Base.metadata.create_all()` 包装入口；没有完整分支级全仓库搜索结果，不能断言它没有调用者。
3. Telegram 同步 Engine 仍由 `get_sync_session_factory()` 从主 `SQLALCHEMY_DATABASE_URI` 派生同步 DSN；尚未切换到独立运行身份。
4. `python -m app.db.migrations validate` 仍是纯离线校验命令。正式 Runner、Ledger、独立 migration DSN、恢复 CLI 和只读 schema gate 均未实现。
5. `_schema_metadata_drift()` 仍只核对缺表 / 缺列，不检查类型、长度、NULL/default、约束、索引和字符集/collation。
6. `20261110_third_party_report_event_idempotency.sql` 的 `UPDATE ... WHERE event_key IS NULL` 仍为单条无批次全表回填。不得在没有代表性规模锁等待、redo/undo、执行时长和复制延迟测试前，将其视为可安全用于大表的迁移。
7. 两个 systemd unit 仍加载同一应用环境文件并启动同一个 FastAPI lifespan；没有独立 provisioning / migration service。

### 当前可证明的权限边界

`tests/test_mysql_runtime_privileges.py` 证明的是：管理员预置 `users` 表后，DML-only 账号可在真实隔离 MySQL 中完成 `init_db()`，两个独立 Session 并发初始化可收敛为一条管理员记录，且该账号执行 CREATE TABLE 被 MySQL 拒绝。

它**不证明**完整 FastAPI lifespan 可用 DML-only 账号启动，也不证明 Telegram 同步 Engine、全部业务写路径或迁移发布流程已完成权限隔离。不得据此修改 systemd 账号或撤销当前 DDL 权限。

### 全仓库调用点审计状态

仍未关闭。GitHub Tree 可以列出文件，但当前连接未提供可验证完整的分支级代码搜索；先前批量读取全部 Python 文件也未成功。只有在完整工作区执行并保存 `git grep` 结果，再检查动态导入、脚本、测试夹具和部署入口后，才能关闭调用点清单。

### 后续实施门槛（保持不变）

- 先完成调用点清单；再实现独立 provisioning、Migration Runner / Ledger、恢复命令和只读 schema gate。
- 对无 DDL 权限的应用账号验证完整 lifespan、Telegram 同步 Engine 和业务 DML；空库初始化则由独立 provisioning / migration 身份执行。
- 对 event_key 回填建立可恢复、限速、按主键分批方案，并在隔离 MySQL 代表性数据量上进行性能与锁影响测试。
- 在上述流程和完整隔离备份恢复 / 兼容回滚验收通过前，不改 systemd 数据库身份、不删除现有自动 bootstrap、不合并、不部署。
- PR #1 继续 Open / Draft；凭据安全专项按用户要求暂缓。


## 2026-11-13 新发现：第三方事件幂等键回填与运行时算法不一致（阻断项）

### 代码证据

本轮交叉核对以下当前分支文件：

- `sql/migrations/20261110_third_party_report_event_idempotency.sql`
- `app/core/third_party_report.py::build_event_idempotency_key()`
- `app/services/third_party_report_outbox.py::enqueue_postback_report()`
- `app/models/third_party.py::ThirdPartyReportLog`
- `tests/test_third_party_report_outbox.py`
- `tests/test_third_party_report_idempotency.py`

确认：

1. SQL 历史回填只使用四个字段：`source, adsid, event, conversion_id`（ViewContent 的 conversion_id 被置空）。
2. `build_event_idempotency_key()` 在传入非空 `platform` 时，会把 `platform.strip()` 作为第五个长度前缀字段纳入 SHA-256。
3. `enqueue_postback_report()` 明确以 `source="postback"` 和调用方传入的 `platform` 构造事件键。
4. `ThirdPartyReportLog` 当前没有独立的 `platform` 列；Outbox 新行写入 event_key，但没有把 platform 持久化为可供历史迁移重建的字段。
5. 现有单元测试验证了 Outbox 新行的 key 包含 platform，却没有覆盖“历史 SQL 回填 key 与运行时 platform-scoped key 必须一致”的跨迁移契约。

### 影响

历史行经 SQL 回填得到四字段 key；同一逻辑事件在新 Outbox 入口中按五字段 key 查询。两者不相等。对升级前已存在的 postback 事件，后续同平台重放可能无法命中旧日志，从而插入第二条日志，破坏跨版本幂等；而简单移除 platform 又可能把不同平台的事件错误合并。

由于历史表没有可靠持久化 platform，不能安全猜测旧行属于哪个平台。此问题不能靠改测试期望或直接删掉 platform 维度来处理。

### 修复前置条件与建议方案

- 将此项列为迁移/事件幂等 P1 阻断，不得在没有解决方案前发布该 migration 到已有数据表。
- 先盘点旧版 postback 日志的真实来源与可用关联证据（例如历史配置引用、短链接、斗篷、历史 payload）；只接受可确定的一对一映射，不用模糊推断。
- 设计显式的历史平台归属映射/人工核对流程；对无法确定平台的历史行，制定隔离状态与重复发送风险的业务决策，并要求发布审批。
- 在 schema 中持久化平台身份，并统一应用运行时、SQL/Runner 回填算法的版本化契约；不要再让 migration 与应用分别手写不一致的身份算法。
- 增加跨层契约测试：四字段 legacy key、五字段 platform key、ViewContent conversion_id 补写、Unicode/空字符串/空白平台、同一事件跨平台隔离，以及旧日志升级路径；必须在真实隔离 MySQL 验证。
- 新增修复 migration，不得修改已登记的 `20261110_third_party_report_event_idempotency.sql` 历史文件或其 manifest checksum。
- 在完成历史数据分类、回填策略、唯一键冲突演练和回滚/前向修复预案前，不得合并或上线。



## 2026-11-13 幂等键问题的调用链精确化（补充，避免过度概括）

进一步读取 `app/core/postback/processor.py` 后，需将上一节风险描述精确限定：

- `PostbackProcessor.process(platform, ...)` 将请求平台原样传递至 `_enqueue_third_party_report_if_needed()`。
- 该方法调用 `enqueue_postback_report(platform=platform, ...)`；Outbox 生成 key 时传入 platform，故新 Outbox 事件使用五字段身份。
- `app/core/third_party_report.py::create_report_log()` 和无既有 report_log_id 的直接发送路径生成 key 时没有传 platform，使用四字段身份。
- SQL migration 的四字段回填与通用 builder 的默认（platform=None）行为相符；它不是对默认算法的错误实现。真正的不一致是：Outbox 的平台作用域算法与历史四字段日志没有显式的兼容/映射策略。
- 因而不能声称“所有历史记录必然产生重复”。可以确认的是：如果历史 postback 日志由四字段直接发送路径创建，而升级后的同一逻辑事件进入五字段 Outbox 查询，则两者 key 不相等，Outbox 的 `SELECT ... WHERE event_key = platform_scoped_key` 无法复用四字段旧日志。是否实际存在此类记录、规模多少，需要离线数据画像和历史调用版本证据确认。

### 必须补充的审计与验收

1. 查明旧版 postback 是否曾通过 `create_report_log(source="postback", ...)` / 直接发送路径创建日志，以及部署版本切换时间。
2. 在脱敏副本或合成数据上分别构造 legacy 四字段行、platform-scoped 五字段行，证明当前 Outbox 查询的命中/不命中行为；禁止读取生产数据库来画像。
3. 对无法确定平台的 legacy 行，不允许按当前请求平台强行归属，也不允许把 platform 维度整体删除。应明确历史事件的复用策略（例如 legacy-key fallback 需有歧义检测、冲突保护和审计记录），并先证明不会跨平台误合并。
4. 将算法定义集中到单一版本化规范；应用代码与迁移脚本可分别实现，但必须通过同一组跨语言 golden vectors（ASCII、中文、emoji、空字符串、前后空格、ViewContent 补写 conversion_id、平台大小写）验证字节级一致。
5. 对 `platform` 当前只做 `strip()`、不统一大小写的行为作明确业务决策；不能在迁移时擅自 lower/casefold，否则可能改变既有平台标识语义。
6. 增加升级前后兼容测试，覆盖唯一键冲突、并发 Postback、重复请求、旧行已发送/未发送/正在租约中，以及 legacy fallback 发现多个候选时 fail-closed。

在完成以上画像与兼容策略前，此项仍是迁移发布阻断，但风险结论应表述为“存在可证明的 key 不兼容路径，实际历史影响待离线确认”，而非“所有旧记录都会重复”。


## 2026-11-13 幂等键算法边界修复与 MySQL Golden Vector 测试

### 本轮代码改动

- `app/core/third_party_report.py::build_event_idempotency_key()` 现在先执行 `normalized_platform = (platform or "").strip()`，只有规范化后非空才增加第五个平台字段。
- 修复前：`platform="   "` 是 truthy 值，`.strip()` 后变成空字符串，却仍被追加为第五个长度前缀字段（`0:`）；这会使纯空白平台与真正未提供平台产生不同 event_key。
- 修复后：`None`、`""`、纯空白平台统一按未提供平台处理；正常平台仍保留 trim 后的平台作用域，且不擅自 lower/casefold。
- 新增单元测试覆盖 None、空字符串、纯空白和带首尾空格的平台名。
- 新增隔离 MySQL 集成 Golden Vector：使用 utf8mb4 临时 schema，对 MySQL `CHAR_LENGTH + CONCAT + SHA2` 与 Python UTF-8 长度前缀算法逐项比对；覆盖 ASCII、中文、emoji、字段内冒号、ViewContent 后补 conversion_id、空 conversion_id、平台为空/空白/首尾空格。
- 该测试仅在 GitHub Actions loopback 临时 MySQL `platform_ci` 安全门禁下运行，测试 schema 由 UUID 隔离，finally 清理；不连接生产数据库。

### 证明范围与限制

- 该改动消除纯空白平台产生“空第五字段”的边界不一致。
- Golden Vector 可验证当前 utf8mb4 CI MySQL 上 Python 与 SQL 字符长度/哈希输入字节的一致性。
- 这**没有**解决历史 legacy 四字段 key 与有效平台五字段 Outbox key 的兼容问题；旧行的平台归属仍不可从当前模型可靠恢复。
- 这也**没有**证明历史迁移脚本在所有历史 schema charset/collation 下都与 utf8mb4 测试等价；发布前仍需核实真实目标表字符集，并在隔离副本做迁移级演练。
- 仍需补充对历史来源/部署版本的证据盘点、legacy fallback 歧义检测、真实 MySQL 端到端 enqueue 命中/冲突测试，以及迁移批次回填设计。
- 不修改已登记的 `20261110_third_party_report_event_idempotency.sql`，不改变 manifest checksum。

### 当前状态

本次代码提交会触发新的 CI；在新 HEAD 的 Backend / Frontend 全部成功前，不将改动视为已验收。PR #1 保持 Open / Draft，不合并、不部署；只使用隔离 CI 服务和合成数据。


## 2026-11-13 Run #1508 验收与大表幂等键回填实施设计

### Run #1508 最新证据

- 验证 HEAD：`101e31b2251ba1b637ab4543ae477b461dac1971`。
- Run #1508：https://github.com/Helong0511/Platform/actions/runs/43354050248。
- Backend：**602 passed、1 skipped、1 warning**；其中真实隔离 MySQL 测试覆盖了本轮 Python / MySQL event identity golden vectors。
- Frontend：依赖安装、advisory、Lint、Build、Mock API Browser E2E 全部成功。
- 1 skipped：本地核对脚本未纳入 CI；1 warning：passlib 在 Python 3.11 使用 `crypt` 的弃用警告。
- CI 服务为 GitHub Actions 隔离 MySQL 8.0 / Redis 7.4；未连接生产服务或真实第三方 API。

### 为什么不能把全表 UPDATE 改成简单的 LIMIT 就结束

当前历史 migration 的数据回填为单条：

`UPDATE third_party_report_logs SET event_key = ... WHERE event_key IS NULL`

仅添加 `ORDER BY id LIMIT N` 只能把一次更新限制为一批，不能自动循环、保存进度或证明所有行都处理完。若在 SQL 文件中手工重复固定批次，也无法安全覆盖任意规模和中途故障恢复。因此需要将 schema DDL 与可恢复数据回填明确拆分。

### 推荐实施：Migration Runner 管理的可恢复 Keyset Backfill

此处为后续新 migration / Runner 的设计要求，不是已实现功能：

1. **历史 SQL 保持不可变**：不得编辑已登记的 `20261110_third_party_report_event_idempotency.sql`，不得修改其 manifest SHA-256。
2. **新增 schema revision**：只负责确认所需列、进度表、索引/约束前置条件；DDL 每一步必须具备信息架构检查和可诊断失败行为。
3. **数据回填声明版本化**：在 manifest 中登记专用 backfill operation 的代码路径、SHA-256、revision 依赖、目标表、主键、目标列、算法版本、batch_size 上限和限速参数。Runner 不允许从数据库内容拼接任意 SQL 标识符；表名、列名和表达式必须来自经过校验的静态声明。
4. **稳定 Keyset 游标**：按主键递增读取待处理范围，记录 `last_processed_id`，避免 OFFSET 随数据增长退化；每批只处理 `event_key IS NULL AND id > last_processed_id` 的有限行，并在同一批内确认更新数量。
5. **批次提交与进度原子性**：每批更新和进度游标在同一事务提交。进程崩溃时，要么本批数据和游标都提交，要么都回滚；恢复后从已提交游标继续。若数据回填需要跨多次 commit，不能把整个回填伪装成一个可回滚事务。
6. **并发防护**：Runner 使用全局 migration session lock；同一 backfill revision 不能被两个 Runner 同时执行。业务写入在回填窗口内若可能插入 NULL event_key，必须先通过双写/写入门禁消除竞态，或在收尾阶段重复扫描 NULL 并做最终一致性检查。
7. **节流和观测**：配置单批行数、批次间隔、最大执行时长、锁等待上限；记录每批起止主键、读取/更新数量、耗时、重试次数和错误类型。日志不得包含 PII、SQL 参数或凭据。
8. **完成条件**：不能只依据游标到达当前 MAX(id)。必须执行 `COUNT(*) WHERE event_key IS NULL`、重复 key 分组检查，并验证本 revision 的回填范围和算法版本。最终 NULL=0、重复=0 后，才允许单独执行 NOT NULL / UNIQUE 收敛 DDL。
9. **唯一键冲突处置**：若批次发现两个不同旧行映射到同一 key，停止该 revision 并保留旧唯一索引；写入脱敏冲突报告，要求人工决定。禁止自动删除、合并或覆盖日志。
10. **失败恢复**：记录 failed 状态和脱敏错误摘要；自动恢复只允许从已提交游标继续执行幂等批次。若目标行在进度游标之后被并发改写，最终 NULL 扫描必须发现并回补；无法证明时 fail-closed。
11. **性能验收**：在临时 MySQL 使用接近目标规模的合成行数，记录每批吞吐、锁等待 P95/P99、事务时长、redo/undo 增长、磁盘使用、buffer pool 命中、复制延迟（如 CI 环境无法模拟复制则明确标记未覆盖）。需至少演练中断、重启续跑、重复执行、并发 Runner 拒绝、冲突停止和最终约束创建。
12. **发布顺序**：先部署兼容写入逻辑（新写入直接生成正确 event_key），再运行可恢复历史回填；完成冲突审查和 NULL/重复校验后再建立 NOT NULL / UNIQUE；最后才允许移除旧约束。实际部署需备份与发布审批。

### 当前实现状态

- 当前 manifest 只有 SQL migration entries，尚未登记 Python backfill operation。
- 当前 planner/parser/离线 CLI 不具备执行批次、记录游标、限速或恢复的能力。
- 当前没有 backfill progress ledger，也没有 Runner。
- 因此上面的分批方案只是明确的实施规范，不能作为已经修复全表 UPDATE 风险的证据。
- 历史四字段与平台五字段身份兼容问题独立存在；即使分批回填成功，也不能自动推断旧日志平台归属。
- 在批次 Runner、历史身份歧义策略、隔离规模演练完成前，迁移仍阻断上线。


## 2026-11-13 事件平台身份兼容：代码级调用链复核与安全决策

### 本轮复核的代码事实

- `PostbackProcessor.process(platform, ...)` 将平台传入 `_enqueue_third_party_report_if_needed(platform=...)`。
- `enqueue_postback_report()` 用 `build_event_idempotency_key("postback", adsid, event, conversion_id, platform=platform)` 生成平台作用域 key，并按该 key 查询已有日志。
- 新建 Outbox 行保存 `source/adsid/event/conversion_id/event_key` 和配置引用，但 `ThirdPartyReportLog` 当前没有独立 platform 字段。
- `create_report_log()` 当前签名没有 platform 参数，始终按四字段构建 key；`send_third_party_report()` 的直接发送路径在无 report_log_id 时调用该函数，也按四字段生成 event_key。
- `send_third_party_report()` 的事件 payload 使用传入 event_key；Outbox 调用传递五字段生成的 event_key，直接发送路径默认使用四字段 key。
- 现有历史 migration 只按四字段回填 event_key。它没有平台来源列，也没有可靠来源可恢复历史平台归属。
- 

## 2026-11-13 第三方事件身份调用入口与管理端编辑复核（Run #1510）

### 本轮核验基线

- PR 分支：`fix/non-credential-hardening-2026-11`
- 核验 HEAD：`ebe8ba5846d00d878d91388a3d1ec2c97476dc35`
- Run #1510：`43354830219`，Backend / Frontend 两个 Job 均成功。
- PR #1 经 API 复核仍为 Open / Draft，`merged=false`。
- 本轮只读取分支文件和 CI 日志；没有连接生产资源，没有执行迁移或发送真实第三方请求。

### 已直接读取并核对的代码

- `app/models/third_party.py`：`ThirdPartyReportLog` 当前没有 `platform` 或 legacy identity 状态字段；`event_key` 是唯一键。
- `app/core/third_party_report.py`：`create_report_log()` 按四字段构建 key；`send_third_party_report()` 在无 `report_log_id` 时调用它；Outbox 路径可传入已有 `report_log_id` 与五字段 `event_key`。
- `app/services/third_party_report_outbox.py`：Postback Outbox 按 `platform` 生成五字段 key，但当前行没有独立持久化平台字段；Worker 发送时将已持久化的 event_key 传回发送函数。
- `app/core/postback/processor.py`：Postback Processor 将平台传入 Outbox。
- `app/routes/short_link/cloak_report_service.py`：斗篷/短链的 `schedule_cloak_facebook_report()` 通过 FastAPI `BackgroundTasks` 直接调用 `send_third_party_report()`，不是 Postback Outbox 路径，也没有 Postback platform 参数。
- `app/api_v1/system/third_party_reports.py`：管理员可以查询列表/详情、修改普通日志参数、对符合条件的失败 Outbox 执行重排队。
- `app/schemas/third_party_report.py`：当前响应 Schema 没有平台字段。
- `app/scheduler_module/tasks/third_party_report_tasks.py`：定时任务消费持久化 Outbox。
- `app/db/migrations/manifest.py`：当前 manifest 显式登记 5 条 SQL migration；新增 migration 必须使用新 revision 并登记 checksum。

### 新确认的身份一致性风险

1. 直接短链/斗篷路径调用 `send_third_party_report()` 时不提供 platform，按无平台四字段身份工作。这是独立业务来源，不能擅自从 dp、short_code 或请求参数推断 Postback 平台。
2. Postback Outbox 新记录使用平台作用域五字段 key；模型却不保存 platform。该平台身份目前只体现在 event_key 计算结果中，缺少可审计的独立身份列。
3. 管理端 `update_report_log_params()` 对非 Outbox 日志允许修改 adsid/event/conversion_id，并重新按四字段算法计算 event_key。Outbox 日志有身份字段冻结保护，但普通历史日志没有 platform 证据；如果未来把历史 Postback 记录纳入平台作用域处理，不能继续按四字段静默重算。
4. 管理端列表/详情 Schema 当前不暴露平台或身份归属状态。新增字段后，必须明确其可见性与脱敏要求；不能让管理端把 NULL 误显示成“默认平台”。
5. 管理端重试仅对带有效配置引用的失败 Outbox 重新排队。若未来引入 legacy ambiguous 状态，必须让自动 worker 和人工 retry 两条路径都显式排除该状态；只增加一个展示字段不足以形成安全门禁。

### 发送入口盘点的范围说明

本轮从未截断的 Git Tree 中筛选了第三方报告、Postback、像素、斗篷和迁移相关文件，并分批读取核心发送入口及 API 文件。已确认上述两条发送路径及 Outbox Worker 调用链。

GitHub Code Search 对目标分支没有提供可用的完整结果，且本轮没有在完整工作区运行 `git grep`。因此，这是一份**已核实入口清单，不是全仓库穷尽性调用点证明**。仍需在可执行工作区搜索所有动态导入、脚本、测试和后台任务入口后才能关闭全量调用点审计。

### 后续实现要求（尚未实施）

- 新增 nullable `platform` 列，采用独立的新 migration；不得修改已登记的 20261110 历史 migration SQL 或其 SHA-256。
- Postback Outbox 创建新记录时持久化规范化 platform；短链/斗篷直接发送继续使用 NULL，除非业务模型明确提供独立平台来源。
- 直接发送函数新增可选 platform 参数时，必须同时保持旧调用兼容；所有身份查询、创建、更新和发送 payload 使用同一规范化身份。
- 历史行 platform 保持 NULL。四字段 legacy key 仅用于只读潜在冲突检测，不得按当前请求平台自动归属、复用或发送。
- 对 legacy ambiguous 事件设计持久化 fail-closed 状态；自动 worker、管理员 retry、后台编辑、导出和审计必须统一遵守该状态。
- 管理员修改身份字段时，必须按行的已证明身份维度重算 key；平台未知的历史 Postback 行不得通过四字段重算而伪装成已完成平台归属。
- 完成平台 A/B 同字段冲突、legacy success/pending/failed、直接短链无平台、管理员编辑与重试、并发写入和新旧 Worker 混跑的隔离 MySQL 测试。

本轮仅补充代码级证据与实施门槛，没有修改业务代码、模型或 migration；历史兼容风险仍是 P1 阻断项。


## 2026-11-13 事件身份状态机：迁移与运行时门禁实施决策（尚未实施）

### 设计目标

在不猜测历史 Postback 平台、不改变历史 event_key、不影响短链/斗篷无平台路径的前提下，让新事件身份可持久化、可审计，并使未知身份在所有自动/人工发送入口 fail-closed。

### 持久化字段

建议在 `third_party_report_logs` 新增：

- `platform VARCHAR(50) NULL`：规范化平台标识。NULL 表示没有已证明的平台值，不代表默认平台。
- `identity_scope VARCHAR(32) NOT NULL DEFAULT 'legacy_unresolved'`：身份作用域状态。

状态仅允许：

| 状态 | 含义 | 发送规则 |
| --- | --- | --- |
| `legacy_unresolved` | 迁移前记录，平台身份/旧算法归属尚未完成安全判定 | 禁止自动发送、人工重试和身份字段编辑 |
| `unscoped` | 新建短链/斗篷直接发送记录，明确没有 Postback platform 维度 | 仅允许四字段 key 的直接发送/幂等复用 |
| `platform_scoped` | 新建 Postback Outbox 记录，平台已规范化并持久化 | 仅允许 platform + 四个基础字段的五字段 key |

禁止将 NULL platform 自动解释为任意平台。状态值应使用应用常量/校验约束；数据库约束能力需结合现有 MySQL 版本和迁移策略确认。

### 历史行策略

- 新 migration 只添加 nullable `platform` 和带默认值的 `identity_scope`；所有既有行默认成为 `legacy_unresolved`。
- 不在该 DDL migration 中对大表执行无批次 UPDATE，也不修改历史 migration 文件或 checksum。
- 旧四字段 event_key 保持原值；旧五字段 Outbox event_key 也保持原值。不得尝试从 hash 反推出 platform。
- 历史成功记录保留为只读证据；历史 pending/failed Outbox 不得被自动 worker 或管理员 retry 发送。
- 如未来需要恢复部分历史记录，必须有独立、可审计的人工 reconciliation 流程，提供可验证的原始 Postback platform 来源、候选唯一性证明、原 event_key 与目标 key 冲突检查、双人审批及不可变审计记录。没有可靠来源时永久保持 unresolved。

### 新写入策略

1. Postback Outbox 入口必须拒绝空白 platform；规范化规则与 key builder 完全一致（仅 trim，不擅自大小写折叠）。
2. 新 Outbox 行同时写入 `platform=<规范化值>`、`identity_scope='platform_scoped'` 和五字段 event_key。
3. 短链/斗篷直接发送不推断平台；新日志写入 `platform=NULL`、`identity_scope='unscoped'`，并以四字段 key 进行身份查询和创建。
4. `create_report_log()` 查询到 `legacy_unresolved` 同 key 行时必须返回明确冲突/不可发送结果，不能把它当作已知 unscoped 日志复用；唯一键冲突后的并发回查也必须校验 identity_scope。
5. 新 Postback 事件命中同 key 旧行时，只有现有记录已经是 `platform_scoped` 且 platform 完全相同，才允许幂等复用；命中 unresolved 或 scope 不一致时中止当前业务事务，不得静默复用。

### 统一发送与管理门禁

- Outbox due scanner 查询必须要求 `identity_scope='platform_scoped'` 且 `platform IS NOT NULL`。
- Outbox item processor 在租约认领时必须带身份作用域条件；不能只在认领后检查，否则会产生无意义的租约占用。
- 人工 retry 的 SQL UPDATE 条件必须与 due scanner 一样检查 `platform_scoped`、非 NULL platform、未清理 PII、有效配置引用和租约过期。
- 直接发送路径只接受 `unscoped` 行；传入既有 `report_log_id` 的调用必须校验该行作用域，不能绕过检查。
- 管理端编辑：`legacy_unresolved` 禁止所有身份字段修改；`platform_scoped` 身份字段继续冻结；`unscoped` 可编辑时只能按四字段重算，且必须保持 scope 不变。
- 管理端列表/详情应展示 `identity_scope` 和 nullable `platform`；明确显示“历史身份待核实”，不显示默认平台。
- 导出、报表统计和审计记录需保留 scope 语义；不得把 unresolved 统计为某个具体平台。

### 必须覆盖的隔离 MySQL 测试

- 迁移后旧记录 scope 全部为 unresolved，platform 均 NULL，event_key 原值不变。
- 新短链/斗篷日志为 unscoped，platform NULL；正常重复请求复用同一日志。
- 新 Postback Outbox 为 platform_scoped，平台字段和五字段 key 一致。
- 平台 A/B 相同四字段事件可以并存；同平台重复事件唯一复用。
- 空白 platform 被拒绝，不得退化成 unscoped Postback。
- unresolved 的 success/pending/failed 行都不能发送、retry、编辑身份字段。
- unresolved 同 key 冲突不能在直接发送创建函数或 Outbox enqueue 中被当作成功去重。
- 直接发送 report_log_id 不能绕过 scope 检查。
- due scanner、item processor、管理员 retry 三条路径分别验证 SQL/并发门禁。
- 新旧 Worker 混跑时，旧 Worker 对新增 platform_scoped 行不得用四字段重新创建日志；发布顺序需先部署兼容代码，再允许写入新 schema。
- 管理端 Schema 明确返回 nullable platform 和 scope；未知值保持 NULL。

### 发布兼容与回滚

- 旧 Worker 不认识新字段，可能继续按四字段 key 直接创建/复用日志；因此新 schema 与新写入逻辑必须作为有顺序的兼容发布，不允许先启用新 Postback 写入再运行旧 Worker。
- 在新旧 Worker 共存期间，必须明确旧版本是否可能消费新 Outbox；若不能证明兼容，必须先停用旧 Worker 或设置发布门禁，不能仅靠数据库新增列解决。
- migration DDL 与应用代码分阶段发布，需先完成旧版本行为审查、临时 MySQL 双版本混跑测试和回滚演练。
- 回滚时不得删除新列或把新记录重写成四字段 key；应回滚应用写入开关并保留新增字段和身份数据。
- 该状态机仍是实施设计，不代表代码、migration、Worker 门禁或历史 reconciliation 已完成。


## 2026-11-13 事件身份状态机：运行时门禁落点复核（Run #1512）

### 本轮新增直接证据

- `create_report_log()` 当前只查询 `event_key` 并选择 ID；命中后不核验记录来源、平台或身份归属状态，直接返回既有 ID。并发唯一键冲突后的回查也只读取 ID。这意味着仅新增 `identity_scope` 字段而不修改两处查询，会让新短链直接发送误复用 legacy unresolved 记录。
- `_claim_report_log()` 当前是共享发送租约入口，只按 ID、状态、PII 清理、尝试预算、租约和重试时间认领，不校验发送路径的身份作用域。直接发送和 Outbox Worker 都可能触发该认领。
- `process_postback_report_outbox_item()` 当前先调用 `_claim_report_log(report_log_id)`，再查询 Outbox 行和检查配置引用。身份状态门禁若只放在认领后的 SELECT，会先为不允许发送的历史行占用租约；正确实现必须把 scope/platform 条件下推到原子 claim UPDATE，并在读取 payload 时再次验证。
- `process_postback_report_outbox()` 的 due scanner 当前仅检查 `outbox_enqueued/status/PII/next_retry_time/attempt_count/lease`，没有身份状态条件。必须在扫描条件中加入 `identity_scope='platform_scoped'` 和 `platform IS NOT NULL`，并让耗尽预算收敛查询、积压统计同样区分 unresolved，避免把历史歧义记录误计入可发送队列。
- `retry_report_log()` 当前只检查 Outbox、失败状态、PII、配置引用和租约，没有平台身份条件。新增状态字段后必须在 UPDATE 的 WHERE 子句中直接约束作用域，不能只在 API 层做前置 SELECT。
- `update_report_log_params()` 当前允许非 Outbox 历史日志修改 adsid/event/conversion_id，并始终按四字段重算 event_key。若新增 unresolved 状态，该函数必须先拒绝 unresolved 的身份字段修改；对 platform_scoped 记录必须保持平台维度（建议身份字段继续冻结）；只有 unscoped 才能按四字段算法重算。
- 当前管理员列表/详情 Schema 没有 platform / identity_scope 字段。新增后需同时更新 list 和 detail 模型，并确保 NULL 仍然是 NULL，不能默认映射为任何平台。

### 实施边界修正

1. `_claim_report_log` 应要求调用者显式指定预期身份作用域，不提供可默认为任意状态的宽松默认值。短链/斗篷直接发送使用 `unscoped`；Postback Outbox 使用 `platform_scoped`。
2. `send_third_party_report(report_log_id=...)` 的现有 Outbox 调用路径已传入预先取得的 lease token；但必须审计所有其他 report_log_id 调用者，确保不会绕过预期 scope。新增参数应显式向上传递，不能只依赖“调用方通常是 Outbox”。
3. `_renew_report_log_lease`、发送前尝试次数读取、状态读取与状态更新都应验证身份作用域或沿用不可伪造的 claim token；不能允许无 scope 证明的旧调用继续持有租约并发出请求。
4. due scanner、claim UPDATE、payload SELECT、管理员 retry、手动编辑和发送函数都需要覆盖测试；只在其中一个入口加过滤不构成 fail-closed。
5. 新 schema 部署前，必须确认所有旧 Worker 都停止消费新写入的 platform_scoped 行。旧 Worker 不识别 identity_scope，可能用四字段路径绕过新模型；不能以“新增 nullable 列”声称向后兼容。

### CI 记录

- Run #1512：`43356690016`，HEAD `cd9e8588ba5ebc1e77bdbe8c4f197b91b341bf82`，Backend / Frontend 均 success。
- Backend：602 passed、1 skipped、1 warning（Python 3.11 `crypt` DeprecationWarning）。
- Frontend：Playwright Mock API Browser E2E 通过，日志覆盖登录校验、认证成功/失败、管理员导航、Outbox 重试资格/详情、登出、移动端抽屉及客户端 RBAC。
- CI 使用隔离 MySQL / Redis 和 Mock API；没有生产连接或真实第三方发送。
- 本轮仍未修改业务代码、模型、migration 或发送行为；以上是实施前的调用链门禁清单，不代表 P1 已修复。


## 2026-11-13 历史四字段冲突保护：CI 验收与并发缺口复核（Run #1515）

### CI 验收

- HEAD：`c015bd99017e1d734300feb8ec43f96771ff647f`
- Run #1515：`43361483180`，Backend / Frontend 均 success。
- Backend：603 passed、1 skipped、1 warning。
- 新增 `test_postback_enqueue_fails_closed_on_legacy_four_field_identity` 通过。
- Frontend Playwright Browser E2E 通过。
- 测试使用 GitHub Actions 临时 MySQL / Redis 和 Mock API；没有生产连接或真实第三方发送。

### 本轮代码改动

- `app/services/third_party_report_outbox.py` 新增 `LegacyEventIdentityConflict`。
- `enqueue_postback_report()` 在当前平台五字段 key 未命中时，额外查询历史四字段 key；若命中则拒绝创建新的 Outbox 行。
- Postback platform 先 trim，空白平台直接拒绝。
- 新增回归测试，验证历史四字段 key 命中时不写入新 Outbox 行。

该改动是入队阶段的**尽力 fail-closed 检查**，不能宣称已消除所有历史身份冲突。

### 新发现：跨路径并发竞态仍未关闭（P1）

重新读取 `app/core/third_party_report.py` 后，确认：

1. `create_report_log()` 仍按四字段生成 key，先 SELECT event_key；若命中直接返回 ID，没有核验来源、scope 或平台。
2. 其 IntegrityError 并发回查同样只按 event_key 读取 ID，不检查身份归属。
3. `create_report_log()` 的查询与 INSERT 不持有一个跨路径共享的身份锁；数据库唯一键只能仲裁完全相同的 event_key，不能仲裁四字段 legacy key 与平台五字段 key 之间的逻辑冲突。
4. `enqueue_postback_report()` 新增的 legacy SELECT 与五字段 INSERT 也没有共享互斥键。并发时可能发生如下顺序：
   - Postback A 查询五字段 key 不存在；
   - A 查询四字段 legacy key 不存在；
   - 直接发送路径按四字段 key 插入并提交；
   - A 插入五字段 key 并提交。
   两条记录的 event_key 不同，现有唯一约束无法阻止它们同时存在。
5. 反向顺序同样需要保护：平台作用域事件已经存在时，直接发送路径仍可能按四字段身份创建无平台记录。
6. 因此，仅在 Outbox 入队函数增加一次 legacy SELECT，不能证明跨路径去重安全；本轮不应新增“并发竞态已解决”的结论。

### 正式修复前的设计要求

- 必须建立跨路径、跨 Worker、跨平台一致的身份仲裁原语；所有创建/复用路径在查重和写入期间都必须持有同一基础事件身份的互斥保护。
- 仲裁键必须基于稳定的四字段基础身份（source、adsid、event、conversion_id 的规范化编码），不能直接使用五字段 event_key，否则平台 A/B 不会互斥。
- 互斥只用于串行化身份决策；在临界区内仍须允许不同明确平台的五字段事件并存，但必须阻止无平台四字段事件与任意平台作用域事件在无法证明语义时同时被创建。
- 需要确认部署使用的 MySQL 版本、隔离级别、连接池和所有写入入口后，再决定采用独立身份锁表（唯一基础身份键 + 行锁）、MySQL advisory lock（严格保证同一物理连接/事务边界），或其他可证明原子性的实现。不能在尚未核验连接生命周期时直接套用 GET_LOCK。
- 若使用锁表，必须解决锁行首次并发创建、事务提交/回滚、死锁重试、锁记录生命周期、哈希碰撞防御、超时和跨 Worker 一致性。
- 所有身份查询、插入、唯一键冲突回查必须在同一仲裁边界内执行，并验证 identity_scope / platform。
- 需要真实隔离 MySQL 并发测试：直接发送与 Postback 同时首次写入；平台 A/B 同时写入；重复 Postback；锁获取超时；事务回滚后释放锁；多连接/多 Worker；不同字符集和空字段规范化。
- 在仲裁原语与统一 scope 门禁实现前，保留当前入队历史冲突检查作为额外保护，但不得将其作为完整解决方案。

### 当前范围与限制

- 本轮没有修改 `create_report_log()`、共享租约认领、Outbox scanner、管理员 retry 或 schema；这些仍未实施 scope 门禁。
- 尚无 `platform` / `identity_scope` 数据库列，也没有正式 migration。
- 当前新增测试是 FakeDB 级单元测试；Run #1515 的既有 MySQL 集成测试通过，但**没有**覆盖上述两条业务路径的真实并发竞态。
- 仍需完整工作区 `git grep` 核实所有直接发送及身份写入调用点；GitHub 文件读取不是全仓库穷尽性扫描。
- 历史 migration SQL 和 manifest checksum 保持不变。
