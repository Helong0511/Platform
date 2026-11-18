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
- 当前 manifest 共 14 条 revision；执行前必须先运行 `validate`，并核对 `status` 与目标环境基线版本。
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

## 10. 审计日志防清空与留存边界（2026-11-14）

审计日志属于安全追踪证据，不应提供普通业务管理员可直接清空的入口。原管理端“清除全部日志”会对 user_audit_logs 执行 MySQL TRUNCATE 和 ALTER TABLE AUTO_INCREMENT = 1，具有不可恢复的数据破坏能力，并且 DDL 隐式提交，无法与“清空动作自身的审计记录”放入同一个普通事务。

本轮已移除该破坏性功能的完整调用链：

- 删除后端 DELETE /api/v1/audit-logs/clear-all 路由。
- 删除服务层执行 TRUNCATE / 重置自增 ID 的方法。
- 删除管理端“清除全部日志”按钮、二次确认处理和对应 composable 状态。
- 删除前端 API 客户端中的清空接口封装。
- 审计查询、详情和统计功能保留，不影响正常日志检索。

运营要求：

- 不允许通过管理端清空、重置或覆盖审计历史。
- 如因法规或隐私政策需要到期处置，应设计独立的、受控的保留期归档/脱敏/销毁流程；必须先归档、记录审批和执行证据，并保证操作记录写入独立的防篡改审计介质，不能复用普通管理员的清表功能。
- 审计日志的查询、导出权限与业务操作权限应分离；后续还需验证导出水印/访问审计、最小权限、留存期限、备份恢复及不可篡改存储。
- 当前移除的是在线清空入口，不代表已经完成法规留存策略或 WORM/外部不可变存储建设。


## 11. 前端错误上报的敏感信息边界（2026-11-14）

- 前端错误消息与堆栈通过 JSON 请求体提交，不再拼接到 URL 查询参数；服务端 Pydantic schema 对字段长度实施入口校验。
- 客户端错误日志写入前，仅保留发生页面的 path，不记录 URL host、query 或 fragment，避免 OAuth code、广告参数或临时凭据进入审计详情。
- 错误消息、堆栈和错误类型对常见 Bearer、token/password/secret/api-key 赋值及邮箱做脱敏；字段仍有长度上限。
- 错误上报失败日志只记录异常类型，不输出异常原文，防止数据库/网络异常把敏感值再次写入应用日志。
- 以上属于针对前端错误上报路径的定向脱敏，不等于所有通用审计写入调用的递归脱敏已经完成。`log_user_action` 的通用 `details`、`request_params` 仍需继续审计调用点与字段语义，不能仅依赖本节保证所有审计内容无敏感信息。
- 未认证错误上报端点仍需单独完成速率限制、体积限制、来源滥用防护与保留策略验收；不得因已加入 CSRF 说明就视为匿名端点具备完整滥用防护。


## 12. 通用审计写入的递归凭据脱敏（2026-11-14）

- `log_user_action` 是审计日志统一写入入口；现在 `request_params` 与 `details` 在 JSON 序列化前统一递归处理，不再只过滤顶层字段。
- 对常见凭据字段名进行大小写/分隔符归一化后匹配，包括 password/passwd、token/access_token/refresh_token、secret/client_secret、api_key、authorization、cookie/set-cookie、private_key、session_id、CSRF/XSRF 与通用 key；命中字段值替换为 `[REDACTED]`。
- 对普通字符串值中的 Bearer 凭据和常见 `token=...`、`password:...` 等赋值形式做二次过滤；`error_message` 同样经过此处理。
- 递归深度上限为 12，日期继续转为 ISO 字符串；列表/元组/集合统一序列化为数组。
- 该规则是常见凭据的防御性过滤，不是任意秘密识别器；业务调用方仍不得把完整请求体、原始凭据或不必要的个人信息传入审计接口。新凭据命名必须同步扩充规则与回归测试。
- 未登录 `/api/v1/audit-logs/client-error` 已在 `RateLimitMiddleware` 中单独使用 `client-error` bucket，生产/默认请求上限再收紧为最多 10 次/分钟（以客户端 IP 为计数维度）；Redis 不可用时回退进程内计数，跨 worker 一致性会下降，需监控 Redis 降级状态。
- 审计日志查看权限、外部不可变归档、数据库账号禁止 UPDATE/DELETE、保留期和备份恢复演练仍是独立待办；本次递归脱敏不代表这些控制已完成。
## 13. 历史审计详情读取时的二次脱敏（2026-11-14）

