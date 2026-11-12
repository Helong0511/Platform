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
- Run #1006 对应代码头 `5891ae5c6a24`：Backend 347 passed、1 skipped，Frontend build 与 Mock API Browser E2E 全部通过。PR #1 继续保持 Draft；CI 通过不代表迁移已获生产审批，也不构成部署许可。

## 9.5 第三方上报 PII 保留与清理策略

- 环境变量：`THIRD_PARTY_REPORT_PII_RETENTION_DAYS`，必须为非负整数；默认 `0`，即关闭自动清理（fail-safe）。
- 只有业务/合规负责人书面确认保留期限、目的与适用司法辖区后，发布负责人才能设置正整数天数；本仓库不自行推断法定期限。
- 每日 03:15 的任务对每类日志每次最多处理 200 条（两类日志合计最多 400 条）；使用 InnoDB 行锁和 `SKIP LOCKED` 避免与其它清理 Worker 重复处理。
- 仅清理超过期限的终态 `success` 记录、旧非 Outbox 终态记录，以及明确耗尽自动重试且租约失效的 Outbox `failed` 记录（即使 `next_retry_time` 留有历史时间戳）；pending、具有下次重试时间、活动租约或重试未耗尽的事件不会被清理。
- 清除字段：`adsid`（置空）、`conversion_id`、`email`、`ip`、`phone`、`ua`、`report_params`、`response_body`、第三方 `log_id`、短链/斗篷配置引用及 `click_time`；失败详情替换为固定说明。
- 下游转发日志 `postback_forward_logs` 同样纳入该保留期限：仅清理已完成、超过期限且不存在对应待重试队列项的日志；清除历史展开后的 `downstream_url`、`request_data`、`request_params`、`response_body` 和 `error_message`，保留转化/产品/渠道关联、HTTP 状态、成功状态及时间等最小审计字段；通过 `pii_scrubbed_at` 阻止对已清理日志执行手动补发。
- 新写入的下游转发日志只保存未展开的 URL 配置模板、请求字段数量摘要，不保存实际请求参数值或下游响应正文；历史下游转发日志的管理员 API 也会脱敏 URL、请求载荷和错误详情。真正用于失败重试的 `postback_forward_queue` 仍需保留必要请求载荷直到成功或达到重试终态，必须纳入后续数据保留决策。
- 保留字段：事件幂等键 `event_key`（哈希形式的最小去重标识）、来源/事件类型、金额与货币、状态及创建/完成时间，用于防止重复入账和保留最小审计证据。`event_key` 仍属于需要纳入备份和后续删除评估的假名化标识。
- 清理后通过 `pii_scrubbed_at` 阻止 worker 发送、管理员重新排队或编辑已清理载荷。此标记不是删除整条日志；数据库备份、日志副本和第三方接收方数据仍须另行纳入保留/删除政策。
- **尚未纳入自动清理的业务数据**：`postback_conversions` 中的 `ip`、`click_id`、设备广告 ID 和 `raw_data`；待处理 `postback_forward_queue` 的重试请求载荷；`postback_notifications.notification_message`（可能包含客户姓名、转化标识）。这些字段可能承担归因、对账、重试或通知历史用途，必须由业务/合规负责人另行确定期限、用途和访问权限；本轮不得宣称全系统 PII 删除已完成。
- 上线前必须完成隔离 MySQL 迁移演练、清理 Worker 回归测试，并由负责人批准具体保留天数；未批准时保持 0，不得开启自动清理。

## 9.4 当前验收缺口

- [ ] 三份增量迁移按真实顺序在隔离 MySQL 上完成从旧 schema/代表性历史数据到新 schema 的升级演练。
- [ ] 覆盖重复 event_key、历史 NULL conversion_id、超长字段、唯一键冲突和中途失败后的恢复/重跑行为。
- [ ] 演练代码回滚兼容性，证明旧版本不会因 NOT NULL `event_key` 写入失败；否则必须提供兼容回滚构建。
- [ ] 演练 worker 停止、pending Outbox 保留、恢复后继续发送及稳定 event_id 不变。
- [ ] 保存迁移前后 schema diff、行数对账、测试日志和审批记录。

在以上项目完成前，第三方 Outbox 迁移/回滚仍是合并及发布阻断项。



## 11. 最新验收记录（2026-11-11，Run #1010）

- 验证提交：`3c51b8443c0893ad5de67cf5d14c807e8bfa1f85`。
- GitHub Actions Run #1010：Backend、Frontend Lint、Frontend Build、Playwright Mock API Browser E2E 全部成功。
- Backend：348 passed、1 skipped、1 warning；Python 编译通过。唯一 skip 是本地核对脚本未检出，CI 不依赖该脚本；warning 为 Python 3.11 环境中 passlib 使用的 `crypt` 弃用提示。
- Frontend：`npm ci`、依赖 Advisory 报告、Lint、Build、Playwright Chromium 安装、隔离 Vite 服务启动及浏览器 E2E 全部成功。E2E 覆盖登录校验、认证失败/成功、管理员导航、Outbox 重试资格/详情、退出登录、移动端抽屉及客户端 RBAC。
- 本轮修复 Outbox 批量 Worker 的异常处理缺陷：异常分支此前引用未绑定的 `exc`，单条任务异常可能在日志阶段再次触发 `NameError`。现已绑定异常并将失败计数纳入批次统计，新增 `tests/test_third_party_report_outbox_worker_errors.py` 回归测试。
- 同时将 Outbox 凭据解析失败日志改为仅记录异常类型和内部日志 ID，不记录原始异常文本，避免第三方响应内容或 PII 进入日志。
- Run #1010 的所有验证仅使用 GitHub Actions 临时 MySQL/Redis、合成数据和 Mock API；未连接生产服务器、生产数据库、生产缓存、生产队列或真实第三方接口。
- Run #1010 仅证明该 SHA 的 CI 验证通过，不替代真实数据库网络断连代理故障注入、完整 migration/rollback 演练、业务/隐私保留政策审批及全项目剩余模块复核。
- PR #1 继续保持 Draft，不合并、不部署。后续任何应用代码变更仍须对最新 SHA 重新运行完整 CI。


## 12. MySQL COMMIT ACK 丢失故障注入复核（2026-11-11，Run #1017）

- 最新已通过应用代码 SHA：`2dfe450319e93a07031d667a88cc576e3629031c`。
- GitHub Actions Run #1017：Backend、Frontend Lint、Build、Playwright Mock API Browser E2E 全部成功。
- Backend：**349 passed、1 skipped、1 warning**；Python compile 通过。skip 是可选的本机核对脚本未随仓库提交；warning 是 passlib 对 Python 3.11 `crypt` 模块的弃用提示。
- 本轮对 Run #1015 的 TCP 故障注入进一步做了测试本身的正确性审查：旧代理在发出 COMMIT 后丢弃“下一段响应数据”，无法严格证明被丢弃的就是 COMMIT 成功确认。
- 修订后，代理按 MySQL packet framing（3 字节 payload length + 1 字节 sequence + payload）解析服务端响应，仅在观察到独立 `COMMIT` 命令后丢弃对应 MySQL OK packet（payload 首字节 `0x00`），并断开客户端连接；其它响应包继续转发。
- 测试随后通过独立直连临时 MySQL 的连接核验该 conversion 行确实已持久化，同时断言应用抛出连接异常、没有回滚 Redis Cap reservation、没有错误地提前 finalize reservation ledger。
- 该测试使用 GitHub Actions 临时 MySQL 8.0 与随机隔离数据库、合成 conversion 数据；Redis 使用同一 CI job 的临时服务。未连接生产 MySQL、Redis、服务器或第三方接口。
- 相关提交：`42f2a37`（只丢弃 COMMIT OK packet）、`2dfe450`（修正 MySQL OK opcode 字节字面量）。
- Run #1017：[查看 CI](https://github.com/Helong0511/Platform/actions/runs/42991799970)。
- Run #1016 因紧随其后的修正提交触发同一 PR concurrency group 而被取消；不作为验收证据。Run #1017 是最终修正 SHA 的完整通过结果。
- 本测试证明指定的 MySQL COMMIT ACK 丢失路径在隔离环境可重现且当前恢复逻辑不会错误回滚 Cap reservation；仍不能替代真实多节点长时间网络抖动、Redis failover/数据淘汰、数据库进程重启、跨区域时钟偏差与生产级压力测试。
- 合并阻断项仍包括：完整旧 schema + 历史数据迁移/中断重跑/兼容回滚演练；Outbox 配置生命周期与高并发多 Worker 压力验证；所有未纳入自动清理的数据类别的 PII 保留/访问/删除审批；其它业务模块的全量回归。PR 继续 Draft，不合并、不部署。


## 13. 增量迁移中断续跑与重复执行验收（2026-11-11，Run #1022）

- 验证提交：`5f3fc53237c1f548116e04f046c89babbc80400e`。
- GitHub Actions Run #1022：Backend、Frontend Lint、Build、Playwright Mock API Browser E2E 全部成功。
- Backend：**349 passed、1 skipped、1 warning**；隔离 MySQL migration tests 实际执行通过。
- 发现并修复此前三份增量迁移的恢复性缺口：若在部分 DDL 已执行后中断，原始 `ADD COLUMN` / `ADD INDEX` 语句直接重跑会因重复字段/索引失败。
- 现在以下迁移逐项检查 `information_schema.COLUMNS` / `information_schema.STATISTICS`，只创建缺失结构；数据回填仅处理 `event_key IS NULL`，NOT NULL 收敛和索引创建可重复执行：
  - `20261110_third_party_report_event_idempotency.sql`
  - `20261111_third_party_report_outbox.sql`
  - `20261112_third_party_report_pii_retention.sql`
