# Click 归因与斗篷点击计数专项审计（2026-11-24）

## 范围与结论

审计基于分支提交 `01d5a36caec6232b87cd22ef4c203cb6d3e828cf` 的只读代码检查。本次未修改业务代码，未运行本地测试；该提交已有 GitHub Actions Full Audit 6/6、Emergency Security 2/2 成功结果，但这些 CI 结果不能证明下述并发/故障语义正确。

本轮确认两个仍需修复的高风险问题：

1. 斗篷 `/report` 的计数写库仍存在 ORM read-modify-write 并发丢增量风险；缓存更新也不是原子操作。
2. Click 归因查询将数据库异常折叠成“未找到”，并允许有效 Token 在数据库校验失败时继续作为归因结果；这会把“数据库不可用”与“合法 token-only 归因”混为一谈。

## 1. 斗篷 /report 点击计数路径

文件：`app/routes/short_link/cloak_report_service.py`、`app/routes/short_link/cloak_click_persist.py`

### 1.1 缓存命中路径

`record_cloak_click_count()`：
- 读取短链缓存；
- 对缓存对象执行 `cached_data["click_count"] = old + 1`；
- 调用 `update_short_link_cache()` 写回；
- 调度持久化任务，传入 `sync_short_link_click_count=True`。

`persist_cloak_report_click()` 在该标志为 True 时再次从数据库读取 ShortLink，然后执行 ORM 属性加一并提交。这里的数据库加一是该次事件的持久化，不是同一次请求重复执行两次 DB 加一；缓存与 DB 分别承载缓存视图和持久值。

### 1.2 缓存未命中路径

`record_cloak_click_count()` 直接查询 ShortLink，执行 ORM 属性加一并提交；之后调度持久化任务，传入 `sync_short_link_click_count=False`，避免第二次 DB 加一。

因此，两个分支的 sync 标志当前是互补的；不能将它们描述为必然双计数。但两条路径的 DB 加一都属于读-改-写，而非数据库原子加一。

### 1.3 并发风险

- 缓存命中时多个请求可同时读取相同旧缓存值，分别加一后覆盖写回，造成缓存计数丢失更新。
- 两条路径最终执行的数据库计数更新均为 ORM 读取旧值后赋新值，两个事务可能覆盖彼此的增量。
- 缓存命中路径先更新缓存，再由 BackgroundTasks 持久化；若任务未执行、进程退出或持久化失败，缓存和数据库可能暂时或持续不一致。
- `update_short_link_cache()` 的返回结果只记录日志，不阻止继续调度持久化；这本身不一定丢 DB 计数，但必须有明确的缓存失效/重建策略。

### 1.4 修复要求

1. 两条 DB 路径统一改为 SQL 原子更新：`UPDATE short_links SET click_count = COALESCE(click_count, 0) + 1 WHERE id = ...`，校验 rowcount，并在同一事务内提交。
2. 缓存计数不得使用 get-modify-set；使用 Redis Lua/INCR 原子递增，或在 DB 成功后失效缓存并从 DB 重建。
3. 明确一次 click 事件的稳定幂等身份。若同一 `/report` 请求可能重试，必须以持久唯一事件账本去重，不能只依赖 Redis TTL key。
4. 明确 BackgroundTasks 失败恢复机制。对计数这类不可丢数据，不应只依赖进程内后台任务；优先采用持久 outbox/事件账本或同步持久化。
5. 加入 MySQL 并发集成测试：同一 short_code 并发 2/10/50/100 次，断言 DB 增量精确；缓存命中、缓存未命中、缓存更新失败、后台任务失败、进程重启及重试均覆盖。
6. 修复前不要将现有主短链计数器 `app/core/short_link_click_counter.py` 与本专项路径混为一谈；主计数器已具有独立 Redis Lua、batch ledger 和 DB 原子更新设计，本报告问题定位在 cloak /report 路径。

## 2. ClickAssociator 数据库异常语义

