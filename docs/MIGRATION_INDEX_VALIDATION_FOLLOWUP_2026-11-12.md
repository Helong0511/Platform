# Migration 同名索引冲突防护与 CI 验收补充记录（2026-11-12）

> 本记录补充 `docs/DEPLOYMENT_READINESS_RUNBOOK_2026-11.md` 第 36 节之后的迁移审查证据。  
> 范围：非凭据安全问题；凭据安全专项继续按用户要求暂缓。  
> 隔离约束：未连接生产服务器、生产数据库、Redis、队列或真实第三方接口。

## 1. 新发现：同名但结构错误的索引会被误判为已迁移

此前增量迁移对部分索引只按索引名称检查是否存在。若数据库已有同名但列、顺序或唯一性错误的索引，迁移可能误认为目标索引已经正确创建，静默跳过结构修复。对事件幂等迁移而言，这种误判还可能使旧唯一约束被删除，造成唯一性保护缺口。

## 2. 修复内容

### 2.1 事件幂等迁移

文件：`sql/migrations/20261110_third_party_report_event_idempotency.sql`

- `unique_event_key` 必须恰好一列、唯一、无前缀索引，且列名为 `event_key`。
- 如果存在错误同名索引，迁移不把它当成正确索引；后续创建目标索引时明确失败（MySQL 1061），旧 `unique_source_adsid` 不会被提前删除。
- 该顺序保持“先建立并确认新唯一约束，再移除旧唯一约束”的保护原则。

### 2.2 Outbox due 索引与字段

文件：`sql/migrations/20261111_third_party_report_outbox.sql`

- `idx_third_party_outbox_due` 必须是非唯一、无前缀、恰好五列，且顺序为 `outbox_enqueued,status,next_retry_time,report_start_time,id`。
- Outbox 新增字段存在性检查同时核对 `COLUMN_TYPE`、NULL 属性及默认值，避免只按字段名误判。
- 修正了曾导致 CI 失败的变量名不一致：赋值与后续判断统一使用 `@has_due_index`。

### 2.3 PII 保留扫描索引和字段

文件：`sql/migrations/20261112_third_party_report_pii_retention.sql`

- 两个保留扫描索引必须是非唯一、无前缀、恰好三列，顺序为 `pii_scrubbed_at,created_at,id`。
- 两张日志表的 `pii_scrubbed_at` 必须是可空 DATETIME。

## 3. 新增真实隔离 MySQL 回归测试

文件：`tests/test_mysql_migrations.py`

- 事件迁移：预建错误同名 `unique_event_key(event)`，执行迁移必须以 MySQL 1061 明确失败；同时断言旧唯一索引仍在、错误索引结构未被篡改。
- Outbox 迁移：预建错误同名 `idx_third_party_outbox_due(status)`，迁移必须明确失败，并核对此前成功执行的独立 DDL 仍存在。
- PII 迁移：预建错误同名 `idx_third_party_pii_retention(created_at)`，迁移必须明确失败，并核对已添加字段。
- 这些测试使用 CI 临时 MySQL 和合成表数据，不触碰生产库。

## 4. CI 失败与修复闭环

- Run #1282（失败）：Backend 479 passed、2 failed、1 skipped、1 warning。失败原因是 Outbox 索引状态变量赋值使用了 `@has_index`，后续却判断 `@has_due_index`；MySQL 用户变量未赋值时为 NULL，导致条件分支错误跳过目标索引创建。
- 修复提交：`c60cf24c4f94a222753a21023a3b41b8af119e84`，将赋值变量修正为 `@has_due_index`。
- Run #1283（上述修复 SHA）：Backend **481 passed、1 skipped、1 warning**；Python Compile 成功。
- Run #1283 Frontend：npm ci、依赖 Advisory 报告、Lint、Build、Playwright Chromium 安装、隔离 Vite 服务启动和 Mock API Browser E2E 全部成功。
- Browser E2E 明确覆盖登录校验、认证失败/成功、管理员导航、Outbox 重试资格/详情、退出登录、移动端抽屉和 Client RBAC。
- Run #1283：https://github.com/Helong0511/Platform/actions/runs/43147557182
- 唯一 pytest skip：本地核对脚本未检出（该脚本不属于 CI 必需文件）；唯一 warning：Passlib 1.7.4 在 Python 3.11 导入 `crypt` 的弃用提示。它们不是测试失败；密码哈希/凭据安全专项仍未在本轮改动。
- Run #1282 的失败记录保留，不将失败轮次计为通过。

## 5. MySQL DDL 中断语义