- `tests/test_mysql_migrations.py` 新增真实 MySQL 场景：模拟事件幂等迁移已添加 event_key 但尚未回填时中断；模拟 Outbox 已创建首字段时中断；模拟 PII 迁移已创建第一张表标记列时中断。三种场景均续跑完成，并对完整迁移重复执行，确认历史事件键、PII 原始历史内容、默认 outbox 状态及索引仍正确。
- 同一测试还覆盖旧版日志表、中文/特殊字符 event_key 回填、事件级唯一键、Outbox 历史默认值、PII 迁移不删除历史数据，以及 Cap reservation ledger 的 MySQL CHECK / UNIQUE / INDEX 约束。
- Run #1022：[查看 CI](https://github.com/Helong0511/Platform/actions/runs/42992422404)。
- 该结果证明当前三份迁移在测试覆盖的 DDL 中断点可续跑，并能重复执行；**不等于**完整发布演练已结束。仍需在隔离副本完成从生产代表性旧 schema/数据出发的全流程升级、备份恢复、每个 DDL 边界故障注入、worker 停止/恢复、应用兼容回滚和 schema/data diff 审核。
- 不得在生产环境尝试本次测试；生产迁移仍须独立备份、审批和维护窗口。


## 14. 第三方日志 PII 生命周期与 API 脱敏补充（2026-11-11，Run #1043 / #1045）

- Run #1043 验证 SHA：`660acaa2d6eb71e9f9c4afbc11a36978c6cdc1d2`；Backend **354 passed、1 skipped、1 warning**，Frontend Lint/Build/Playwright E2E 全部通过。
- 管理端第三方上报日志列表和详情原先会返回完整 `adsid`。该字段可能承载 fbclid/click_id 等可关联用户的在线标识。现改为只显示首尾片段；短标识直接隐藏，查询过滤仍可使用管理员输入的原值。
- 第三方日志 API 的列表、统计、详情、更新、重排队异常响应原先把 `str(e)` 放入响应 detail，可能回显 SQL 参数、请求值或 PII。现全部改为固定通用错误文案；服务端日志只记录异常类型。
- 新增回归测试覆盖 adsid 脱敏、列表/详情均应用脱敏，以及 API 不回显原始异常文本。
- Run #1043：[查看 CI](https://github.com/Helong0511/Platform/actions/runs/42994645439)。

## 15. PII 清理终态识别、调度批次与 Outbox 耗尽状态（2026-11-11，Run #1045）

- 最新已验证应用代码 SHA：`367abbc1b16f53b04d9d5f8ffed8c75e1bca7ad0`。
- GitHub Actions Run #1045：Backend、Frontend Lint、Build、Playwright Mock API Browser E2E 全部成功；Backend Python compile 与 unit test job 均通过。
- PII 清理终态条件新增：失败 Outbox 若没有短链/斗篷有效配置引用且 `next_retry_time IS NULL`，属于不可人工重排的终态，可按获批保留期限清理；避免无配置引用的失败事件永久保留 PII。
- 每日 PII 调度不再在综合清理（已同时处理第三方日志与下游转发日志）后重复执行第二次 forward sweep，保持每类每次最多 200 条的批次上限。独立 forward 清理函数仍保留给受控单独调用。
- PII 保留期限为 0 时，综合清理函数返回两类日志各自的零计数；调度任务据此正常记录“关闭/跳过”，不会因缺少字典键而失败。默认仍为 0，不会自动删除数据。
- Outbox 达到自动重试上限后若 worker 崩溃留下 `pending` + 过期租约，扫描任务会先将其收敛为 `failed`、清空下次重试时间并记录完成时间，避免永久隐藏在 pending 状态。
- 耗尽状态收敛和统计增加 `next_retry_time` 条件，利用现有 `idx_third_party_outbox_due (outbox_enqueued, status, next_retry_time, report_start_time, id)` 限定扫描范围，避免每分钟对历史日志做无界全表扫描。
- 已修正 scrubbed Outbox 记录的 worker 查询过滤：现在可以读取到清理标记并返回明确的 `pii_payload_scrubbed` 拒绝原因，而不是因 SQL 过滤提前返回 `outbox_not_found`。
- Run #1045：[查看 CI](https://github.com/Helong0511/Platform/actions/runs/42994911629)。
- PII 自动清理仍未启用；必须由业务/合规负责人批准期限、目的、访问权限及适用司法辖区后，才允许设置非零天数。


## 16. Gunicorn 多 Worker Pixel 凭证缓存一致性（2026-11-11）

- Run #1063（SHA `5903b39a16bdfad25b510e115e152be6d8328cfe`）的 Backend、Frontend Lint、Build、Playwright Mock API Browser E2E 全部成功；该 SHA 不含本节后续修复。
- 复核发现 `CloakPixelMappingService` 使用进程内全局字典缓存 Pixel ID / CAPI Token，TTL 为 3600 秒。Gunicorn 多 Worker 之间不共享该字典；短链更新/删除或斗篷配置变更时，当前进程的同步失效函数无法通知其它 Worker。其它 Worker 因而可能在 TTL 内继续使用旧凭证、旧启停状态或旧配置。
- 为先消除跨 Worker 继续使用旧凭证的正确性风险，本轮采取保守的临时措施：`get_pixel_config_by_dp_param` 每次都以数据库为权威来源，绕过本地凭证缓存；兼容保留 `use_cache` 参数和缓存失效 API，避免调用方接口破坏。数据库查询失败时返回无可用配置，不返回旧缓存。
- 增加 `test_multiple_worker_instances_never_serve_stale_pixel_credentials`：模拟两个独立 Worker 服务实例；Worker A 读取旧配置后，数据库发生 Token/Pixel 轮换，随后两个实例再次查询都必须返回新值，且不能从各自本地字典命中旧配置。
- 修复提交：`e9d5fb4`（绕过本地凭证缓存）、`6c4b9e9`（每次权威查询时清除当前进程遗留条目）、`fd78633`（多 Worker 回归测试）。
- **性能代价**：每次解析 Pixel 配置都会执行数据库查询；需通过 CI 基准或隔离压测评估 QPS、数据库连接池占用和查询延迟。正确性优先于未经跨 Worker 证明的本地缓存性能。
- 后续优化目标：引入 Redis 共享缓存与版本化失效协议（按 short_code / dp 维度），所有配置写入路径必须在数据库事务提交后发布失效版本；Redis 不可用或版本读取失败时必须绕过缓存并查询数据库，绝不回退到旧本地凭证。需覆盖多进程、多实例、Redis failover、网络分区、写提交与失效通知之间的竞态后，才能重新启用共享缓存。
- 还需逐一审计 `cloak_configs` 的创建、更新、删除、启停、改名及桥页上传/删除路径，确认每条写路径均纳入同一失效协议。
- 本轮仅使用隔离 CI 数据库/Redis 与合成凭证；未连接生产服务器、数据库、Redis 或真实 Meta API。当前修复等待最新 SHA 的完整 CI 结果，不得以 Run #1063 作为新 SHA 的验证证据。
- PR #1 保持 Draft，不合并、不部署。


### 16.1 多 Worker 缓存一致性临时修复验收（Run #1068）

- 最新应用/测试提交：`419414a65266f8e9e57ea66851e2929c6f4c1148`。
- GitHub Actions Run #1068：Backend、Frontend Lint、Frontend Build、Playwright Mock API Browser E2E 全部成功。
- Backend：**366 passed、1 skipped、1 warning**；Python compile 成功。唯一 skip 是仓库默认 gitignore 下未提交的本机核对脚本，CI 不依赖该脚本；warning 是 passlib 在 Python 3.11 使用 `crypt` 的弃用提示。
- 新增双 Worker 服务实例回归测试：Worker A 读取旧 Pixel/Token 后，数据库发生轮换，Worker B 和 Worker A 后续读取都必须取得新配置，证明当前路径不再命中进程内旧缓存。
- 本次测试通过不代表共享缓存已实现；当前采用数据库权威直读，性能影响仍需独立压测。Redis 共享缓存版本化失效协议尚未开发，不得提前启用本地缓存。
- Run #1068：[查看 CI](https://github.com/Helong0511/Platform/actions/runs/42997889155)。
- Run #1067 因后续提交触发 PR concurrency 而取消；不作为通过证据。
- 仍须评估数据库查询额外负载，并继续审计 cloak_configs 的所有变更入口；PR 继续 Draft，不合并、不部署。


## 17. 桥页文件系统边界与静态资源安全（2026-11-11，Run #1085）

- 最新应用/测试代码 SHA：`98565600ca11ca98756d47c1f918ce09947a49ba`。
- GitHub Actions Run #1085：Backend、Frontend Lint、Frontend Build、Playwright Mock API Browser E2E 全部成功。
- Backend：**392 passed、1 skipped、1 warning**；Python compile 成功。Skip 为本机核对脚本未提交（CI 不依赖）；warning 为 passlib 在 Python 3.11 使用 `crypt` 的弃用提示。
- 对 `/change` 桥页读取路径进行纵深检查：仅依赖 Pydantic 校验不足以保护历史数据库脏数据及内部调用。现由文件系统边界再次校验斗篷名和单层 `.html` 文件名；路径穿越、绝对路径、嵌套路径被拒绝。历史非法名称在可用性检查中按不可用处理。
- 桥页读取通过 `lstat` 检查普通文件，不跟随符号链接；上传目标拒绝符号链接和特殊文件。桥页上传采用同目录临时文件、flush/fsync、`os.replace` 原子替换，避免读取到半写入 HTML；替换失败保留旧桥页。
- 桥页模板缓存签名使用 `mtime_ns + size + inode`，覆盖原子替换后文件系统时间戳精度不足的情况；每个 Worker 都重新检查文件元数据。
- `/bridge/{filename}` 静态资源路由新增独立解析器：限制单层文件名和已声明 MIME 扩展名白名单，仅返回普通文件，拒绝路径穿越、未知扩展名、符号链接及特殊文件。当前仓库桥页资源引用 `/bridge/109.png`，在白名单内。
- 新增测试覆盖原子写入/替换失败保留旧文件/缓存签名刷新/只读目标/路径穿越/历史非法名称/符号链接/静态资源扩展名白名单。
- Run #1084（SHA `de9d5e58497e4567b179a6b7e03fac62ed8f5567`）曾因 4 个错误提示断言失败（388 passed、4 failed、1 skipped）；已修正文件名校验错误归一化。该失败 run 不计入验收。Run #1085：[查看 CI](https://github.com/Helong0511/Platform/actions/runs/42999653442)。
- 仍需在部署环境隔离副本验证目录属主/权限、原子替换和文件系统语义；CI 不等于生产文件系统演练。没有连接生产服务器或真实第三方接口。
- PR #1 保持 Draft，不合并、不部署。