- 通用审计写入脱敏不能追溯清理上线前已经落库的记录；详情 API 必须在响应边界再次解析并脱敏 `request_params`、`details` 与 `error_message`。
- 详情响应 Schema 显式包含 `details`，由同一脱敏函数处理后再序列化，避免前端读取历史明文凭据。
- 敏感字段匹配保留 `accessToken`、`client-secret`、`api_key`、Authorization、Cookie 等明确凭据名称；不把通用业务字段 `key` 一概判为凭据，避免损坏关联键、业务标识。
- 未知对象不再展开 `__dict__`，避免对象内部属性被意外写入审计记录；不可序列化对象以类型标记替代。
- 该修复只覆盖审计详情 API 的历史记录读取路径；数据库中旧值仍然存在，不代表已完成静态数据清理。需要清理数据库时，应另行设计备份、审计与可回滚的数据迁移。
- 审计详情目前仍由 `require_admin` 角色保护；系统当前角色模型没有经过确认的细粒度审计查看权限。上线前仍需评估管理员是否应默认看到完整请求上下文，以及是否需要拆分基础详情与敏感字段授权。
- 匿名客户端错误上报虽有独立 10 次/分钟 IP 限流且继续要求 CSRF，但应用层尚未建立对 chunked/缺失 Content-Length 请求体的统一硬上限。生产反向代理也必须配置请求体大小限制；在代理配置和端到端验证完成前，不应把 Pydantic 字段长度约束视为完整的请求体 DoS 防护。


## 14. 全量 Migration DDL 风险盘点（2026-11-16）

本节根据当前分支 `fix/non-credential-hardening-2026-11` 的 `app/db/migrations/manifest.py` 和其中登记的 13 个 SQL 文件逐项静态检查。它是 DDL 风险分级，不代表已在目标 MySQL 版本、目标表规模或生产数据上执行。

### 14.1 逐项盘点

| Revision | 主要结构变更 | 静态风险与上线前要求 |
|---|---|---|
| `20261110_short_link_click_sync_idempotency` | 新建同步批次表 | 新表创建；需验证目标库中同名表的完整列、索引、字符集与引擎，不能只依赖 `IF NOT EXISTS`。 |
| `20261110_third_party_report_event_idempotency` | 在既有上报日志表增加 event_key（指定 AFTER）、回填、改 NOT NULL、创建唯一索引、删除旧索引 | **高风险**：包含历史数据回填和多次 ALTER；唯一索引可能扫描/构建大表索引；回填可能产生大量 redo/undo 与复制流量；删旧索引前必须确认新唯一约束与旧查询路径。 |
| `20261111_cap_reservation_ledger` | 新建 CAP 预留账本表 | 新表创建；核验完整物理结构、唯一约束、索引和字符集。 |
| `20261111_third_party_report_outbox` | 在上报日志表连续增加多列（多处指定 AFTER）并增加 due 索引 | **高风险**：多个 ALTER 分开执行；MySQL 8.0.16 下指定列位置的 ADD COLUMN 不能假定 INSTANT；索引构建需要评估表扫描、I/O、复制延迟和 metadata lock。 |
| `20261112_third_party_report_pii_retention` | 在两张既有日志表增加清理时间列并增加索引 | **高风险**：两张日志表分别执行 ALTER/索引创建；必须分别测量，不能以一张表的演练结果代表另一张。 |
| `20261113_cap_reservation_key_hex` | 增加 CHECK 约束 | 需核验存量数据全部满足约束、目标 MySQL 版本对 CHECK 的执行语义，以及约束添加时的扫描/锁影响。 |
| `20261113_cap_reservation_schema_guard` | 结构核验/保护逻辑 | 主要是前置结构验证；需确认遇到不匹配结构时 fail closed，不能误把“表存在”视为 schema 正确。 |
| `20261113_third_party_report_identity_scope` | 增加 platform、identity_scope、destination_pixel_id 列并增加复合索引 | **高风险**：既有大表多列 ALTER 与复合索引构建；历史记录归属保持 unresolved 是正确的保守策略，但仍需评估默认值写入、行版本和索引构建开销。 |
| `20261113_third_party_report_identity_scope_constraints` | 增加 CHECK 约束 | 需在真实结构副本验证历史 NULL / legacy_unresolved 行与约束兼容，并检查约束确实被目标 MySQL 版本执行。 |
| `20261113_third_party_report_identity_scope_locks` | 新建身份锁表 | 新表创建；检查字符集/排序规则、主键、唯一键及表结构漂移保护。 |
| `20261114_third_party_report_manual_retry_budget` | 在上报日志表增加 manual_retry_count | **中高风险**：既有表 ADD COLUMN；必须明确算法和写入可用性要求，并验证旧记录默认值与 ORM 默认值一致。 |
| `20261114_third_party_report_platform_binary_collation` | 修改 platform 列字符集/排序规则 | **高风险**：既有列定义变更且可能影响关联索引；必须在同版本、相近数据量副本测量实际算法、索引重建、磁盘峰值、metadata lock 和复制延迟。 |

