# Platform 上线与回滚操作手册（Cap Reservation 恢复改造）

> 状态：发布准备文档，尚未执行任何生产操作。  
> 适用范围：PR #1 的 Cap Reservation 持久化账本与恢复 Worker。  
> 生产隔离约束：代码审计、CI 和本手册编写期间没有连接生产服务器、生产 MySQL、生产 Redis、队列或第三方接口。

## 1. 发布前硬性条件

以下条件全部满足才允许把 Draft PR 转为 Ready：

- [ ] PR 最新 HEAD 的 Backend、Frontend lint/build、Playwright Mock API E2E 全绿。
- [ ] CI 隔离 MySQL 8.0.16+ migration 测试通过；CI 隔离 MySQL + Redis 跨存储恢复测试通过，并验证 CHECK 约束确实拒绝非法账本行。
- [ ] 生产 MySQL 版本满足 MySQL 8.0.16+（恢复任务依赖 `FOR UPDATE SKIP LOCKED`，账本 CHECK 约束也必须由数据库实际强制执行）。
- [ ] 已确认部署包包含 `sql/migrations/20261111_cap_reservation_ledger.sql`、`sql/platform.sql` 和恢复任务代码。
- [ ] 发布负责人已安排旧 Postback 请求排空窗口；不能在旧/新 worker 混跑期间启用新恢复任务。
- [ ] 已完成旧版本 Redis Cap 计数与 DB 快照基线核对；不允许直接把 Redis 计数盲目同步到 DB。
- [ ] MySQL 备份和 Redis RDB/AOF 备份已验证可恢复。
- [ ] 回滚负责人、维护窗口、告警接收人明确。

## 2. 旧版本切换风险

旧版本 Postback 使用随机 UUID reservation token，没有 `cap_reservations` 账本。新恢复 Worker 无法将旧随机 token 与正式转化事件可靠关联。

因此切换时必须：

1. 先停止向旧 API worker 分发新的 Postback 请求，并等待在途 Postback 全部结束。
2. 确认没有旧 worker 仍在处理 Cap 预留。
3. 对每个 Daily / Total Redis scope 核对 Redis counter 与 DB `offer_caps.current_daily_count/current_total_count`，并结合正式转化记录检查差异。
4. 若存在无法解释的差异，暂停发布并人工完成基线核对；不得把 `sync_all_active_caps()` 当作自动修复工具，因为它可能把旧孤儿计数固化进 DB。
5. 旧版本随机 token 的历史孤儿无法由新账本自动恢复；切换前必须完成差异处置并留存审计记录。

## 3. 建议发布顺序

1. 维护窗口开始，排空 Postback 流量并停止旧 API worker。
2. 完成并记录 Cap Redis/DB 基线核对。
3. 备份数据库；确认 Redis 持久化文件/快照可用。
4. 在目标 MySQL 数据库执行 `sql/migrations/20261111_cap_reservation_ledger.sql`。该 DDL 为新增表，仍须按发布审批执行；不要在应用启动时依赖 `create_all()` 替代迁移。
5. 使用只读核验确认 `cap_reservations` 的字段、唯一键、恢复索引和 `utf8mb4_unicode_ci`。
6. 发布同一 SHA 的完整应用代码到所有 API worker；确认没有旧版本 worker。
7. 启动/重启 API 服务：`Platform-backend.service`（其配置将 `ENABLE_SCHEDULER=false`）。
8. 启动/重启独立调度服务：`Platform-scheduler.service`（其配置为单 worker、`ENABLE_SCHEDULER=true`）。
9. 确认调度任务 `Cap Reservation 崩溃恢复` 已同步并按每分钟周期执行。
10. 先进行受控内部 Postback 冒烟，检查账本状态与 Redis counter/token，再恢复正常 Postback 流量。

## 4. 发布后观察

重点观察恢复任务结果中的：

- `pending_prepared`、`pending_reserved`：正常请求应快速进入终态；持续增长或最老年龄超过 600 秒需调查。
- `needs_reconciliation`：任何非零都必须人工核对，不能自动 DECR。
- `committed_token_cleanup_pending`：应在 Redis 恢复后持续下降。
- `failed`、`cleanup_pending`：应触发告警。
- Postback 重复事件、Cap 超限率、Redis key 缺失/损坏、DB commit 错误及调度任务连续失败。