文件：`app/core/postback/transformers/click_associator.py`

### 2.1 当前行为

- `associate_from_db()` 最多重试 5 次；查询异常被宽泛捕获后继续在同一个 AsyncSession 上重试。
- SQLAlchemy 事务失败后，同一 Session 通常需要 rollback 才能恢复；当前重试循环没有在异常后 rollback，也没有使用独立 Session。
- 五次失败后统一返回 None，无法区分“确实没有 Click”与“数据库查询不可用”。
- `associate()` 对有效 Token 先查 DB；若 DB 查询返回 None（包括异常导致的 None），仍会返回 Token 归因。
- `_enrich_association()` 再次捕获数据库异常并继续返回部分 Token 字段。
- Token 与 DB 同时存在时，`_merge_token_and_db_association()` 允许 Token 的非空字段覆盖 DB 的 offer_id、publisher_id、advertiser_id、short_link_id 等身份字段；未先验证双方身份一致。

### 2.2 财务风险

Postback pipeline 的 `step_associate_click()` 直接接收该返回值。后续 Offer 状态校验、Cap、扣量和转发都根据关联字典提取归因 ID。当前 None/Token-only/DB-validated 没有明确状态字段，因此数据库不可用可能退化成“无归因”或“Token-only”，而不是可重试失败；身份冲突也没有统一 fail-closed 处理。

### 2.3 修复要求

1. 定义显式归因结果状态：`validated_db`、`validated_token_only`、`not_found`、`db_unavailable`、`identity_conflict`、`invalid_token`。不得用 None 同时表达这些状态。
2. DB 查询异常必须 rollback 当前 Session 后向上抛出可重试错误，或使用独立短生命周期 Session 重试；禁止在 failed transaction 上原样重试。
3. 有效 Token + DB 查询异常时，不得自动等同于 DB not found。是否允许 token-only 必须由明确的业务策略决定；财务决策默认 fail-closed，且需要可审计的策略开关与状态。
4. Token 与 DB 同时存在时，比较不可变身份字段（click_id、offer_id、publisher_id、advertiser_id、short_link_id、归因版本）；冲突时拒绝归因并记录脱敏审计事件，不得静默覆盖。
5. 禁止通过当前 Publisher.client_id 推导历史点击客户归属。客户归属应使用点击时保存的不可变快照；历史数据无法可靠回填时保持 unknown，不得按当前值猜测。
6. Postback handler 必须把 `db_unavailable` 映射为明确的 retryable failure，并确保不会返回成功 ACK；`not_found` 与 `identity_conflict` 则按业务规则拒绝财务处理。

## 3. 必须补充的回归测试

- ClickAssociator 查询异常：第一次 DB 查询抛出 SQLAlchemy DBAPIError，验证 rollback/Session 生命周期正确，结果为 db_unavailable 而非 not_found。
- Token 有效 + DB 不可用：验证不会进入扣量、Cap、转发和转化保存，且 handler 返回 retryable。
- Token 与 DB 的 offer/publisher/advertiser/short_link 任一身份字段冲突：验证 fail-closed。
- DB 找不到记录但 Token 策略明确允许 token-only：验证状态显式为 validated_token_only，且历史 client_id 不从当前 Publisher 反推。
- cloak 缓存命中/未命中两条路径并发 2/10/50/100 次：验证 MySQL 计数精确且 Redis cache 最终一致。
- cloak 持久化提交失败、BackgroundTasks 丢失、Redis 故障及重试：验证没有静默丢数或重复计数。

## 4. 验收门槛

在真实 MySQL（与生产相同主版本、InnoDB、事务隔离级别）上完成并发和故障注入测试；检查 migration、索引、锁顺序、事务回滚和 commit-unknown 恢复。单元测试或 SQLite 不能替代这些验证。

本报告只记录已核实风险与修复验收标准，不代表问题已经修复。PR #205 仍应保持 Draft；在 Redis/MySQL 扣量权威账本、窗口算法、Click 归因 fail-closed 和真实 MySQL 并发测试完成前，不得合并上线。