### 14.2 MySQL 算法不能靠“默认在线”推断

MySQL 官方手册明确说明：省略 `ALGORITHM` 时，服务器优先使用支持的 INSTANT，否则使用 INPLACE；若 INPLACE 不支持，还可能使用 COPY。COPY 会复制整表且不允许并发 DML。指定算法则要求服务器使用该算法，不支持时直接失败。见：

- ALTER TABLE 算法、COPY 行为和 LOCK 语义：https://dev.mysql.com/doc/refman/8.0/en/alter-table.html
- InnoDB Online DDL 支持矩阵：https://dev.mysql.com/doc/refman/8.0/en/innodb-online-ddl-operations.html
- Online DDL 性能与并发：https://dev.mysql.com/doc/refman/8.0/en/innodb-online-ddl-performance.html

MySQL 8.0.29 之前，INSTANT ADD COLUMN 只能追加到表尾；8.0.29 起才支持放在任意位置。因此本项目当前最低版本 8.0.16，不能将带 `AFTER` 的 ADD COLUMN 当作 INSTANT。官方说明：https://dev.mysql.com/doc/relnotes/mysql/8.0/en/news-8-0-29.html

### 14.3 执行门禁

在满足以下条件之前，不得把上述迁移标记为生产可执行：

1. 为每个 revision 记录目标 MySQL 精确小版本、存储引擎、表行数/数据量、索引规模、表空间类型和关键配置。
2. 在同版本、同结构、相近数据量的隔离副本逐条执行；记录实际算法（不得只记录 SQL 返回成功）、执行耗时、受影响行数、metadata lock 等待、并发读写影响、redo/undo、磁盘峰值和复制延迟。
3. 对大表增加索引、列定义修改和历史回填分别制定时间窗口、限速、暂停业务写入策略及失败处置步骤。
4. 对无法证明低影响的 ALTER，优先选择明确算法并让不支持的操作失败；若最低版本不支持所需算法，则应先调整最低版本策略或采用经验证的在线 schema change 流程，不能静默退化为 COPY。
5. 对 MySQL DDL 隐式提交的迁移，逐条设计“执行到中途断连”的人工恢复手册；Runner 留下 running/failed 时，禁止直接删除 ledger 记录后盲目重跑。
6. 所有 SQL migration 内容一旦可能被任何环境应用即视为不可变；后续调整使用新的 forward-only revision，并同步更新 manifest/checksum 与恢复文档。

### 14.4 当前结论

- 原有 12 条 manifest revision 已完成静态 DDL 分类；2026-11-16 两条新增迁移另见后续专项记录。
- 尚无本轮证据证明这些 DDL 已在生产规模数据副本完成算法、锁、耗时和磁盘峰值演练。
- CI 临时 MySQL 的 migration 成功，只能证明该测试数据与该 CI MySQL 配置下可执行，不能替代生产规模演练。
- 本节不修改任何已登记 SQL migration，也不改变其 SHA-256；未对生产或外部数据库执行任何操作。
- **上线门禁保持阻断**，直到每条高风险 DDL 有可复核的副本演练记录及失败恢复方案。


## 15. Runtime 权限边界与旧数据库引导入口复核（2026-11-16）

### 15.1 已确认的安全边界

- `app/bootstrap/lifespan.py` 启动先执行只读 `verify_schema_revision` 与 ORM schema drift 检查，之后才调用 `init_db()`；当前 lifespan 中未见调用 `create_database()` 或 `Base.metadata.create_all()`。
- `app/core/database.py` 的旧兼容入口 `create_tables()` 已明确抛出异常，提示使用独立 Migration Runner；该入口本身不会执行 DDL。
- `app/db/migrations/runner.py` 的 `apply_migrations()` 强制要求独立的 `MIGRATION_DATABASE_URL` 与应用 DSN，检查数据库名、MySQL endpoint 和用户名不同；并在单一物理连接持有 GET_LOCK 直到 RELEASE_LOCK。
- `tests/test_mysql_runtime_privileges.py` 在 GitHub Actions loopback 临时 MySQL 中创建专用 runtime 用户，仅授予目标 schema 的 SELECT/INSERT/UPDATE/DELETE；验证管理员 bootstrap、两个 Worker 并发首次初始化、重复初始化，以及 CREATE/ALTER/CREATE INDEX/DROP 被拒绝。