恢复任务遵循 fail-closed：Redis 状态 UNKNOWN、token ABSENT 但 counter 仍存在/无法确认存在性、或 token PRESENT 但 counter 丢失时，保留证据并进入 NEEDS_RECONCILIATION，不进行猜测性扣减。只有 token ABSENT 且对应 counter key 明确不存在时，才可结束当前 reservation；后续 Redis counter 必须从已提交 DB Cap 快照重新建立，不能从 0 覆盖 DB 基线。

## 5. 回滚策略

若新版本出现异常：

1. 暂停 Postback 流量，避免回滚期间继续产生新账本。
2. 先停止 `Platform-scheduler.service`，避免新旧代码混合处理账本。
3. 保留 MySQL `cap_reservations` 表和 Redis token/counter；不要删除账本表、清空 Redis 或手工 DECR。
4. 按批准的回滚包回退 API 代码；回退后继续保留数据库备份和账本表供审计/后续恢复。
5. 如果新版本期间存在 PREPARED / RESERVED / NEEDS_RECONCILIATION 记录，不得直接恢复旧版本后放任不管；必须先完成这些记录的人工核对或重新部署兼容版本恢复。
6. 只有在没有活动账本、没有待清理 token、且完成审批后，才可另行制定 schema 清理方案；本次发布不提供自动 DROP TABLE 回滚。

## 6. 当前禁止事项

- 不连接生产环境进行审计或测试。
- 不在生产环境直接执行 CI 测试、故障注入或 Redis FLUSH。
- 不在未核对旧版本随机 token 的情况下直接启用恢复 Worker。
- 不因恢复任务告警而手工删除 token 或执行无 token 的 DECR。
- 不因 migration 是 `CREATE TABLE IF NOT EXISTS` 就跳过备份、审批和 MySQL 版本核验。

## 7. 本轮验证证据（2026-11-11 更新）

- 最新全量 CI：Run #808，SHA `41ad452653b1e1579f3721e3f84b0fcecb302a0b`。
- Run #808：Backend / Frontend lint/build / Playwright Mock API E2E 全部成功；Backend 为 300 passed、1 skipped、1 warning。
- Backend 使用隔离 MySQL 8.0 与 Redis 服务，覆盖 Reservation migration 的 CHECK 约束实际执行、ORM SQLite 约束、Postback reservation 生命周期、并发 claim、恢复 Worker 双 worker 和 token 丢失/计数 key 保留的对账保护。
- 历史 CI 失败修复记录：
  - Run #750：集成测试未隔离账本会话导致缺少表；后续通过测试隔离和显式 mock 修复。
  - Run #777：Redis counter missing 错误文本与测试断言不一致；已修复为明确兼容的 fail-closed 错误信息。
  - Run #806：MySQL CHECK 约束错误码 3819 被测试错误地期待为 IntegrityError；已改为 OperationalError 并断言错误码 3819，Run #807 全绿。
- Run #808 前端 npm audit 仍报告 2 个 production High advisories，均属于用户明确排除的凭据/重定向敏感头安全专项；本轮未改动该专项，详见第 8 节。
- 上述证据仅证明对应 SHA 在隔离 CI 环境通过，不代表已在生产环境部署或验证。后续任何代码提交仍须重新验收最新 SHA。


## 8. 明确保留的范围外风险

CI 的前端 `npm audit --omit=dev` 仍报告 2 个 High 项，均由直接依赖 axios 间接引入 follow-redirects，公告涉及跨域重定向时敏感凭据/请求头的剥离行为。该问题属于用户明确排除的“凭据安全”专项，本轮没有修改相关依赖或重定向逻辑。

因此：
- 不得将当前依赖审计描述为“零漏洞”。
- 该风险必须作为独立的凭据安全事项留档并由发布负责人单独接受/安排修复。
- 本轮其余非凭据安全问题仍按本手册继续验收。

## 9. 第三方上报事件幂等键与事务性 Outbox 发布/回滚

> 本节是发布评审清单，不代表已执行生产迁移。当前审计只允许隔离 CI 数据库和合成数据。

### 9.1 发布前检查