## 5. 2026-11-24 后续修复进展（以最新分支提交为准）

本次追加修复：

- `associate_from_db()`：数据库查询异常时回滚当前 Session 并向上抛出，不再在同一失败 Session 上重试，也不再把数据库故障折叠为 Click not-found。
- `_enrich_association()`：此前会捕获 Token 关联 ORM enrichment 的数据库异常并返回部分 Token 身份。现改为记录异常类型、尝试回滚并重新抛出，避免数据库不可用时携带未完成校验的 Token 身份继续进入后续财务处理。
- 新增 `test_token_enrichment_database_error_rolls_back_and_propagates`，验证 enrichment 查询异常只执行一次、回滚一次、异常向上传播且不返回部分 publisher 关联。

以上改动已提交到 PR #205 分支；尚未由最新提交对应 CI 验证，本地未执行测试。接收层已将未捕获处理异常转换为 HTTP 503 retryable response。

仍未解决：

- Token 与 DB 同时存在时，`_merge_token_and_db_association()` 仍允许 Token 非空身份字段覆盖 DB 的 offer/publisher/advertiser/short_link 身份字段，尚未完成冲突检测。
- DB 查无 Click 时是否允许 Token-only 仍是业务策略问题；不得将 DB unavailable 解释为 not-found。若允许 Token-only，必须明确其身份可信边界、审计状态及财务处理策略。
- 历史 Publisher `client_id` 归属快照仍缺失，不能用当前 Publisher 值反推历史归属。
- 斗篷计数、MySQL 权威扣量账本、Redis/MySQL 非原子边界及 24 小时窗口算法仍未解决。

因此 PR #205 继续保持 Draft；本节记录的是代码提交状态，不代表测试通过或验收完成。

### 5.1 Token 与 DB 身份冲突的后续修复

- `_merge_token_and_db_association()` 现在对 `click_id`、`offer_id`、`publisher_id`、`advertiser_id`、`short_link_id` 做双边非空值一致性检查；任一身份字段不一致即抛出拒绝异常。
- 合并时上述身份字段始终保留数据库点击快照，不再由 Token 覆盖。
- 新增冲突拒绝测试，以及身份一致时数据库身份字段保持权威的回归测试。
- 当前冲突异常会中止 Postback pipeline；接收层将其作为非重试的请求拒绝处理（HTTP 400），不会继续进入 Cap、扣量、转化保存或转发。

注意：此修复只解决 Token/DB 已同时存在时的字段冲突，不解决 DB 查无记录时的 Token-only 策略，也不解决历史 `client_id` 快照缺失。

### 5.2 历史客户归属快照修复（本轮追加）

**根因确认：** `clicks` 表原先没有客户 ID 快照。DB 归因从 `click.publisher.client_id` 读取当前值；Token-only enrichment 也会用当前 Publisher 值补齐；`ConversionSaver.resolve_trusted_attribution()` 还有一次相同的当前值 fallback。Publisher 的客户归属一旦从 A 改成 B，历史点击可能被归到 B。

**修复内容：**

- `clicks.client_id` 新增点击时客户 ID 快照字段；ORM 与 `sql/platform.sql` 同步。
- 新增迁移 `sql/migrations/20261124_click_client_attribution_snapshot.sql`。该列不设置 clients 外键，避免客户后续删除/迁移清空已发生点击的历史归属。
- `/track/click/{offer_id}` 在创建点击时将 `publisher.client_id` 同时写入 Click 记录和签名 Token。
- Token 解析新增 `client_id` 字段；紧凑 Token 载荷优先保留该字段，碰撞重建 Token 时也保留快照。
- DB 归因读取 `clicks.client_id`，不再读取 Publisher 当前 `client_id`。
- Token enrichment 不再用 Publisher 当前归属补齐缺失快照。
- Token 与 DB 合并时，双方非空客户 ID 不一致即拒绝；DB 快照存在时 DB 优先；DB 历史行缺失快照时可使用签名 Token 快照。
- `ConversionSaver.resolve_trusted_attribution()` 不再回退读取 Publisher 当前 `client_id`。旧点击若 DB 与 Token 均无快照，客户归属保持 NULL，不信任请求体 client_id，也不猜测当前 Publisher 归属。