### 15.2 尚未封闭的旧入口

`app/db/database.py` 仍保留 `create_database()`。它直接使用 `settings.SQLALCHEMY_DATABASE_URI` 建立无默认库连接并执行 `CREATE DATABASE IF NOT EXISTS`。这意味着如果任何脚本、CLI、测试或未来启动流程误调用该 helper，应用运行账号就必须拥有数据库级 CREATE 权限，违背“运行账号 DML-only”的部署原则。

当前确认 lifespan 没有调用该 helper，但本轮无法据此证明全仓库不存在其它调用点。**在全仓库调用点核查完成之前，不得给应用运行账号授予 CREATE DATABASE，也不得把此 helper 视为受支持的生产 provisioning 入口。**

建议后续将数据库创建责任明确交给独立 provisioning 身份/运维流程；在调用点核查后，再决定删除该 helper 或将其改为显式要求独立 provisioning DSN。不得简单把应用 DSN 继续用于 provisioning。

### 15.3 权限测试覆盖边界

当前真实 MySQL 权限测试有意验证的是预置 `users` 表上的管理员初始化路径和 DDL 拒绝边界。它没有覆盖所有 ORM 模型表，也没有执行完整 lifespan、Scheduler、Telegram、CAP recovery、点击队列、Outbox worker、第三方上报扫描器等路径。

因此测试通过只能证明当前 fixture 和所测 SQL 路径可用，不能证明部署账号拥有完整且最小化的生产权限。下一步应从所有运行时 SQL / ORM 操作构建权限矩阵，在完整 schema 上以 runtime 用户逐条执行关键路径，并验证：
- 业务表仅有必要的 SELECT/INSERT/UPDATE/DELETE；
- 不具备 CREATE/ALTER/DROP/INDEX/REFERENCES/TRIGGER/EVENT/CREATE ROUTINE 等 schema/对象管理权限；
- Scheduler、Telegram、Outbox、CAP 恢复与所有 API 启动路径在相同权限下工作；
- 迁移账号仅在受控 migration job 中使用，不进入 API、Scheduler、Telegram 或常驻 Worker 环境变量。

### 15.4 Migration Runner 的身份检查不是 GRANT 验证

Runner 当前检查迁移账号与应用账号用户名不同、目标数据库和 endpoint 相同。这是身份分离的必要条件，但**不是数据库授权证明**：代码未对实际 `SHOW GRANTS` 或等价授权状态建立完整断言。迁移账号实际具备哪些 DDL 权限、runtime 账号是否存在全局/角色继承权限，仍须由部署前权限审计与真实 MySQL 测试确认。

生产部署验收必须保存两个账号的授权清单（脱敏），核验无全局通配授权、无意外角色继承，并验证 runtime 用户无法执行任何 schema DDL。迁移账号的 DDL 权限应限制在目标 schema 和迁移窗口内；不应因 Runner 使用独立用户名就直接判定权限隔离合格。

### 15.5 当前状态

- Lifespan 启动顺序和只读 schema gate：代码已确认。
- 旧 `create_tables()`：已 fail closed。
- 旧 `create_database()`：仍存在；全仓调用点审计未完成。
- Runtime 权限测试：真实 MySQL fixture 覆盖有限路径；完整业务路径权限矩阵未完成。
- Migration / runtime 账号真实 GRANT 审计：未完成。
- 本节仅记录代码审查事实和上线门禁；没有连接生产数据库，也没有执行任何生产授权变更。

## 16. 运行入口追踪与最新 CI 复核（2026-11-16）

### 16.1 本轮核验范围

本轮在 PR 分支当前 HEAD `1198ac6adf0ad24b2a9dca55debb9e4e7b9ba61f` 复核以下文件：

- `app/main.py`：FastAPI 组装根，生产入口为 `app.main:app`，绑定 `app.bootstrap.lifespan.lifespan`；文件中未发现调用 `create_database()`、`create_tables()` 或 `Base.metadata.create_all()`。
- `app/bootstrap/lifespan.py`：启动先执行只读 schema revision / ORM drift gate，再执行 `init_db()`；当前启动流程不调用数据库创建 helper。
- `gunicorn.conf.py` 与 `app/core/uvicorn_worker.py`：检查了 API / Scheduler Gunicorn 进程入口与 Worker 装配，未发现调用数据库创建 helper。
- `app/core/database.py`：`create_tables()` 仍为 fail-closed 兼容入口。
- `app/db/database.py`：`create_database()` 仍保留并直接使用应用 DSN 执行数据库级 CREATE。