- MySQL InnoDB 的单条 Atomic DDL 具备崩溃原子性，但不等于多条迁移语句组成一个事务。
- `ALTER TABLE`、`CREATE INDEX`、`DROP INDEX` 等 DDL 会隐式提交；本项目迁移不可描述为整体事务回滚。
- 同名错误索引触发 1061、错误同名字段触发 1060，属于 fail-closed：明确停止迁移并保留现场，等待人工修复冲突后重跑。
- 分步 DDL 中此前成功的语句可能保留；必须通过逐 DDL 边界故障注入证明每个中间状态均可诊断和安全续跑。

官方资料：
- MySQL 8.0 Atomic DDL：https://dev.mysql.com/doc/refman/8.0/en/atomic-ddl.html
- MySQL 8.0 Statements That Cause an Implicit Commit：https://dev.mysql.com/doc/refman/8.0/en/implicit-commit.html
- MySQL Metadata Locking：https://dev.mysql.com/doc/refman/8.0/en/metadata-locking.html

## 6. 尚未关闭的迁移发布阻断项

以下项目仍未完成，不得因 Run #1283 全绿而宣称迁移已达到生产上线条件：

- [x] 对三份增量迁移的 15 个 DDL 执行边界逐点注入进程退出，验证中断后的 schema 状态与安全重跑（Run #1288）；该项不涵盖 MySQL server crash / 磁盘故障。
- [ ] 代表性旧 schema + 合成历史数据的完整升级演练。
- [ ] 逻辑备份导出、导入隔离实例恢复，核对行数、主键范围、索引定义和关键数据校验值。
- [ ] Worker pause/resume 与迁移期间应用读写兼容性。
- [ ] 旧版本应用兼容回滚；确认 `event_key NOT NULL` 约束下旧二进制是否仍可安全写入。
- [ ] 迁移前后 schema/data diff。
- [ ] 大规模合成数据升级耗时、锁等待、元数据锁与业务写入影响评估。
- [ ] Migration runner / manifest 的执行顺序、重复执行和并发执行保护审查。
- [ ] PII 保留期限及其它数据类别的业务/合规审批。

## 7. 当前决策

- Run #1283 对当前 SHA 的 Backend、Frontend、Build、Lint 和 Mock API Browser E2E 验收通过。
- Run #1283 不替代上述迁移演练，也不代表生产数据库已升级。
- PR #1 继续保持 Open / Draft；不合并 main、不部署。
- 本轮仍不访问生产环境；凭据安全专项仍按用户要求暂缓。


## 8. PII 下游转发索引结构校验补强（Run #1285）

### 复核发现

- 二次逐行检查发现，`idx_forward_log_pii_retention` 的结构断言此前只检查列数与列顺序，遗漏 `NON_UNIQUE` 和 `SUB_PART`。
- 因此一个列顺序正确但实际为唯一索引的同名索引，可能被误判为已满足普通扫描索引要求。
- 这是结构校验遗漏，不代表已经证明生产数据库存在该错误索引。

### 修复与测试

- 在 `sql/migrations/20261112_third_party_report_pii_retention.sql` 的下游转发日志索引检查中补齐：
  - `MAX(NON_UNIQUE) = 1`：必须是非唯一索引。
  - `MAX(SUB_PART) IS NULL`：不允许前缀索引。
  - 保留恰好三列及列顺序 `pii_scrubbed_at,created_at,id` 的检查。
- 新增真实隔离 MySQL 测试：预建列顺序正确但唯一的同名 `idx_forward_log_pii_retention`，迁移必须以 MySQL 1061 明确失败，且原错误索引保持不变。
- 事件幂等和 Outbox 索引检查保持原有精确结构断言。

### CI 证据

- 修复提交：SQL `5e5d63b86e7c538a2dccdb79b9dae0759fa8d852`；测试 `3bf643a6f119b38b30037bf7c37f8b4ea422da21`。
- Run #1284 因后续 PR 提交触发 concurrency 取消，未作为验收依据。
- Run #1285（SHA `3bf643a6f119b38b30037bf7c37f8b4ea422da21`）：Backend **482 passed、1 skipped、1 warning**；Python Compile 成功；Frontend npm ci、依赖 Advisory 报告、Lint、Build、Playwright Mock API Browser E2E 全部成功。
- Run #1285：https://github.com/Helong0511/Platform/actions/runs/43148171446
- 测试使用 GitHub Actions 临时 MySQL 8.0.46 / Redis 7.4、合成数据及 Mock API；没有访问生产资源。

### 仍未关闭

- 逐 DDL 中断故障注入、代表性旧 schema 与历史数据升级、逻辑备份导入恢复、worker pause/resume、应用兼容回滚及 schema/data diff 尚未完成。
- PR #1 仍 Open / Draft；不合并 main、不部署；凭据安全专项仍按用户要求暂缓。


## 9. 逐 DDL 中断恢复演练与启动迁移机制复核（Run #1288）