## 18. Outbox 尝试预算持久化与 Daily Reservation 孤儿 token 恢复（2026-11-11，Run #1095 / #1097）

### Outbox 发送预算与 PII 清理竞态

- Run #1089（SHA `e09a7ce36eede66cb8d870bdb14d7718aefacbdb`）新增 PII 清理与 Outbox 发送之间的竞态保护：发送租约条件 UPDATE 同时要求 `pii_scrubbed_at IS NULL`，并增加“Worker 已读取载荷、清理随后提交、最终认领失败”的回归测试。Backend / Frontend / Playwright 全部通过。
- 后续复核发现固定每轮 3 次哈希请求 + 1 次非哈希兜底可能在累计次数接近 `max_attempts` 时超出预算。现在按数据库剩余预算计算哈希尝试次数和兜底是否可执行；认领 SQL 也要求 `attempt_count < max_attempts`，耗尽事件不会再占用 300 秒租约。
- `update_report_log` 现在返回持久化成功/失败状态。哈希请求或非哈希兜底请求发送前，必须先成功提交本次 `attempt_count` 与请求载荷；若数据库未确认持久化，则 fail-closed 暂停外部请求，避免 DB 故障时持续发送而突破自动重试预算。
- 新增预算边界测试（新事件、剩余 2 次、剩余 1 次、预算耗尽、不使用哈希）及“尝试次数持久化失败不得调用第三方”的回归测试。
- Run #1093：SHA `e3142cca605e525e67418ecbe4b3752f4cbdd77f`，Backend **394 passed、1 skipped、1 warning**，Frontend Lint/Build/Playwright 全部通过。
- Run #1097：SHA `4a4b7613cc9fa78729e13bc3342bd3c90cef1e70`，Backend **396 passed、1 skipped、1 warning**，Frontend Lint/Build/Playwright 全部通过。Run #1097：[查看 CI](https://github.com/Helong0511/Platform/actions/runs/43002383440)。

### Cap Daily 计数器与 Reservation token 生命周期

- Daily counter 设置 48 小时 TTL；Reservation token 不设置固定 TTL，必须等账本终态后清理。
- 发现恢复任务只在 token 状态 `UNKNOWN` 时处理“Daily 业务日已过且 counter key 已自然过期”的孤儿 token；token 状态实际为 `PRESENT` 时，旧逻辑仍尝试对已不存在的 counter 执行原子回滚，随后进入 `NEEDS_RECONCILIATION`，无法自动收敛。
- 现已补充 `PRESENT` 分支：确认业务日期至少已过 2 天且 Redis counter key 明确不存在时，只删除孤儿 token，不执行 `DECR`，再将账本结束为 `ROLLED_BACK`。若 counter 仍存在或无法确认，继续保留证据并进入对账流程。
- 新增 token `PRESENT`、Daily counter 缺失的独立回归测试；保留既有 `UNKNOWN` / `ABSENT` 分支的 fail-closed 保护。
- Run #1095：SHA `69518a653720f05a13a8930c7f1dbcd0d2d5936a`，Backend **395 passed、1 skipped、1 warning**，Frontend Lint/Build/Playwright 全部通过。Run #1095：[查看 CI](https://github.com/Helong0511/Platform/actions/runs/43002032772)。

### 本节结论与剩余限制

- 上述验证仅使用 GitHub Actions 临时 MySQL / Redis、合成数据及 Mock API；没有连接生产服务器、生产数据库、生产 Redis、生产队列或真实第三方接口。
- 第三方上报采用 at-least-once + 稳定 event_id 幂等保护，不承诺 exactly-once。COMMIT ACK 丢失、远端已接收但本地 ACK 未确认时，仍可能重试同一 event_id。
- 手工管理员重试会重置该事件当前自动重试计数；属于显式人工操作，仍需结合审计日志、权限与业务流程核查。
- Daily 业务日过期后，只有 counter key 明确不存在才清理孤儿 token；Redis 查询 UNKNOWN、counter 仍存在或状态不一致时绝不猜测扣减。
- PR 仍保持 Draft。完整 migration/backup/rollback、Outbox 配置生命周期压力组合、PII 政策审批及其它业务模块全量复核仍是合并/上线阻断项。


## 19. HTTPS 代理头信任与 Cloudflare 客户端 IP 防伪造（2026-11-11，Run #1109）

### 发现的问题

- `HTTPSRedirectMiddleware` 原先只要收到 `X-Forwarded-Proto: https` 或 `CF-Connecting-IP`，就可能放行 HTTP 请求；这两个请求头都不能在未验证代理来源时直接信任。
- `get_client_ip` 虽然只在直连对端位于 `TRUSTED_PROXY_IPS` 时读取代理头，但 Nginx API 代理原先将客户端原始 `CF-Connecting-IP` 直接透传给应用。直接访问源站的客户端可伪造该头，影响 IP 归因、审计和按 IP 限流。
- 项目已有 `TRUST_PROXY_HEADERS` / `TRUSTED_PROXIES` 配置；Gunicorn 绑定 `127.0.0.1:8960`，Nginx 通过本机回环地址代理。Nginx 的 `cloudflare_real_ip.conf` 通过 Cloudflare 官方网段限制 realip 头的来源信任。

### 修复

- HTTPS 中间件现在只有在 `TRUST_PROXY_HEADERS=true` 且 `request.client.host` 精确匹配配置的可信代理 IP 时，才接受 `X-Forwarded-Proto`。
- `CF-Connecting-IP` 只用于客户端 IP 解析，不再作为 HTTPS/TLS 证明；可信代理发送该头也不能单独绕过 HTTPS 检查。
- Nginx API 代理改为 `proxy_set_header CF-Connecting-IP $remote_addr;`，不再透传 `$http_cf_connecting_ip`。Nginx realip 模块仅在原始连接来源命中 Cloudflare 官方 CIDR 时才会把 `$remote_addr` 还原为访客 IP；直接访问源站时保留真实对端 IP，再覆盖写入应用请求头。
- `get_client_ip` 文档明确要求 Nginx 覆盖该请求头，禁止透传客户端原始值。
- 新增测试覆盖：外部客户端伪造 `X-Forwarded-Proto` / `CF-Connecting-IP`、可信本机代理转发 HTTPS、仅有 CF 客户端 IP 头不能绕过 HTTPS、关闭代理头信任、外部 peer 伪造 IP 头、Nginx 配置必须覆盖原始 CF 头。

### CI 证据

- Run #1104（SHA `b91f05af32ce6d7478071ebdc115c9c75fa03fca`）Backend 测试阶段出现 **5 failed、397 passed、1 skipped、1 warning**。失败根因是新增测试直接 monkeypatch Pydantic Settings 的只读 `is_production` property 和不存在的实例字段，测试初始化阶段抛出 AttributeError / ValueError，未进入被测逻辑。保留该失败记录。
- 随后将测试改为替换被测模块的 settings 对象，不修改 Pydantic Settings 实例本身。
- Run #1109（SHA `751e05027b8d050b3d2882dd9da0edf3ad104dd1`）：Backend **402 passed、1 skipped、1 warning**；Frontend Lint、Build、Playwright Mock API E2E 全部通过。Run #1109：[查看 CI](https://github.com/Helong0511/Platform/actions/runs/43003839190)。

### 代理部署限制

- 生产 Nginx 配置必须继续包含 `cloudflare_real_ip.conf`，并按 Cloudflare 官方发布的 IP ranges 维护 `set_real_ip_from`；不能仅因为请求带有 `CF-Connecting-IP` 就信任来源。
- `TRUSTED_PROXIES` 必须只配置实际反向代理的直连地址（当前仓库示例为 loopback）；禁止配置任意客户端网段或宽泛网段。
- 生产源站网络层应限制回源来源，只允许 Cloudflare 和明确批准的可信代理/运维来源。CI 无法证明生产防火墙实际生效，部署前仍须由运维在变更评审中核实；本轮没有连接或修改生产环境。
- Cloudflare 官方说明：源站应允许 Cloudflare IP ranges，并阻止非 Cloudflare 来源直接访问；官方地址范围文档：https://developers.cloudflare.com/fundamentals/concepts/cloudflare-ip-addresses/ 及 https://www.cloudflare.com/ips/。

### 结论

- 代码层的代理头信任边界及 Nginx 头覆盖配置已修复并通过隔离 CI。
- 生产防火墙/安全组是否限制源站访问无法从仓库代码证明，仍需部署前人工核实。
- PR 保持 Draft；不合并、不部署。其余 migration/backup/rollback、Outbox/Cap 故障组合、PII 政策和其它业务模块审计仍未关闭。


