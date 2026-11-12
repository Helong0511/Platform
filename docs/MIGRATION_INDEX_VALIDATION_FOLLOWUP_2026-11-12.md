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

- [ ] 对三份增量迁移的每一个 DDL 边界逐点注入失败/进程退出，验证中断后的 schema 状态、错误诊断与安全重跑。
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