**历史数据处理：** 不执行自动回填。旧 `clicks` 行没有足以证明点击时客户归属的字段，使用当前 Publisher 值回填会把已发生的 A→B 变更错误写入历史。历史 NULL 应保持 NULL，除非存在可信的外部历史快照或可验证审计记录。

**上线顺序：** 先备份并执行新增列迁移，再部署包含新 ORM/Token/归因逻辑的应用。迁移前不得部署新代码；迁移完成后再逐步切换实例。新旧实例短暂混跑时，旧实例新写入的 Click 可能没有 `client_id`，但签名 Token 仍包含快照；若旧实例生成的 Token 也不含快照，则该事件客户归属保持 NULL，属于安全降级，不得用当前 Publisher 值补猜。

**验证范围：** 已新增 Token 载荷保留/解析、DB 缺失快照时签名 Token 补充、客户快照冲突拒绝、enrichment 不覆盖快照，以及 ConversionSaver 不回退当前 Publisher 的测试。代码已提交，必须以最终提交 SHA 的 CI 结果为准；尚未执行生产 MySQL migration，也没有声称历史数据已回填。


### 5.3 斗篷 /report 去重与计数一致性复核（Head 6206e2d）

本节基于当前 PR Head 的 `cloak_report.py`、`cloak_report_service.py`、`cloak_click_persist.py`、`short_link_cache.py` 复核。仅记录代码事实与风险；本轮未修改计数业务逻辑，也未执行真实 MySQL/Redis 故障注入测试。

#### A. Redis 去重故障时 fail-open

`try_mark_report_dedupe()` 在 Redis 客户端不存在或 `SET NX` 抛异常时返回 False；路由将 False 解释为“首次请求”，继续执行 click 计数和 CAPI 调度。因此 Redis 故障期间，同一 session 的重复请求可能重复计数/重复上报。

反向故障窗口也存在：Redis `SET NX` 成功后，后续 DB 计数失败或任务未执行，去重键仍保留 24 小时；客户端重试会被当作重复请求直接返回成功，无法补偿未完成的计数。

#### B. click 去重身份并不总是存在

`build_dedupe_key()` 对 click 阶段仅在存在 cookie `session_id` 时返回去重键；无 session_id 时返回 None，完全不去重。load 阶段则回退到 fbclid 或 anon。必须明确 click 事件的可信稳定身份，不能把缺少 session cookie 的请求视为天然唯一。

#### C. HTTP 成功响应与持久化结果脱节

`record_cloak_click_count()` 在 DB 查询不到短链时只记录 warning 并 return；DB commit 捕获 `StaleDataError` 后 rollback 并继续 return。路由随后仍可能返回 `status=success`，并调度 CAPI。另有 Click 明细写入通过 FastAPI BackgroundTasks 执行，`persist_cloak_report_click()` 捕获异常后只记录日志，不向调用方传播，也没有持久 outbox 可恢复。

因此接口 success 当前不等价于“计数已可靠提交且明细已持久化”。必须明确 API 接收语义：若改为持久化确认，需 DB 事务成功后才返回 success；若采用异步接收，则必须先把事件和幂等身份写入持久 inbox/outbox，再 ACK。

#### D. DB 计数仍有两个 read-modify-write 入口

- 缓存未命中：`record_cloak_click_count()` 读取 ShortLink ORM 对象，赋值 `(click_count or 0) + 1` 后 commit。
- 缓存命中：先对 Redis 缓存 JSON 做 get-modify-set；随后 BackgroundTasks 中 `persist_cloak_report_click(sync_short_link_click_count=True)` 再读取 ORM 值并加一提交。