- [ ] 确认目标 MySQL 为 InnoDB，版本满足项目实际使用的 MySQL 8.0 功能要求；先在与目标版本一致的隔离实例完整演练。
- [ ] 对 `third_party_report_logs` 完成可恢复备份，并验证恢复到隔离实例成功；记录行数、主键范围、索引定义及备份校验值。
- [ ] 暂停第三方上报旧 worker 和会修改 `third_party_report_logs` 身份字段的管理操作；排空正在执行的上报请求。
- [ ] 运行事件幂等键预检查：确认 `source/adsid/event/conversion_id` 的历史数据可按应用的长度前缀算法生成键；检查重复键、空键和字段截断风险。
- [ ] 若重复键查询返回任何行，必须逐条核对业务事件并形成经批准的去重/合并方案；禁止直接删除历史记录或跳过唯一索引创建。
- [ ] 确认当前应用版本和目标版本的写入字段兼容，且管理端不会改写已进入 Outbox 的事件身份字段。

### 9.2 强制迁移顺序

1. 完成数据库备份、恢复验证、维护窗口审批及上报流量排空。
2. 执行 `sql/migrations/20261110_third_party_report_event_idempotency.sql`。
3. 检查 `missing_event_keys=0`，重复键查询无结果；确认 `unique_event_key` 已创建，且旧的 `unique_source_adsid` 已按迁移预期替换。
4. 执行 `sql/migrations/20261111_third_party_report_outbox.sql`。
5. 核验 Outbox 五个字段和 `idx_third_party_outbox_due`，与 ORM `ThirdPartyReportLog` 定义一致。
6. 执行 `sql/migrations/20261112_third_party_report_pii_retention.sql`，核对 `third_party_report_logs.pii_scrubbed_at` / `idx_third_party_pii_retention` 及 `postback_forward_logs.pii_scrubbed_at` / `idx_forward_log_pii_retention`；该迁移只新增元数据，不清理历史数据。
7. 发布同一 SHA 的兼容应用代码；先保持 Outbox worker 禁用，执行隔离/受控验证后再按发布审批启用 worker。
8. 确认新旧 API/worker 不混跑；观察 pending、failed、重试耗尽和租约恢复指标后再恢复正常流量。

`sql/platform.sql` 是完整建库基线，已经包含 `event_key`、Outbox 字段及相关索引；它不是在线增量迁移脚本。已有数据库必须按上面的增量迁移编号顺序执行，禁止对现有生产库直接运行会 DROP/重建表的完整基线脚本。

### 9.3 回滚原则与兼容边界

- MySQL DDL 可能隐式提交；三份迁移不能按一个事务整体回滚。**默认回滚只回应用代码，不删除新增列、索引或历史事件记录。**
- Outbox migration 新增列/索引可以保留；回退应用前必须停止新 Outbox worker，并确认已入队事件的处置方案（由兼容 worker 继续处理，或暂停并保留待恢复队列），不得静默丢弃。
- event-id migration 将 `event_key` 改为 NOT NULL 并替换旧唯一索引。旧版应用若不写 `event_key`，不能直接回滚到该旧二进制版本；必须使用仍能生成/写入 `event_key` 的兼容回滚版本。若不存在兼容版本，回滚被阻断，需先制定并在隔离库演练 schema 与数据回退方案。
- 不得自动 DROP `event_key`、Outbox 字段或索引；不得未经审批恢复旧 `unique_source_adsid`，因为新数据可能已允许同一 source/adsid 下存在不同 event。
- 任何 schema 回退都必须先停止写入、备份当前库、在隔离副本验证数据映射和索引重建，并由数据库负责人审批；本手册不提供可直接用于生产的 DROP/DELETE 回滚 SQL。

### 10. 最新验收记录（2026-11-11，PR #1 持续审计）