## 20. Cap Reservation 批量恢复租约续期与 MySQL rowcount 边界（2026-11-11，Run #1113 / #1114）

### 发现的问题

- 恢复 Worker 每批最多认领 100 条记录，所有行最初使用同一个 300 秒租约截止时间，然后按行串行执行 MySQL 查询和 Redis 检查/回滚。
- Redis 故障时单次 socket timeout 可达 5 秒；后半批记录可能在轮到处理前租约已过期，被其他 Worker 接管。旧 Worker 若仍继续处理，会与新 owner 争抢同一条 reservation。
- 增加逐条续租后，第一次 MySQL + Redis 集成测试又暴露 rowcount 边界：刚完成批量认领时，续租写入与原租约截止时间可能完全相同；MySQL 在 changed-rows 语义下返回 rowcount=0，导致 Worker 误以为 lease 已丢失并跳过记录。

### 修复

- 新增 `CapReservationLedger.renew_recovery_lease`：只允许当前 `lease_owner` 续租；支持 PREPARED、RESERVED、NEEDS_RECONCILIATION，以及尚未清理 token 的 COMMITTED 终态。
- 恢复 Worker 每条记录开始处理前都续租；续租返回 false 时增加 `lease_lost` 计数并立即跳过，不能继续检查/修改 Redis。
- 续租截止时间至少比当前时间多 `lease_seconds + 1` 秒，确保与刚认领时的截止时间不同，避免 MySQL changed-row count=0 被误判。
- 新增单元测试：模拟批次第二条记录已被其他 Worker 接管，验证旧 Worker 只处理第一条，第二条不再触碰 Redis。
- 保留 MySQL + Redis 真实隔离集成测试，覆盖孤儿预留回滚、已提交转化保留/清理 token、NEEDS_RECONCILIATION 退避后恢复，以及多恢复 Worker 不重复回滚。

### CI 证据

- Run #1113（SHA `b13b052b109766f0fecbfcc5d56a296ae57b560a`）出现 **4 failed、399 passed、1 skipped、1 warning**。失败集中在 4 个真实 MySQL + Redis 恢复集成测试，根因是续租 SQL 的截止时间与原值相同，rowcount=0 被误判为 lease_lost。保留该失败记录。
- Run #1114（SHA `eff1377092acf6b3aec55c73ab79df0369879ed2`）：Backend **403 passed、1 skipped、1 warning**；Frontend Lint、Build、Playwright Mock API E2E 全部通过。Run #1114：[查看 CI](https://github.com/Helong0511/Platform/actions/runs/43004636477)。

### 剩余限制

- 此修复避免批次后半段的旧 owner 在租约丢失后继续操作；单条 Redis 操作仍依赖 Redis 客户端的 5 秒 socket timeout 和任务级异常处理。
- MySQL/Redis 集成测试只使用 CI 临时实例和随机合成标识，不连接生产服务。
- 完整 migration/backup/rollback、PII 保留政策、Outbox 配置生命周期组合及其它业务模块全量审计仍是合并/上线阻断项。PR 保持 Draft。


## 21. 认证时权限缓存新鲜度与账号状态即时生效（2026-11-11，Run #1117 / #1119）

### 发现的问题

- `permission_cache` 默认 TTL 为 300 秒。旧 `get_current_user` 路径先读取 Redis 权限缓存，再读取完整 User 行；缓存命中时，旧逻辑可能在缓存显示 `is_active=true`、`login_restricted=false` 时放行已经在数据库中被禁用/限制登录的账号。
- 旧路径随后仍查询完整 User 对象，因此权限缓存并未真正省去 User 表查询，却增加一次 Redis/DB 权限读取和缓存失效竞态。
- 用户服务会尝试调用 `invalidate_user_permission_cache`，但 Redis 不可用、跨 Worker 失效失败时，不能把账号停用的安全性依赖于缓存 TTL。

### 修复

- `get_current_user` 现在直接从当前请求的数据库会话读取 User 行，并以数据库最新的 `is_active`、`login_restricted`、`login_message` 做认证判定。
- 认证路径不再先读 `get_user_permissions` 缓存后又重复查询 User 表；避免旧缓存放行禁用账号，也避免缓存显示旧禁用状态导致账号重新启用后继续被误拒绝。
- 角色授权仍由返回的数据库 User 对象交给 `require_admin`、`require_client` 等依赖执行；资源归属仍由各业务服务查询数据库进行校验。
- 新增三项回归测试：缓存模拟旧的“仍启用”状态但数据库已禁用；缓存模拟未限制但数据库已限制登录；数据库当前有效账号不受旧缓存影响。测试同时断言认证流程不再访问权限缓存。

### CI 证据

- Run #1117（SHA `a90b33d0a2119323f20efc21fff4816a1b04da88`）：Backend **405 passed、1 skipped、1 warning**；Frontend Lint/Build/Playwright 全部通过。
- Run #1119（SHA `70d588fb3759e028dcf72a2d02f398b44dc9b2b8`）：Backend **406 passed、1 skipped、1 warning**；Frontend Lint、Build、Playwright Mock API E2E 全部通过。Run #1119：[查看 CI](https://github.com/Helong0511/Platform/actions/runs/43005368581)。

### 结论

- 账号禁用和登录限制不再依赖 5 分钟权限缓存的失效及时性。
- 权限缓存模块仍可供其它明确允许短暂陈旧的只读展示/优化场景使用；不得用于绕过实时账号状态和资源归属校验。
- 其余 RBAC 路由覆盖、数据租户隔离、迁移/备份恢复和 PII 治理仍需继续审计。PR 保持 Draft，不合并、不部署。


## 22. Postback 错误响应与数据库异常日志 PII 脱敏（2026-11-11，Run #1122 / #1124）

### 发现的问题

- 公开 `/postback/{platform}` 回调入口在可恢复失败时，旧逻辑会把处理结果中的 `message` 原样返回给上游；若错误消息包含 SQL/下游响应内容，可能泄露内部细节或 PII。
- Postback 接收服务异常日志原先使用 `str(exc)` 和 `exc_info=True`；异常消息可能包含邮箱、IP、click_id、SQL 参数等原始内容。
- `get_postback_db`、通用 `get_db`、`get_db_readonly` 在数据库异常时也记录原始异常文本和 traceback；SQLAlchemy 异常字符串可能包含绑定参数。

### 修复

- Postback 可恢复错误统一返回固定的 `503` + 通用重试提示；不再把内部 `result.message` 暴露给上游。
- Postback 接收服务只记录异常类型，不记录原始异常文本或 traceback。
- 三类数据库会话依赖的异常日志只记录异常类型，不输出 SQL 参数或原始错误消息。
- 新增回归测试：公开 Postback 异常响应不包含内部错误消息；接收服务日志不包含 email/click_id/IP；三类数据库依赖均不把异常中的 PII 写入日志。

### CI 证据

- Run #1122（SHA `0ff14efa69e4f4560b077bb88fe9906776a339ce`）：Backend **408 passed、1 skipped、1 warning**；Frontend Lint/Build/Playwright 全部通过。
- Run #1124（SHA `46c988f689a9e1389f62a1f27558a98eab4d3c73`）：Backend **411 passed、1 skipped、1 warning**；Frontend Lint、Build、Playwright Mock API E2E 全部通过。Run #1124：[查看 CI](https://github.com/Helong0511/Platform/actions/runs/43006102884)。

### 未解决的数据生命周期问题

- 本修复只减少日志和上游响应的 PII 暴露，不代表持久化 PII 已全部治理。
- `postback_conversions`、未完成 `postback_forward_queue`、`postback_notifications.notification_message`、备份副本及第三方接收方数据仍需要经批准的用途、保留期限、访问权限和删除流程。
- PII 清理配置默认关闭；未经业务/合规负责人批准，不得擅自设置保留天数或删除仍需重试的队列载荷。


## 23. 下游重试目标匹配与 Outbox 耗尽指标（2026-11-12，Run #1132）

### 发现的问题

- 综合 PII 清理任务是每日调度实际调用的入口。此前它检查 postback_forward_queue 时，只要产品 ID 或渠道 ID 任一匹配就认为存在活动队列，未按完整目标组合匹配；同时没有对两个外键均为 NULL 的目标执行 NULL-safe equality。
- 这会导致同一转化下不同目标的重试队列互相阻塞日志清理；当日志和队列的目标外键都为 NULL 时，也可能漏掉仍在等待的队列，导致提前清理重试诊断载荷。
- Outbox 的 exhausted 指标此前没有排除 pii_scrubbed_at 已设置的事件。已清理且不可能再次发送的历史失败事件可能持续计入人工处理积压，造成监控假阳性。

### 修复

- 活动转发队列现在按完整三元组关联：conversion_id + product_id + publisher_id。
- product_id、publisher_id 均采用 NULL-safe equality；两个维度必须同时匹配，避免不同转发目标相互干扰。
- Outbox exhausted 统计增加 pii_scrubbed_at IS NULL，已清理事件不再计入可操作的耗尽队列；耗尽状态归一化与正常发送扫描原有清理保护保持一致。
- 新增 SQL 回归断言，验证两个外键的普通相等和双方 NULL 分支均存在；新增 exhausted 统计不包含已清理事件的断言。
- 未改变 PII 保留期限、未启用自动清理、未改变事件幂等键和第三方发送语义。

### CI 证据

- Run #1132（SHA f254530c094eb4b090d18aaf809b3424f436920c）：Backend **412 passed、1 skipped、1 warning**；Python compile、Frontend Lint、Build、Playwright Mock API Browser E2E 全部通过。
- Skip 是本机核对脚本未提交（CI 不依赖）；warning 是 passlib 在 Python 3.11 使用 crypt 的弃用提示。
- Run #1132：https://github.com/Helong0511/Platform/actions/runs/43133126073。