### 9.1 逐 DDL 中断注入测试

- 在 `tests/test_mysql_migrations.py` 增加 `_run_sql_file_with_ddl_interruption`，在指定 DDL 执行完成后模拟进程退出，并关闭旧连接。
- 对三份增量迁移的全部 DDL 执行边界逐点注入：
  - 事件幂等迁移：4 个边界（事件键列创建、NOT NULL 收敛、新唯一索引、删除旧唯一索引）。
  - Outbox 迁移：7 个边界（6 个字段、due 索引）。
  - PII 保留迁移：4 个边界（两张表的标记列及两个扫描索引）。
- 每个用例都使用全新隔离 MySQL 表结构，在中断后建立新连接，完整重跑迁移两次，并检查最终字段、NULL 属性、索引列顺序及旧唯一约束状态。
- 共新增 15 个中断恢复场景。此测试验证 DDL 边界之后的进程退出和安全续跑；不等同于 MySQL server crash、磁盘故障或备份恢复演练。

### 9.2 CI 失败与修复

- Run #1287 失败：新增 15 个测试辅助函数把换行分隔符写成字面量 `\\n`，导致 SQL 语句前出现反斜杠字符；原有 **482 passed**，新增 **15 failed**。这是测试辅助代码缺陷，不是迁移 SQL 被证明有问题。
- 修复提交：`326ae1545eafba53d0afb550d7d005d670c06bba`，将行分隔恢复为真实换行。
- Run #1288：Backend **497 passed、1 skipped、1 warning**；Python Compile 成功；Frontend npm ci、依赖 Advisory、Lint、Build、Playwright Mock API Browser E2E 全部成功。
- Run #1288：https://github.com/Helong0511/Platform/actions/runs/43149106367
- Run #1287 保留为失败记录，不计入通过统计。

### 9.3 新确认的发布阻断：应用启动时的 schema bootstrap 不能替代迁移

检查文件：`app/bootstrap/lifespan.py`、`app/core/database.py`、`app/db/database.py`、`app/models/__init__.py`。

观察到的代码行为：
- 每个 API / scheduler worker 的 lifespan 启动都会调用 `create_database()`，然后执行 `Base.metadata.create_all`。
- `create_all` 只负责创建 metadata 中尚不存在的表，不会把既有表自动 ALTER 到新增列或索引结构；因此它不能替代本目录的增量 SQL migrations。
- lifespan 捕获 schema bootstrap 异常后继续启动；对 MySQL 错误码 1684 特别降级为信息日志并继续。随后 `init_db()` 失败也被记录后吞掉。
- 当前仓库树中存在 `sql/migrations/*.sql` 和隔离测试，但没有发现 Alembic 配置、统一 migration runner、schema revision ledger 或 manifest。
- 因而部署过程依赖人工按文档顺序执行 SQL；应用启动本身既不证明增量迁移已经执行，也不保证 schema 初始化失败后阻止服务对外提供流量。

风险判断：
- MySQL 官方将 1684 定义为 `ER_WARN_I_S_SKIPPED_TABLE`：information_schema 中的表因其定义正被并发 DDL 修改而被跳过。它不能单独证明所有表已创建完成；当前代码不在忽略后执行完整 schema 再核验。
- 如果任一增量迁移未执行，`create_all` 不会补齐既有表的新增列；服务可能启动成功，但访问相关 ORM 字段时才失败。
- 这属于发布流程/启动就绪性风险，不代表已观察到生产 schema 损坏；本轮没有访问生产数据库。

下一步必须修复/验收：
- [ ] 明确唯一 schema 变更入口：建立受控 migration runner 或确定等价的发布工具；为每个 migration 建立有序 revision、校验和、执行记录和并发锁。
- [ ] migration runner 在执行前校验 MySQL 版本、目标 schema、表/索引前置条件；执行后验证精确结构并记录 revision；失败必须停止，不得登记成功。
- [ ] 应用 readiness 在启动时校验所需 schema revision / 关键字段结构；缺失或结构不匹配时不得报告 ready。
- [ ] 重新评估每个 worker 在 lifespan 内重复执行 `create_all` 的必要性；移除对生产 schema 的隐式 DDL，或至少串行化并在结束后做完整核验。
- [ ] 不得把 1684 无条件当作“可安全忽略”；需要受控重试并验证目标表结构，无法确认时 fail closed。
- [ ] 为启动失败、schema revision 缺失、并发 worker 启动和 DDL 正在执行等情况增加隔离集成测试。