两者都不是 DB 原子递增；并发事务可能覆盖增量。缓存命中分支还存在 Redis JSON 覆盖写丢更新风险。不能仅将 Redis 更新替换为 INCR 就认为 DB 计数已正确。

#### E. 建议的目标语义与修复架构

1. 为一次 click 定义稳定的 `event_id`（由桥页生成并重试复用，服务端校验格式/长度）；若客户端无法提供，需定义可验证的替代身份，不能用每次请求新生成的 UUID 作为重试幂等键。
2. MySQL 建立持久事件 inbox/ledger，至少包含 `event_id` 唯一键、`short_link_id`、接收时间、处理状态、必要的脱敏审计字段；唯一键冲突表示已接收，不能再次计数。
3. 在同一 MySQL 事务中插入事件身份并执行 `UPDATE short_links SET click_count = COALESCE(click_count, 0) + 1 WHERE id = :id`；检查 rowcount，事务提交后才标记事件完成。并发重试通过唯一键保证 exactly-once effect。
4. 若 Click 明细也必须可靠，使用同事务 outbox；独立 worker 幂等消费 outbox，不能仅依赖 FastAPI BackgroundTasks。明确 outbox 状态、重试、死信、监控和人工重放机制。
5. Redis 只作为可重建缓存/非权威加速层。DB 事务成功后失效短链缓存；失效失败记录可重试 outbox 或依靠短 TTL 明确最终一致窗口。禁止把 Redis 去重结果作为财务/统计唯一幂等凭证。
6. 定义接口 ACK：持久 inbox 事务提交后才返回“已接收”；若 DB 不可用返回可重试错误。CAPI 外部调用采用独立 outbox 和外部事件幂等键，不能因 DB 成功但外部请求失败而丢失重试。
7. 对 `session_id` 缺失、Redis unavailable、SET NX 成功后 DB rollback、commit unknown、并发重复 event_id、不同 event_id 同时到达、缓存 hit/miss、outbox worker 崩溃/重启等场景做真实 MySQL + Redis 集成/故障注入测试。

#### F. 当前结论

斗篷 /report 计数目前仍有 P1 级数据完整性风险：Redis 去重 fail-open、先去重后持久化导致无法补偿、无 session_id 时不去重、DB read-modify-write 丢增量、BackgroundTasks 非持久化，以及 success 响应可能早于可靠持久化。该路径应在上线前修复。此项与 PR #205 的 CPL Redis/DB 扣量一致性是两个独立问题，不能用其中一个的修复替代另一个。


### 5.4 与现有点击账本、CAPI Outbox 的边界复核（Head 320861d）

本轮进一步检查了 `app/core/short_link_click_counter.py`、`app/routes/short_link/handlers.py`、`app/core/third_party_report.py`、`app/services/third_party_report_outbox.py` 及对应迁移，发现仓库已经存在可复用的基础设施，修复时不能重复造一套相互竞争的计数器或发送队列。

**1. 正常短链重定向（/s/{short_code}）与斗篷 /report 是两条不同路径**

- `handlers.py` 的缓存命中和 DB 未命中两条重定向路径，都会生成本次 `click_id`，先创建 Click 记录，再调用 `increment_click_count_async(short_code, click_id=click_id)`。
- `short_link_click_counter.py` 已有 Redis Lua 原子 marker + INCR、Redis pending batch、MySQL `short_link_click_sync_batches` 唯一账本，以及 Redis 不可用时“唯一账本插入 + SQL 原子 UPDATE”的 DB 降级路径；还处理 commit-unknown 查询账本、缓存失效确认和账本 ACK。
- 因此不能把“主短链点击计数完全没有原子/幂等设施”作为结论。该路径仍需单独检查 Redis marker TTL、pending batch 刷盘/清理边界，但它不是本轮确认的 ORM lost-update 路径。
- `/report` 的 `record_cloak_click_count()` 并未调用这个计数器，仍使用 Redis JSON get-modify-set 和 ORM 读改写；这是本轮 P1 风险的实际边界。