### 剩余限制

- PII 清理配置仍默认关闭；通知消息、PostbackConversion 原始数据、未完成转发队列、备份副本及第三方接收方数据仍需经批准的保留策略和独立生命周期设计。
- 当前清理查询按完整目标身份保护已存在的重试队列；生产发布前仍需在隔离副本验证转发任务创建/完成/重新入队与每日清理的并发时序。
- 完整 migration/backup/restore/rollback 演练、Outbox 配置禁用/删除/轮换/恢复的多 Worker 故障组合，以及 RBAC/归因/统计/结算/API/队列/前端剩余模块全量复核仍未关闭。
- PR 继续 Open / Draft，不合并、不部署；所有验证只使用隔离 CI、合成数据和 Mock API。


## 24. 客户 API IP 白名单、异常日志脱敏与报表结束日期边界（2026-11-12，Run #1135 / #1145）

### A. 客户 API IP 白名单实际执行

**发现的问题**

- Client ORM 和管理 Schema 已提供 allowed_ips，字段文档约定逗号分隔多个 IP、空值不限制、回环地址必须显式列入白名单。
- 但原 verify_client_request() 只验证客户状态、API 开关、时间戳和签名，没有校验 allowed_ips；管理员配置的客户 API 来源限制实际上没有生效。

**修复**

- 新增 _is_client_ip_allowed()，在客户 API 签名验证入口执行白名单判断。
- IP 来源只接收 API 路由通过 get_client_ip() 解析后的结果；该函数沿用 TRUST_PROXY_HEADERS 与可信代理 peer 校验，不直接信任请求携带的 X-Forwarded-For / CF-Connecting-IP 原始值。
- 客户产品列表、广告数据两个外部 API 均在认证前解析来源 IP 并传入 verify_client_request()。
- allowed_ips 为空/空白时保持不限制；逗号分隔的精确 IP 地址可匹配；回环地址不再隐式放行，必须显式列入 allowed_ips；来源 IP 无效或配置中存在非法条目时 fail-closed。
- 新增测试覆盖白名单允许、非白名单拒绝、空配置兼容、非法配置拒绝、127.0.0.1 未显式列入时拒绝、显式列入时允许、unknown 来源拒绝，以及产品 API 路由确实传入解析后的客户端 IP。
- 当前格式按 Schema 约定只支持逗号分隔的单个 IP，不支持 CIDR 网段；如需网段授权，应单独扩展 Schema、管理端校验和测试，不得把 CIDR 当作已支持能力。

### B. 客户开放 API 异常信息脱敏

- 客户产品列表异常不再把原始异常文本返回给调用方，统一返回通用错误提示；日志仅记录异常类型，不记录异常原文或 traceback。
- 客户广告数据异常日志同样只记录异常类型。
- 后台客户 API 审计写入及 Telegram 通知异常只记录异常类型，避免 SQLAlchemy 绑定参数或通知响应内容中的 PII 进入日志。
- Run #1135（SHA f9541653d277302360be484cb1c631370403241a）：Backend **414 passed、1 skipped、1 warning**；Frontend Lint/Build/Playwright Mock API E2E 全通过。
- 后续 IP 白名单与测试已合入最新 HEAD；未把 API 密钥或其它凭据安全专项纳入本轮范围。

### C. 转化报表结束日期排他边界

- 按日期筛选的结束日原先转换为当天 23:59:59，再使用 <=；数据库中结束日最后一秒内带微秒的记录可能被漏掉。
- 现在统一通过 _exclusive_end_datetime() 将结束日期转换为次日 00:00:00，并使用 < 作为排他上界，覆盖结束日全部微秒精度记录。
- 新增边界测试验证共享 helper 将 2026-11-11 转换为 2026-11-12 00:00:00。
- 中间 Run #1139（SHA d2bb3c3eb42d75c31ab975532af819a0fcb6cd0e）因 API auth 文件更新时遗留重复函数尾部而在 Python compile 阶段失败（SyntaxError: unmatched ')'）；已删除重复片段。该失败记录保留。
- Run #1145（SHA fb9aec043062a3d30f1e01a2afa0eff01d9829ce）：Backend **422 passed、1 skipped、1 warning**；Python compile、Frontend Lint/Build、Playwright Mock API Browser E2E 全部通过。Run #1145：https://github.com/Helong0511/Platform/actions/runs/43134250167。

### 仍需继续验收

- allowed_ips 的生产代理链路正确性仍依赖部署环境的 TRUST_PROXY_HEADERS、TRUSTED_PROXIES、Nginx realip 与源站防火墙配置；CI 只能验证代码与合成请求，不能证明生产网络配置。
- PII 保留政策仍未获业务/合规批准，自动清理保持默认关闭。
- 完整 migration/backup/restore/rollback 演练、Outbox 多 Worker 配置生命周期、Cap Reservation Redis/MySQL 故障组合、RBAC/租户隔离及统计/结算/API/队列/前端剩余模块全量复核仍是合并阻断项。
- PR 保持 Open / Draft，不合并、不部署；只允许隔离 CI、合成数据和 Mock API。


## 25. 仪表盘与转化报表异常信息脱敏（2026-11-12，Run #1148）

### 发现的问题

- Dashboard 的 stats、trends 异常处理原先将 str(exception) 同时写入日志并放入 API detail；数据库驱动异常可能包含 SQL 参数、邮箱、IP、click_id 等业务数据。
- Dashboard recent-ads 的路由和服务层也曾将原始异常文本写入日志，尽管服务层会回退为空列表。
- 转化总览与按 Offer 统计的异常处理同样把原始异常文本和 traceback 写入日志，并返回给 API 调用方。

### 修复

- Dashboard stats、trends 只记录异常类型，响应使用固定通用错误提示。
- Dashboard recent-ads 路由与服务层只记录异常类型，保留既有空数据降级行为。
- 转化总览、按 Offer 统计只记录异常类型，API 不再暴露底层异常原文。
- 新增 6 项回归测试：Dashboard stats/trends 响应与日志脱敏；recent-ads 路由与服务层日志脱敏；转化总览和按 Offer 统计响应与日志脱敏。

### CI 证据

- Run #1148（SHA 90539d1ed09687b643a57f5863c6542ee6bdc601）：Backend **428 passed、1 skipped、1 warning**；Python compile、Frontend Lint/Build、Playwright Mock API Browser E2E 全部通过。
- Skip 是本机核对脚本未提交（CI 不依赖）；warning 是 passlib 在 Python 3.11 使用 crypt 的弃用提示。
- Run #1148：https://github.com/Helong0511/Platform/actions/runs/43134611858。

### 剩余工作

- 这轮只处理已定位的 Dashboard 和转化报表异常出口；还需继续扫描其它业务模块的异常日志、错误响应和第三方响应透传。
- PII 保留政策、通知消息、原始 Postback 数据、未完成转发队列、备份与第三方接收方数据仍需单独治理。
- PR 保持 Open / Draft；不合并、不部署。后续代码/文档更新仍需以最新 HEAD 的完整 CI 为准。


## 26. 管理端、认证与调度 API 异常脱敏；客户转化空范围回归（2026-11-12，Run #1163）

### API 异常与诊断信息治理

本轮在前述客户 API、Dashboard、转化报表修复基础上，继续清理其它已定位的原始异常出口：

- Client 创建、更新、开关更新失败时，响应改用固定通用错误提示，日志只记录异常类型；客户更新审计日志失败也不再输出异常原文。
- Product 可用名称列表失败时不再把底层异常返回调用方；产品创建审计日志异常仅记录异常类型。
- Short-link 诊断的 DB / Redis / 进程内计数器错误不再把原始异常放进诊断响应或日志；手动同步失败返回通用提示。
- Audit log 列表、统计、详情、清理接口统一不返回数据库异常原文。
- Scheduled task 列表、详情、状态、队列、GAM 配置、触发、重载、锁释放等错误响应和日志不再透传原始异常。
- 登录和刷新令牌失败日志不再包含异常原文、用户名/IP拼接和 traceback；登录错误统一返回通用服务不可用提示。
- Telegram 诊断不应暴露 webhook URL 或原始异常；短链接与后台 API 的诊断响应只提供可操作的通用信息。
- 新增静态回归检查覆盖上述模块的异常字符串、traceback 和敏感 URL 泄露模式。

### 客户转化范围保护

- 核对 ConversionService 的 get_conversion_summary 与 get_conversions_by_offer：当前代码在客户用户找不到关联 Client 记录时，已提前返回全零结构/空列表，不会继续执行全局查询。
- 新增 tests/test_conversion_client_scope.py，验证缺少 Client 记录时两个路径均返回空范围，且只执行 Client 查找，不会继续查询全局 Click/Conversion 数据。
- 该边界目前不是已确认的线上漏洞；本轮增加回归测试以防未来重构删除现有保护。

### CI 证据

- Run #1163（SHA 91df3fd1d0519915c5307be6f57e6e8784addf6b）：Backend **438 passed、1 skipped、1 warning**；Python compile、Frontend Lint/Build、Playwright Mock API Browser E2E 全部通过。
- Skip 是本机核对脚本未提交（CI 不依赖）；warning 是 passlib 在 Python 3.11 使用 crypt 的弃用提示。
- Run #1163：https://github.com/Helong0511/Platform/actions/runs/43135437064。

### 当前剩余项