以上是对实际生产装配入口的核验，不等于已逐个读取 548 个 Python 文件并完成全仓调用图。当前仍不能作出“全仓无调用点”的结论；尤其部署脚本、外部运维脚本、测试工具和动态导入路径还需要继续排查。

### 16.2 Runtime MySQL 权限测试的具体边界

复核 `tests/test_mysql_runtime_privileges.py` 后，确认当前测试：

- 在隔离 MySQL 中创建临时 schema 和专用用户；
- 仅对目标 schema 授予 SELECT、INSERT、UPDATE、DELETE；
- 通过预置的 `users` 表验证管理员初始化、两个 Worker 首次启动竞争和重复初始化；
- 以 runtime 用户执行 CREATE TABLE、ALTER TABLE、CREATE INDEX、DROP TABLE，确认被拒绝。

当前测试**没有**直接以 runtime 用户尝试 `CREATE DATABASE`，也没有覆盖所有业务表和所有常驻任务路径；没有将 `SHOW GRANTS` / 角色继承状态作为一份完整权限快照进行断言。因此它不能代替部署前全局权限与角色审计。

后续测试扩展应至少补齐：

1. runtime 用户尝试 `CREATE DATABASE`，确认失败且目标 schema 外也无建库能力；
2. 读取并规范化 runtime 用户实际授权，检查全局权限、角色授予及默认角色，不只依赖 fixture 中预期的 GRANT 语句；
3. 在完整 migration schema 上，以 runtime 用户执行关键 API、Scheduler、Telegram、CAP recovery、点击队列和 Outbox 任务的代表性读写路径；
4. 逐项确认不需要的 CREATE、ALTER、DROP、INDEX、REFERENCES、TRIGGER、EVENT、CREATE ROUTINE 等权限均不可用。

### 16.3 最新 CI 结果

通过分支 Actions runs 列表复核，PR HEAD `1198ac6adf0ad24b2a9dca55debb9e4e7b9ba61f` 对应 Run **43787078201**，状态为 completed / success：

- Backend job：成功；安装依赖、Python compile、unit tests 均成功；
- Frontend job：成功；npm ci、dependency advisory report、lint、build、Playwright mock API E2E 均成功；
- 本次运行没有发现仍在执行的 job。

运行链接：https://github.com/Helong0511/Platform/actions/runs/43787078201

该 CI 结果只证明当前自动化任务在隔离环境中通过，不代表生产账号 GRANT、生产级 Migration DDL 演练、完整业务权限矩阵或所有上线门禁已通过。

### 16.4 当前处置结论

- 生产 API / Scheduler 装配入口未发现调用旧数据库创建 helper；但全仓、部署脚本和动态调用路径仍未全部排除。
- 暂不删除或改写 `create_database()`，避免在调用图未完整前破坏可能存在的受控 provisioning 流程；该 helper 不得作为应用运行账号可用的生产入口。
- 不得给 runtime 用户授予 CREATE DATABASE；数据库创建应由独立 provisioning 身份或运维流程完成。
- 下一步优先完成全仓调用点追踪、runtime 的 CREATE DATABASE 拒绝测试、SHOW GRANTS / role 权限快照，以及完整业务路径权限矩阵。
- PR #1 继续保持 Open / Draft；本轮不合并、不部署，也未连接生产数据库或执行生产授权变更。



## 17. Runtime DDL 权限测试与最新分支复核（2026-11-16）

### 17.1 最新提交 CI

- PR 分支 HEAD：`38b36c7a4ade231aa1e14b9b6cefcd1257e7ffbe`。
- CI Run #1798（Run ID `43788892106`）：completed / success。
- Backend 与 Frontend Job 均成功；前端 npm ci、依赖 Advisory 报告、Lint、Build、Playwright Mock API E2E 成功；后端 Python compile 与 unit tests 成功。
- 运行记录：https://github.com/Helong0511/Platform/actions/runs/43788892106
- 此 CI 仅证明隔离测试环境中的任务通过，不代表生产账号权限、生产数据规模 DDL 或完整业务路径已经验收。

### 17.2 Runtime 权限测试最新代码覆盖

复核当前 HEAD 的 `tests/test_mysql_runtime_privileges.py`，确认测试现在已包含以下实际断言：