**2. 现有 CAPI Outbox 不等于 /report 已经进入持久 Outbox**

- `third_party_report_logs` 已扩展 `outbox_enqueued`、`short_link_id`、`cloak_name`、`short_code`、`click_time`、`next_retry_time` 等字段，并有 `third_party_report_outbox` worker、租约、重试、身份绑定和 PII retention 机制。
- 但 `schedule_cloak_facebook_report()` 把 `send_third_party_report` 直接加入 FastAPI `BackgroundTasks`，调用时没有传入转化事务创建的 `report_log_id`。直接发送路径随后调用 `create_report_log()` 创建 `identity_scope='unscoped'` 的日志；该创建路径没有把 `outbox_enqueued` 置为 True。
- 因此现有 outbox worker 的持久重试能力不能自动覆盖这个 /report 直接发送路径。若进程在 BackgroundTask 开始前退出，连日志都不会创建；若任务已创建 unscoped 日志后中断，不能据此认定平台作用域 Outbox worker 会接管。
- 不能简单把该路径改为 `outbox_enqueued=True`：现有平台 Outbox 对 `platform`、`destination_pixel_id`、`event_key`、PII 清理状态和租约令牌有严格约束；必须复用现有 enqueue/worker 契约，或为 unscoped 直接发送设计独立且明确的持久接管机制，不能混淆两种身份作用域。

**3. 稳定事件身份仍是 /report 改造的前置条件**

当前路由仅接收 query 参数 `id`、`fbclid`、`email`、`phone`、`dp`、`phase`；click 去重键仅在存在 `session_id` cookie 时构造。没有客户端稳定 `event_id` / Idempotency-Key。服务端每次生成新 UUID 不能解决网络重试的幂等问题；`fbclid` 也不能在缺失时用每次新生成的 UUID 占位后再当作稳定事件身份。

**4. 推荐实施顺序**

1. 先确定 /report 的业务计数语义：同一 session 是“只计一次”还是每次真实按钮点击都计数；明确 load 与 click 是否分别幂等。不能在代码层擅自改变当前业务统计口径。
2. 修改桥页与路由协议，让同一逻辑 click 的重试复用客户端生成的稳定事件 ID；服务端校验长度、字符集和作用域。若必须兼容旧桥页，明确旧请求的降级语义，并将无法证明唯一身份的情况标记为 legacy，而非假装 exactly-once。
3. 在 MySQL 中复用或扩展合适的持久事件账本：唯一身份插入、短链原子计数更新、Click 明细 outbox enqueue 应在一个事务内完成。先做 schema/唯一键碰撞预检查，迁移不能破坏既有 `short_link_click_sync_batches` 语义。
4. CAPI 事件在同一接收事务中写入可被 worker 接管的持久记录；按现有 Outbox 的身份作用域、PII retention、目的地快照、租约与重试约束实现，不再把 FastAPI BackgroundTasks 当作唯一调度保证。
5. Redis 只承担缓存或可恢复加速；DB 提交成功后通过现有缓存失效机制处理缓存一致性。不可用 Redis 的去重标记决定是否 ACK 一次尚未持久化的点击。
6. 真实 MySQL + Redis 测试覆盖并发重复 event_id、不同 event_id 并发、commit-unknown、Redis SET NX 成功后 DB 回滚、Redis 不可用、旧桥页兼容、Click outbox 与 CAPI worker 崩溃恢复。

**本轮修正后的结论：** 主短链重定向点击计数已有专门的原子计数与 MySQL 账本设计；斗篷 /report 是独立且绕过该基础设施的路径。CAPI 仓库已有事务性 Outbox，但 /report 当前调用的是 BackgroundTasks 直接发送路径，不能把已有 Outbox 的可靠性算到该路径上。本节是代码审计结论，不代表 /report 已完成修复。