- 以上是本轮已扫描并修复的异常出口，不代表所有模块已完成全仓日志/响应脱敏；仍需继续审查结算、归因、队列、导入导出及外部回调边界。
- IP 白名单实际效果依赖部署环境可信代理配置、Nginx realip 与源站防火墙；尚未验证生产网络（本轮严禁连接生产）。
- PII 保留政策仍待批准，自动清理保持默认关闭；备份副本、第三方接收方、通知消息、原始 Postback 数据的全生命周期仍未闭环。
- PR 保持 Open / Draft，不合并、不部署；所有测试继续仅使用隔离 CI、合成数据和 Mock API。


## 27. Offer 短链接操作日志与 Pixel 映射异常脱敏（2026-11-12，Run #1167）

### 修复

- Offer 创建主短链接、检查/创建下游 Tracklink 短链接、同步 Offer 短链接的异常日志不再记录 str(exception) 或 traceback，仅记录 Offer ID 与异常类型。
- 新增 tests/test_api_exception_redaction.py 回归断言，防止上述 Offer 短链接操作重新写入原始异常文本。
- Pixel Mapping 数据库异常路径增加 PII 日志回归测试：合成异常包含邮箱、IP、click_id 时，日志只保留异常类型和安全的短链接标识，不出现异常中的邮箱/IP/click_id。
- 保留既有 Pixel 配置缓存失效行为；本轮新增的是异常日志隐私保护测试，不改变 Pixel 读取、缓存 TTL 或凭据解析语义。

### CI 证据

- Run #1167（SHA aff6b3b316f3e93813f2c3e2514240b938d46c33）：Backend **440 passed、1 skipped、1 warning**；Python compile、Frontend Lint/Build、Playwright Mock API Browser E2E 全部通过。
- Skip 是本机核对脚本未提交（CI 不依赖）；warning 是 passlib 在 Python 3.11 使用 crypt 的弃用提示。
- Run #1167：https://github.com/Helong0511/Platform/actions/runs/43135837802。

### 注意

- 日志只记录异常类型能降低 PII 暴露，但不替代受控的内部诊断平台；若未来需要 traceback，应使用脱敏后的结构化上下文、受限访问和保留期限，不得直接重新启用原始异常文本。
- 继续保持 PR Open / Draft，不合并、不部署；生产环境仍完全隔离。



## 28. Cap Reservation / Outbox 异常脱敏与无效任务收敛（2026-11-12，Run #1177）

### 修复与回归验证

- Cap Reservation 恢复 Worker 的异常处理只记录异常类型；账本 `last_error` 不再持久化 Redis/数据库异常原文，避免邮箱、IP、click_id、连接信息或 SQL 参数进入长期记录。
- Cap Manager / Cap Checker 的 Redis 回滚失败记录改为受控错误描述；回滚失败聚合日志仅保留异常类型，不包含异常原文。
- 新增恢复异常回归测试：注入包含合成邮箱、IP、click_id 的异常，验证日志与账本均不包含这些原始值。
- 第三方 Report Outbox 对缺少短链接/斗篷配置引用的历史脏记录，先原子争抢发送租约，再终结为 failed，清除 next_retry_time 并写入 completed_at；争抢失败则返回可重试的 report_in_progress，避免多个 Worker 重复终结或 due scanner 无限重扫。
- 新增 Outbox 回归测试验证缺少配置引用的记录被终态收敛，不再保留下一次重试时间。
- 修复 Cap Reservation 集成测试的过时断言：测试现在验证账本记录受控的“回滚异常 / error_type=RuntimeError”，同时仍验证不会误报 ROLLED_BACK。该修改没有放宽业务断言或恢复原始异常文本。

### CI 证据

- Run #1176（SHA `bd853198f0d5ac8f5cc93432b01213398f0899a5`）曾因旧测试仍断言原始错误描述而失败：Backend 1 failed、442 passed、1 skipped、1 warning；Frontend Lint/Build/Playwright Mock API E2E 成功。保留历史失败记录。
- Run #1175（较早 SHA）后续被取消，不作为通过证据。
- Run #1177（SHA `46d3907d0ebe2f288e7576b0d68e2a2bd5cead61`）完整成功：Backend **443 passed、1 skipped、1 warning**；Python compile 成功；Frontend npm ci、依赖 advisory 报告、Lint、Build、Playwright Mock API Browser E2E 全部成功。
- Run #1177：https://github.com/Helong0511/Platform/actions/runs/43136785298。
- Skip 仍是本地核对脚本未提交（CI 不依赖）；warning 仍是 passlib 在 Python 3.11 使用 crypt 的弃用提示。前端 Production High advisories 仍属于按用户要求暂缓的凭据安全专项，不宣称依赖零漏洞。

### 尚未关闭的阻断项

- Outbox 多 Worker 争抢、发送中租约过期、Worker 崩溃、配置禁用/删除/轮换/恢复及长时间网络故障的组合验收仍需补齐；不能宣称第三方 exactly-once。
- Cap Reservation 仍需覆盖 Redis failover/淘汰、DB commit 阻塞/ACK 丢失、时钟偏差、多恢复 Worker 竞争与进程重启的组合故障注入。
- 完整旧 schema + 代表性历史数据 migration、全量备份恢复、逐 DDL 中断续跑、应用兼容回滚及 schema/data diff 尚未完成。
- PII 保留政策仍待业务/合规审批；PostbackConversion 原始数据、待处理转发队列、通知消息、备份副本及第三方接收方数据仍需独立治理。
- RBAC、租户隔离、归因、统计、结算、API、队列及前端剩余业务模块仍需全量复核。

PR 继续 Open / Draft；不合并 main、不部署。所有验证仅使用 GitHub Actions 隔离 MySQL/Redis、合成数据和 Mock API；严禁连接生产环境或真实第三方接口。


## 29. 点击记录与扣减 API 异常脱敏（2026-11-12，Run #1177）

### 修复

- 点击访问记录列表/详情只记录异常类型；Facebook 像素手动补报日志移除原始异常文本、用户名和 traceback，只保留 click_record_id 与异常类型。
- 扣减配置列表、扣减统计、扣减日志，以及扣减配置/统计/日志三类导出接口，不再向调用方返回底层异常原文；日志只记录异常类型。
- 新增静态回归测试，确保点击记录与扣减 API 不重新引入 str(exception)、detail=str(exception) 或 exc_info traceback。

### 失败记录与验收

- Run #1171 曾因 Facebook 像素手动补报路径仍输出原始异常而失败（1 failed、440 passed、1 skipped、1 warning）；已定位并修复。
- Run #1177 在包含上述修复的最新代码 SHA 上完整通过：Backend **443 passed、1 skipped、1 warning**；Frontend Lint、Build、Playwright Mock API E2E 均通过。
- Run #1177：https://github.com/Helong0511/Platform/actions/runs/43136785298。
- 不删除历史失败记录；Skip 与 warning 的原因沿用第 28 节说明。

### 后续

- 继续对结算、归因、导入导出、外部回调与其它业务 API 做相同检查；本轮只覆盖已确认的点击记录与扣减 API。
- PR 继续 Open / Draft，不合并、不部署；不得连接生产服务器、数据库、Redis、队列或真实第三方接口。



## 29. 破坏性集成测试的目标环境强制隔离（2026-11-12，Run #1190）

### 发现与修复

- 原 MySQL 迁移集成测试会 DROP/重建 `third_party_report_logs`、`postback_forward_logs` 和 `cap_reservations`；此前主要依赖 `MYSQL_INTEGRATION_HOST` 存在判断是否运行，没有从测试代码层强制限制 loopback 主机和隔离数据库名。
- Cap Reservation MySQL + Redis 集成测试会动态 CREATE/DROP 测试数据库并写入/删除 Redis 测试键；此前仅检查两个连接环境变量是否存在。
- Redis 集成测试会直接写入、删除 Redis key；此前没有验证 URL 指向本机 Redis DB 14。

现已完成以下防护：

1. MySQL 迁移测试必须同时满足 `GITHUB_ACTIONS=true`、`UNIT_TEST=1`、明确的破坏性测试授权、MySQL host 为 loopback、数据库名严格等于 `platform_ci`；GitHub Actions 缺少主机配置或目标不安全时直接失败，不静默跳过。
2. Cap Reservation 跨存储测试必须同时满足 `GITHUB_ACTIONS=true`、`UNIT_TEST=1`、MySQL loopback + `platform_ci`、Redis loopback + DB 14，以及 MySQL/Redis 两项明确授权；否则禁止执行。
3. Redis 集成测试必须满足 `GITHUB_ACTIONS=true`、`UNIT_TEST=1`、loopback Redis DB 14 和显式 Redis 授权；否则禁止执行。
4. 新增地址白名单回归测试，覆盖 IPv4 loopback、IPv6 loopback、localhost、远程 IPv4、远程 hostname、错误 DB 编号、非 Redis URL 和缺失地址。
5. GitHub Actions 只对临时服务设置授权变量：MySQL `127.0.0.1/platform_ci`，Redis `127.0.0.1:6379/14`。应用默认 Redis DB 15 与集成 DB 14 继续隔离。

### CI 证据

- Run #1186（SHA `e7017d3514c46a812196a4ee6c07b9a06a39d16b`）：Backend **444 passed、1 skipped、1 warning**；Frontend Lint/Build/Playwright Mock API E2E 全部通过。验证了 MySQL 迁移测试的 loopback / database / 显式授权防护。
- Run #1190（SHA `4d633598fa576e7a212d3c480a4c565dc40bc41c`）：Backend **459 passed、1 skipped、1 warning**；Python Compile、Frontend Lint/Build、Playwright Mock API Browser E2E 全部通过。
- Run #1196（SHA `de8bb52dbf37b952e0d9bf5c727d6d2d96e0386f`）：Backend **459 passed、1 skipped、1 warning**；在此轮基础上进一步强制破坏性 MySQL/Redis 集成测试只能由 GitHub Actions 临时服务执行；Python Compile、Frontend Lint/Build、Playwright Mock API Browser E2E 全部通过。
- Run #1196：https://github.com/Helong0511/Platform/actions/runs/43139353500。
- Run #1195 因后续提交替代而取消，不作为通过证据。
- Run #1190：https://github.com/Helong0511/Platform/actions/runs/43138500303。
- 唯一 Skip 是本地核对脚本未提交（CI 不依赖）；warning 是 passlib 在 Python 3.11 使用 crypt 的弃用提示。