权威资料：
- MySQL 8.0 Error Reference（1684 / ER_WARN_I_S_SKIPPED_TABLE）：https://dev.mysql.com/doc/mysql-errors/8.0/en/server-error-reference.html
- SQLAlchemy 2.0 MetaData.create_all：只检查并创建不存在的表：https://docs.sqlalchemy.org/en/20/core/metadata.html
- SQLAlchemy 2.1 Metadata 教程说明长期 schema 管理应采用 Alembic 等迁移工具：https://docs.sqlalchemy.org/en/21/tutorial/metadata.html

### 9.4 当前发布决策

- 15 个 DDL 边界中断后续跑测试已由 Run #1288 验收通过。
- MySQL server crash、逻辑备份导入恢复、应用 worker pause/resume、旧版本兼容回滚、schema/data diff、大规模数据升级性能仍未完成。
- 启动时 schema bootstrap / migration runner / readiness 风险仍是发布阻断项。
- PR #1 继续 Open / Draft；不合并 main、不部署、不访问生产环境；凭据安全专项继续暂缓。


## 10. PII 清理真实 MySQL 集成验收（Run #1291）

### 覆盖范围

在 `tests/test_third_party_report_outbox_mysql_integration.py` 增加独立临时数据库测试，使用 CI loopback MySQL 和随机隔离数据库，不连接生产环境。

- 终态第三方上报记录：应清除 PII 载荷，同时保留稳定 `event_key`，并将 `adsid` / `conversion_id` 按策略处理。
- 活跃 Report Outbox 租约：`report_start_time` 在 300 秒租约内，必须跳过清理。
- 待重试 Outbox：未耗尽次数且有后续重试时间/配置引用，必须保留载荷。
- 下游转发日志：存在完全匹配的活动队列目标时必须保留；同一 conversion 但目标不同不得错误阻塞清理。
- `publisher_id/product_id` 同时为 NULL 的目标必须通过 NULL-safe 相等匹配，防止误清理仍在排队的目标。
- 使用真实 MySQL 执行 `FOR UPDATE SKIP LOCKED`、子查询 `NOT EXISTS` 和 ORM 更新/提交，断言最终数据库内容。

### CI 证据

- Run #1291：https://github.com/Helong0511/Platform/actions/runs/43149636500
- Backend：**498 passed、1 skipped、1 warning**；Python Compile 成功。
- Frontend：npm ci、依赖 Advisory、Lint、Build、Playwright Mock API Browser E2E 全部成功。
- 新测试在 CI 临时 MySQL 随机数据库内执行，测试结束删除隔离数据库。

### 仍需明确

- 自动 PII 清理默认配置仍为 `THIRD_PARTY_REPORT_PII_RETENTION_DAYS=0`，本轮没有启用任何真实数据清理。
- 具体保留期限、业务审计需求和法律/合同要求仍需负责人审批；不能仅因技术测试通过就设置生产保留天数。
- 当前 MySQL 集成测试证明目标匹配、活跃租约保护和基本清理结果，不替代真实备份恢复、长时间并发压力、跨 worker 故障注入。


## 11. Schema bootstrap fail-closed 修复与模型索引冲突闭环（Run #1296 / #1298）

### 11.1 启动 schema 初始化机制修复

文件：`app/bootstrap/lifespan.py`

- MySQL schema bootstrap 使用 session advisory lock `GET_LOCK('platform_schema_bootstrap', 60)` 串行化多个 API / scheduler worker 的建表检查。
- 锁持有期间执行 `Base.metadata.create_all`，随后逐表核对 ORM metadata 声明的表和列。
- 对已存在表，`create_all` 不会 ALTER 新列；结构核验发现缺表/缺列时抛错并拒绝启动。
- 不再无条件忽略 MySQL 1684 或其它 schema 初始化异常。
- 释放锁失败会记录异常类型；连接关闭会按 MySQL 语义释放 session advisory lock。
- `init_db()` 失败也不再被 lifespan 静默吞掉。

### 11.2 全量 ORM schema 创建暴露的重复索引

Run #1295 对完整 `Base.metadata` 执行真实 MySQL create_all 时失败：

- MySQL 1061：`Duplicate key name 'ix_user_sessions_token_type'`。
- 根因：`app/models/session.py` 的 `token_type` 列声明 `index=True`，SQLAlchemy 已生成默认索引 `ix_user_sessions_token_type`；`__table_args__` 又显式声明同名 Index，导致创建同一表时重复创建。
- 同一模型还对 `expires_at` 同时使用 `index=True` 和显式单列索引；此外主键 `id` 的 `index=True` 会产生不必要的主键重复索引。
- 修复：保留 `token_type` / `expires_at` 列级索引声明，删除重复显式索引；移除主键 `id` 的冗余 `index=True`。
- 这次错误证明之前 lifespan 的“记录错误后继续启动”会掩盖全量 schema 创建失败，fail-closed 改动成功暴露真实问题。

### 11.3 多 Worker 默认管理员初始化竞态