- Runtime 用户仅获得目标 schema 的 SELECT、INSERT、UPDATE、DELETE。
- 使用不带 FOR 的 `SHOW GRANTS` 读取授权快照，检查只有预期的 USAGE 与目标 schema DML 授权；同时检查没有 GRANT OPTION。
- 使用 `CURRENT_ROLE()` 检查当前会话激活角色；该断言本身不能代替 `SHOW GRANTS` 对授予角色/mandatory roles 的检查。
- Runtime 用户执行 `CREATE DATABASE` 必须失败，错误码限定为 MySQL 1044 或 1142。
- Runtime 用户执行 CREATE TABLE、ALTER TABLE、CREATE INDEX、DROP TABLE 必须失败。
- 测试 finally 清理数据库级建库探针，避免权限回归时遗留测试数据库。

以上比早期仅验证 schema 内 DDL 拒绝的测试更完整；但它仍是一个临时用户、一个 schema 和有限 SQL 操作的权限边界测试，不是全量生产授权审计。

### 17.3 旧数据库创建 helper 的调用点状态

本轮重新检查了当前分支以下实际文件：

- `app/main.py`：生产 ASGI 组装入口使用 `app.bootstrap.lifespan.lifespan`。
- `app/bootstrap/lifespan.py`：先执行只读 schema revision / ORM drift gate，再调用管理员初始化；当前代码未见调用 `create_database()`、`create_tables()` 或 `Base.metadata.create_all()`。
- `gunicorn.conf.py`：检查 API / Scheduler Gunicorn 配置入口。
- `app/core/database.py`：`create_tables()` 为 fail-closed 兼容入口。
- `app/db/database.py`：旧 `create_database()` 名称暂时保留兼容，但已改为无条件抛出明确 `RuntimeError`；不再读取应用 DSN、不再创建 SQLAlchemy Engine、不再执行任何 SQL。旧 URL 解析 helper 与对应过时测试已删除。

本轮未在上述已检查的生产装配文件中发现旧 helper 的调用，但当前分支有 436 个 `app/**/*.py` 文件；本轮没有逐一读取全部 Python 文件，也没有穷尽测试、运维脚本、动态导入和外部部署脚本。因此**仍不能声称全仓库不存在调用点**。GitHub 代码搜索接口检索的是默认分支，不能将其无结果当作当前 PR 分支全量搜索证据。

处置与后续核查：

1. 不得向 API / Scheduler / 常驻 Worker 的 runtime 账号授予 CREATE DATABASE。
2. 旧 `create_database()` 入口现已 fail-closed；任何遗留调用会立即失败，不可能通过应用 DSN 建库。
3. 数据库创建必须由独立 provisioning 身份/运维流程完成；不得将应用 DSN 复用为 provisioning DSN。
4. 仍需继续完成全仓调用点核查，以定位并移除/改写遗留调用，避免启动或任务因旧调用而失败。
5. 后续调用图应覆盖 app、tests、scripts、部署配置、CI workflow、文档命令和动态导入路径，并记录检索范围与结果。

### 17.4 本轮结论

- 最新 HEAD 的 CI Run #1798 全部成功。
- Runtime 测试已经显式覆盖 CREATE DATABASE 拒绝与授权快照；早期文档中“尚未直接测试 CREATE DATABASE”的描述应以本节当前代码状态为准。
- 生产 ASGI / Lifespan / Gunicorn 装配入口已复核，未见旧数据库创建 helper 被调用。
- 全仓调用点扫描仍未完成；不得把局部入口检查升级为“全仓无调用点”结论。
- 未连接生产数据库、未执行生产授权变更、未运行生产 DDL；PR #1 继续保持 Open / Draft，不合并 main、不部署。


## 18. 旧数据库创建入口 fail-closed 修复（2026-11-16）

### 18.1 修复内容

- `app/db/database.py` 保留旧 `create_database()` 函数名，避免未识别的外部调用在导入阶段直接失败。
- 函数现在无条件抛出明确的 `RuntimeError`，不读取 `SQLALCHEMY_DATABASE_URI`，不创建 SQLAlchemy Engine，不执行 SQL。
- 删除仅服务于旧建库流程的 URL 解析 helper，避免保留无生产用途的引导逻辑。
- 将 `tests/test_database_bootstrap_url.py` 改为 fail-closed 回归测试，断言旧入口必须拒绝执行。
- 此防线是纵深防御：即使未来误将旧 helper 接回 Lifespan、Scheduler 或 Worker，也不能使用应用数据库身份执行 CREATE DATABASE。

### 18.2 当前验证边界