### 当前边界

- 该保护降低测试误连外部/生产资源的风险；CI 本身仍只验证代码、临时服务和合成数据，不能替代生产发布前的网络隔离、权限与基础设施审计。
- 迁移全流程备份恢复、逐 DDL 中断、应用兼容回滚、Outbox 多 Worker 配置生命周期及 Cap Redis/MySQL 组合故障仍未全部验收。
- PR 继续 Open / Draft；不合并 main、不部署；凭据安全专项继续按既定范围暂缓。



## 30. Outbox 终态失败积压持续告警（2026-11-12，Run #1202）

### 发现的问题

- Outbox 对缺少短链接/斗篷配置引用的记录会正确终结为 `failed` 并清除 `next_retry_time`，防止扫描器每分钟重复选择。
- 但原有 `exhausted` 计数只统计 `attempt_count >= max_attempts` 的记录；这类尚未尝试发送的配置缺失记录不会进入该计数。
- 终态失败记录后续不再进入 due scan，调度任务的单轮 `failed` 也会恢复为 0，因此可能出现数据库持续存在失败 Outbox、调度状态却显示无积压且不再告警的情况。

### 修复

- `process_postback_report_outbox` 新增 `terminal_failed` 计数：统计仍未清理、`status=failed` 且 `next_retry_time IS NULL` 的 Outbox 行。
- 原有 `exhausted` 保留其“自动重试次数耗尽”语义；`terminal_failed` 覆盖所有终态失败，包括配置引用缺失和重试耗尽，不把两者混为一谈。
- 每分钟调度任务在任务结果中输出 `terminal_failed`；只要该计数非零，就持续写入 warning，直到管理员处置或记录按策略清理。
- 新增 SQL 编译断言和调度告警测试；同时更新单条 Worker 异常测试夹具，确保所有 stats 返回契约一致。

### CI 证据

- Run #1201（SHA `02317a69037a2c8c727a9a449a1585fd4d093605`）发现一处测试 FakeDB 返回值断言未同步新增字段：Backend 1 failed、459 passed、1 skipped、1 warning；Frontend 全部通过。失败仅为测试夹具漏掉 `terminal_failed=0`，已更新并保留该历史失败记录。
- Run #1202（SHA `da0eaf5dec85eda0b8b1fd1eeb2b221915008209`）：Backend **460 passed、1 skipped、1 warning**；Python Compile、Frontend Lint/Build、Playwright Mock API Browser E2E 全部通过。
- Run #1202：https://github.com/Helong0511/Platform/actions/runs/43140432286。

### 仍需注意

- `terminal_failed` 是持续积压数量，不代表自动重试；这些记录需要管理员检查配置引用、确认事件是否应补发，再按受控流程处理。
- 对已清理 PII 的记录不计入该告警；Outbox worker 仍不得重新发送已清理载荷。
- PR 继续 Open / Draft；不合并 main、不部署。



## 31. 事件幂等迁移失败保护、Cap 日志脱敏与 IP 白名单端到端回归（2026-11-12，Run #1210）

### 新发现与修复

1. **事件幂等迁移的中断安全**
   - 原迁移先删除旧的 `unique_source_adsid`，再创建新的 `unique_event_key`。
   - 如果历史 `event_key` 存在碰撞，新唯一索引创建会失败，但旧唯一约束已被删除，迁移中断窗口内可能暂时失去唯一性保护。
   - 已调整顺序：先完成 `event_key NOT NULL`，再创建 `unique_event_key`；只有确认新索引存在后才删除旧索引。
   - 新增真实隔离 MySQL 故障测试：人为构造不同 source/adsid 共用同一 event_key，验证新索引创建失败时旧唯一索引仍存在、新索引不存在。

2. **Cap ORM 刷新异常日志**
   - `_refresh_offer_caps()` 不再记录数据库异常原文，只记录 OfferCap ID 与异常类型。
   - 新增包含合成邮箱、IP 和 SQL 敏感值的异常回归测试，验证日志不包含原始内容。

3. **PII 清理与 Outbox 活跃发送租约**
   - PII 清理查询必须排除尚未过期的 `report_start_time` 租约，避免清理任务在活跃 worker 发送期间抢先擦除其载荷。
   - 新增 SQL 编译回归断言，确保查询包含空租约和过期租约判断；PII 清理仍使用 `FOR UPDATE SKIP LOCKED`。

4. **客户登录与刷新令牌 IP 白名单**
   - 新增客户登录和刷新令牌端到端路由测试。
   - 未显式配置回环地址时，127.0.0.1 不会被隐式放行；刷新令牌路径同样返回 403，不会轮换或撤销会话令牌。

### CI 证据

- Run #1210（SHA `e785a8a90fb7d419be4c0d2b448c5f32ab019234`）：Backend **464 passed、1 skipped、1 warning**；Python Compile 通过；Frontend Lint、Build、Playwright Mock API Browser E2E 全部通过。
- Run #1210：https://github.com/Helong0511/Platform/actions/runs/43141093206。
- Run #1209（SHA `a210de684637091d55f0eea1236105b83cf9c449`）被后续 PR 提交触发的 concurrency 机制取消；不作为验收依据，也未删除历史记录。

### 仍未关闭的发布阻断项

- 代表性旧 schema + 真实规模合成数据的完整迁移、全量备份恢复、每个 DDL 边界故障注入、应用兼容回滚及 schema/data diff。
- Outbox 配置禁用/删除/轮换/恢复、发送中 lease 过期、Worker 崩溃、长时间网络故障、多 Worker 竞争的组合压力验收。
- Cap Reservation Redis failover/淘汰、MySQL commit 阻塞/ACK 丢失、时钟偏差和多恢复 Worker 组合故障验收。
- PII 保留期限与删除政策审批；PostbackConversion 原始数据、通知消息、备份副本和第三方接收方数据仍需独立治理。
- RBAC/租户隔离、归因、统计、结算、API、队列和前端其它业务模块的最终全量回归。
- PR 继续 Open / Draft；不合并 main、不部署；凭据安全专项仍按既定范围暂缓。



## 32. Cloudflare 可信代理网段完整性回归（2026-11-12）

### 核查结论

- `nginx/btfrx.online/cloudflare_real_ip.conf` 当前配置包含 Cloudflare 官方 IPv4 15 段、IPv6 7 段，逐项与官方清单核对一致。
- 配置使用 `real_ip_header CF-Connecting-IP` 和 `real_ip_recursive on`；Nginx 转发给后端的是经过 realip 模块解析后的 `$remote_addr`，不直接透传客户端提交的 `CF-Connecting-IP`。
- `tests/test_proxy_header_trust.py` 新增完整 CIDR 集合相等断言：不仅检查代表性网段，也会在遗漏、增加或错误放宽可信网段时失败；同时断言启用 `real_ip_recursive on`。
- 未修改生产 Nginx 配置、未 reload Nginx、未连接任何生产服务器。

### 权威资料

- Cloudflare 官方说明（页面标注 2026-04-21 更新）：https://developers.cloudflare.com/fundamentals/concepts/cloudflare-ip-addresses/
- Cloudflare 官方当前 IP 范围清单：https://www.cloudflare.com/ips/
- Nginx 官方 realip 模块文档：https://nginx.org/en/docs/http/ngx_http_realip_module.html

### CI 证据

- Run #1212（SHA `d536a021eddddb0f24d5da005f32fad92a90d745`）：Backend **464 passed、1 skipped、1 warning**；Python Compile、Frontend Lint/Build、Playwright Mock API Browser E2E 全部通过。
- Run #1212：https://github.com/Helong0511/Platform/actions/runs/43141328240。
- 完整 Cloudflare CIDR 集合断言是其后新增的测试，必须以包含该测试的最新 CI 为准，不能把 Run #1212 当作该新增测试的验收证据。



## 32. 多 Client 用户的转化统计租户范围修复（2026-11-12，Run #1217）

### 发现的问题

- `User.clients` 与 `Client.user` 是一对多关系，单个客户用户可以关联多个 Client。
- 转化总览与按 Offer 汇总原先使用 `SELECT Client.id ... LIMIT 1` 任取一条 Client，再只查询该 Client 的 Publisher。
- 对关联多个 Client 的用户，统计会因数据库返回顺序而只显示其中一部分客户渠道，导致同一用户不同统计接口范围不完整/不一致。

### 修复

- 两个转化统计入口均查询该用户的全部 Client ID。
- Publisher 查询统一使用 `Publisher.client_id IN (client_ids)`；转化总览的 Cap 展示汇总也使用全部 Client ID。
- 保留无 Client 记录或无可见 Publisher 时返回空统计/空列表的 fail-closed 行为，不会退化为全局查询。
- 新增多 Client 用户回归测试，验证查询不再带 `LIMIT 1`，并且 Publisher 范围按全部归属 Client ID 过滤；更新无 Client 记录测试夹具。

### CI 证据

- Run #1217（SHA `67558d8659e99d949df7588a2560566a7aa17390`）：Backend **466 passed、1 skipped、1 warning**；Python Compile、Frontend Lint/Build、Playwright Mock API Browser E2E 全部通过。
- Run #1217：https://github.com/Helong0511/Platform/actions/runs/43141592737。

### 仍需复核