文件：`app/core/database.py`

- 多 worker 同时启动时，可能同时查询到“尚无管理员”，然后竞争插入同一个默认管理员。
- 唯一键只允许一个 worker 成功；其它 worker 可能得到 IntegrityError。
- 现已只对 MySQL 1062 / 明确 duplicate entry / SQLite unique constraint 失败执行回滚后复查管理员：
  - 如果管理员已由其它 worker 创建，视为并发初始化成功。
  - 如果没有管理员，或错误不是重复键，继续抛错，不能吞掉真实 DB 问题。
- 新增 `tests/test_database_init.py` 覆盖并发重复键成功确认和非重复完整性错误继续抛出。

### 11.4 CI 验收记录

- Run #1294：在全量 metadata 并发测试执行过久后，被后续测试拆分提交取消；不计为通过。
- Run #1295：**500 passed、1 failed、1 skipped、1 warning**；失败是上述真实重复索引名，未计为通过。
- Run #1296：**501 passed、1 skipped、1 warning**；完整 ORM schema 创建及列核验通过，Frontend 全部通过。
- Run #1298：**503 passed、1 skipped、1 warning**；新增管理员初始化竞态测试通过，Frontend npm ci、Advisory、Lint、Build、Playwright Mock API Browser E2E 全部成功。
- Run #1296：https://github.com/Helong0511/Platform/actions/runs/43151042571
- Run #1298：https://github.com/Helong0511/Platform/actions/runs/43151286645

### 11.5 GET_LOCK 使用边界与发布前提

MySQL 官方文档确认：
- `GET_LOCK` 是独占 session-level named lock；同名锁被持有时其它 session 等待。
- 返回 1 表示成功，0 表示超时，NULL 表示错误。
- `COMMIT/ROLLBACK` 不释放该锁；必须调用 `RELEASE_LOCK` 或结束连接。
- 锁名最大 64 字符，锁作用域是单个 MySQL Server，不是多节点集群全局协调。
- `GET_LOCK` 对 statement-based replication 不安全；NDB Cluster 也不能依赖它跨节点协调。

因此部署前仍需核实：
- [ ] 生产 MySQL 是单一协调主节点/适用的拓扑，所有应用 worker 连接同一 MySQL Server。
- [ ] 生产 binlog_format 与复制拓扑适合使用 `GET_LOCK`；若为 statement-based replication 或多主/多节点协调场景，需改用适配的锁服务或迁移锁表方案。
- [ ] 人工 SQL migration 执行流程与应用启动锁协调；当前 SQL 文件尚未统一接入 runner，因此不能在应用 worker 运行期间随意执行 schema DDL。

官方资料：
- MySQL 8.0 Locking Functions / GET_LOCK：https://dev.mysql.com/doc/refman/8.0/en/locking-functions.html

### 11.6 尚未达到上线条件的项目

- [ ] 建立有序 migration runner / revision ledger / manifest，并让手工迁移与应用启动使用同一协调机制。
- [ ] 启动 readiness 除表/列外，补充关键唯一约束与索引列顺序的结构核验；不能仅依赖 create_all。
- [ ] 逻辑备份导出、导入隔离实例恢复及数据校验。
- [ ] MySQL server crash、磁盘故障及 DDL 执行中断的更强故障注入。
- [ ] Worker pause/resume、旧版本应用兼容回滚、schema/data diff、大规模数据升级耗时/锁等待评估。
- [ ] PII 保留期限业务/合规审批仍未完成，默认仍为 0（禁用）。
- [ ] PR #1 继续 Open / Draft；不合并 main、不部署、不访问生产环境；凭据安全专项仍按用户要求暂缓。


## 12. CPL Offer 多客户账号范围修复（Run #1306）

### 12.1 发现的问题

`Client` 模型允许同一用户关联多个 Client 记录，但 Offer 查询路径曾使用 `get_client_id_for_user()` 并通过 `LIMIT 1` 只取一个客户 ID。该行为会造成同一账号下其它客户关联的 Offer、渠道分配和统计数据遗漏；更危险的是，若不同路径采用不同的单一 ID 取值顺序，列表、详情和统计可能产生不一致的数据范围。

### 12.2 修复范围

- 新增 `get_client_ids_for_user()`，按稳定 ID 顺序返回用户全部 Client ID；非 CLIENT 角色返回 `None`，CLIENT 但没有关联记录返回空列表。
- `assert_client_can_access_offer()` 使用全部客户 ID 检查激活渠道分配；空关联列表 fail-closed。
- Offer 列表计数与分页查询统一使用 `Publisher.client_id IN (...)`。
- Offer 单条分配和批量分配查询均使用完整客户 ID 集合；空集合返回空结果。
- Offer 详情响应仅保留属于当前账号全部 Client ID 的分配数据，同时继续剔除上游价格、Cap、广告主、Tracklink 和内部 Postback。
- Offer 统计查询的 Publisher 范围也改为当前账号全部 Client ID，避免共享 Offer 的其它客户点击/转化指标泄露。
- 旧 `get_client_id_for_user()` 暂时保留为兼容包装，但新权限判断路径不得继续调用它。

