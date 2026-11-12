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