- 当前修复覆盖 ConversionService 的转化总览与按 Offer 汇总；仍需全仓检查其它以 `Client.user_id` 取单条记录或以 first-loaded Client 作为唯一租户范围的查询，确认多 Client 账号的列表、产品、统计、结算与导出范围一致。
- PR 继续 Open / Draft；不合并 main、不部署。



## 33. 多 Client 归属范围与 Cloudflare CIDR 全量回归（2026-11-12，Run #1217）

### 多 Client 归属范围

- 进一步核对发现，单个 CLIENT 用户可能关联多条 Client 记录；只取第一条会漏掉其它 Client 关联的 Publisher，造成客户统计数据不完整。
- `ConversionService.get_conversion_summary` 与 `get_conversions_by_offer` 现在读取该用户全部 Client ID，再通过 `Publisher.client_id.in_(client_ids)` 限定可见渠道。
- 没有 Client 记录或没有关联 Publisher 时继续 fail-closed，返回空结果；不会退化为全局查询。
- 新增两项多 Client 记录范围测试，并保留无 Client 记录时返回空范围的回归测试。

### Cloudflare 可信代理范围

- 新增测试将 Nginx 可信代理 CIDR 配置与 Cloudflare 官方清单做完整集合比较，当前要求 IPv4 15 段 + IPv6 7 段精确匹配，并要求 `real_ip_recursive on`。
- 测试只验证仓库配置，不触碰线上 Nginx 或防火墙。

### CI 证据

- Run #1217（SHA `67558d8659e99d949df7588a2560566a7aa17390`）：Backend **466 passed、1 skipped、1 warning**；Python Compile、Frontend Lint/Build、Playwright Mock API Browser E2E 全部通过。
- Run #1217：https://github.com/Helong0511/Platform/actions/runs/43141592737。

### 仍需在部署环境单独确认的代理边界

- 仓库 Nginx 配置监听所有接口；代码仓库无法证明服务器防火墙已阻止绕过 Cloudflare 直连源站。上线前必须核验 80/443 入站规则仅允许 Cloudflare 官方网段及明确批准的合作方/运维来源，其它来源拒绝；SSH 等管理端口另行配置。
- 必须在目标环境执行 `nginx -V` / `nginx -t`，确认 `http_realip_module` 已编译或正确加载，且 include 路径存在。当前 CI 的文本断言不替代目标服务器 Nginx 实际配置验证。



## 34. 多 Client 用户的 Publisher 权限守卫一致性（2026-11-12，Run #1221）

### 发现的问题

- ConversionService 已修复为读取用户全部 Client ID，但 `require_publisher_or_admin` 仍只取第一条 Client，再检查该 Client 是否有 active Publisher。
- 当用户关联多个 Client、只有后续 Client 配置了渠道时，权限守卫会错误拒绝；当第一个 Client 有渠道时，守卫和服务层的租户范围也不一致。

### 修复

- 权限守卫现在查询该用户全部 Client ID，再通过 `Publisher.client_id IN (client_ids)` 检查是否至少存在一个 active Publisher。
- 无 Client 记录或全部 Client 都没有 active Publisher 时继续 fail-closed。
- 移除单 Client 的 UserService 检查路径，避免权限守卫与 ConversionService 多 Client 逻辑不一致。
- 新增测试覆盖多 Client 中任意一个存在 active Publisher 时允许，以及无 Client / 无 active Publisher 时拒绝。

### CI 证据

- Run #1221（SHA `a4062099c56e940c70d68383e41b1bcd62a99c3b`）：Backend **469 passed、1 skipped、1 warning**；Python Compile、Frontend Lint/Build、Playwright Mock API Browser E2E 全部通过。
- Run #1221：https://github.com/Helong0511/Platform/actions/runs/43142037373。

### 仍需复核

- ConversionService 和 `require_publisher_or_admin` 已覆盖多 Client 账号；其它 API、导出、产品、结算、报表及密码策略仍需检查是否存在 first-loaded Client 造成的范围遗漏或策略不一致。
- PR 继续 Open / Draft；不合并 main、不部署。



## 30. 全量隔离回归复验（2026-11-12，Run #1228）

- 最新 PR head：`a66a5e00a775de8aadac9e58f4a05e981788bcc7`。
- GitHub Actions Run #1228：https://github.com/Helong0511/Platform/actions/runs/43142529211。
- Backend：**470 passed、1 skipped、1 warning**；Python Compile 通过。
- Frontend：依赖安装、依赖告警报告、Lint、Build、Playwright Mock API Browser E2E 全部通过。
- 该次 CI 仍只连接 Workflow 声明的临时 MySQL 8.0 / Redis 7.4 服务，测试数据均为合成数据；没有连接生产服务。
- 唯一 Skip：本地核对脚本未检出（该脚本在 `tests/*` 默认 gitignore 范围，CI 不依赖）。
- 唯一 pytest warning：Passlib 1.7.4 导入 Python 3.11 的 `crypt` 模块产生弃用提示（该模块计划在 Python 3.13 移除）。这不是测试失败，也未在本轮更改密码哈希方案；密码凭据安全专项仍按本轮范围暂缓，后续应单独评估哈希方案兼容迁移，不应直接替换现有密码验证实现。
- Redis/MySQL 容器启动日志另有基础镜像环境警告（Redis memory overcommit、MySQL 临时 CI 容器配置）；不代表应用测试失败，亦不应将这些 CI 容器警告误判为生产环境配置结论。

### 仍未完成的验收项

1. Outbox Worker 发送过程超过租约时长时的租约续期/失租保护与远端请求幂等验证。
2. Outbox 多 Worker 争抢同一事件的真实 MySQL 并发测试（当前已有 Cap Reservation 多 Worker 争抢测试；Outbox 需补充同等级真实集成证据）。
3. 数据库迁移的备份恢复、逐 DDL 中断恢复、迁移前后应用兼容性与可执行回滚演练。
4. Cap Reservation 在 Redis 短暂不可用、重启、token 丢失、counter 保留/过期、MySQL commit ACK 丢失等组合故障下的真实隔离集成验证。
5. 其余多租户隔离、归因幂等、PII 生命周期和业务流程仍需按清单逐项完成；当前全量测试通过不等同于全部上线风险已消除。

PR #1 保持 Open / Draft，不合并 main，不连接生产环境。凭据安全专项继续暂缓。


## 35. Cap Reservation 墓碑重试保护与 Outbox 斗篷生命周期回归（2026-11-12，Run #1270）

### Cap Reservation

- Run #1268 曾因真实 Redis 集成测试缺少 `datetime` 导入而失败；保留历史失败记录，未将失败 Run 伪装为成功。
- 修复测试导入后，Run #1269（SHA `e1d8664931886ae5d4a262dc299fb8b9fb3c419c`）Backend **477 passed、1 skipped、1 warning**；Frontend Lint、Build、Playwright Mock API Browser E2E 全部通过。
- 对同一 reservation_id 在 Redis 中留下 `ROLLED_BACK` 墓碑后再次预留的路径，Lua 必须拒绝把墓碑当成有效 reservation；Daily / Total Cap 均 fail-closed，不能落入 CAP_FAIL_OPEN。
- 真实隔离 Redis 回归测试覆盖 rollback 后复用同一 reservation_id：抛出已回滚异常，counter 不增加，墓碑保留。

### Outbox 斗篷配置生命周期

- 新增测试覆盖斗篷停用、删除、同名恢复和 Pixel/Token 轮换。
- 配置停用或删除时不允许继续使用旧凭据；同名配置恢复后，后续 Outbox 重试必须重新解析数据库中的当前配置。
- 当前 Pixel 凭据读取仍以数据库为权威来源，进程内旧凭据缓存不参与运行时读取；共享缓存版本化失效协议尚未实现，不得提前恢复本地缓存。
- Run #1270（SHA `4f42b4ca09b88d71f0be47d0aa5f37c1a740ec9f`）Backend **478 passed、1 skipped、1 warning**；Python Compile、Frontend Lint/Build、Playwright Mock API Browser E2E 全部成功。
- Run #1270：https://github.com/Helong0511/Platform/actions/runs/43145988558。

### Outbox 多 Worker / 租约证据边界

- 隔离 MySQL 集成测试已覆盖两个 Worker 并发认领同一事件只能有一个成功、租约过期后新 Worker 接管，以及旧 Worker 的 fencing token 不能覆盖新 Worker 状态。
- Outbox 批次扫描不提前修改待发送事件状态；最终发送由条件 UPDATE 认领，失败/崩溃后通过过期租约重新进入扫描。
- PII 清理与发送认领均检查 `pii_scrubbed_at IS NULL`，并使用数据库行锁/条件 UPDATE 仲裁；清理先提交时，旧 Worker 内存中的载荷也不能取得发送租约。
- 本轮新增斗篷生命周期测试属于隔离单元测试，不等同于完整第三方端到端投递；没有调用真实 Meta / Facebook API。

### 仍需完成

1. Outbox 长时间 HTTP 阻塞超过租约、网络分区、Worker 进程强杀、数据库重启与远端 ACK 丢失的组合故障测试。
2. Outbox 斗篷生命周期的真实隔离 MySQL + Redis 多 Worker 端到端组合测试。
3. 完整 Migration 备份恢复、逐 DDL 中断重跑、worker pause/resume、兼容回滚及 schema/data diff。
4. PII 保留政策审批及未纳入自动清理的数据类别治理。
5. RBAC、租户隔离、归因、统计、结算、API、队列及前端剩余业务模块全量复核。

PR #1 继续 Open / Draft，不合并 main、不部署；验证只使用隔离 CI、合成数据及 Mock API，禁止连接生产环境。凭据安全专项仍按用户要求暂缓。