- 最新已通过 CI：Run #927，SHA `7b5326152aecf4852985b49f03b44928273d2ab5`。
- Backend：327 passed、1 skipped、1 warning；Python 编译通过。
- Frontend：依赖审计步骤、Lint、Build、Playwright Mock API E2E 均通过。
- 本轮新增隔离 MySQL 故障注入：在真实临时 MySQL 事务 COMMIT 成功后，模拟客户端收到连接中断异常；验证应用重新查询到正式转化后保留 Redis Cap 预留、不执行回滚，并尝试把账本标记为 COMMITTED。
- 本轮新增 Cap `NEEDS_RECONCILIATION` 退避重试逻辑：超过 5 分钟后重新核对正式转化与 Redis token/counter；未能确认时仍保持待核对，不做猜测性 DECR。
- 本轮进一步新增真实 MySQL + Redis 集成测试：先把账本置为 `NEEDS_RECONCILIATION`，将 `updated_at` 回拨到退避窗口之前，再运行真实恢复 Worker；验证账本转为 `ROLLED_BACK`、Redis counter 回到 0、token 被删除。
- 上述测试只使用 CI 临时 MySQL 8.0.46、临时 Redis、独立随机数据库和合成数据；不连接生产服务。
- Run #923 曾因新增测试的调用记录断言错误而失败（324 passed、1 failed）；已修正测试断言，Run #924 全绿。随后 Run #925 增加真实 MySQL COMMIT 响应丢失测试并全绿。
- 仍未完成：完整旧 schema 到新 schema 的真实升级/中断重跑/兼容回滚演练；Outbox 配置生命周期与发送租约压力测试；PII 数据保留、删除、访问审计政策核定；全项目业务模块最终回归。
- PII 生命周期修复：新增第三方上报与下游转发日志的 `pii_scrubbed_at` 标记、扫描索引、分批清除服务和每日调度任务；仅清理终态历史载荷，保留 `event_key`/最小审计骨架；待重试 Outbox 不会被清理。默认 `THIRD_PARTY_REPORT_PII_RETENTION_DAYS=0`（关闭），须经业务/合规负责人确定期限后显式设置；未设置前不得声称已自动执行个人信息到期清理。
- PR #1 继续保持 Draft；最新 CI 通过不代表迁移已获生产审批，也不构成部署许可。

## 9.5 第三方上报 PII 保留与清理策略

- 环境变量：`THIRD_PARTY_REPORT_PII_RETENTION_DAYS`，必须为非负整数；默认 `0`，即关闭自动清理（fail-safe）。
- 只有业务/合规负责人书面确认保留期限、目的与适用司法辖区后，发布负责人才能设置正整数天数；本仓库不自行推断法定期限。
- 每日 03:15 的任务按批次最多 200 条处理；使用 InnoDB 行锁和 `SKIP LOCKED` 避免与其它清理 Worker 重复处理。
- 仅清理超过期限的终态 `success` 记录、旧非 Outbox 终态记录，以及明确耗尽自动重试且租约失效的 Outbox `failed` 记录（即使 `next_retry_time` 留有历史时间戳）；pending、具有下次重试时间、活动租约或重试未耗尽的事件不会被清理。
- 清除字段：`adsid`（置空）、`conversion_id`、`email`、`ip`、`phone`、`ua`、`report_params`、`response_body`、第三方 `log_id`、短链/斗篷配置引用及 `click_time`；失败详情替换为固定说明。
- 下游转发日志 `postback_forward_logs` 同样纳入该保留期限：清除历史展开后的 `downstream_url`、`request_data`、`request_params`、`response_body` 和 `error_message`，保留转化/产品/渠道关联、HTTP 状态、成功状态及时间等最小审计字段；通过 `pii_scrubbed_at` 阻止对已清理日志执行手动补发。
- 新写入的下游转发日志只保存未展开的 URL 配置模板、请求字段数量摘要，不保存实际请求参数值或下游响应正文；真正用于失败重试的 `postback_forward_queue` 仍需保留必要请求载荷直到成功或达到重试终态，必须纳入后续数据保留决策。
- 保留字段：事件幂等键 `event_key`（哈希形式的最小去重标识）、来源/事件类型、金额与货币、状态及创建/完成时间，用于防止重复入账和保留最小审计证据。`event_key` 仍属于需要纳入备份和后续删除评估的假名化标识。
- 清理后通过 `pii_scrubbed_at` 阻止 worker 发送、管理员重新排队或编辑已清理载荷。此标记不是删除整条日志；数据库备份、日志副本和第三方接收方数据仍须另行纳入保留/删除政策。
- 上线前必须完成隔离 MySQL 迁移演练、清理 Worker 回归测试，并由负责人批准具体保留天数；未批准时保持 0，不得开启自动清理。

## 9.4 当前验收缺口

- [ ] 两份迁移按真实顺序在隔离 MySQL 上完成从旧 schema/代表性历史数据到新 schema 的升级演练。
- [ ] 覆盖重复 event_key、历史 NULL conversion_id、超长字段、唯一键冲突和中途失败后的恢复/重跑行为。
- [ ] 演练代码回滚兼容性，证明旧版本不会因 NOT NULL `event_key` 写入失败；否则必须提供兼容回滚构建。
- [ ] 演练 worker 停止、pending Outbox 保留、恢复后继续发送及稳定 event_id 不变。
- [ ] 保存迁移前后 schema diff、行数对账、测试日志和审批记录。

在以上项目完成前，第三方 Outbox 迁移/回滚仍是合并及发布阻断项。