### 12.3 回归测试

新增 `tests/test_cpl_offer_multi_client_scope.py`，覆盖：
- 一个账号返回多个 Client ID；
- Offer 访问授权按全部 Client ID 判断；
- Offer 列表计数、分页与分配批量查询 SQL 均包含完整 ID 集合；
- 详情响应保留所有自有客户分配、过滤第三方客户，并隐藏上游敏感业务字段。

### 12.4 CI 证据

- Run #1306，SHA `95e445fed1698e3dbe28c6f0266f058f6a3a5b7a`。
- Backend：**507 passed、1 skipped、1 warning**。
- Frontend：npm ci、依赖 advisory、Lint、Build、Playwright Chromium 安装及 Mock API Browser E2E 全部通过。
- E2E 日志明确报告登录校验、认证失败/成功、管理员导航、Outbox 重试资格/详情、退出登录、移动端抽屉及客户端 RBAC 通过。
- CI：https://github.com/Helong0511/Platform/actions/runs/43152004569

### 12.5 尚未完成

- 继续检查 Client 多记录关联在产品分配、报表、结算、API Key、导出和 Dashboard 等其它模块中的范围一致性。
- 需要补充隔离 MySQL 数据库端到端多客户账号测试，当前新增测试主要验证 SQL 条件与响应过滤。
- 完整 migration/backup/restore/rollback 演练、PII 保留政策审批和 Outbox/Cap 组合故障演练仍未关闭。
- PR #1 仍 Open / Draft；不合并 main、不部署、不访问生产环境。凭据安全专项继续按用户要求暂缓。


## 13. 多客户账号模型、客户 API 密钥与管理入口一致性修复（Run #1313）

### 13.1 关联模型与管理入口冲突

- `Client` ORM 模型明确声明 `clients.user_id` 为多对一关系：同一个客户登录用户可以关联多个客户主体。
- 创建客户 API 允许管理员把新客户关联到已有用户，但更新客户关联用户时曾额外执行“一用户只能关联一个 Client”的检查。
- 这造成 create/update 行为不一致，并与 Offer、Dashboard、产品分配历史等按 `Client.user_id` 汇总多客户主体的既有实现冲突。
- 已删除更新入口的一对一限制；更新时仍验证目标 User 存在，客户归属范围由所有按 user_id 过滤的业务查询负责。
- 新增 `tests/test_client_user_multi_membership.py`，验证一个已有客户账号可以再关联另一客户主体。

### 13.2 客户开放 API 密钥选择

- 原 `GET /client/api-key` 对当前用户查询所有激活 Client 后直接使用 `first()`，没有稳定的客户选择语义；多客户账号可能拿到任意一个客户主体的 API Key。
- 现在支持可选查询参数 `client_id`，并始终同时限制 `Client.user_id == current_user.id` 与 `Client.is_active == True`：
  - 单客户账号不传参数时保持兼容。
  - 多客户账号不传参数时拒绝模糊选择，要求显式传入 `client_id`。
  - 指定不属于当前账号的客户 ID 时返回不存在/无权访问，不泄露其它客户密钥。
  - 成功响应包含 `client_id` 与对应 `key`。
- 前端 `getClientApiKey(clientId)` 现在显式提交 `client_id`；API 文档示例页使用当前选中的客户主体 ID 请求密钥。
- 新增 `tests/test_client_api_key_multi_client.py` 覆盖多客户缺少选择、明确选择、单客户旧调用兼容和越权客户 ID。

### 13.3 CI 验收

- Run #1313，HEAD SHA `b23af10e388a236deaf11e1022fe1b3583b47b1f)。
- Backend：**512 passed、1 skipped、1 warning**，无失败。
- Frontend：npm ci、依赖 advisory、Lint、Build、Playwright Chromium 与 Mock API Browser E2E 全部通过。
- Browser E2E 覆盖登录校验、认证成功/失败、管理员导航、Outbox 重试资格/详情、退出登录、移动端抽屉和客户端 RBAC。
- CI：https://github.com/Helong0511/Platform/actions/runs/43152934213
- 前端 Production dependency advisories 仍按用户要求留在凭据安全专项范围之外，不宣称依赖零漏洞。

### 13.4 仍需继续审计