- 本次已检查 ASGI / Lifespan、Gunicorn 配置、Scheduler 初始化、CAP Recovery / 点击批处理任务、Telegram 同步数据库模块、Migration CLI 与 Runner 的关键入口。
- 在已读取的生产入口文件中未发现 `create_database()` 的直接调用；但尚未逐一读取全部 436 个 app Python 文件、全部 111 个 tests Python 文件及部署/外部运维脚本，因此全仓调用点清单仍未完成。
- 新增的 fail-closed 单测尚待本次提交对应 CI 运行确认；不得提前声称测试已通过。
- 生产数据库授权和实际 provisioning 流程未被本次代码变更触及。

### 18.3 后续动作

1. 等待本次提交 CI，检查新增测试和完整 Backend / Frontend 检查。
2. 继续以当前 PR HEAD 为基准，扫描剩余 app / tests 文件及部署配置中的旧 helper 导入/调用。
3. 对 Scheduler、Outbox、CAP Recovery、Telegram 和外部回传路径建立操作级 SQL 权限矩阵；区分只读、DML、锁/事务操作与 DDL。
4. PR #1 继续保持 Open / Draft，不合并 main、不部署。


## 2026-11-16 新增迁移：第三方上报随机租约令牌

- Revision：`20261116_third_party_report_random_lease_token`
- 新增列：`third_party_report_logs.lease_token CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL`，追加到表尾。
- 新增 CHECK：非空令牌必须为 32 位小写十六进制，且必须同时有 `report_start_time`。
- 旧行不回填令牌；旧行的 `lease_token` 保持 NULL，由下一次原子认领生成新的随机令牌。
- 该迁移依赖 2026-11-14 手动重试预算与平台二进制排序规则迁移；既有迁移 SQL 与 checksum 不得修改。
- 表尾新增列可在 MySQL 8.0.29+ 争取 INSTANT ADD COLUMN；CHECK 约束验证、8.0.16–8.0.28 DDL 算法仍须在目标版本副本实测。
- 部署时先停止并排空旧版 API、Scheduler、Outbox Worker，再执行 migration runner，最后启动全部新版进程；禁止新旧 Worker 混跑。
- 截至本次审计，尚未在生产等价数据规模上执行迁移；必须记录 DDL 耗时、metadata lock、并发 DML、磁盘峰值与恢复演练结果。


## 2026-11-16 新增迁移：转发队列独立租约 fencing

- Revision：`20261116_postback_forward_queue_lease_fencing`。该迁移只作用于 `postback_forward_queue`，与第三方上报日志的随机租约迁移相互独立。
- 在 `postback_forward_queue` 增加可空 `lease_token CHAR(32) CHARACTER SET ascii COLLATE ascii_bin` 与 `lease_expires_at DATETIME(6)`；CHECK 要求两列同时为空或同时有效。旧记录不回填，首次领取时生成 128-bit 随机令牌。
- `next_retry_time` 只承担业务重试调度，不再被改写为租约到期时间。Worker 领取条件、续租、成功删除、失败退避和超限删除均使用独立 token 与数据库时钟进行条件更新。
- HTTP 客户端设置 60 秒总请求 deadline，队列租约为 300 秒，给连接/处理和最终状态提交留出余量；仍不能排除进程长时间暂停、网络层已发出请求后租约过期等情形。
- fencing 只能防止旧 Worker 覆盖新 Worker 的队列状态，不能撤销已经发出的外部 HTTP 副作用；Exactly-once 仍需下游幂等键或接收端去重。
- 上线顺序：停止并排空旧版 Scheduler/Worker，执行迁移，再启动新版进程；禁止新旧 Worker 混跑。迁移 DDL 算法、metadata lock、数据规模影响仍须在目标 MySQL 版本副本演练。



## 19. 2026-11-18 Migration 身份边界复核与文档校正

### 19.1 最新隔离 CI 证据

- PR HEAD：`b6f51ce63595250b120a09bc0a21d39c460e2f84`。
- Run ID：`44233598397`，Backend / Frontend 均 completed / success。
- Backend：**730 passed、1 skipped、1 warning**；其中真实隔离 MySQL 的 Migration Runner 测试、Runtime 权限测试均实际执行并通过。
- Migration Runner 集成测试覆盖：顺序执行与重复 apply 幂等、GET_LOCK 互斥、部分 DDL 失败后拒绝自动重跑、错误同名 ledger 拒绝执行、迁移/应用 DSN 用户名分离检查、目标数据库与 endpoint 检查、只读 status、身份作用域 CHECK 约束真实执行。
- Runtime 权限测试当前代码已经覆盖：SHOW GRANTS 快照、CURRENT_ROLE()、CREATE DATABASE 拒绝，以及 CREATE TABLE / ALTER / CREATE INDEX / DROP 拒绝。早期第 16.2 节关于“尚未直接测试 CREATE DATABASE”的描述已过时，应以第 17 节和当前测试源码为准。
- CI 运行链接：https://github.com/Helong0511/Platform/actions/runs/44233598397
- 本次仅复核隔离 CI 与 GitHub 源码；未连接生产数据库、未执行生产授权或 DDL。

