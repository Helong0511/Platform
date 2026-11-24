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