- API 文档页当前从登录态读取的 `client_id` 是当前上下文客户 ID；如果后续 UI 要支持在多个客户主体间切换，应提供明确的客户选择 UI，不能重新退回无序 `first()`。
- 继续检查报表导出、产品权限变更、结算与统计 API 是否全部按当前账号的 Client 集合过滤，并验证历史产品归属切换时的租户隔离。
- 隔离 MySQL 多客户真实数据端到端测试仍需补齐；当前新增测试验证 SQL 约束和接口选择行为。
- PR #1 仍 Open / Draft；不合并 main、不部署、不访问生产环境。凭据安全专项继续暂缓。

## 14. Cap Reservation 迁移同名错误表 fail-closed 校验（Run #1403）

### 14.1 本轮发现与修复

- `CREATE TABLE IF NOT EXISTS cap_reservations` 在目标库已经存在同名但结构错误的表时会静默跳过建表；仅执行后续 `SHOW CREATE TABLE` 的测试无法证明迁移会拒绝这种状态。
- 在迁移末尾新增结构验收：精确核对 23 个字段的类型/NULL 属性、表排序规则、6 个 CHECK 约束、索引集合数量以及每个复合索引的列顺序。
- 如果结构不符合预期，通过动态 SQL 执行指向故意不存在的哨兵表的查询，使迁移以明确 MySQL 1146 错误失败；迁移不删除、不重建、不覆盖原有同名表。
- 新增隔离 MySQL 测试，预建仅含 `id` 和 `reservation_key` 的错误同名表，执行迁移后断言收到 1146，且原表结构仍保持不变。

### 14.2 CI 失败与修复记录

- Run #1402（SHA `4eefce50e832d2be433770251f08f963ca00316f`）出现 **1 failed、538 passed、1 skipped、1 warning**。失败是新测试对 MySQL 1146 错误类型的断言不准确：PyMySQL 将“表不存在”映射为 `ProgrammingError`，测试错误地期待 `OperationalError`；迁移实际按预期拒绝错误表。
- 已将测试异常类型断言修正为 `pymysql.err.ProgrammingError`，并保留 1146 错误码断言。
- Run #1403（SHA `77cd5a885bc0357c0ec163a5da9cb3da959ad109`）：Backend **539 passed、1 skipped、1 warning**；Python Compile、Frontend npm ci、依赖 Advisory 报告、Lint、Build、Playwright Mock API Browser E2E 全部成功。
- Run #1403：https://github.com/Helong0511/Platform/actions/runs/43178129007
- 1 skipped 为未提交的本地核对脚本（CI 不依赖）；1 warning 为 passlib 在 Python 3.11 使用 `crypt` 的弃用提示。前端 Production High advisory 仍属用户明确暂缓的凭据安全专项，不宣称依赖零漏洞。

### 14.3 仍未关闭的迁移阻断项

- 仓库当前有 5 份 SQL 增量迁移，但完整文件树中未发现 Alembic 配置、统一 migration runner、revision ledger 或 manifest；应用启动仍调用 `Base.metadata.create_all`。
- 当前 `_schema_metadata_drift` 仅核对 ORM 声明的表和列存在，不验证字段类型/长度/default/NULL、索引、唯一约束、CHECK、字符集/排序规则的完整一致性。
- 迁移执行顺序、revision/checksum、执行状态、并发协调和失败恢复仍没有统一的应用内机制；SQL 脚本依赖人工按发布文档执行。
- 不得仅凭本轮 23 字段结构检查就认定整个应用 schema 已完整验证；此校验只针对 `cap_reservations` 表。
- 旧 schema + 代表性历史数据、逻辑备份恢复、MySQL server crash、worker pause/resume、应用兼容回滚、schema/data diff 和大规模升级性能仍未完成。

### 14.4 发布决策

- Run #1403 验证了本轮 SQL 迁移及错误同名表拒绝测试，不代表完整迁移机制或生产升级已验收。
- PR #1 继续 Open / Draft；不合并 main、不部署、不访问生产环境。所有验证继续只使用 GitHub Actions 隔离 MySQL/Redis、合成数据及 Mock API；凭据安全专项继续按用户要求暂缓。

## 15. Cap Reservation 索引唯一性校验与 Run #1405（2026-11-12）

### 15.1 本轮补强

- 对 `cap_reservations` 迁移结构验收继续复核，发现只核对索引名称、列顺序和统计行数仍不足以确认唯一性语义。
- 新增约束：主键与 `uq_cap_reservation_key` 必须为唯一索引；其它业务索引必须为非唯一索引；所有索引必须为完整列索引（无 `SUB_PART` 前缀）及 BTREE；并要求索引总数与目标集合一致。
- 新增隔离 MySQL 测试：先执行正常迁移，再将 `uq_cap_reservation_key` 替换成同名同列普通索引；重跑迁移必须以 MySQL 1146 fail-closed，且断言错误索引仍为非唯一、未被迁移覆盖。