### 19.2 新发现：DSN 用户名不同不等于 MySQL 有效身份不同

当前 `_ensure_distinct_database_account()` 比较 migration DSN 与 application DSN 的用户名、数据库名和 endpoint；它没有在两条实际连接上读取并比较 `CURRENT_USER()`，也没有核验代理认证后的有效授权身份。

MySQL 官方手册说明，Proxy User 认证可以让外部连接用户以另一个被代理用户的权限执行操作；`USER()` 与 `CURRENT_USER()` 可能不同，后者反映服务器用于权限检查的账号：
- https://dev.mysql.com/doc/refman/8.0/en/proxy-users.html
- https://dev.mysql.com/doc/refman/8.0/en/information-functions.html

因此，两个 DSN 即使配置了不同的用户名，也不能单凭字符串比较证明最终生效的 MySQL 权限主体不同。若部署启用了 Proxy User / 外部认证映射，可能出现两个连接身份映射到同一有效授权账号的情况。

**风险等级：P2（部署身份隔离强化项；在使用代理认证的环境中升级为部署阻断项）。**

建议后续改进：
1. Runner 分别建立 migration 与 application DSN 的实际连接，读取 `USER()`、`CURRENT_USER()`、`CURRENT_ROLE()` 和 `@@proxy_user`，拒绝两个连接的有效 `CURRENT_USER()` 相同或代理身份不符合部署策略。
2. 对两个账号分别留存脱敏后的 `SHOW GRANTS` / 角色快照；明确区分账号身份校验与权限最小化校验。
3. 增加隔离 MySQL 代理映射测试（若 CI MySQL 未启用所需认证插件，则将其列为专项测试环境，而不能假称现有 CI 已覆盖）。
4. Migration 账号仍须由部署流程证明仅具备目标 schema 所需 DDL/DML 权限；Runtime 账号须在完整 schema 上通过关键业务读写路径并拒绝全部不需要的 DDL 权限。

当前不应将此发现描述为已被利用或已造成越权；它是 Runner 现有 DSN 身份检查的覆盖边界。第 15.4 节关于 Runner 不验证实际 GRANT 的说明继续有效。

### 19.3 Runner / Manifest 静态复核结论

- Manifest 当前登记 **14 条**迁移；校验 revision 顺序、文件路径、文件集合、SHA-256、依赖前置关系，并拒绝未登记 SQL 文件。
- Ledger 校验拒绝重复 revision、重复/不连续 execution_order、未知 revision、非 applied 状态、checksum 漂移及非 manifest 前缀历史。
- Runner 使用单一物理连接持有 GET_LOCK 至 RELEASE_LOCK；每条 migration 先持久化 running，再逐条执行 SQL，失败时记录 failed 或保留 running 墓碑，禁止对部分 DDL 自动猜测重试。
- MySQL 真实集成测试证明了上述若干核心路径在 CI 临时 MySQL 上工作；不代表已完成目标环境的完整 migration / backup / restore / rollback 演练。
- Runner 对 ledger CHECK 表达式目前采用关键片段核验，而不是对规范化后的完整表达式做严格等价比较。Python ledger 校验仍对 revision、checksum、status 和 execution_order 执行独立检查；但物理 CHECK 表达式完整性仍可进一步加强，建议后续增加“同名但逻辑被放宽”的错误 ledger 结构测试。

### 19.4 仍然阻断生产迁移的事项

1. 逐条高风险 DDL 在目标 MySQL 精确版本、接近生产数据量的隔离副本中实测算法、metadata lock、耗时、redo/undo、磁盘峰值和复制延迟。
2. 完整备份恢复、逐 DDL 中断重跑、应用兼容回滚、schema/data diff 演练。
3. Runtime 账号在完整 schema 上的 API、Scheduler、Telegram、CAP、点击队列、Outbox 等关键路径权限矩阵。
4. Migration / Runtime 实际账号的脱敏 GRANT、默认角色、mandatory roles、代理映射审计。
5. 全仓库调用点与外部部署脚本核查；旧 `create_database()` 已 fail-closed，但尚不能声称所有外部/动态调用点均已排除。

PR #1 继续 Open / Draft；本轮没有合并 main、没有部署，也没有连接生产资源。