### 15.2 CI 结果

- 修复提交：SQL `718e23e58817ee42d72453b90b4216fc8dc7a87a`；回归测试 `a33937a9571f65d9a5f54e0745fbc334a3309392`。
- Run #1405（SHA `a33937a9571f65d9a5f54e0745fbc334a3309392`）全部成功：Backend **540 passed、1 skipped、1 warning**；Frontend Lint、Build、Playwright Mock API Browser E2E 全部成功。
- Run #1405：https://github.com/Helong0511/Platform/actions/runs/43178473822
- 1 skipped 与 1 warning 的性质与前述轮次相同；不得据此宣称依赖零告警或凭据安全专项已完成。

### 15.3 Drift 检查的实际覆盖边界

复核 `app/bootstrap/lifespan.py` 与 `tests/test_schema_metadata_drift.py` 后确认：

- `_schema_metadata_drift` 目前只检查 ORM 声明的表、列是否存在。
- 测试只覆盖缺失表、缺失列和完整 schema 三种情况。
- 当前检查没有比较字段类型/长度、NULL、server default、自动更新时间属性、索引列与唯一性、唯一约束、CHECK 表达式、字符集/排序规则。
- 启动时先执行 `Base.metadata.create_all`，再运行上述有限 Drift 检查；`create_all` 不是增量 ALTER 迁移机制，不能修复已存在表的列定义漂移。
- 因此启动检查目前只能发现部分缺失结构，不能作为完整 schema 兼容性证明。扩展前必须基于 MySQL 8.0 与 SQLite 测试 fixture 明确方言差异，并先以只读诊断模式报告，不应未经全模型验证就直接让启动流程因历史 schema 差异而拒绝服务。

### 15.4 仍未关闭的发布阻断项

- 未发现统一 Migration Runner、revision/checksum ledger 或迁移 manifest；现有 SQL 文件仍缺少应用统一执行/登记机制。
- `_schema_metadata_drift` 完整结构比较尚未实现。
- 旧 schema + 合成历史数据升级、逻辑备份恢复、worker pause/resume、应用兼容回滚、schema/data diff、MySQL server crash 与大规模数据升级性能尚未完成。
- PR #1 继续 Open / Draft；不合并 main、不部署、不访问生产环境；凭据安全专项继续暂缓。

## 16. Cap Reservation updated_at ORM/DDL 一致性（2026-11-12）

### 16.1 问题与修复

- 对比 `app/models/cap_reservation.py` 与 `sql/migrations/20261111_cap_reservation_ledger.sql` 时发现，ORM 的 `updated_at` 定义为 `server_default=CURRENT_TIMESTAMP` 加应用层 `onupdate=get_app_now_naive`；迁移 SQL 之前额外声明了数据库级 `ON UPDATE CURRENT_TIMESTAMP`。
- 两种建表路径因此具有不同的更新语义：ORM `create_all` 不会创建数据库自动更新属性，而手工 SQL 迁移会创建该属性。
- 已移除迁移 SQL 中额外的 `ON UPDATE CURRENT_TIMESTAMP`，保持两条建表路径语义一致；迁移结构校验新增 `information_schema.COLUMNS.EXTRA` 检查，拒绝出现 `ON UPDATE` 的漂移结构。
- 新增隔离 MySQL 回归测试：先创建正确表，再人为给 `updated_at` 增加数据库级 `ON UPDATE CURRENT_TIMESTAMP`，重跑迁移必须 fail-closed（1146），并确认错误结构未被自动覆盖。

### 16.2 CI 结果

- SQL 修复提交：`4bb1ff5418470c39cae3cdf6e81b8ca10e598eac`。
- 回归测试提交：`1b98f0f8f10ada7474bf4308aaf56fe382377331`。
- Run #1408 全部成功：Backend **542 passed、1 skipped、1 warning**；Frontend Lint、Build、Playwright Mock API Browser E2E 全部成功。
- Run #1408：https://github.com/Helong0511/Platform/actions/runs/43179489431
- 唯一 warning 是 Passlib 在 Python 3.11 引用 `crypt` 的弃用警告；CI 中 MySQL/Redis 容器自身也输出初始化/配置警告。它们不代表本轮测试失败，但依赖兼容性仍需后续单独评估。

### 16.3 尚未覆盖

- 本轮仅统一 Cap Reservation `updated_at` 的 ORM/SQL 建表语义；尚未证明全部 ORM 模型与全部增量迁移在所有字段、索引、CHECK、字符集/排序规则和默认值上完全一致。
- `_schema_metadata_drift` 仍只检查表/列是否存在；统一 Migration Runner、revision/checksum ledger、历史数据升级与恢复演练仍未完成。
