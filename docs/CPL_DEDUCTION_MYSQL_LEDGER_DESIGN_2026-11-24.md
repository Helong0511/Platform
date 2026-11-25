# CPL 扣量 MySQL 权威决策账本设计

**日期：** 2026-11-24  
**状态：** 设计基线，待实现与真实 MySQL 集成验收  
**关联：** Platform PR #205（Draft）；main 上已有 PR #206 的 Postback event receipt

## 1. 目标与强制原则

解决 CPL 扣量决策中 MySQL 与 Redis 分属两个事务域导致的计数漂移、重试改变决策、窗口滚动失真和并发超额问题。

必须满足：

1. MySQL 是事件身份、扣量决策结果、统计窗口和财务审计的唯一权威来源。
2. 一个规范化 Postback 事件最多产生一条持久化决策记录；重试返回第一次提交的结果，不重新抽签、不重新占用名额。
3. 决策结果、普通转化记录（如适用）、扣量审计日志、事件收据/账本状态在同一个 MySQL 事务中提交或回滚。
4. Redis 不得参与决定是否扣量、扣量额度是否已用完或事件序号。Redis 只能用于非权威缓存、监控和可重建的加速数据。
5. 24 小时统计窗口继续使用滑动窗口，不能擅自改为 48 小时或固定自然日。
6. 窗口统一采用半开区间 [window_start, window_end)，一次决策只捕获一个 window_end，所有查询共用该边界。
7. 配置 scope 必须来自最终命中的配置行，不能把请求归因的多个 ID 混合成一个 scope。
8. 数据库不可用、锁超时、身份不稳定、审计日志失败等不确定情况必须按财务安全策略 fail-closed。
9. 迁移不能伪造历史事件身份。无法可靠关联的历史扣量日志必须标记为历史未知，不得猜测补齐。

## 2. 当前实现与问题边界

### 2.1 Redis 决策状态

DeductionManager 当前使用 _DECISION_STATS_LUA 初始化 deducted baseline 并递增 decision_seq；_RESERVE_DEDUCTED_LUA 在 Redis 预留扣量名额；_incr_decision_deducted 递增 Redis deducted。DECISION_SEQ_TTL 为 2 天，而 DB 统计默认窗口为 24 小时。

这些 Redis 更新发生在 Postback 外层 MySQL 事务提交前。若扣量日志 flush 失败、转化保存失败、Cap reservation 失败或 DB commit 失败，MySQL rollback 不会自动撤销 Redis 更新，可能出现：
- 已回滚事件仍占用序号或扣量名额；
- 同一事件重试时获得不同决策；
- Redis key 过期/重启后重新初始化，状态与数据库窗口不一致；
- 48 小时 TTL 与 24 小时滑动窗口语义不一致；
- fail-open 分支无法提供财务级准确性。

### 2.2 现有事件收据

main 上已有 postback_event_receipts，唯一身份为 platform + conversion_id + normalized event_name。目前正常转化保存成功后删除临时收据；被 volume deduction 拦截的事件保留收据。

它解决了部分事件重放问题，但没有保存扣量决策、scope、窗口、配置快照和最终结果，不能直接充当统计账本。

### 2.3 必须完整计数的事件

账本不能只记录发生扣量的事件。普通转化、金额扣减转化、未命中扣量的转化和无配置事件也必须保留事件及归因，否则新配置启用时，最近 24 小时统计基线会漏算。

每个事件只计一次：
- 普通转化：一条已处理事件，扣量数为 0；
- volume deduction：一条已处理事件，扣量数为实际 deducted_volume；
- amount deduction：一条已处理事件，扣量数为 0，金额扣减独立记录；
- 同时扣量和扣金额：仍只计一条事件；
- 无扣量配置：也保留事件及归因，供之后新建/启用配置时重建窗口基线。

金额日志不能额外当成第二条转化计数。

## 3. 目标架构：升级现有 receipt 为持久化事件账本

不再创建第二张具有相同事件唯一键的 CPL ledger 表。建议扩展现有 postback_event_receipts，将其升级为所有已处理 Postback 事件的永久幂等凭证和决策账本。

避免 receipt 与 ledger 两个唯一键仲裁顺序不一致、两张表事务不一致、DuplicateChecker 与 DeductionManager 生成不同事件身份，以及正常转化释放临时 receipt 后决策信息丢失。

### 3.1 建议字段

保留现有 id、platform、conversion_id、event_name、created_at。新增字段建议如下，最终长度/精度须按真实业务上限、索引长度和 MySQL 版本验证：

| 字段 | 类型建议 | 说明 |
|---|---|---|
| decision_status | VARCHAR(32) NOT NULL | accepted、volume_deducted、amount_deducted、volume_and_amount_deducted、no_config、legacy_unknown |
| decision_at | DATETIME(6) NOT NULL | 事件接收/决策时间 |
| window_start | DATETIME(6) NULL | 本次统计窗口起点 |
| window_end | DATETIME(6) NULL | 本次统计窗口终点 |
| config_id | INT NULL | 最终命中的配置 ID；不强制 FK，避免配置删除破坏审计 |
| config_version | VARCHAR(64) NULL | 配置版本或规范化配置快照 hash |
| scope_type | VARCHAR(16) NULL | offer / advertiser / publisher |
| scope_id | BIGINT NULL | 唯一生效 scope ID |
| attributed_offer_id | BIGINT NULL | 事件归因 Offer |
| attributed_advertiser_id | BIGINT NULL | 事件归因 Advertiser |
| attributed_publisher_id | BIGINT NULL | 事件归因 Publisher |
| click_id | VARCHAR(255) NULL | 归因点击 ID，不是事件唯一键 |
| strategy | VARCHAR(50) NULL | 实际使用策略 |
| volume_ratio | DECIMAL(5,4) NULL | 决策时扣量比例快照 |
| amount_ratio | DECIMAL(5,4) NULL | 决策时扣金额比例快照 |
| processed_before | BIGINT NULL | 当前事件决策前窗口已处理数 |
| deducted_before | BIGINT NULL | 当前事件决策前窗口已扣量数 |
| deducted_volume | INT NOT NULL DEFAULT 0 | 本事件实际扣量数量 |
| deducted_amount | DECIMAL(12,4) NOT NULL DEFAULT 0 | 本事件实际扣金额 |
| original_amount | DECIMAL(12,4) NULL | 扣减前金额 |
| final_amount | DECIMAL(12,4) NULL | 扣减后金额 |
| decision_version | SMALLINT NOT NULL | 决策算法/语义版本 |

约束：
- 账本只持久化已完成决策的终态。中间态不能作为已处理事件对外可见。
- 一个事务内插入唯一收据、锁定 scope、统计、决策、写转化/扣量日志并提交终态。
- 任一异常回滚整个事务，唯一收据也回滚，重试可以重新处理。
- COMMIT 响应丢失时，必须按唯一事件身份查询账本终态恢复结果，不能重新决策。

### 3.2 事件身份规范

唯一身份继续采用 platform + conversion_id + normalized event_name，但必须先明确各平台契约：
- platform 只执行平台契约明确允许的规范化（通常 trim）；不能无依据 lower-case。
- conversion_id 是不透明标识，默认区分大小写；不得擅自改变上游语义。
- event_name 使用现有 normalize_event_name 规则，并固定默认值、大小写和空值语义。
- DuplicateChecker、账本查询、转化表唯一约束和下游 outbox 必须使用同一规范化规则。
- 唯一键列需使用明确的二进制/大小写敏感比较规则，避免默认 utf8mb4_unicode_ci 将不同标识合并。
- 必须同时核对 postback_conversions 与 postback_event_receipts 两张表的 collation；只修改其中一张不够。
- 迁移前检测已有大小写/重音冲突；有冲突时停止迁移并人工处置，不可自动合并财务事件。

#### 缺少 conversion_id

当前部分路径允许 click_id 作为 conversion_id fallback。这不是普适安全的事件身份：一个 click 可以对应多个合法转化。

实施前必须：
1. 在平台 adapter 中区分显式 conversion_id 与 fallback 值；
2. 为每个平台定义稳定唯一事件 ID 契约；
3. 有可靠上游 event ID 时使用它；
4. 无稳定唯一 ID 时不能声称 exactly-once；
5. 对启用 volume deduction 的配置，缺少稳定事件 ID 时应 fail-closed，或由业务明确禁用该扣量策略；
6. 不得仅用 click_id、时间戳或未经评估的 payload hash 作为通用替代。payload hash 可能把同一 click 下内容相同的两个真实事件错误合并。

## 4. 统计与时间窗口语义

### 4.1 窗口定义

默认仍为最近 24 小时滑动窗口：

window_start = decision_now - 24 hours  
window_end = decision_now

SQL 条件统一为 decision_at >= window_start AND decision_at < window_end。

- 不允许一处使用 <=、另一处使用 <。
- 同一次决策只读取一次 decision_now，统计与账本字段共用。
- 时间口径明确为系统接收时间，不是上游发生时间。以后若要求按 event_time 统计，必须增加独立字段、时区解析和迟到事件规则。
- 所有 Worker 必须使用相同应用时区配置；当前代码使用 get_app_now_naive()，实现时将其作为唯一时间来源并注入全链路。禁止混用 datetime.now()、系统本地时区和 UTC naive。
- 上线前核查 Windows/Ubuntu 应用时区与数据库 DATETIME 存储约定一致。

### 4.2 计数公式

对当前命中配置的 scope，查询账本所有事件（包含 no_config / accepted 等历史归因事件）：
- total = COUNT(*)
- deducted = SUM(deducted_volume)
- processed = total

scope 过滤必须按最终命中配置选择唯一维度：
- Offer：attributed_offer_id = config.offer_id
- Advertiser：attributed_advertiser_id = config.advertiser_id
- Publisher：attributed_publisher_id = config.publisher_id

禁止同时用 advertiser/offer/publisher 三个 ID 做 AND 过滤。

### 4.3 配置变化语义

延续现有业务口径：当前配置决定当前事件的策略与比例；最近 24 小时窗口基线按事件归因 scope 统计，不因历史事件当时没有配置而排除。

账本保存决策时配置快照，用于审计和复现历史结果。不能用当前配置反算历史决策。

## 5. 并发控制与事务边界

### 5.1 Scope 锁

建议使用命中的 ConversionDeductionConfig 行作为 scope mutex：
- 唯一事件收据预留成功后，在当前事务 SELECT ... FOR UPDATE 锁定配置行；
- 同一配置 scope 决策串行化，不同配置 scope 并行；
- 配置更新/停用/删除与决策使用统一锁顺序；
- 缓存 ORM config 不能视为锁定对象，必须在当前事务重新 SELECT FOR UPDATE 并校验 active、scope 唯一性和配置版本；
- 配置不存在时仍写 no_config 账本事件。为避免首次创建配置时并发漏算基线，必要时增加独立 scope lock 表或稳定归因 scope 锁行；不能依赖不存在的 config row。
- 配置层级缺失、多选、非法 ID 必须 fail-closed。

### 5.2 单事件事务顺序

1. 标准化平台、conversion_id、event_name 和归因数据。
2. 插入唯一事件收据/账本；唯一键冲突则读取已提交终态并返回重复。
3. 在当前事务重新读取并锁定命中的扣量配置/稳定 scope 锁。
4. 捕获一次 decision_now，计算 24h 半开窗口。
5. 从 MySQL 账本统计 scope 的 total、deducted。
6. 按策略确定本事件结果；事件身份必须传入策略层。
7. 写入扣量日志（如有）。
8. 普通事件保存 postback_conversions、转发 outbox、第三方 report outbox 等现有事务内记录；volume deduction 不创建正式转化，但保留账本终态。
9. 更新账本决策快照和终态。
10. 与 Postback 其它同事务业务记录一起 commit。

不得在事务提交前写入任何不可回滚的 Redis 决策计数。事务失败则全部回滚。

### 5.3 COMMIT 结果未知

若客户端收到 commit exception，不能立即假设事务回滚：
- 新 Session/连接按唯一事件键查询账本；
- 找到终态：返回该次已提交结果，不再执行扣量决策；
- 查不到：在确认事务已终止后允许安全重试；
- 数据库暂时不可查询：返回 retryable，不允许 Redis 猜测结果；
- 必须测试 TCP proxy 丢弃真实 COMMIT ACK 的情况。

## 6. 策略语义与事件身份

### 6.1 Hash / Random

当前 random 已实现为确定性 hash，不是随机数。

建议稳定决策输入为 decision_version + scope_type + scope_id + event_identity：
- 不得继续只 hash click_id；
- 同一事件重试必须得到同一结果；
- 同 click_id 的不同 event identity 必须可区分；
- 是否使用 HMAC secret 属于策略版本设计，不能随意更换，否则改变既有事件结论；
- ratio 边界使用 Decimal/整数基点，避免 float 精度误差。

### 6.2 Proportional / Round Robin

当前实现使用 (processed + 1) % interval == 0，并以 int(1 / ratio) 取间隔。这意味着：
- ratio 不是 1/N 时存在向下取整偏差；
- 当前语义是窗口内顺序计数，不是严格数学比例；
- 并发顺序必须由数据库 scope 锁确定；
- 24 小时滑动窗口中旧事件滚出后 processed 会减少，序号会回退，这是窗口语义的一部分，不能悄悄改成永久单调序号。

实施前需由产品/财务确认是否保留每 N 个扣 1 个的既有语义，还是改成累计目标差值算法。若改变，必须升高 decision_version 并提供对账说明。

### 6.3 Quota / 比例上限

若策略按 floor(total * ratio) 限制窗口扣量：
- total=0 的语义必须明确；
- limit 使用 Decimal 精确计算后转整数；
- 已扣量数从账本 SUM(deducted_volume) 得出；
- 新事件决策在 scope 锁内读取统计并写账本；
- 不能 Redis 先占名额。

## 7. Redis 的新职责

允许配置缓存、Dashboard 非权威统计缓存、监控告警和可从 MySQL 账本完全重建的辅助索引。

禁止：
- Redis sequence 决定事件顺序；
- Redis deducted 作为财务已扣量权威值；
- Redis reserve 成功就认定扣量成功；
- DB rollback 后依赖 best-effort DECR 补偿；
- Redis 不可用时静默切换到另一套扣量算法。

财务决策读取必须绕过普通统计缓存。缓存失效失败不得改变账本结果。

## 8. 数据库迁移与历史兼容

### 8.1 迁移前检查

- 检查 receipt 与 conversion 是否存在大小写/重音不敏感唯一键冲突；
- 检查重复 platform/conversion_id/event_name；
- 检查 event_name NULL/default 语义；
- 检查字符集、collation、索引长度、MySQL 版本和 DDL 算法；
- 测量大表 ALTER 锁时间、磁盘空间和复制延迟；
- 确认备份、回滚和维护窗口。

### 8.2 历史回填

- postback_conversions 可按既定规范化规则回填普通转化账本记录，但必须先检测唯一键冲突。
- 当前 volume-deducted conversion_deduction_logs 没有 platform、上游 conversion_id、event_name，不能可靠关联具体 Postback 事件。
- 已存在的 volume receipt 可以保留身份；缺少决策历史时标记 legacy_unknown，不得伪造时间、scope 或金额。
- 不能根据 click_id 猜测历史 event identity。
- 24h 窗口迁移瞬间需要双读/回填切换策略，保证迁移前后统计基线不双算、不漏算。可在维护窗口短暂停止 Postback 入站或使用明确迁移水位；不能让旧 Worker 与新 Worker 混合写入不同账本语义。

### 8.3 回滚

账本上线后，Redis 不再是财务权威源。回滚代码时不能恢复旧 Redis 决策流程并假设 Redis counters 完整。
- 保留新账本数据；
- 回退前排空所有 Worker；
- 若必须回退，使用仍读取 MySQL 账本的兼容版本，或暂停扣量并 fail-closed；
- 不删除事件收据/账本表；
- 不自动清理账本行。

## 9. 索引与性能

候选索引，最终以 EXPLAIN 和生产数据分布确认：
- UNIQUE(platform, conversion_id, event_name)
- (attributed_offer_id, decision_at)
- (attributed_advertiser_id, decision_at)
- (attributed_publisher_id, decision_at)

注意：
- 复合唯一索引总字节长度必须符合目标 MySQL/InnoDB 版本限制；如使用 identity hash 辅助唯一键，必须保留原始身份并检测 hash 冲突。
- 评估账本写入量、索引写放大、锁热点、磁盘增长、备份恢复时间。
- 不能为性能把财务决策降级到最终一致的异步聚合。
- 账本保留期须满足财务审计、争议处理和隐私政策；不能按 24 小时窗口到期即删除。

## 10. 真实 MySQL 集成测试矩阵

测试环境必须使用 MySQL 8.x、InnoDB、明确设为 REPEATABLE READ，至少两个独立连接/Session；SQLite 或 Mock 不能替代。

| 场景 | 验收标准 |
|---|---|
| 同一事件并发 2/10/50 次 | 仅一个账本终态、一个扣量日志/转化；重试返回同一决策 |
| 不同事件同 scope 并发 | 窗口计数串行正确；扣量上限不超额 |
| 不同 scope 并发 | 不发生全局串行化，结果互不污染 |
| DB rollback | receipt、ledger、conversion、deduction log 全部回滚 |
| flush 失败 | 不留下可见终态 |
| COMMIT ACK 丢失 | 按事件键恢复已提交决策，不二次扣量 |
| commit 前 worker 崩溃 | 回滚后重试可接管 |
| commit 后 worker 崩溃 | 重试读到账本终态 |
| Redis 停机/重启/清空 | 财务决策完全一致 |
| 24h 左边界 | window_start 被计入 |
| 24h 右边界 | window_end 不被计入 |
| 相邻窗口 | 边界事件不会双计 |
| 多 OS 时区 | 配置统一时结果一致；错误时区能被启动检查发现 |
| 配置变更 | 快照可审计，窗口基线不漏算 |
| 配置删除/停用并发 | 锁顺序稳定，不使用过期配置 |
| scope 不合规 | 缺失/多选/非法 scope fail-closed |
| 缺少 conversion_id | 不将 click_id 默认为通用唯一事件身份 |
| collation 大小写/重音 | 不同标识不被错误合并 |
| Deadlock / lock wait timeout | 有限退避；最终失败无重复账本 |
| 多实例并发 | 不依赖进程内锁 |
| 策略边界 | ratio=0、ratio=1、非 1/N、total=0、窗口滚动符合批准语义 |
| 金额精度 | Decimal 无 float 漂移，金额日志与账本一致 |
| 大量事件性能 | EXPLAIN 使用预期索引，锁等待和事务时长有基准 |

## 11. 实施拆分与验收门槛

### 阶段 A：事件身份与账本 schema
- 明确平台 conversion_id 契约，停止将 click_id 当通用唯一 ID。
- 评审 receipt 扩展迁移。
- 检查并统一 receipt 与 conversion 唯一键 collation。
- 增加 ORM 字段、schema 校验和 migration manifest SHA256。
- 历史回填与 legacy_unknown 策略通过 MySQL 测试。

### 阶段 B：事务化决策服务
- 引入独立服务，输入当前 AsyncSession、规范事件身份、归因快照和 payout。
- 当前事务内获取唯一事件、scope 锁、窗口统计、策略决策和终态写入。
- event identity 从 PostbackProcessor 贯穿到 DiscountChecker/DeductionManager。
- 移除 Redis 决策计数与 reservation。
- amount deduction 计算保留，但日志与账本同事务。

### 阶段 C：真实 MySQL 验收
- 完成第 10 节关键并发、故障、窗口测试。
- 运行 Full Audit 与 Emergency Security。
- 在 PR merge context（包含 main 上 PR #206）重新运行 CI。
- 检查查询计划、索引、迁移 DDL 锁风险和字符集。

### 阶段 D：部署
- 先迁移，再排空旧 Worker；
- 确认所有 Worker 使用新事务账本代码后恢复流量；
- 监控账本写入失败、duplicate rate、scope lock wait、deadlock、决策耗时；
- 进行 24h 财务对账，核对 ledger、conversion、deduction log；
- 对账完成前不启用大比例扣量策略。

PR #205 必须继续保持 Draft，直到账本实现与迁移完成、平台身份契约明确、MySQL REPEATABLE READ 多连接测试通过、Redis 故障不影响决策、rollback/commit-unknown/retry 通过、24h 窗口和金额结果验收、最新 head 的 Full Audit 与 Emergency Security 成功，并在包含 PR #206 的 main merge context 中完成集成验证。

仅 CI 通过或 GitHub 显示 mergeable，不构成财务业务正确性的验收。

## 12. 尚待业务确认的事项

- 各上游平台 conversion_id 是否区分大小写、是否允许复用、event_name 默认值；
- 无 conversion_id 平台是否支持稳定 event_id；
- Proportional / Round Robin 是否保留当前 int(1/ratio) 间隔语义；
- 24h 窗口是否继续按系统接收时间；
- 配置变化是否继续沿用最近 24h 全量归因事件作为基线；
- 账本财务/隐私保留期限及归档策略；
- 生产 MySQL 版本、字符集、collation、时区和在线 DDL 能力。

以上事项不得由实现者自行猜测；未确认前不得上线会改变扣量财务结果的简化实现。


## 13. 当前代码身份链路核查补充（2026-11-24）

本节基于 main 当前源码核对，作为实现前必须处理的兼容性事实：

1. DataNormalizer 当前 conversion_id 取值顺序为 raw_data.conversion_id、raw_data.conversionId、click_id_raw；因此缺少显式 conversion_id 时会直接把 click_id 作为 conversion_id。
2. DataValidator 当前只要求 click_id 或 conversion_id 至少有一个，不区分显式 conversion_id 与 click_id fallback；所以验证通过并不意味着事件有稳定的上游 conversion identity。
3. DataNormalizer 对 conversion_id 最后执行 str(...).strip()。由于取值使用 Python 的 or，纯空格字符串是 truthy，可能先选中空白 conversion_id，随后 strip 成空字符串，而不会回退到有效 click_id。DuplicateChecker 遇到空 conversion_id 会跳过 receipt 预留。应增加空白规范化后再做 fallback 的回归测试，并由平台契约决定此类数据是拒绝还是 fallback。
4. normalize_event_name 当前只 strip；空值映射为 default；不会 lower-case，也不会改变大小写。因此事件名大小写目前属于身份语义的一部分，不能在迁移中自行折叠。
5. DataNormalizer 将调用方传入的 platform 原样写入 normalized data；没有在该层统一 trim/lower-case。平台规范化必须在入口 adapter 明确实现，并与数据库唯一键比较规则一致。
6. DataValidator 对 ID 字符长度当前限制为 200，而 PostbackConversion 与 receipt 模型列为 VARCHAR(255)。这可以是有意设置的更严格 API 上限，并非必然缺陷；应在平台契约中明确 200 是应用层最大值，并测试 200/201 边界，避免未来误把数据库列长度当成接口允许长度。

建议在正式账本迁移前，先补齐以上身份规范化单元测试；身份规范不明确时，不应把 click_id fallback 宣称为 exactly-once。


## 14. BFT 专用处理器身份映射复核（2026-11-24）

本轮进一步检查了 main 与 PR #205 分支相同的 `app/core/postback/bft_handler.py`，发现专用处理器绕过通用 `DataNormalizer` 的身份提取逻辑，存在单独的身份映射风险：

1. `validate()` 与 `normalize()` 的字段优先级均为 `clk_id`、`click_id`、`cid`、`clickid`、`clickId`、`ClickId`，之后才是显式 `conversion_id`、`conversionId`。因此同一请求同时携带 click 标识和显式 conversion 标识时，当前实现会优先把前者写入 `conversion_id`，显式 conversion 标识被忽略。
2. 标准化结果中的 `click_id` 也直接赋值为上述同一个 `conversion_id` 值，而不是独立提取 click 字段。由此，ClickAssociator 使用的 click_id 与幂等收据使用的 conversion_id 被强制绑定为同一字符串。
3. BFT 专用处理器验证只证明上述任一字段存在且长度不超过 200，并不能证明它是上游稳定唯一的 conversion/event ID。
4. 该专用处理器当前没有调用 PR #205 通用标准化器新增的空白 conversion_id fallback helper；通用路径修复不能自动覆盖 BFT 路径。

**当前可以确定的代码事实：** 当请求同时提供不同的 click_id/clk_id 与 conversion_id 时，BFT handler 优先使用 click 类字段作为 conversion_id，并将同一值同时写入 click_id。  
**当前不能确定的业务事实：** BFT 上游对 `clk_id`、`cid`、`conversion_id` 的正式定义、唯一性范围、是否允许一条 click 产生多条 conversion，以及 event_id 是否存在。没有官方接口文档或已确认的上游 payload 契约，不得擅自改变字段优先级或把任一字段宣布为稳定事件 ID。

### BFT 账本接入前置条件

- 获取并归档 BFT 上游官方 Postback 字段说明，或由业务方确认并留存真实脱敏请求样例及字段契约。
- 分别定义 `extract_click_id()` 与 `extract_event_id()`；click 归因字段不得自动成为事件唯一身份。
- 显式 conversion/event ID 存在时，必须有测试证明它不会被 click 字段覆盖。
- 只有 click ID 而没有稳定事件 ID 时，明确标记为 identity_unverified；启用 volume deduction 的请求不得进入声称 exactly-once 的账本流程，应按经批准的 fail-closed/禁用策略处理。
- 添加 BFT 专用测试：仅 click ID、仅 conversion ID、二者同时存在且不同、空白显式 ID、event_name 缺省/大小写、长度 200/201，以及同 click 下两个不同 conversion 的并发重放。
- 在 BFT 身份契约完成前，不对现有历史 BFT receipt 做自动重键、合并或回填。

这项发现是独立于通用 DataNormalizer 空白值修复的 adapter 级问题，不能因为 PR #205 的通用路径测试通过而视为已解决。


## 15. 历史 NULL event_name 与唯一键防重缺口（2026-11-24）

对照 main 的 `app/models/postback.py`、`app/core/postback_event_name.py`、`app/core/postback/validators/duplicate_checker.py` 和 receipt migration，发现正式转化表与 receipt 的身份列约束并不完全一致：

1. `PostbackConversion.event_name` 在 ORM 中为 nullable；正式转化唯一约束是 `(platform, conversion_id, event_name)`。
2. MySQL 官方文档明确说明：包含可空列的 UNIQUE index 允许存在多条 NULL 值。因此，正式转化表的复合唯一键不能阻止同一 platform/conversion_id 对应多条 event_name=NULL 的历史记录。
3. `normalize_event_name(None)` 会把新请求的空事件名映射为 `default`；DuplicateChecker 也只按规范化后的 `default` 查询，不会匹配历史 `event_name IS NULL` 的记录。
4. receipt migration 将 `event_name` 定义为 NOT NULL，和正式转化表的历史可空语义不同。只依赖两张表各自的唯一键，无法自动封闭旧 NULL 行的重放窗口。

### 迁移前必须执行的只读检查

```sql
-- 历史 NULL 事件名数量
SELECT COUNT(*) AS null_event_name_rows
FROM postback_conversions
WHERE event_name IS NULL;

-- NULL 事件名是否已有同一 platform/conversion_id 多条记录
SELECT platform, conversion_id, COUNT(*) AS row_count
FROM postback_conversions
WHERE event_name IS NULL
GROUP BY platform, conversion_id
HAVING COUNT(*) > 1;

-- 将 NULL 映射为 default 后是否会与现有 default 记录冲突
SELECT a.platform, a.conversion_id,
       COUNT(*) AS conflicting_rows
FROM postback_conversions a
JOIN postback_conversions b
  ON b.platform = a.platform
 AND b.conversion_id = a.conversion_id
 AND b.event_name = 'default'
WHERE a.event_name IS NULL
GROUP BY a.platform, a.conversion_id;
```

以上检查必须在真实生产数据库执行并保存结果；当前无法从仓库源码推断生产数据中是否确实存在这些行。

### 修复/迁移约束

- 不得在未检测冲突前直接批量执行 `UPDATE ... SET event_name='default' WHERE event_name IS NULL`。
- 若 NULL 与 default 发生冲突，必须人工确认历史事件语义和保留记录，不能自动合并财务事件。
- 对确认可映射的历史行，在维护窗口/事务化迁移方案中统一成明确的非空默认值，再将 ORM 和数据库列约束改为 NOT NULL。
- 迁移后必须测试缺失 event_name 的重复回调，确保历史事件、receipt 和 conversion 表对同一身份采用一致规则。
- 若业务决定 NULL 与 default 代表不同事件，必须改用显式、稳定且全链路一致的身份编码；不能让 MySQL NULL 唯一键语义隐式决定业务规则。

MySQL 官方依据：CREATE INDEX / CREATE TABLE 对 UNIQUE index 允许多个 NULL 的说明：  
https://dev.mysql.com/doc/refman/8.4/en/create-index.html  
https://dev.mysql.com/doc/refman/8.4/en/create-table.html


## 16. 当前确定性策略键的重试稳定性缺陷（2026-11-24）

进一步检查 PR #205 分支 `DeductionManager.apply_deduction()` 和 `DeterministicHashDeductionStrategy.should_deduct()`，确认当前决策键仍不是事件级身份：

1. `apply_deduction()` 当前使用 `decision_key = click_id`；同一 click 下的多个不同 conversion/event 会得到相同 hash bucket，无法作为独立事件进行确定性抽样。
2. 当 click_id 缺失时，fallback 为 `offer:{offer_id}:seq:{stats.processed}`。而 `_get_stats_for_decision()` 在 Redis Lua 中先执行 INCR，返回的 seq 每次请求都会增长；同一事件重试会获得新的 sequence fallback，可能改变 hash 结果。
3. sequence 本身在 DB commit 前已递增；若本次事件后续回滚，重试仍会拿到新 sequence。即使 MySQL receipt 已在同事务回滚，也不能保证扣量决策重放一致。
4. Proportional / Round Robin 直接使用 `stats.processed + 1`，其序号同样依赖 Redis 请求次数，而非已提交的唯一事件账本数量。

### 必须满足的修复条件

- 决策键只能由规范事件身份构造，建议包含 decision_version、scope_type、scope_id、platform、conversion_id、event_name；字段编码必须无歧义（长度前缀/规范 JSON 等），不得简单拼接可能含分隔符的原始字符串。
- click_id 只用于点击归因，不能替代 event identity。
- 无稳定 event identity 的事件不得生成伪造的 sequence fallback；按平台批准的身份策略拒绝/隔离或禁止 volume deduction。
- 顺序策略的 processed 必须是当前 24h 窗口内已提交账本事件数，并在数据库 scope 锁内计算；不能把每次 HTTP 请求次数当作事件序号。
- 同一事件的重试必须在决策前命中唯一账本并返回已提交决策；任何未提交事件都不得影响后续事件统计。
- 增加回归测试：同 click 两个 conversion 的决策输入不同；缺失 click 不允许 fallback 到 request sequence；同一事件 rollback 后重试身份一致；同事件并发只产生一次决策；顺序策略只计入已提交事件。

在 MySQL 账本方案完成前，当前 deterministic hash 只能保证“相同 click_id 的哈希结果相同”，不能保证“相同 Postback 事件重试结果相同”，也不能正确区分同一 click 下的不同事件。


### 15.1 仓库 schema 快照与 receipt migration 的默认 collation 不一致

继续检查 `sql/platform.sql` 中 `postback_conversions` 的建表定义，确认仓库 schema 快照使用：

```sql
ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
```

而 main 的 `sql/migrations/20261124_postback_event_deduction_receipts.sql` 为 `postback_event_receipts` 显式指定：

```sql
ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
```

因此仓库内两张事件身份表的默认字符串比较规则已经存在版本差异。不能假设两张表的唯一键对大小写、重音、Unicode 等价字符及排序权重拥有完全一致的判等语义。该差异是仓库 schema/migration 的确定事实；生产数据库是否与仓库快照一致仍需实际查询确认。

迁移前必须在目标 MySQL 执行并保存：

```sql
SHOW CREATE TABLE postback_conversions;
SHOW CREATE TABLE postback_event_receipts;

SELECT TABLE_NAME, COLUMN_NAME, CHARACTER_SET_NAME, COLLATION_NAME,
       IS_NULLABLE, COLUMN_TYPE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('postback_conversions', 'postback_event_receipts')
  AND COLUMN_NAME IN ('platform', 'conversion_id', 'event_name')
ORDER BY TABLE_NAME, ORDINAL_POSITION;
```

不得仅通过修改 ORM Column 定义推断现有表已变更；必须由受控 migration 显式修改数据库列 collation，并在迁移前扫描新旧 collation 下的身份冲突。统一采用何种 collation（binary、明确的 *_as_cs，或业务批准的大小写不敏感规则）须结合上游 ID 契约、MySQL 版本和索引长度决定，不在本轮猜测。


## 17. 无配置事件与配置创建并发：稳定 Scope Mutex 协议（2026-11-24）

第 5.1 节指出“配置不存在时不能依赖不存在的 config row”。本节将该要求具体化，避免 no_config 事件与首次创建/启用配置并发时漏入 24h 基线。

### 17.1 为什么只锁命中的配置行不够

假设 Offer 还没有扣量配置：
- Postback A 关联该 Offer，查询不到配置，准备写入 `no_config` 事件；
- 管理员同时创建 Offer 级扣量配置；
- 若 A 没有锁任何稳定 scope 行，配置创建与 A 的 ledger commit 可以交错；
- 新配置生效后的首个 Postback 可能在 A commit 前完成统计查询，从而漏掉 A；A 虽然稍后进入账本，但此前的决策已按不完整基线执行。

因此，只有“命中配置行 SELECT FOR UPDATE”无法保护无配置事件和配置首次创建之间的竞态。

### 17.2 推荐的稳定 Scope Lock 表

建议新增轻量 mutex 表（不是第二张事件账本）：

```sql
CREATE TABLE conversion_deduction_scope_locks (
    scope_type VARCHAR(16) NOT NULL,
    scope_id BIGINT NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (scope_type, scope_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

最终字符集/collation 应按项目统一 schema 规范确定；scope_type 建议使用受控 ASCII 值。锁表只存稳定锁键，不存统计数据或财务决策。

### 17.3 事件事务锁定协议

每个 Postback 在当前 MySQL 事务中：
1. 根据服务端可信归因，收集所有非空候选 scope：Offer、Advertiser、Publisher。
2. 按固定顺序（例如 scope_type 字典序，再按 scope_id 升序）处理，避免不同请求采用不同锁顺序。
3. 对每个 scope 执行幂等建行（`INSERT ... ON DUPLICATE KEY UPDATE`，更新值必须保持无业务副作用），随后 `SELECT ... FOR UPDATE` 锁定该 scope lock row。
4. 完成 scope locks 后，再重新从数据库读取当前有效配置并锁定命中配置行；不能使用配置缓存对象作为锁。
5. 在持有锁期间写入 no_config 或正式决策账本终态，并与 Postback 其它记录一起提交。

一个事件最多锁定 3 个候选 scope；未归因的直连事件没有可匹配的当前三层配置，不得伪造 scope ID。

### 17.4 配置 CRUD 必须遵守相同协议

创建、启用、停用、修改比例/策略、改变层级归属和删除配置的服务必须：
- 先锁定该配置所属的同一个稳定 scope lock row；
- 再执行配置行写入/更新/删除；
- 与事件路径使用相同的锁顺序；
- 提交后再清理配置缓存（缓存失效不能代替数据库锁）。

这样：
- 若 no_config 事件先获得 scope lock，配置创建必须等待事件账本提交；新配置后续决策能读到该事件。
- 若配置创建先获得 scope lock，事件必须等待配置提交；事件随后读取新配置并按新配置处理。
- 配置变更与事件决策在同一 scope 上具有明确的串行顺序。

### 17.5 必测并发场景

- 首次创建 Offer 配置与同 Offer no_config Postback 并发；
- 首次创建 Advertiser 配置与归因事件并发；
- 首次创建 Publisher 配置与归因事件并发；
- 配置启用/停用与 Postback 并发；
- 同一事件携带多个归因 ID，不同请求以不同到达顺序竞争锁；
- 两个事件以相反输入顺序锁定不同 scope，验证固定排序避免死锁；
- scope lock 行首次创建的 2/10/50 并发；
- 锁超时/死锁回滚后事件重试不产生残留计数。

如果现有配置 CRUD 路径无法统一接入此锁协议，则账本上线前必须暂停并发配置变更或提供维护窗口，不能只在 Postback 路径加锁后宣称竞态已解决。

## 18. 配置 CRUD 未接入 Scope Mutex，且激活配置唯一性仅靠应用层检查（2026-11-24）

本轮直接检查了扣量配置 ORM、DDL、服务层、API 路由、配置缓存和 Postback 配置查找路径。第 17 节的 Scope Mutex 目前仍只是设计要求，当前运行时代码没有实现该协议。

### 18.1 已核实的配置写入入口

当前扣量配置写入集中在 `app/services/cpl/conversion_deduction_service.py`：

| 操作 | 服务方法 | 当前行为 |
|---|---|---|
| 创建 | `create_deduction_config` | 先检查目标和激活配置，再 INSERT/flush |
| 单条更新 | `update_deduction_config` | 先按 ID 读取配置，再修改字段并 flush |
| 单条启停 | `update_deduction_config_status` | 先按 ID 读取配置，再修改 is_active 并 flush |
| 单条删除 | `delete_deduction_config` | 先读取配置，再 DELETE/flush |
| 批量启停 | `batch_update_status` | 先批量读取配置，再执行 UPDATE ... WHERE id IN (...) |
| 批量删除 | `batch_delete` | 先批量读取配置，再执行 DELETE ... WHERE id IN (...) |

API 路由位于 `app/api_v1/cpl/conversions/deductions.py`。上述六条服务写路径均未获取 `conversion_deduction_scope_locks` 行锁，也没有在锁内重新校验目标 scope 与配置状态。批量操作尤其不能遗漏：必须先读取并规范化全部目标 scope，去重后按统一顺序加锁，再执行批量 DML。

配置缓存的 Generation 失效不能替代数据库互斥锁。当前配置读取会先读 Generation，再按 Offer/Advertiser/Publisher 查询缓存或数据库；缓存对象本身也不能提供事务锁定语义。

### 18.2 新发现：同一 scope 的激活配置可能并发重复创建

创建路径调用 `deduction_helpers.check_existing_config()`，其逻辑是先 SELECT 是否存在同 scope 的 active 配置，再 INSERT。检查与插入之间没有 scope 锁，也没有数据库唯一约束。

仓库 `sql/platform.sql` 的 `conversion_deduction_configs` 表定义目前只有主键、三个 scope 普通索引、状态/优先级索引和外键，没有对“每个 scope 最多一条 active 配置”实施唯一约束。ORM `__table_args__` 同样只有普通索引。

因此两个并发创建请求可以同时：
1. 查询到该 scope 尚无 active 配置；
2. 分别通过 `check_existing_config()`；
3. 插入两条 active 配置并提交。

随后 `DeductionConfigCache._load_from_db()` 使用 `ORDER BY priority DESC LIMIT 1` 取其中一条；若优先级相同，当前查询没有稳定的第二排序键，命中配置可能随执行计划/数据布局变化。该问题会让同一 scope 的扣量比例和策略不确定，属于财务决策正确性风险。

### 18.3 修复要求

实现账本前，必须同时完成：

1. 六条配置写路径全部接入第 17 节 Scope Mutex。单条更新/删除先读取旧 scope，再加锁并重新读取行；若允许改变 scope（当前 Update Schema 暴露 level/target_id 字段，但 service 当前忽略这两个字段），必须同时锁旧、新 scope 并按统一顺序排序。若不支持迁移 scope，应在 API schema 明确禁止，而不是静默忽略。
2. 批量启停/删除先加载所有配置，收集 scope 键、去重、排序后统一加锁；锁内重新读取并确认目标集合未变化，再执行 UPDATE/DELETE。
3. 创建路径必须在目标 scope lock 内执行“检查 active 配置 + INSERT”，并且 Postback 的 no_config 事件路径也使用同一把锁。
4. 对广告主、Offer、Publisher 父实体的删除路径做全仓库审计。当前配置外键使用 `ON DELETE CASCADE`，父实体删除可能绕过这六条配置服务方法而直接级联删除配置。父实体删除必须遵循相同 Scope Mutex，或在扣量配置存在时拒绝删除并要求先显式处理配置。
5. 增加数据库层防御，避免未来漏接锁的写入口再次制造重复 active 配置。可评估 MySQL 支持版本后使用 enforced CHECK 约束保证三个 scope 字段恰好一个非空，并使用 generated active-scope key + UNIQUE 约束（inactive 行生成 NULL）实现每个 scope 最多一条 active 配置；迁移前必须检测并人工处理现存零/多 scope 和重复 active 数据。不能直接加唯一索引后让生产 DDL 失败或自动删除配置。
6. 配置查找查询增加确定性排序（例如 priority DESC, id ASC），作为异常数据尚未完全清理期间的稳定性保护；但这只是兜底，不替代唯一性约束。
7. 配置写入、scope lock、Generation Outbox 变更必须处于同一个 MySQL 事务；缓存刷新在事务提交后执行或通过现有可靠 Outbox 完成。

### 18.4 必测场景

- 同一 Offer/Advertiser/Publisher scope 并发创建 2/10/50 次，最终最多一条 active 配置；
- 两个创建请求不同 priority 并发，结果不允许出现重复 active 配置；
- 单条比例更新与同 scope Postback 决策并发；
- 单条启停/删除与 Postback 决策并发；
- 批量启停/删除同时覆盖多个 scope，验证统一排序、无死锁且不漏锁；
- 两个批量操作包含相同 scope 但输入 ID 顺序相反，验证无死锁；
- 父实体删除与 no_config Postback/配置决策并发，验证级联删除不会绕过 scope 锁；
- DB rollback 后配置和 Generation 均不变；
- 迁移前重复 active 数据扫描、清理审计与数据库约束验证；
- 缓存命中旧 Generation、缓存写入与配置提交交错时，Postback 最终只能使用锁内确认的配置版本。

**当前结论：** 该风险已由仓库代码与 DDL 静态核查确认；不是已经修复的运行时问题。第 17 节 Scope Mutex 不能标记为完成，直到六条服务写路径、父实体级联删除路径和数据库唯一性防线均已实现并通过真实 MySQL 并发测试。

### 18.5 父实体删除路径复核：Offer / Publisher 删除会触发配置级联删除

继续追查了 main 分支父实体服务的实际删除实现：

- `app/services/cpl/offer_service.py::delete_offer` 只检查关联 Click 数量；若没有点击记录，执行 `db.delete(offer)`。它没有检查或锁定 `ConversionDeductionConfig.offer_id` 对应配置。
- `app/services/cpl/publisher_service.py::delete_publisher` 只检查 `OfferPublisherAssignment`；若没有分配记录，执行 `db.delete(publisher)`。它没有检查或锁定 `ConversionDeductionConfig.publisher_id` 对应配置。
- `app/services/cpl/advertiser_service.py::delete_advertiser` 会阻止仍有关联 Offer 的广告主删除，但没有检查广告主级扣减配置；无关联 Offer 但仍有 advertiser 级配置时，仍可能进入父实体删除。
- `sql/platform.sql` 中三个扣减配置外键均定义为 `ON DELETE CASCADE`。

因此 Offer、Publisher 的父实体删除路径已确认可以在未走 `ConversionDeductionService` 的情况下级联删除扣量配置；Advertiser 删除路径也存在配置未被显式保护的缺口（是否能成功还受其它外键/业务关联约束影响）。这不是理论上的“可能有其他入口”，而是已定位到具体 service 方法。

账本实施前应选择并统一一种策略：
1. 父实体删除前，收集对应扣减配置 scope 并按固定顺序获取 Scope Mutex；在锁内重新检查并拒绝删除，要求管理员先显式停用/删除扣减配置；或
2. 在同一事务中安全处理关联配置，但必须确保账本历史快照不受 FK 级联影响，且与 Postback 决策使用同一 scope lock。

更安全的默认行为是：存在扣减配置时拒绝父实体删除，要求先显式处理配置；不能让 FK cascade 静默移除财务策略。父实体删除的 2/10/50 并发测试也必须覆盖正在处理的 no_config 事件和配置决策。

## 19. 配置 DB 查询异常可能被吞成“无配置”，绕过 fail-closed（2026-11-24）

本轮继续检查配置缓存读取错误路径，发现一个独立于 Redis 统计的 fail-closed 缺口：

- `app/core/deduction/deduction_cache.py::DeductionConfigCache._load_from_db()` 对数据库查询使用 `try/except Exception`，捕获异常后记录日志并返回 `None`。
- `DeductionConfigCache.get_config()` 将该返回值直接作为“没有配置”返回给调用方。
- `DeductionManager.find_config()` 只有在异常真正向外传播时，才会根据 `settings.DEDUCTION_FAIL_OPEN` 决定返回 None 或 raise。
- 因此 DB 查询异常如果发生在最后一个待查 scope（例如本次只有 publisher_id，或前面 scope 均未命中、publisher 查询失败），异常会在 `_load_from_db` 内被转换成 None；`find_config` 随后正常返回 None。即使 `DEDUCTION_FAIL_OPEN=false`，调用方也可能把“配置查询失败”当成“确实没有扣减配置”，继续正常入库/转发，漏执行已配置的扣量或扣金额策略。

这不是“fail-open 模式允许跳过策略”的问题，而是 fail-closed 模式无法识别数据库故障。尤其当目标 scope 本来存在 active 配置时，DB 查询失败不应等价于配置不存在。

### 19.1 修复要求

1. 对已知 scope 的数据库读取失败必须向上传播明确异常（例如 `DeductionConfigLoadError`），不得返回 None。
2. 只有 SQL 查询成功且结果为空时，才允许返回 None 表示“确实无配置”。
3. Redis 缓存读取失败可以按策略回源 MySQL；MySQL 回源失败必须遵守 `DEDUCTION_FAIL_OPEN`：fail-closed 时拒绝继续处理，fail-open 时才可明确记录“配置不可用并跳过扣减”的降级状态。
4. 未知 level、缓存反序列化失败和 DB 连接/查询失败应区分分类；不能把所有异常折叠成无配置。
5. 如果 SQLAlchemy Session 已进入 failed transaction，必须由 Postback 外层统一 rollback；不得捕获异常后继续在同一 Session 上执行其它 scope 查询。
6. 日志不得输出敏感请求字段；记录 scope type/id、异常类型、降级模式和 correlation/event identity 即可。

### 19.2 必测回归

- 仅 publisher_id 存在、配置缓存 miss、MySQL SELECT 抛异常、`DEDUCTION_FAIL_OPEN=false`：必须抛出并回滚，不得返回 no_config。
- Offer/Advertiser 查询正常但未命中，Publisher 查询失败：必须 fail-closed。
- DB 查询成功且无配置：正常返回 None 并记录 no_config。
- `DEDUCTION_FAIL_OPEN=true` 且 DB 查询失败：允许按批准策略跳过扣减，但必须产生可观测降级结果，不能伪装成“没有配置”。
- Redis 缓存不可用但 MySQL 正常：应按设计回源，不得误判无配置。
- SQLAlchemy flush/SELECT 失败导致 Session 失效后，不得继续复用该事务处理 Postback。

**当前结论：** 已确认异常吞噬路径存在于代码；尚未修改运行时代码，也未声称该缺陷已修复。该问题必须在 PR #205 的财务事务重构/配置读取重构中一并关闭。

### 18.6 补充确认：单条更新/启用也可顺序制造重复 active 配置

进一步核对 `ConversionDeductionConfigUpdate` 与两个更新方法后，发现重复 active 配置不只来自并发创建：

- `app/schemas/cpl/deduction.py::ConversionDeductionConfigUpdate` 允许传入 `is_active`。
- `ConversionDeductionService.update_deduction_config()` 对传入字段直接 setattr；没有在 `is_active` 从 false 变 true 时调用 `check_existing_config()`。
- `update_deduction_config_status()` 同样直接设置 `config.is_active = is_active`，没有检查同 scope 是否已有另一条 active 配置。
- 因此即使没有并发，只要同 scope 已有 active 配置 A，再把 inactive 配置 B 启用，当前服务也可能成功产生两条 active 配置。

修复时不能只给 create 路径加锁/检查。创建、通用 PUT 更新中的 is_active 变更、PATCH status 启用、批量启用必须共用同一个 scope lock 和唯一性校验；批量启用应先验证整个目标集合不会在同一 scope 内互相冲突，也不会与集合外已有 active 配置冲突，再统一更新。停用操作则需同样持锁，避免与并发启用/决策交错。

建议在目标 MySQL 执行以下只读检查，迁移前保存结果并人工处理冲突：

```sql
-- 发现 scope 字段不是“恰好一个非 NULL”的历史配置
SELECT id, advertiser_id, offer_id, publisher_id,
       (advertiser_id IS NOT NULL)
       + (offer_id IS NOT NULL)
       + (publisher_id IS NOT NULL) AS scope_count,
       is_active
FROM conversion_deduction_configs
WHERE (advertiser_id IS NOT NULL)
    + (offer_id IS NOT NULL)
    + (publisher_id IS NOT NULL) <> 1;

-- 查找重复的 active Advertiser / Offer / Publisher 配置
SELECT 'advertiser' AS scope_type, advertiser_id AS scope_id,
       COUNT(*) AS active_count
FROM conversion_deduction_configs
WHERE is_active = 1 AND advertiser_id IS NOT NULL
GROUP BY advertiser_id HAVING COUNT(*) > 1
UNION ALL
SELECT 'offer', offer_id, COUNT(*)
FROM conversion_deduction_configs
WHERE is_active = 1 AND offer_id IS NOT NULL
GROUP BY offer_id HAVING COUNT(*) > 1
UNION ALL
SELECT 'publisher', publisher_id, COUNT(*)
FROM conversion_deduction_configs
WHERE is_active = 1 AND publisher_id IS NOT NULL
GROUP BY publisher_id HAVING COUNT(*) > 1;
```

这些 SQL 只检查当前数据库快照，不会自动修复；生产执行前应确认只读权限、备份查询结果，并由业务方确定保留哪条策略。不能按最高 priority 自动删除其它财务配置。

## 20. REPEATABLE READ 下 Generation 与 Scope Lock 混用会读到不同版本（2026-11-24）

本轮对 `DeductionConfigCache`、`get_cache_generation()` 和 MySQL 隔离级别做了联合核查。

当前实现事实：
- `DeductionConfigCache._get_generation()` 通过普通 SELECT 读取 `cache_namespace_generations`，并在该 Cache 实例内缓存 generation。
- `get_config()` 用该 generation 拼 Redis key；缓存 miss 后，`_load_from_db()` 仍用普通 SELECT 读取配置。
- 当前配置服务在同一业务事务中更新配置并调用 `advance_cache_generation()`；generation UPDATE 与 Outbox 在同一事务内。

如果 Postback 事务使用 MySQL InnoDB 默认 `REPEATABLE READ`，普通 SELECT 使用事务一致性快照。事务第一次普通 SELECT 建立 read view 后，即使后续获得了某个 Scope Mutex 行锁，后续普通 SELECT 仍可能继续读取旧快照；而 `SELECT ... FOR UPDATE` / UPDATE 使用当前锁定读语义。MySQL 官方文档明确说明了普通一致性读与锁定读可能看到不同状态，不建议在同一 REPEATABLE READ 事务中混合后却假设两者是同一个数据库版本。

这意味着第 17 节不能只增加一条 Scope Mutex 锁：
1. Postback 在加锁前若已读取旧 Generation，可能选中旧 generation cache key；
2. 加锁后若继续使用普通 SELECT 配置查询，可能仍读到旧 read view；
3. 如果锁内改用当前读读取配置，却仍使用事务旧快照的 generation，配置与缓存版本又不匹配；
4. 因此“锁成功”不自动意味着配置和 Generation 读取一致。

### 20.1 必须明确的事务读取协议

建议采用一个清晰、可验证的协议，而不是混合普通 SELECT 与锁定读：

- Postback 对候选 scope 加锁前，不得读取配置 Generation、配置缓存或扣量统计快照。
- 获取 Scope Mutex 后，以当前读方式读取配置与相关权威版本；必要时对配置行使用 `SELECT ... FOR UPDATE`，并保证所有写路径使用同一锁顺序。
- 对 generation 也必须定义与 scope lock 一致的读取规则。可选方案包括：将 generation 版本按 scope 拆分并随 scope 锁读取；或采用统一的 DB 事务/隔离级别方案，明确保证读配置、读 generation、写账本使用同一可见版本。
- 若使用 `READ COMMITTED`，必须明确它对统计查询、重复读取和并发事件的影响，并通过真实 MySQL 测试验证；不能只通过修改连接默认隔离级别解决。
- 不允许在锁定读拿到新配置后，再从旧 generation 的 Redis key 取出旧配置。
- 对配置写入，Scope Mutex、配置 DML、generation 更新和 Outbox 必须处于同一事务；提交后才能让后续事务看到新版本。
- 对 Postback，锁内读取到的配置版本必须写入最终决策账本，便于重放和审计。

### 20.2 必测交错时序

- Postback 先建立 REPEATABLE READ 快照，管理员更新配置并提交，Postback 随后获得 scope lock：必须按定义的线性化顺序读取配置，不能混合旧 generation 和新配置。
- Postback 先获得 scope lock，管理员更新配置等待：Postback 使用旧配置完成并提交，随后管理员更新；结果必须符合锁顺序。
- Postback 锁内读配置期间，generation 更新事务并发提交：不得发生配置/Generation 版本错配。
- Redis 中仍存在旧 generation 缓存时，Postback 必须只读取锁定协议所确定的版本。
- 多个 Offer/Advertiser/Publisher scope 组合时，锁顺序一致且没有死锁。
- 在 MySQL REPEATABLE READ 和 READ COMMITTED 两种真实隔离级别分别运行测试，明确最终生产采用的隔离级别与理由。

官方参考：MySQL 8.4 InnoDB Transaction Isolation Levels，说明 REPEATABLE READ 普通一致性读取使用首次读取建立的快照，锁定读使用不同锁语义；官方也明确提醒不要在同一 REPEATABLE READ 事务中混用两种读取而假设状态一致。

**当前结论：** 第 17 节 Scope Mutex 设计还缺少 Generation/read-view 协议，不能直接按“加锁后重新 SELECT”就认定问题解决。该问题必须在运行时代码实现前定稿，并用真实 MySQL 隔离级别测试验证。



## 21. 扣量配置缓存异常边界不正确：缓存故障与数据库故障混为一类（2026-11-24）

继续沿 PR 分支的真实代码检查 `DeductionConfigCache.get_config()` 与 `DeductionManager.find_config()`，确认配置读取链存在三种不同故障被混淆的问题：

1. `get_config()` 调用 `get_cached()` 时没有隔离 Redis 读取异常。Redis 短暂不可用会直接中断配置读取，没有按“缓存非权威、MySQL 为回源来源”的方式继续查询数据库。
2. `_load_from_db()` 捕获所有异常并返回 `None`。这会把 MySQL 查询失败伪装成“当前 scope 没有激活配置”，绕过上层 fail-closed 判断。
3. `_save_to_cache()` 在数据库已成功读取配置后执行；若 Redis 写缓存失败，异常会继续向上传播。缓存写入属于性能优化，不应使一次成功的数据库配置读取失败。
4. `find_config()` 又对整个配置查找过程捕获异常；在 `DEDUCTION_FAIL_OPEN=true` 时返回 `None`。这可以是明确批准的业务降级，但当前返回值无法区分“数据库确认无配置”和“配置系统不可用后跳过策略”，缺少可审计的降级结果。

### 21.1 必须拆分的故障语义

| 操作 | 故障处理 |
|---|---|
| Generation 权威版本 DB 读取失败 | 不能使用任意旧版本；按扣量 fail-open/closed 策略处理并记录降级 |
| Redis 缓存 GET 失败 | 记录缓存故障，直接回源 MySQL |
| Redis 缓存值损坏/反序列化失败 | 记录缓存污染，回源 MySQL；不得返回“无配置” |
| MySQL 配置 SELECT 失败 | 明确抛出配置加载异常；fail-closed 必须中止，fail-open 才允许显式降级 |
| MySQL SELECT 成功且无记录 | 才能返回 `None` 表示 no_config |
| Redis 缓存 SET 失败 | 记录告警，不影响已经成功读取的 DB 配置 |
| 未知 level / 非法 scope | 参数或程序错误，不能当成 no_config |

注意：当前 Generation 来自 MySQL 权威表，因此 Redis 配置缓存故障可以回源，但 Generation DB 读取失败不能简单使用旧缓存键绕过；应由最终事务读取协议决定是否终止或显式降级。

### 21.2 推荐代码边界

- 将 Redis GET、Redis SET、缓存反序列化、MySQL SELECT 分别置于独立错误边界。
- `_load_from_db()` 不捕获数据库异常并返回 None；SQLAlchemy 异常应携带 scope 信息向上抛出专用异常，外层负责 rollback。
- 缓存 GET 失败时继续执行 DB SELECT；缓存 SET 失败仅记录告警。
- `find_config()` 不应以裸 `None` 表示 fail-open 降级。可返回带状态的结果对象（例如 `found` / `not_found` / `unavailable_skipped`），或抛出可识别异常由 Postback 入口明确决定是否跳过扣量；无论采用哪种接口，都必须写入结构化审计/指标。
- 当 SQLAlchemy Session 已进入 failed transaction，必须立即交由外层 rollback；不得继续查下一个 scope。
- 缓存反序列化后的 ORM 对象不得被当作锁定读结果。最终决策仍需遵守第 20 节的数据库可见性协议。

### 21.3 必测场景

- Redis GET 抛连接异常、MySQL SELECT 成功且命中配置：必须返回数据库配置。
- Redis GET 抛异常、MySQL SELECT 成功且无配置：必须返回真实 no_config。
- Redis GET 返回损坏结构：丢弃缓存并回源 DB。
- Redis SET 抛异常、MySQL SELECT 命中：必须仍返回 DB 配置。
- MySQL SELECT 抛异常且 fail-closed：必须中止 Postback 并 rollback。
- MySQL SELECT 抛异常且 fail-open：允许显式降级，但必须区分 unavailable 与 no_config，并产生可观测记录。
- Offer/Advertiser 已查询未命中、Publisher DB 查询失败：不得继续把失败当成 no_config。
- Generation DB 读取失败：不得读取旧 generation 缓存冒充当前配置。
- Session 因 SQLAlchemy 数据库异常进入 failed state：确认外层 rollback 后才允许重试。

**当前结论：** PR 分支中的缓存 GET、DB SELECT、缓存 SET 三条路径仍未按上述边界隔离；`_load_from_db()` 的异常吞噬仍存在。该项属于运行时代码缺陷，本轮仅补充审计设计，未修改代码，不能标记为已修复。


## 22. Postback 事件身份提取仍混淆 click_id 与 conversion_id（2026-11-24 追加）

本节为对当前 PR Head `d4dc1c8e2b6db470f3507f303513f4f9ca08308c` 的再次静态核查结果。以下问题由当前分支代码直接确认，不能视为已修复。

### 22.1 通用标准化器把点击 ID 回退成转化事件 ID

文件：`app/core/postback/transformers/normalizer.py`

- `_extract_conversion_id()` 首先读取显式 `conversion_id` / `conversionId`，未找到时直接返回 `_extract_click_id()`。
- 因此缺少显式事件 ID 时，click_id 会被伪装成 conversion_id。
- 同一点击对应多个购买/注册/激活事件时，多个真实事件可能被合并为同一个身份；这与 PR #206 的唯一事件身份 `platform + conversion_id + event_name` 不兼容。
- `normalize()` 对缺失 conversion ID 使用 `str(conversion_id or '').strip()`，最终可能生成空字符串，而不是明确的缺失状态。

### 22.2 BFT 专用处理器优先级错误且丢失独立 click_id

文件：`app/core/postback/bft_handler.py`

- `validate()` 与 `normalize()` 都把 `clk_id`、`click_id`、`cid`、`clickid` 等点击字段放在显式 `conversion_id` / `conversionId` 之前。
- 当请求同时包含不同的 click ID 与 conversion ID 时，点击字段会抢先成为 conversion_id。
- 输出字段 `click_id` 又直接复制该 conversion_id，两个不同概念被合并。
- BFT 当前校验只保证其中某个字段非空，并不能证明它是事件级唯一 ID。字段语义必须依据 BFT 官方协议或经过脱敏的真实回调样例确认；在确认前不得仅靠调整字段优先级推断协议。

### 22.3 数据库与入口缺失值语义不一致

文件：`app/models/postback.py`、`app/core/postback/validators/duplicate_checker.py`

- ORM 中 `PostbackConversion.conversion_id` 为 `String(255), nullable=False`。
- 通用标准化器可能输出空字符串；DuplicateChecker 对 falsy conversion_id 直接跳过重复检测。
- 空字符串不是 SQL NULL，且唯一约束 `(platform, conversion_id, event_name)` 会把同平台同事件的空字符串视为同一个键；可能出现入口放过、后续唯一键冲突的行为。
- 不能把空字符串当成稳定事件身份，也不能把 click_id 的存在当作 conversion_id 已验证。

### 22.4 必须完成的修复协议

1. 将 `extract_click_id()` 与 `extract_conversion_id()` 分离；click_id 只用于点击归因，不得隐式成为事件身份。
2. 事件身份必须规范化为同一份不可歧义的结构：平台规范值、显式 conversion_id、规范 event_name。字段 trim、大小写、空值、最大长度和字符集规则必须与唯一账本/数据库 collation 一致。
3. 无显式稳定事件 ID 时，标记为 `identity_unverified`；不得生成空字符串键，不得执行依赖事件幂等性的 volume deduction。根据平台业务合同选择拒绝、隔离或仅允许不涉及扣量的安全路径。
4. BFT 字段映射必须先取得官方字段合同或脱敏样例，明确 `clk_id` 是否为 click ID、是否存在独立 conversion/event ID；没有证据时保持未决并阻断该平台的事件级扣量，不得猜测。
5. 为通用标准化器和 BFT handler 增加一致的参数化测试：
   - click_id 与 conversion_id 同时存在且值不同；
   - 同一 click_id 对应两个不同 conversion_id；
   - 显式 conversion_id 缺失、空白、数值 0、超长 200/201/255/256 边界；
   - event_name 缺失、空白、大小写差异及别名；
   - 同一事件重试、不同事件并发、缺少稳定事件 ID；
   - DuplicateChecker、PR #206 receipt、PostbackConversion 三者对规范身份得出相同判定。
6. 测试必须覆盖真实 MySQL 唯一约束和 collation；SQLite/mock 测试不能替代 MySQL 身份比较语义验证。

**验收结论：** 当前 PR #205 仍不能解除 Draft。即使 Full Audit 与 Emergency Security CI 通过，也不能证明 BFT/通用入口已经具备事件级身份正确性。只有身份提取、receipt 唯一键、扣量决策键和 MySQL 账本使用同一规范事件身份，并通过真实 MySQL 并发/重试测试后，才可重新评估。


## 23. 扣量决策发生在 Postback 数据库提交之前，Redis 状态没有事务补偿（2026-11-24 追加）

本节对 PR #205 当前 Head `2fac90ce25a8eb0a6be03d5a09718613d4bf021e` 的运行链路进行逐段核查。文件与代码位置均已从该 Head 读取确认。

### 23.1 事件身份在调用链中被缩减为 click_id

- `app/core/postback/pipeline.py::step_apply_discount` 调用 `DiscountChecker.calculate(..., click_id=ctx.normalized_data.get("click_id"))`，没有传入 platform、conversion_id、event_name。
- `app/core/postback/checks/discount_checker.py::DiscountChecker.calculate` 的接口只有 click_id；命中配置后调用 `apply_deduction(..., click_id=click_id)`。
- `app/core/deduction/deduction_manager.py::DeductionManager.apply_deduction` 构造 `decision_key = click_id or offer:{offer_id}:seq:{stats.processed}`。
- 因而 PR #206 receipt 虽然可以保护 `platform + conversion_id + event_name` 的事件重复身份，但扣量决策仍不使用该身份；receipt 的存在本身不会让扣量决策变成事件幂等。

### 23.2 Redis 写入早于正式转化事务提交

`DeductionManager` 当前扣量路径的顺序：

1. `_get_stats_for_decision()` 先查询 MySQL 统计，再执行 Redis Lua `_DECISION_STATS_LUA` 获取序号/扣量计数。
2. 命中扣量时，`_reserve_volume_deduction()` 或 `_incr_decision_deducted()` 立即写 Redis。
3. `DiscountChecker.calculate()` 随后写数据库扣量日志。
4. `PostbackProcessor.process()` 才继续执行 Cap 预留、保存正式转化、Outbox 入队及事务提交。

若第 3/4 步失败，或后续事务回滚，Redis 中的 sequence/reservation 不会随 MySQL rollback 自动撤销。当前代码只对 Cap reservation 有单独补偿流程，未见对 deduction decision sequence/reservation 的等价事务化补偿。

### 23.3 失败与重试可能产生永久统计漂移

- 在 Redis Lua 成功后、MySQL commit 前发生异常，Redis 已经把请求计入 sequence；重试会再次增加序号。
- 哈希策略使用 click_id 时，同一 click 的多个 conversion/event 仍共享决策键；无 click_id 时 fallback sequence 会在重试时变化。
- 预留扣量名额成功、DB 事务回滚时，Redis deducted 仍保留；之后的请求可能被错误地拒绝扣量或导致比例偏离。
- 反向情况也需验证：Redis key 过期/重启后，MySQL 已提交的历史统计与新序列初始化如何衔接，避免重复预留或额度突然重置。

### 23.4 修复验收必须满足的事务边界

1. 在同一个 MySQL 事务内，以规范事件身份取得/创建唯一 decision ledger 行，并锁定对应 scope 计数行。
2. 重复事件必须读取并返回已提交的既有决策；不能再次推进统计序号或再次预留。
3. 统计分子/分母只统计已经提交的唯一事件终态；事务回滚不能改变后续请求可见的统计结果。
4. 正式转化、扣量日志、事件 receipt、decision ledger 终态以及需要原子保证的 Outbox 必须有明确且一致的提交边界。
5. Redis 只能作为可重建缓存、通知或非权威加速层；不得以 Redis INCR/TTL 作为财务账本或不可回滚的扣量名额来源。
6. 真实 MySQL 测试必须覆盖：扣量决策后日志插入失败、正式转化插入失败、Outbox 插入失败、COMMIT 失败/连接中断、回滚后同事件重试、不同事件并发、Redis 重启/清空/过期，以及 2/10/50 并发下账本计数和扣量比例。
7. 测试需在目标 MySQL 版本及生产隔离级别执行；SQLite、mock Redis、单元测试不能证明锁、隔离级别和事务提交边界正确。

**当前结论：** PR #205 的 Redis 决策序号与扣量预留在 MySQL 事务提交前发生，是明确的财务一致性阻断项。不能通过延长 TTL、在异常时简单 DECR，或仅增加重试测试解决；必须以 MySQL 事件级账本作为唯一权威来源后再验收。


## 24. 历史状态：PR #205 当时尚未集成 PR #206（已被后续状态取代）

> **本节为 2026-11-24 较早时点的历史记录，不代表当前分支状态。** 后续 PR #205 已同步 main，merge-base 已更新至 PR #206 的 merge commit `1c0857a35f01ae46eee520e8934a41dc24410393`。当前代码已包含 PR #206 的事件收据实现；请以第 25 节及当前分支源码为准。

当时记录的 ahead/behind 数值、merge-base、以及“缺少 receipt 代码”的判断均已过期，不应作为当前审计结论或合并依据。需要持续审查的剩余问题不是 receipt 是否存在，而是**receipt 的事件身份是否贯通到扣量决策，以及 Redis 决策状态是否能与 MySQL 事务保持一致**。

## 25. PR #205 已同步 main 与 PR #206 收据实现（2026-11-24 追加）

本节更新第 24 节记录的历史状态。第 24 节描述的是同步前状态；本节记录实际完成的同步结果。

### 25.1 同步提交

- 同步前 PR #205 Head：`1df7c5c2c99ba900ef7fc38b144d40d6f79b79a7`。
- main 基线（PR #206 merge commit）：`1c0857a35f01ae46eee520e8934a41dc24410393`。
- 同步提交：`e0767af13d125393343b7cec575488fcdcab280c`。
- 同步提交第一父提交为 main 基线，第二父提交为同步前 PR Head；不是 squash、不是 force push，也没有改写原 PR 历史。
- 同步树以 main tree 为基础，将 PR #205 相对 main 的 13 个变更文件应用到树中；检查了 PR #205 的文件变更清单，未发现删除文件或缺失文件。7 个路径与 main 同时修改，最终保留 PR #205 对这些路径的版本；PR #206 的 receipt 改动位于其它路径，因此保留在同步树中。
- GitHub Compare 确认 PR 分支相对 main：ahead 53、behind 0；GitHub PR 返回 mergeable=true。

### 25.2 PR #206 收据代码同步后核验

在同步 Head 上重新读取文件，确认以下内容存在：

- `app/models/postback.py`：`PostbackEventReceipt` 模型和复合唯一索引。
- `app/core/postback/validators/duplicate_checker.py`：savepoint 内插入收据、唯一键冲突识别、正式转化二次查询及 `release_receipt`。
- `app/core/postback/pipeline.py`：`step_release_event_receipt`。
- `app/core/postback/processor.py`：正式转化保存后调用释放步骤；扣量提前返回分支不调用。
- `app/db/migrations/manifest.py`：包含 `20261124_postback_event_deduction_receipts` migration revision。

以上只确认代码已同步，不替代真实数据库测试，也不代表第 22、23 节财务阻断项已解决。

### 25.3 同步 Head CI 验收

精确 Head `e0767af13d125393343b7cec575488fcdcab280c` 对应：

- Full Audit CI #959：6/6 Jobs success（Backend、Frontend、Python 3.10/3.11/3.13 Telegram dependency compatibility、Python 3.13 password hash compatibility）。
- Emergency Security CI #2949：2/2 Jobs success（Frontend lint/build、Backend security configuration tests）。

因此，同步提交已通过这两项现有 CI。该结果不代表尚未纳入 CI 的生产 MySQL 财务一致性场景全部通过。

### 25.4 同步后仍未解决的阻断项

静态复核同步后代码仍确认：

1. `step_apply_discount` 只向 `DiscountChecker.calculate` 传递 `click_id`；没有传递完整 `platform + conversion_id + normalized event_name`。
2. `DiscountChecker.calculate` 仍只向 `apply_deduction` 传递 click_id；扣量决策身份与 PR #206 receipt 身份尚未统一。
3. `DeductionManager._get_stats_for_decision`、`_reserve_volume_deduction`、`_incr_decision_deducted` 仍使用 Redis Lua 更新决策序号/扣量计数，写入早于 Postback MySQL 事务最终提交。
4. 通用 Normalizer 与 BFT Handler 的 click_id/conversion_id 混用问题仍存在；BFT 映射必须取得官方协议或脱敏样例后再改，不能猜测。
5. 24 小时 MySQL 统计窗口与 Redis 48 小时决策状态 TTL 的语义不一致仍未解决。

### 25.5 当前 PR 状态与处置

- PR #205 仍为 open、Draft、未合并。
- 当前 Head 为 `e0767af13d125393343b7cec575488fcdcab280c`。
- 当前分支 ahead 53 / behind 0，GitHub mergeable=true。
- CI #959 与 #2949 已成功，但不能以此作为解除 Draft 或合并的充分条件。
- 下一步应先实现规范事件身份贯穿和 MySQL 权威决策账本，再补真实 MySQL 事务/并发测试。财务决策 Redis 原子计数在 MySQL commit 前发生的问题仍是上线阻断项。

**审计结论：** 本节只关闭“PR #205 未同步 PR #206”的基线问题；不关闭事件身份、财务事务原子性、滑动窗口一致性和 BFT 字段语义等问题。

## 26. 事件身份缺失并非单纯代码遗漏：现有兼容测试明确允许 click_id 充当 conversion_id（2026-11-24 追加）

本节基于同步后的实际代码与测试文件复核，进一步明确第 22 节修复时的兼容边界。

### 26.1 当前测试把 click-only 回调定义为合法输入

文件：`tests/test_postback_data_validation.py`

当前参数化用例明确要求以下只有点击 ID 的 payload 通过通用验证：

- `{"clk_id": "click-1", "amount": "1.2500"}`
- `{"cid": "click-2", "payout": "2.0000"}`
- `{"clickId": "click-4", "payout": "4"}`

另有 `test_blank_conversion_id_is_ignored_before_fallback`，明确断言显式 conversion_id 为空时，使用 click_id 作为 normalized conversion_id。

文件：`app/core/postback/validators/data_validator.py`

- 验证逻辑把 `DataNormalizer._extract_conversion_id(raw_data)` 与 click_id fallback 组合使用。
- 只要 click_id 或 conversion_id 任一存在，就允许进入处理流程。
- 当前测试因此不是偶然漏测，而是把 click-only 兼容作为既有行为契约。

### 26.2 当前通用标准化与扣量决策实际语义

文件：`app/core/postback/transformers/normalizer.py`

- `_extract_conversion_id()` 在显式 conversion_id 缺失时返回 `_extract_click_id()`。
- `normalize()` 将该值写入 `conversion_id`，并将原始点击标识另写入 `click_id`。

文件：`app/core/deduction/deduction_manager.py`

- `apply_deduction()` 的决策键为 click_id；没有 click_id 时回退到 `offer:{offer_id}:seq:{stats.processed}`。
- 同一 click_id 下多个不同 conversion/event 会共享相同的哈希决策键。
- 无稳定事件身份时 sequence fallback 会因 Redis 计数变化而改变，不能保证重试决策稳定。

### 26.3 为什么不能直接把 conversion_id 改为必填并删除 fallback

直接删除 click_id fallback 会改变当前测试和平台接入契约，并可能使现有只提供点击 ID 的回调在数据库非空字段、唯一约束或入口验证处失败。对所有平台一刀切改为必填之前，需要逐个平台核实其事件 ID 合同和历史数据行为。

但继续把 click_id 当成事件 ID 同样不安全：同一 click 可关联多个合法转化事件，receipt 唯一身份与财务决策身份可能错误合并。

### 26.4 推荐分阶段兼容策略

1. 在标准化结果中显式区分 `click_id`、`conversion_id`、`event_identity_verified`；不得仅因 click_id 存在就把身份标记为已验证。
2. 逐个平台确认稳定事件 ID 字段、别名、大小写/空白规则、最大长度和唯一性范围；保存协议来源或脱敏样例作为审查依据。
3. 对已经确认事件 ID 的平台，使用规范化的 `platform + conversion_id + event_name` 贯穿 DuplicateChecker、receipt、扣量决策及账本。
4. 对暂时没有稳定事件 ID 的平台，保持 click 归因兼容，但将 volume deduction 标记为不可安全执行；按业务批准策略跳过扣量或隔离回调。不得把 click_id 或递增序号伪装成事件幂等键。
5. 先增加兼容性指标，统计各平台 `identity_verified` / `identity_unverified` 比例；在明确受影响流量和业务决策后，再逐平台启用严格模式。
6. 旧转换表唯一键与新 receipt 的身份规则必须一致；如需历史迁移，先做冲突扫描，不得直接批量改写 conversion_id。
7. BFT 的 `clk_id` 字段语义仍需官方协议或脱敏样例确认；现有测试只证明当前实现接受 clk_id，不证明它是事件级唯一 ID。

### 26.5 新增必须覆盖的测试

- click-only 回调可以按批准的兼容策略继续归因，但不得获得 `event_identity_verified=True`。
- 显式 conversion_id 与 click_id 不同，两个字段必须分别保留。
- 同一 click_id 对应两个 conversion_id，必须形成两个独立事件身份。
- 同一 conversion_id 在不同平台、不同 event_name 下的身份边界正确。
- 缺失稳定事件 ID 时，volume deduction 不得执行；amount-only 行为按既有配置独立验证。
- 已验证事件重复投递时，receipt 与财务 decision ledger 只产生一个终态。
- MySQL 实际唯一键、字符集、collation 和字段长度边界必须与应用规范化逻辑一致。

**当前结论：** 事件身份修复需要先建立逐平台协议清单和兼容指标，不能只改一个 Normalizer 函数。当前代码与测试明确允许 click_id 充当 conversion_id；在新旧语义切换方案确定前，不应盲目更改入口必填规则或 BFT 字段优先级。该项仍是财务扣量上线阻断项。


## 26. 事件身份贯通第一阶段修复（2026-11-24）

本节记录当前分支已提交的防御性代码改动。它只解决“把 click_id 当作扣量事件身份”的一部分问题，**不代表 MySQL 财务账本与 Redis 事务不一致问题已经解决**。

### 26.1 显式事件身份与点击归因分离

- 通用 `DataNormalizer` 新增只读取 `conversion_id/conversionId` 的显式提取方法。
- 为兼容历史入库字段，缺少显式 ID 时仍暂时允许 `conversion_id` 字段回退为 click ID；但同时标记 `event_identity_verified=false`。
- 通用入口 `DataValidator` 已改为要求显式 `conversion_id/conversionId`，只有 click_id 的新回调会在入库前拒绝，避免继续把一次点击误当作一笔转化事件。
- BFT handler 分别提取 click_id 与显式 conversion_id；两个值不同的时候分别保存，不再把 click_id 覆盖到 conversion_id。
- BFT 缺少显式 conversion_id 时拒绝新回调。历史标准化函数仍保留 click ID 回退值，但标记身份未验证，不能进入财务扣量决策。
- BFT 的 `clk_id/cid` 等字段究竟代表 click ID 还是 conversion ID，尚无已核实的 BFT 官方协议；本次没有宣称这些字段已被正确映射。上线前必须取得官方字段定义或脱敏真实请求样例。

### 26.2 扣量决策键

- Postback pipeline 只在 `event_identity_verified=true` 时向 DiscountChecker 传递 `platform + conversion_id + normalized event_name`。
- DeductionManager 对三字段做长度边界校验，并用长度前缀编码后计算 SHA-256 事件键；避免简单字符串拼接的歧义。
- click_id 不再参与确定性哈希键；缺少可信事件身份时跳过 volume deduction。
- proportional / round_robin 顺序策略依赖 Redis 递增序号，尚无事务级重试幂等保障；在 MySQL ledger 落地前暂时跳过这些策略的扣量。金额扣减路径不受此门控影响。

### 26.3 当前明确未解决的阻断项

1. **Redis 与 MySQL 仍非原子事务**：随机/哈希策略仍会在 MySQL commit 前使用 Redis 统计和预留。DB rollback 仍可能遗留 Redis 计数；本次事件键只能让同一事件的哈希结论稳定，不能把 Redis 预留纳入 MySQL 事务。
2. **历史兼容标准化路径仍有回退字段**：直接调用标准化器而绕过 DataValidator 的旧调用方，可能仍获得 click ID 回退的 conversion_id。该字段不能被视为稳定事件 ID；必须确保生产入口都经过 validator。
3. **事件收据与无效身份的历史数据**：旧数据可能已经把 click ID 存入 conversion_id。不能自动推断或批量重写；需按平台与时间范围做冲突扫描。
4. **BFT 协议未确认**：当前缺少显式 conversion_id 的 BFT 请求会被拒绝。这是防止财务事件错误合并的 fail-closed 行为；如 BFT 官方确认 `clk_id` 本身就是每笔转化唯一 ID，需先提供协议证据，再单独调整映射和测试。
5. **真实 MySQL 并发测试未完成**：本次新增的是身份与策略门控单元测试；没有执行 MySQL 8.0 REPEATABLE READ 多连接并发、rollback、COMMIT 结果未知和 Redis 重启测试。

### 26.4 上线约束

- 不得仅凭本次单元测试或 CI 全绿解除 PR Draft。
- 部署前必须确认所有平台均能提供稳定事件 ID；BFT 需先核对官方协议。
- MySQL 事件决策账本、scope lock、窗口统计与 Redis 降级方案仍需按前述章节设计实施并用真实 MySQL 验证。


## 27. 第二阶段代码复核：CI 全绿不等于财务事务闭环（2026-11-24 追加）

本节基于 PR #205 当前 Head `76e39452ce52348c6bc81d5a919145c243023532` 的源码复核。该 Head 对应 Full Audit CI 6/6、Emergency Security CI 2/2 均成功；这些工作流未覆盖下述所有真实 MySQL 财务一致性场景。

### 27.1 现有扣量决策仍然依赖 Redis 非事务计数

文件：`app/core/deduction/deduction_manager.py`

- `_get_stats_for_decision()` 先读取 MySQL 统计，再调用 `_DECISION_STATS_LUA` 对 Redis `decision_seq` 执行 INCR，并读取 Redis `decision_deducted`。
- 命中扣量后，`_reserve_volume_deduction()` 或 `_incr_decision_deducted()` 再次直接修改 Redis。
- 这些 Redis 写操作发生在 Postback 外层 MySQL 事务提交之前；数据库回滚无法回滚 Redis。
- `get_recent_stats(strict=True)` 当前统计来源仍是 `postback_conversions` 与 `conversion_deduction_logs` 的组合，并非完整事件决策账本。
- `ConversionDeductionLog` 没有外部平台、外部 conversion_id、规范 event_name、stable event_key 或未扣量决策状态；不能单独作为所有事件的幂等决策账本。

**结论：** 当前代码仍存在 Redis ghost sequence / ghost reservation 风险。不能通过简单 DECR 补偿解决 COMMIT 结果未知、进程崩溃或重复补偿问题。必须把事件决策、scope 统计、扣量名额和终态记录迁移到同一 MySQL 事务。

### 27.2 当前收据不是完整决策账本

文件：`app/core/postback/validators/duplicate_checker.py`、`app/models/postback.py`

- `PostbackEventReceipt` 的唯一键为 `platform + conversion_id + event_name`，能为扣量事件保留防重收据。
- 普通转化保存后，`release_receipt()` 会在同一事务删除临时收据，长期防重依赖 `postback_conversions` 唯一键。
- 收据没有保存 should_deduct / should_not_deduct、配置版本、命中原因、统计窗口、扣量数量/金额等决策结果。
- 对重复请求，现有逻辑返回“重复转化，已跳过”，不是读取并返回原事件的财务决策快照。

**实施要求：** 新增事件决策账本或等价扩展，所有事件（扣量、未扣量、金额扣减、跳过扣量）都必须保存终态；唯一事件身份冲突时读取既有终态，不重新计算。收据、决策账本、转化、扣量日志及必要 Outbox 必须明确处于同一个事务边界。

### 27.3 事件决策键与收据身份尚未完全规范化为同一协议

文件：`app/core/deduction/deduction_manager.py`、`app/core/postback/pipeline.py`、`app/core/postback/validators/duplicate_checker.py`

- 收据身份通过 `normalize_event_name(event_name)` 规范化事件名称。
- Pipeline 传给 `event_identity` 的 event_name 当前直接取标准化数据字段；`_build_event_decision_key()` 只做 strip，不调用同一事件名称规范化函数。
- 因此决策哈希键与收据唯一键目前不是由同一个 canonical identity 函数产生。即使收据先阻断重复事件，也不应把两套规范化实现长期并存。
- `PostbackConversion.event_name` ORM 仍允许 NULL，而收据 event_name 不允许 NULL；历史 NULL 数据与默认事件名称的映射仍需冲突扫描。
- `postback_conversions` 与 `postback_event_receipts` 的数据库 collation 仍需在生产库核实，避免大小写/重音比较规则不一致。

**实施要求：** 建立单一 canonical identity 模块，输出 platform、conversion_id、event_name 的规范值及版本；DuplicateChecker、receipt、decision ledger、哈希键全部消费同一结果。上线迁移前执行真实 MySQL collation 冲突预扫描，不自动合并或改写历史记录。

### 27.4 扣量配置写路径尚无与决策路径共用的 scope mutex

文件：`app/services/cpl/conversion_deduction_service.py`

当前检查到以下写路径仍是先读取/修改配置并 flush，没有统一的 scope lock 协议：

- `create_deduction_config()`：检查已有配置后插入，检查与插入之间存在并发竞态。
- `update_deduction_config()`：允许更新配置字段；当前路径未在 scope mutex 下重新读取并验证同 scope 活跃配置。
- `update_deduction_config_status()`：启用配置前未串行化同 scope 的其它 active 配置。
- `batch_update_status()`：批量启停没有按 scope 去重、排序、加锁后再验证。
- `delete_deduction_config()`、`batch_delete()`：删除路径也未与扣量决策共享同一 scope mutex。

配置创建/启用与 Postback 的 no_config 决策并发时，可能出现决策读到无配置、同时另一事务创建并启用配置的竞态；多个 active config 也可能并存。仅在决策路径加锁不够，所有配置 CRUD 和相关父实体删除必须遵守同一锁协议。

**实施要求：** 配置 CRUD 与 Postback 决策使用相同的 `(scope_type, scope_id)` 锁表；多 scope 批量操作按固定字典序获取锁，再 current-read 重新检查。配合唯一约束/生成列方案前，先扫描历史重复 active config，不自动删除。Offer、Advertiser、Publisher 的父实体删除也必须阻止或协调级联删除配置。

### 27.5 本轮复核结论与下一阶段验收门槛

当前 PR #205 的身份第一阶段修复和现有 CI 均通过，但不能据此合并。下一阶段必须一次性闭环以下内容：

1. 单一规范事件身份模块及平台协议清单；BFT 字段仍需官方协议或脱敏 payload 证据。
2. MySQL 事件决策账本，保存所有事件终态和可复用决策结果。
3. MySQL scope mutex；决策和所有配置 CRUD 共享锁顺序与事务语义。
4. 使用 MySQL 已提交账本计算统计窗口，Redis 不再参与权威序号/扣量额度计数。
5. 固定单次决策时间，明确 24 小时窗口按接收时间还是上游 event_time 计算，并使用半开区间。
6. 真实 MySQL 8.0 REPEATABLE READ 多连接测试：2/10/50 并发同事件、同 scope 不同事件、配置首行创建竞态、rollback、COMMIT 结果未知、Outbox/日志插入失败、死锁/锁超时、Redis 断开/重启/清空。
7. migration manifest checksum、升级/回滚策略、生产数据预检查与可观测性全部完成。

**当前处置：** PR #205 保持 Draft。不能以 CI 全绿、GitHub mergeable=true 或单元测试通过代替财务事务验收。


## 28. 最新 Head 验证与第三阶段复核（2026-11-24 追加）

### 28.1 最新提交的自动化检查与分支基线

本节基于 PR #205 最新 Head `4851a81945641bd1fad3fb37adea3be1aeecd7d9`。

- Full Audit CI Run `45360733326`：6/6 Jobs 成功（backend、frontend、Python 3.10/3.11/3.13 兼容性、Python 3.13 password hash compatibility）。
- Emergency Security CI Run `45360733582`：2/2 Jobs 成功（Frontend lint/build、Backend security configuration tests）。
- GitHub Compare：PR Head 相对 main ahead 81、behind 0；merge-base 为 PR #206 merge commit `1c0857a35f01ae46eee520e8934a41dc24410393`。
- PR #205 仍为 open、Draft、未合并。

上述结果仅证明这两个工作流在该精确 SHA 上成功，不等于真实 MySQL 财务事务一致性验收完成。

### 28.2 event_name 决策键规范化修复已进入最新 Head

文件：`app/core/postback/pipeline.py`、`app/core/deduction/deduction_manager.py`。

- Pipeline 传给 `DiscountChecker.calculate()` 的事件身份 event_name 已通过 `normalize_event_name()` 规范化，与 receipt 层使用的事件名称规则对齐。
- 回归测试 `tests/test_postback_event_name_normalization.py` 已加入“空白 event_name 进入扣量身份时应规范化为 default”的覆盖；该测试包含在上述最新 Head CI 中。
- 但 `DeductionManager._build_event_decision_key()` 本身仍只执行 strip 和长度检查，不是一个独立、统一的 canonical identity API。未来所有调用方（包括非 Postback 调用方）仍可能传入未按相同规则规范化的身份。
- 后续账本实现必须把 platform、conversion_id、event_name 的规范化、验证、版本化封装为单一 API，并让 receipt、decision ledger、PostbackConversion 唯一约束前置校验及哈希键全部使用同一结果。不能只依赖调用链上游恰好调用过 normalizer。

### 28.3 最新源码确认：Redis 仍是扣量决策的非事务状态源

文件：`app/core/deduction/deduction_manager.py`。

最新 Head 仍执行以下步骤：

1. `_get_stats_for_decision()` 先从 MySQL 读取严格统计。
2. 随后执行 `_DECISION_STATS_LUA`，在 Redis 中递增 `decision_seq`，并读取/初始化 `decision_deducted`。
3. 哈希命中后再执行 `_reserve_volume_deduction()` 或 `_incr_decision_deducted()`，直接改变 Redis 扣量计数。
4. 上述 Redis 写入均早于 Postback 外层 MySQL 事务最终提交。

因此，即使事件哈希键已稳定、receipt 已阻止同一身份重复进入，MySQL 后续 flush/commit 失败、事务回滚、进程崩溃或提交结果未知，Redis 状态仍可能保留未提交事件的序号/名额。最新 CI 没有关闭该风险。

**要求：** 不允许继续以 Redis INCR/DECR 作为权威扣量名额账本；应迁移为 MySQL 事务内的事件决策终态记录和 scope 级计数/额度控制。Redis 只能承担非权威缓存、限流或可丢弃优化。

### 28.4 最新源码确认：事件决策账本仍不存在

当前 `ConversionDeductionLog` 仍主要保存内部 conversion FK、click_id、scope、扣量前后金额/数量和配置快照，不含外部 platform、外部 conversion_id、规范 event_name、稳定 event_key、决策终态及完整重放结果。

当前 `PostbackEventReceipt` 仅用于唯一身份占位：
- volume deduction 路径保留 receipt；
- 正常转化路径在转化记录写入后释放 receipt；
- receipt 不保存 should_deduct / should_not_deduct、配置版本、决策窗口、扣量原因和最终金额/数量等可重放快照。

因此 receipt 不能替代事件决策账本。必须为每个通过业务处理的事件保存一个持久化终态，包括未扣量、扣量、仅扣金额、扣量跳过/降级等状态，并确保重复投递读取既有终态而不是重新计算。

### 28.5 最新源码确认：配置 CRUD 尚未使用共同 scope mutex

文件：`app/services/cpl/conversion_deduction_service.py`。

再次确认 create、update、单条启停、批量启停、单条删除、批量删除均没有先取得与 Postback 决策相同的 scope mutex，再 current-read 并验证配置状态。当前创建仍是先 `check_existing_config()` 再 insert；启用配置直接更新 `is_active`；批量操作直接执行 UPDATE/DELETE。

这意味着：
- 同一 scope 的并发创建/启用仍可能出现多个 active config；
- Postback 决策和配置变更之间仍缺少共同串行化边界；
- generation/cache invalidation 不能代替数据库锁，也不能保证决策事务读到一致的配置版本。

所有 CRUD 与相关父实体删除必须纳入同一 scope lock 协议；多 scope 批量操作按固定顺序锁定，锁后重新读取并验证。历史重复 active config 必须先扫描，不能自动删除。

### 28.6 当前阻断清单与处置

以下事项仍未通过生产级验收：

1. MySQL 事件决策账本：所有事件终态、幂等唯一键、配置/策略快照、重复请求原决策重放。
2. MySQL scope mutex：Postback 决策、6 条配置 CRUD、Offer/Advertiser/Publisher 删除路径共享。
3. Redis 不再参与权威决策序号和扣量额度；解决 rollback、进程崩溃、COMMIT 结果未知的状态恢复。
4. 统计窗口定义：明确按接收时间还是上游 event_time；统一窗口、决策时刻、数据库时钟和半开区间。
5. REPEATABLE READ 语义：配置/generation 查询必须与锁协议使用一致的 current-read 方案，避免旧 snapshot 混入。
6. MySQL 真实并发测试：至少 2/10/50 并发；同事件重复、同 scope 不同事件、首配置创建竞态、启停与 Postback 并发、死锁/锁超时、rollback、COMMIT 结果未知、日志/Outbox 写失败。
7. 数据迁移安全：NULL event_name、重复身份、collation 漂移、字段长度、checksum、升级与回滚演练。
8. BFT 字段合同：取得官方协议或脱敏真实 payload 前，不得猜测 `clk_id/cid` 的事件唯一性语义。

**当前处置：PR #205 继续保持 Draft，不合并。** 两项 CI 全绿和 GitHub mergeable=true 都不是财务一致性验收的替代品。

## 29. 第四阶段：MySQL 权威事件决策账本事务协议（设计评审稿，未实施）

本节将账本设计约束明确到事务顺序、身份唯一性、锁顺序、窗口统计和提交未知恢复。它是实施前的设计基线，不代表代码、DDL 或测试已经完成。

### 29.1 设计目标与不可破坏的业务语义

必须同时满足：

- 一个规范事件身份最多产生一个终态决策；相同身份的重试只能重放原决策。
- 事件终态、扣量日志、正常转化记录、必要的审计记录和 Outbox 在同一个 MySQL 事务中提交或回滚。
- 扣量统计、扣量额度、顺序序号均以 MySQL 已提交账本为准；Redis 不再是权威计数器。
- 配置变更和 Postback 决策通过相同的数据库 scope mutex 串行化。
- 每个事件都要有持久终态，不得只记录命中扣量的事件。
- 不能将“数据库提交结果未知”误判成回滚，也不能因此重新执行一遍扣量决策。

### 29.2 建议的表职责

建议新增两类核心表，而不是继续扩展临时 receipt 的职责：

1. `conversion_deduction_event_decisions`：事件级决策账本，一条规范事件身份一行，保存完整决策快照和终态。
2. `conversion_deduction_scope_locks`：广告主/Offer/Publisher 级互斥行，配置 CRUD、Postback 决策和父实体删除共用。

决策账本建议字段（最终字段类型必须与项目 MySQL 版本、ORM 和历史数据核查结果一致）：

- 主键：BIGINT 自增。
- `event_key`：CHAR(64) CHARACTER SET ascii COLLATE ascii_bin，SHA-256 规范身份键，唯一。
- `identity_fingerprint`：BINARY(64)，对规范身份独立计算 SHA-512，用于发现 event_key 碰撞并 fail closed。
- `platform`、`conversion_id`、`event_name`：保存规范身份字段，采用明确的二进制比较语义；不得依赖数据库默认不区分大小写 collation。
- `state`：事务内只允许临时 PENDING；提交前必须转为终态。建议终态至少包括 `ACCEPTED`、`VOLUME_DEDUCTED`、`AMOUNT_ADJUSTED`、`VOLUME_AND_AMOUNT_DEDUCTED`、`SKIPPED_FAIL_OPEN`、`SKIPPED_POLICY`。如果事件被拒绝或未进入扣量业务，是否创建终态需与业务入口契约明确，不可把校验失败伪装成成功转化。
- Scope 快照：advertiser_id、offer_id、publisher_id；允许 NULL 的语义必须明确。
- 决策快照：config_id、config_version/updated_at、strategy、ratio、amount ratio、原始/扣减/最终 volume 与 amount、reason、policy version。
- 窗口快照：window_kind、window_start、decision_at、window_total_before、window_deducted_before、window_total_after、window_deducted_after；金额使用 DECIMAL，禁止 float 持久化。
- 时间字段：received_at / decision_at / finalized_at 均由数据库 UTC 时钟生成；上游 event_time 另存，仅用于明确约定的业务分析，不可隐式替代接收时间。
- 错误/降级字段只保存安全错误类别与受控摘要，不写入密钥、完整原始请求或未经脱敏的个人数据。

索引建议：
- UNIQUE(event_key)。
- INDEX(scope/window/decision_at/event_key)，实际列序须通过真实查询计划验证。
- INDEX(state, finalized_at, id) 仅在确实需要运维扫描时建立。
- 不对长原始 ID 直接建立宽联合唯一索引；使用固定长度二进制键并保留 fingerprint collision guard。

### 29.3 唯一身份生成规则

必须提供一个 canonical identity 模块，作为所有事件入口的唯一身份实现：

1. platform：按已确认的现有合同执行 strip，保留大小写；不得擅自 casefold。
2. conversion_id：只接受明确的上游转化唯一 ID，不得回退到 click_id；空值、超长值和控制字符策略必须显式定义。
3. event_name：只调用唯一的 `normalize_event_name()`，空值/空白映射 default。
4. 采用 UTF-8 长度前缀编码后计算 SHA-256 event_key；另用独立 SHA-512 计算 fingerprint。
5. 数据库中 event_key 用 ascii_bin；规范字段比较规则与 Python 规范化结果完全一致。
6. 同 event_key 但 fingerprint 或规范字段不同，视为哈希碰撞/实现漂移，必须告警并 fail closed；禁止覆盖赢家记录。

Canonical API 必须同时供 PostbackEventReceipt 迁移兼容层、decision ledger、PostbackConversion 查重及所有 DeductionManager 调用使用。不得在不同模块重复实现规范化规则。

### 29.4 必须统一的事务与锁顺序

推荐 Postback 主事务按以下顺序执行，任何入口不得另行变更顺序：

1. 完成不涉及数据库写锁的请求结构/IP/平台字段校验；得到可信规范事件身份及归因候选 scope。
2. 在主 MySQL 事务中尝试插入 PENDING decision ledger（唯一 event_key）。若唯一键冲突，等待竞争事务结束，再读取赢家终态；终态存在则原样重放，禁止再次计算。
3. 对本次事件涉及的全部 scope key 去重后排序，按固定全局顺序逐一确保锁行存在，再逐一 `SELECT ... FOR UPDATE`。建议顺序固定为 advertiser → offer → publisher，层级内按数值 ID 升序。
4. 锁定后以 current read 重新读取有效配置、父实体状态、配置版本及需要的历史终态；不允许使用锁前建立的旧 REPEATABLE READ snapshot。
5. 从 MySQL decision ledger 读取同一 scope 和窗口内的已提交终态统计，计算本事件决策。当前事务内的 PENDING 行必须排除，或显式按“本事件 +1”计算，不能重复计数。
6. 写入完整决策快照；若正常转化，写入 PostbackConversion；若扣量，写入 ConversionDeductionLog；同时写入审计/Outbox。所有写入必须在同一主事务。
7. 将 decision ledger 从 PENDING 更新为且仅更新为一个终态；提交整个事务。
8. commit 返回成功后才允许异步转发/通知；外部副作用通过 Outbox，不允许在事务提交前直接发送。

锁表主键建议为 `(scope_type, scope_id)`，scope_type 使用固定枚举值；scope_id 必须为正整数。创建锁行使用幂等 INSERT（例如 INSERT ... ON DUPLICATE KEY UPDATE 的无业务字段变化形式），随后按排序逐行 current-read `FOR UPDATE`。锁行不设置 TTL，不得清理正在作为并发仲裁对象的锁行。

### 29.5 配置 CRUD 和父实体删除必须遵守同一协议

- create：先锁 scope，再 current-read active config，再插入；不能先普通 SELECT 检查后 INSERT。
- update：先锁原 scope；若允许移动 scope，必须同时锁原 scope 和新 scope，按全局顺序锁定，重新读取记录后再更新。
- enable/disable：先锁 scope，重新读取并检查同 scope 的 active 冲突，再更新。
- batch enable/disable/delete：先读取目标的候选 scope，仅用于确定锁集合；去重排序锁定后必须重新 current-read 全部目标及冲突配置，最后执行批量写入。
- Offer/Advertiser/Publisher 删除：不得依赖 ON DELETE CASCADE 静默删除扣量配置。删除前锁定目标 scope 与受影响子 scope，明确拒绝删除或在同事务执行已审批的配置停用/删除流程。
- 配置缓存 Generation 只能在配置变更事务内更新；缓存失效/Outbox 失败不能绕过锁协议，也不能把数据库配置变更部分提交。

### 29.6 REPEATABLE READ 的关键实现要求

MySQL 默认 REPEATABLE READ 下，普通 SELECT 使用事务一致性快照，而 `SELECT ... FOR UPDATE` 使用当前锁定读。不能先做普通配置/Generation SELECT 建立旧 read view，再锁 scope，最后普通 SELECT 配置并假设看到最新值。

实现必须选择并固定其中一种策略：
- 整个扣量事务采用明确的 READ COMMITTED，并确认 binlog/部署配置兼容；或
- 保留 REPEATABLE READ，但在锁定 scope 后，对配置、Generation、事件账本及窗口统计中要求最新状态的读取全部使用锁定读/current read，并避免混合旧 snapshot。

不允许仅凭“已经 SELECT FOR UPDATE 过 scope lock row”就认为其他表的普通 SELECT 自动变成 current read。真实 MySQL 集成测试必须复现：事务 A 先普通读建立快照；事务 B 修改配置并提交；事务 A 再获取 scope 锁并读取配置，验证所选方案不会读到过期配置。官方依据见 MySQL 8.4 Transaction Isolation Levels 与 Consistent Nonlocking Reads。

### 29.7 24 小时统计窗口与决策时间

为保持当前实现的接收时间语义，初步建议决策窗口继续按数据库接收时间，而不是上游 event_time：

- 每个事件在完成 scope 锁定后，从 MySQL 获取一次 `decision_at = UTC_TIMESTAMP(6)`；整个事件决策只使用该值。
- 窗口定义为 `[decision_at - INTERVAL 24 HOUR, decision_at]`，按已提交事件 ledger 的 `decision_at` 统计；窗口左边界包含，右边界包含当前时刻。
- 当前事件先处于 PENDING，统计时显式排除当前 event_key；由于 scope mutex 已串行化，查询中不存在同 scope 尚未提交的其他决策。右边界必须包含，以免多个事务在微秒精度下取得相同 decision_at 时漏算先前已提交事件。
- scope lock 行建议另设单调递增 `decision_seq`，在锁内事务中递增并与事件终态同事务提交，作为稳定审计顺序和相同时间戳的 tie-breaker；滚动窗口的 processed_before 仍由窗口内终态 ledger 统计，不能用永久序号冒充 24 小时窗口计数。
- 窗口滚动自然由 SQL 时间条件实现；不再依赖 Redis 48 小时 TTL，也不需要对 Redis counter 做过期递减。
- 同一 scope 由 mutex 串行化后，窗口统计、序号和额度检查在同一事务中完成。
- 若业务实际要求按上游事件发生时间扣量，必须另行定义 event_time 来源可信度、迟到事件、时区、回补和窗口重算规则；不能悄悄将现有 created_at 改成 event_time。
- 比例舍入规则必须与现有业务行为做 characterization tests 后冻结；当前实现使用 `int(total * ratio)` 的截断语义，迁移时不得无意改成四舍五入或 ceil。

### 29.8 Redis 移除后的策略语义

- random/hash/deterministic：事件身份作为稳定输入；MySQL ledger 保存实际结果，重复事件不再重新抽样。
- proportional/round_robin：使用同 scope 锁内的 MySQL processed_before/decision sequence；顺序定义为 scope 锁成功取得后的数据库决策顺序，而不是客户端发送时间或网络到达时间。
- 所有策略的 quota/limit 均由 MySQL ledger 统计和 scope 锁保护；Redis 只可用于非权威展示缓存。
- 迁移期间不得让一部分 Worker 使用 MySQL ledger、另一部分仍使用 Redis 做权威决策。必须通过停旧 Worker、排空队列、切换所有 Worker 的版本门禁完成单一写入权威切换。

### 29.9 COMMIT 结果未知与恢复

数据库连接在 COMMIT 请求发送后断开时，客户端无法仅凭异常判断事务是否提交。处理规则：

1. 不得执行 Redis DECR（未来权威路径不应有此写入），不得生成第二条事件决策。
2. 使用新的数据库连接按 event_key 查询 ledger。
3. 若找到终态，按已提交处理并返回原决策；若唯一键仍被未完成事务持有，等待/有限退避后重查。
4. 若明确确认不存在 ledger，才允许重新提交整个事件处理流程；仍由唯一 event_key 保证并发只会有一个赢家。
5. 若数据库不可用或状态暂时无法判定，返回 retryable=true 的暂时失败，不能返回“成功扣量”或“成功未扣量”。
6. 运维恢复任务只能修复可证明的非终态异常；不允许仅凭超时把一条未知事件改为 ROLLED_BACK。

### 29.10 必须通过的真实 MySQL 测试矩阵

必须连接 MySQL 8.0/目标生产兼容版本，不能用 SQLite 替代：

- 同一 event_key 2/10/50 并发：只有一个决策行、一个终态、一个财务结果；所有请求重放完全相同的结果。
- 同 scope 不同 event_key 2/10/50 并发：扣量总数不超过按既定舍入规则计算的 quota。
- 不同 scope 并发：不发生不必要的全局串行化。
- 首次 scope lock row 并发创建：所有事务锁定同一行，不产生重复锁记录。
- create/enable/disable/update/delete 与 Postback 决策并发：配置快照与生效顺序符合锁协议。
- 多 scope 反向请求：排序后不发生可复现死锁；仍需验证死锁重试仅重试完整事务。
- 人为注入 flush 失败、日志失败、Outbox 失败、commit 前断连：事件决策、转化、日志均回滚。
- 模拟 COMMIT 成功但客户端丢失响应：重连查询得到唯一终态，不重复扣量。
- Redis 不可用、Redis 数据清空：权威决策结果不变。
- 24 小时边界、窗口滚动、同一微秒/相同时间戳排序：计数和策略结果确定。
- REPEATABLE READ 旧 snapshot/current read 场景：配置读取必须符合明确策略。
- deadlock 1213、lock wait timeout 1205：只重试完整事务，设置有界退避；不可在失败事务中继续查询/写入。

### 29.11 设计结论与当前禁止事项

该协议仍处于设计评审阶段。尚未实现 ORM、DDL、migration manifest/checksum、服务层、scope mutex、MySQL 权威统计、回滚恢复及上述测试。因此：
- 不得将 Redis 计数改成 MySQL 查询的局部替换视为完成。
- 不得仅新增 decision 表却继续从 Redis 预留名额。
- 不得先上线 schema 再让新旧 Worker 混合写入。
- 不得自动补写历史事件终态；历史扣量事件缺少外部事件身份时不能安全回填。
- PR #205 保持 Draft，直到完整实现和真实 MySQL 测试全部通过。

### 29.12 官方参考

- MySQL 8.4 Transaction Isolation Levels：<https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html>
- MySQL 8.4 Consistent Nonlocking Reads：<https://dev.mysql.com/doc/refman/8.4/en/innodb-consistent-read.html>
- MySQL 8.4 Locking Reads：<https://dev.mysql.com/doc/refman/8.4/en/innodb-locking-reads.html>
- MySQL 8.4 Locks Set by Different SQL Statements：<https://dev.mysql.com/doc/refman/8.4/en/innodb-locks-set.html>
- MySQL 8.4 Internal Locking Methods / deadlock avoidance：<https://dev.mysql.com/doc/refman/8.4/en/internal-locking.html>

### 29.13 归因快照与 scope 锁集合的竞态

scope mutex 能保护扣量配置，但前提是本事件取得的 scope 集合本身可靠。Postback 通过 click_id 关联 Click、Offer、Publisher、Advertiser；如果归因关联或父对象状态允许并发修改，仅在解析后锁 advertiser/offer/publisher 仍可能锁错 scope。

实施时必须明确以下约束：

1. 在锁 scope 前解析归因，只能形成候选 scope 集合，不能直接视为最终可信快照。
2. 若 Click → Offer/Publisher/Advertiser 关联在业务上不可变，必须通过数据库约束/服务层禁止修改，并以此作为设计前提。
3. 若允许修改，必须先锁定归因源记录（例如 Click/assignment row），重新读取关联，再计算完整 scope 集合；随后按统一顺序锁 scope。所有修改归因关系的写路径必须先取得相同归因源锁，不能反向锁 scope 后再锁 Click。
4. 若无法在不破坏全局锁顺序的情况下先锁归因源，则应在事务内读取归因版本，锁 scope 后再次 current-read 校验版本；版本变化时回滚整个事务并从头重试，禁止拿旧 scope 继续决策。
5. 父实体删除、Offer 归属迁移、Publisher assignment 变更必须纳入相同的锁顺序与版本栅栏。
6. 真实 MySQL 测试需覆盖归因解析与关系修改并发，确保一个事件不会在错误 scope 上计算扣量比例或读取错误层级配置。

### 29.14 本轮源码复核的额外事实

- 仓库已经存在 `third_party_report_identity_locks` 的设计与 migration，可参考其“固定身份锁行、永久保留、冲突时 fail closed”的做法；但该锁表只服务第三方上报身份，不是 CPL scope mutex，不能直接复用其业务键。
- 仓库已有 `CapReservationLedger`，采用独立会话、租约、状态机和恢复 Worker 处理 Redis Cap token；该机制说明跨 Redis/MySQL 状态需要显式账本，但它不是扣量决策账本。CPL 事件决策必须与 Postback 主事务原子提交，不能照搬 Cap Reservation 的独立事务边界。
- 当前 `ConversionDeductionConfig` 的三个目标 FK 均为 `ON DELETE CASCADE`；因此父实体删除路径若不显式纳入 mutex，确实可能绕过配置 CRUD 的互斥协议。
- 当前 `check_existing_config()` 是普通 SELECT 后再由服务层 INSERT；它本身不具备并发互斥能力。不能将其当作唯一性保证。

### 30. 第五阶段源码复核：归因关系可变与 Click 查询异常被降级

本轮检查 click_associator.py、publisher_service.py、offer_service.py、cpl.py、pipeline.py，确认第 29.13 节提出的归因竞态不是纯理论风险，当前代码已经存在可变关系与异常降级路径。

#### 30.1 Publisher.client_id 是可变归属，但 Click 没有客户归属快照

已确认的代码事实：

- Click 模型保存 offer_id、publisher_id、advertiser_id，但没有 client_id 快照字段。
- Publisher.client_id 可通过 PublisherService.update_publisher() 修改。
- ClickAssociator.associate_from_db() 通过 joinedload(Click.publisher) 取出当前 Publisher，并将 association['client_id'] 设置为 click.publisher.client_id。
- ConversionSaver.resolve_trusted_attribution() 优先采用该 association.client_id，随后以该客户 ID 验证产品归属。
- step_apply_discount() 将解析出的 trusted_client_id / trusted_product_id 传入 DiscountChecker.calculate()，因此客户级/产品级扣量配置会受当前 Publisher.client_id 影响。

风险：点击发生后若 Publisher 被迁移到另一个 Client，历史 Click 的客户归属会随当前 Publisher 变化。历史 Postback 可能读取新客户的产品/扣量配置，而不是点击发生时的归属；这会改变历史事件的扣量 scope，造成跨客户数据归属错误。

#### 30.2 Offer.advertiser_id 可变，Click 与当前 Offer 关系可能不一致

已确认：

- Offer.advertiser_id 可由 OfferService.update_offer() 更新。
- Click 自身保存独立的 advertiser_id 与 offer_id。
- Postback 关联时读取 Click 保存的 advertiser_id，同时也加载当前 Offer ORM 对象；Offer 状态校验读取当前 Offer 的 is_active/status。

风险：Offer 归属迁移后，历史 Click 的 advertiser_id 快照、当前 Offer.advertiser_id 及 Offer 当前状态可能属于不同业务上下文。当前流程没有对这组关系做一致性校验，也没有归因版本栅栏。必须先确定业务规则：历史点击是否永久归属点击时广告主；如果是，扣量层级、报表、Cap 和转发均应统一使用点击快照；若允许历史关系追随迁移，则必须有明确迁移事件与版本规则，不能混用旧 advertiser_id 和当前 Offer 关系。

#### 30.3 Click 查询异常被当成“没有找到 Click”

ClickAssociator.associate_from_db() 当前对查询异常执行以下行为：

- 捕获所有 Exception；
- 使用同一个 AsyncSession 继续指数退避重试；
- 不执行 rollback()，也不区分连接暂时错误、事务失效、SQL 错误与普通未命中；
- 最终仍无 Click 时返回 None。

PostbackProcessor.process() 在拿到 click_association=None 后没有因“请求提供了 click_id 但归因数据库查询失败”而停止处理，而是继续 Offer 状态校验、重复检测和扣量流程。无关联的直连 Postback 也是被允许的兼容路径。

风险：真实的数据库故障可能被伪装成“Click 不存在”，导致系统把本应关联到某个 Offer/Publisher/Advertiser/Client 的事件按无归因事件继续处理，可能漏掉对应 scope 的扣量配置或 Cap 约束。对同一个已失败的 AsyncSession 继续查询也不构成可靠重试。

必须修复的语义：

1. 区分“没有提供 click_id”“Click 查询成功但确实未命中”“Click 查询/数据库事务失败”三种状态。
2. 如果请求带有 click_id 且查询因数据库错误失败，必须向 Postback 主流程抛出可重试异常；不得降级成 None，也不得继续走直连路径。
3. 数据库异常后的重试必须在回滚/关闭旧事务后使用全新 AsyncSession，或由上层事务边界统一重试整个 Postback；不得在失效事务中继续执行 SQL。
4. 若查询成功但确实未命中，是否允许按直连 Postback 处理必须由平台接入策略显式决定。对要求 Click 归因的入口应 fail-closed；只有明确配置为 direct-postback 的平台/路由才可无 Click 继续。
5. 令牌关联 _enrich_association() 当前也会捕获 ORM enrichment 异常并继续返回 token association。若后续业务需要数据库补充的 Publisher/Client 信息，必须把“ID 已解析但归属未能验证”作为独立状态，不能把不完整 enrichment 视为完整可信归因。

#### 30.4 推荐的归因快照方案

在实现 MySQL 决策账本前，先确定归因数据契约：

- 对新 Click，在创建时保存 client_id_at_click（或明确版本化的归因快照），并保存 offer/publisher/advertiser 归属快照及 attribution_version。字段命名需与项目现有模型规范统一。
- Click 归因快照创建后不可被普通 CRUD 修改；确需纠错时使用受审计的显式迁移流程，并产生版本变更。
- 历史 Click 没有客户快照，不能通过当前 Publisher.client_id 无条件回填并声称是点击时真实归属。应标记为 legacy/unverified，按人工审查、可证明的历史记录回填或 fail-closed 策略处理。
- Postback 在事务内锁定/读取 Click 归因快照及版本；扣量 scope、Cap、报表、转发使用同一份快照，不允许部分字段取历史 Click、部分字段取当前 Publisher/Offer。
- Offer/Publisher/Advertiser 的修改、删除、客户迁移路径必须遵循统一归因版本/锁协议；对已有 Click 的父对象关系变更必须定义历史事件行为。
- 测试至少覆盖：Publisher.client_id 变更前后历史 Click 的归属不漂移；Offer.advertiser_id 变更前后快照一致；Click 查询异常不会降级为 direct postback；事务失效后不复用 Session；令牌 enrichment 不完整时不会错误应用 scope；归因迁移与 Postback 并发。

#### 30.5 本节结论

本轮没有修改上述业务代码，也没有新增数据库字段或 migration。该项属于新的财务归因正确性阻断项，应与第 29 节的 MySQL 权威决策账本、scope mutex、CRUD 同锁协议一起设计和实现。不得只在 ClickAssociator 中简单增加 rollback 后继续重试，也不得只新增 client_id 字段而不处理历史数据、Offer/Publisher 迁移、Cap/报表一致性及真实 MySQL 并发测试。

### 31. 第六阶段源码复核：令牌模式下 Click 可不落库，且令牌不包含 Client 快照

本轮继续检查 app/core/tracking/click_persist.py、app/core/tracking/click_token.py、app/api_v1/tracking/tracking.py、app/routes/short_link/cloak_click_persist.py、app/core/postback/transformers/click_associator.py 与 ConversionSaver。

#### 31.1 Click 落库不是所有环境下的必选路径

`should_persist_clicks_to_db()` 的行为为：

- `PERSIST_CLICKS_TO_DB=true` 时强制写库；
- `PERSIST_CLICKS_TO_DB=false` 时强制不写库；
- 未设置时，`USE_TRACKING_TOKEN=true` 默认不写 clicks 表；否则默认写库。

因此不能把 Click 表当作所有 Postback 都必定存在的归因事实来源。令牌模式下，Postback 可能完全依靠签名令牌中的归因字段继续处理。任何归因快照方案都必须同时覆盖“Click DB 行存在”和“仅令牌归因”两种模式，不能只给 Click 表新增字段。

#### 31.2 当前追踪令牌只编码 Offer/Publisher/Advertiser/ShortLink 等标识，不包含 Client ID

`click_token.py` 的令牌身份字段包括 offer_id、publisher_id、advertiser_id、short_link_id，未包含 client_id。`association_from_parsed()` 也只还原这些 ID 与 URL 参数。

当令牌模式下 Click 没有落库时，`ClickAssociator.associate()` 会尝试 `_enrich_association()`，通过当前 Publisher 记录读取 `Publisher.client_id`。该 enrichment 捕获所有异常后仍返回原 token association。此时 Postback 可能继续处理，但 association 中没有可信 client_id；`ConversionSaver.resolve_trusted_attribution()` 可能因此无法建立客户/产品 scope。

这意味着第 30 节风险需要扩展：仅给 Click 表增加 client_id_at_click 仍不够。必须为令牌模式设计可验证、可版本化且不暴露敏感租户数据的客户归属快照；或者明确要求所有需要客户/产品扣量的 Click 强制落库并且在 DB 归因验证失败时拒绝处理。不能让令牌模式悄悄退化成“缺少 Client scope 但照常扣量/保存”。

#### 31.3 普通追踪入口与斗篷入口的归因字段完整性不同

- `app/api_v1/tracking/tracking.py` 的普通追踪入口在生成令牌和 Click 数据时，传入 offer_id、publisher_id、advertiser_id。
- `app/routes/short_link/cloak_click_persist.py` 的斗篷点击落库数据显式写入 `advertiser_id=None`，即使 Offer 可能有关联广告主；其归因是否由 `resolve_cloak_click_offer_and_publisher()` 补全需要单独核对，不得假设与普通入口一致。
- 斗篷路径在更新 short_links.click_count 后会先 commit，再调用 persist_click_record；点击计数与 Click 落库/队列入队不是一个原子事务。队列或 DB 备用写入失败时可能出现点击计数已增加、Click 记录缺失的差异。

应明确 Click persistence 的 SLA、队列积压/丢弃监控、重放/修复机制，以及点击计数的统计口径。扣量归因不可依赖异步 Click 行在 Postback 到达前必定完成。

#### 31.4 必须补充的测试

1. `USE_TRACKING_TOKEN=true` 且 `PERSIST_CLICKS_TO_DB` 未设置：Click 不写 DB，Postback 仍能获得完整可信归因快照。
2. Token 中的 offer/publisher/advertiser ID 与数据库当前对象归属不一致：按明确版本/快照策略 fail closed，不静默覆盖。
3. Token enrichment 数据库异常：客户/产品扣量不得在缺失 trusted_client_id 时被误当作完整归因成功。
4. `PERSIST_CLICKS_TO_DB=false` 与 `true` 两种模式的行为均有集成测试。
5. 斗篷入口 advertiser_id 的来源与普通追踪入口一致性测试；若业务上允许为空，必须明确哪些扣量 scope 不适用。
6. Click queue 入队失败、后台 DB fallback 失败、队列延迟/重复写入时，点击计数和 Click 记录差异可监控、可恢复，且不污染财务决策身份。

#### 31.5 本节结论

本轮没有修改 Click/token/persistence 代码，也没有新增 migration 或测试。当前 PR 的 Click 归因存在双模式（持久化 Click / 仅令牌）和多入口字段完整性差异。MySQL 权威扣量账本实现前，必须统一定义 canonical attribution snapshot，覆盖两种存储模式和所有 Click 入口；不能只依赖当前 Publisher/Offer 表回查，也不能把缺失客户归属默认为无配置。



### 32. 第七阶段源码复核：令牌与 DB 归因合并优先级、斗篷计数并发更新

本轮对当前 PR Head 的以下文件逐段复核：`app/core/postback/transformers/click_associator.py`、`app/core/tracking/click_token.py`、`app/routes/short_link/cloak_click_persist.py`、`app/services/cpl/offer_service.py`、`app/services/cpl/publisher_service.py`。

#### 32.1 Token 与 DB 同时存在时，Token 非空字段覆盖 DB 归因字段

`ClickAssociator._merge_token_and_db_association()` 先复制 DB association，再遍历 token association；除 None 和 url_params 外，Token 中所有非空字段都会覆盖 DB 字段。这包括 offer_id、publisher_id、advertiser_id、short_link_id。

这本身不一定错误：签名令牌可以是点击时身份来源。但当前代码没有在覆盖前验证 Token 与 Click 行的身份字段是否一致，也没有 attribution_version 或冲突审计。若 Click 行被修改、令牌由不同的点击上下文产生，或数据发生异常，系统会静默选择 Token 值；而 client_id 又来自 DB 当前 Publisher，可能形成“Token 的 publisher_id + DB 当前 Publisher.client_id”的混合归因。

要求：合并时必须逐字段比较不可变身份字段；一致才形成可信快照。不一致时不得静默覆盖，应返回明确的 attribution_conflict 并 fail closed/进入人工调查。若设计选择 Token 为权威来源，则所有下游字段必须从同一个已验证 Token 快照取得，不能再混用 DB 当前关联关系。

#### 32.2 Token 解析成功后，DB 查询异常仍可能被当成 DB 未命中

`associate()` 在 Token 解析成功后仍调用 `associate_from_db()`，目的是补充 url_params、IP/UA 等字段。但 `associate_from_db()` 会捕获查询异常并最终返回 None。于是上层无法区分“DB 确实没有 Click 行”和“DB 查询失败”。

随后 `associate()` 会将 Token association 交给 `_enrich_association()`；后者也捕获所有异常并继续返回原 association。最终可能在 Click DB 查询和 Publisher/Client enrichment 均失败时，仍返回看似成功的 Token association。

要求：归因结果应显式携带验证状态，例如 token_signature_valid、db_record_found、db_identity_consistent、tenant_scope_verified、attribution_version；不得用一个 Optional[dict] 同时表达未提供 Click、真实未命中、DB 不可用、Token-only 已验证和归因冲突。凡扣量 scope 需要 Client/Publisher/Offer 当前状态验证时，未验证状态必须阻止相应财务决策，不能被当成“没有配置”。

#### 32.3 Offer 与 Publisher 的可变关系已存在普通更新入口

进一步确认：
- `OfferService.update_offer()` 接受 advertiser_id 变更，验证目标 Advertiser 存在后直接修改 Offer.advertiser_id。
- `PublisherService.update_publisher()` 接受 client_id 变更并直接修改 Publisher.client_id。
- 两条路径当前均未显示与 Click 归因快照/版本栅栏共享的锁协议。

因此第 30 节提出的历史归因漂移是可由正常管理 API 触发的业务场景，不是仅需考虑 DBA 手工改库的边界情况。实现时必须把这两条更新路径纳入归因锁/版本协议，并定义变更对历史 Click、Postback、Cap、扣量、报表和转发的统一语义。

#### 32.4 斗篷点击计数存在并发丢增量风险

`persist_cloak_report_click()` 当前先查询 ShortLink ORM 行，再执行 Python read-modify-write：`short_link.click_count = (short_link.click_count or 0) + 1`，随后 commit。查询没有使用 `SELECT ... FOR UPDATE`，更新也不是数据库原子表达式。

多个并发请求可能同时读到相同旧值，再分别写入旧值 + 1，造成计数丢增量。该问题独立于 Click 队列是否成功：即使所有请求都正常执行，也可能发生统计不准确。

要求：改为数据库原子增量（例如 `UPDATE short_links SET click_count = COALESCE(click_count, 0) + 1 WHERE id = ...`），并根据数据库方言/驱动决定是否使用 RETURNING；如需与 Click 落库保持一致，应采用可靠 Outbox/事件流水与幂等消费者，而不是将 DB 计数更新与异步队列入队误认为原子事务。测试应使用真实 MySQL 多连接并发执行 2/10/50 请求，验证最终计数精确等于成功请求数，并覆盖事务回滚和重复投递。

#### 32.5 本节结论与修复顺序

本轮没有修改业务代码、没有增加 migration，也没有执行本地或真实 MySQL 测试。新增风险包括 Token/DB 身份冲突未检测、Token-only enrichment 异常被吞、归因可变关系更新缺少共享栅栏，以及斗篷点击计数并发丢增量。

建议顺序：
1. 先定义单一 AttributionSnapshot 与显式状态枚举，统一 Token、Click DB、直连 Postback 的可信边界。
2. 让 Token 与 DB 归因字段冲突显式失败；禁止静默混合两个不同来源的租户归属。
3. 将 Offer.advertiser_id 与 Publisher.client_id 修改路径纳入归因锁/版本协议。
4. 将斗篷计数改成 MySQL 原子增量，并定义 Click 事件持久化的可靠 Outbox/幂等恢复策略。
5. 再与第 29 节 MySQL 权威事件决策账本、scope mutex、配置 CRUD 互斥合并实施，配套真实 MySQL 并发/故障测试。

这些问题仍属于上线前阻断项。不能把文档设计或 CI 通过当作代码修复完成。


### 33. 第八阶段复核：修正斗篷计数风险范围，并确认主计数器已有原子账本

对第 32.4 节“斗篷点击计数并发丢增量”进行调用链反查后，需要收窄此前表述，避免把系统主计数路径与斗篷落库辅助路径混为一谈。

#### 33.1 主短链计数器并非简单 ORM read-modify-write

`app/core/short_link_click_counter.py` 已实现较完整的计数同步机制：
- Redis 计数使用 Lua 原子操作；
- Redis 不可用时，DB fallback 使用 `ShortLinkClickSyncBatch` 唯一事件账本；
- DB 自增使用 SQL 表达式 `ShortLink.click_count + 1`，不是 Python 读-改-写；
- COMMIT 结果不确定时，通过唯一 batch_id 在新 Session 查询账本，避免盲目重复自增；
- 缓存失效确认后才 ACK 账本，失败保留待恢复状态。

因此，不能笼统声称“短链点击计数整体存在并发丢增量”。主计数器有 Redis Lua 与 DB 原子账本保护，应继续针对其 Redis 执行结果不确定、事件 ID 生成稳定性、批次刷盘和恢复 Worker 做专项验收，但不能把已存在的原子机制遗漏。

#### 33.2 风险仍存在于斗篷持久化模块的可选同步分支

`app/routes/short_link/cloak_click_persist.py` 中，当 `sync_short_link_click_count` 为真时，仍执行：
```python
short_link.click_count = (short_link.click_count or 0) + 1
await db_session.commit()
```

这是独立于 `short_link_click_counter.py` 的 ORM read-modify-write。若该分支与主计数器同时用于同一类点击，可能产生并发丢增量，也可能造成重复计数；是否实际启用及调用方是否已在外层计数，必须追踪 `sync_short_link_click_count` 的全部调用点后才能判定线上影响。

修复前必须先确认计数责任唯一：同一个点击事件只能由一个路径负责增加 short_links.click_count。若保留该分支，应改为原子 SQL，并通过事件幂等键防止与主计数器重复入账；不能只替换为 SQL 原子加一而忽略双路径重复计数。

#### 33.3 本节结论

第 32.4 节的总体风险已修正为“斗篷模块可选同步分支存在非原子 read-modify-write”，不再扩展到整个短链计数系统。主计数器已有原子 Redis/DB 机制，后续审计重点转为调用链去重、同事件双路径计数和账本恢复验证。本轮仍未修改业务代码。


### 34. 第九阶段复核：确认斗篷计数可选分支的真实调用条件

继续追踪 `cloak_report_service.py` 后，进一步收窄第 33 节的风险范围：

- 缓存命中路径调用 `persist_cloak_report_click(..., sync_short_link_click_count=False)`，不会在该函数内再次增加 click_count。
- 缓存未命中、回源 DB 的路径调用 `sync_short_link_click_count=True`，会进入第 33.2 节指出的 ORM read-modify-write 分支。
- `persist_cloak_report_click()` 默认参数也是 True，但目前已确认的主要调用方显式传入 True/False。

因此，当前能确认的风险不是所有斗篷点击都会重复计数，而是“缓存未命中 DB 回源路径中的计数自增并发非原子”。仍需核对缓存计数与 DB 回源分支的上游计数时序，确保缓存 miss 时此前没有已经成功计数；同时应以真实 MySQL 并发测试覆盖该分支。

修复建议仍是：在确认该分支确实承担唯一计数责任后，将其改为 SQL 原子增量；若计数可能已由 Redis/主计数器完成，则必须先统一计数所有权和幂等事件键，避免简单原子加一造成重复计数。

本轮仅补充调用条件核查，没有改动业务代码或测试。

### 35. 第十阶段复核：扣量配置唯一性存在并发写入旁路

本轮直接复核 `ConversionDeductionService`、`app/services/cpl/deduction/helpers.py` 与扣量管理 API，确认“同一作用域只能有一条激活配置”目前主要依赖应用层先查后写，尚未形成并发安全的数据库约束和统一锁协议。

#### 35.1 创建配置是典型 check-then-insert 竞态

`create_deduction_config()` 当前依次执行：
1. `validate_target_exists()`；
2. `check_existing_config()` 查询同一 level/target 的激活配置；
3. 创建 ORM 对象并 flush。

`check_existing_config()` 是普通 SELECT，不持有目标作用域互斥锁；数据库模型/当前迁移也未证明存在覆盖“激活配置唯一性”的唯一约束。两个并发事务可同时查到无激活配置，再分别插入两条 `is_active=true` 配置。事务隔离级别为 REPEATABLE READ 时，普通查询也不能替代明确的锁协议。

#### 35.2 单条与批量状态更新都能绕过创建时检查

- `update_deduction_config()` 对传入字段直接 setattr；只要 Update Schema 接受 `is_active`，更新接口即可直接把现有配置启用，而不调用 `check_existing_config()`。
- `update_deduction_config_status()` 直接设置 `config.is_active` 并 flush，没有重新检查目标作用域是否已有另一条激活配置。
- `batch_update_status()` 先按 ID 普通查询，再用批量 UPDATE 直接修改 `is_active`；它没有按 scope 排序加锁，也没有在锁后重新读取当前激活集合。
- 因而即使创建接口的预检查在单请求场景有效，单条更新和批量启用仍可能形成重复激活配置。

#### 35.3 删除与缓存 generation 也缺少同一作用域互斥

单条删除先普通读取配置，再 delete/flush 并推进 generation；批量删除也需核对其具体写入实现。创建、更新、启用、禁用、删除如果没有共享同一 scope mutex，可能与 Postback 决策同时发生，造成配置选择和 generation 快照不一致。只推进 generation 不等于阻止并发配置写入，也不等于锁定正在进行的财务决策。

#### 35.4 必须采用数据库级唯一性 + 所有写入口统一锁

建议按以下顺序实施，不得只在 API 层补一个 SELECT：

1. 明确唯一业务键：`(scope_type, scope_id)`，scope_type 分别为 advertiser / offer / publisher；同一作用域最多一条激活配置。
2. 上线前执行只读碰撞扫描，列出每个 scope 的多条 active 配置及其 ID、创建时间、优先级、扣量策略。存在冲突时停止迁移，由业务确认保留项，禁止自动随意停用。
3. 设计可验证的 generated active-scope key + UNIQUE 约束（或经 MySQL 版本验证的等价方案）；inactive 行的键必须为 NULL，且需验证 MySQL 多 NULL 唯一索引语义、字段长度、字符集和生成列表达式。
4. 所有单条和批量 create/update/status/delete 入口必须先按固定顺序锁定 scope mutex，再执行 current read 重新校验唯一性，最后写配置并在同一事务推进 generation。
5. 批量操作先去重 config IDs，再解析 scope、排序去重后统一加锁；锁后重新读取记录和父实体状态，不可依赖加锁前的 ORM 对象快照。
6. Offer / Advertiser / Publisher 的删除或级联删除也必须遵循同一锁协议；不能让父实体删除绕过配置唯一性维护。
7. 对配置 CRUD 与 Postback 决策并发时，统一定义锁顺序和隔离级别；避免只锁 scope 表，却仍使用旧 REPEATABLE READ consistent snapshot 读取配置。

#### 35.5 最低测试验收矩阵

必须用真实 MySQL 多连接、独立 Session 验证：
- 两个并发 create 同一 scope，只允许一个 active；
- 两条 inactive 配置并发 enable，只允许一个成功；
- batch enable 包含同 scope 多条记录时整批按定义失败或明确处理，不能留下重复 active；
- batch update 与单条 create/update/status/delete 并发；
- 两个批量请求以相反 ID 顺序操作时不产生永久死锁，死锁重试有界；
- 父实体删除与配置创建/启用并发；
- active unique 约束拒绝直接 SQL 写入的重复配置；
- generation 推进与 Postback 读取在 REPEATABLE READ 下不存在旧快照误用。

**本轮结论：** 该风险已由当前源码路径确认，不是推测。重复 active 配置会使 `get_config()` 的优先级选择变得不稳定，并可能让财务扣量规则随查询顺序/缓存状态变化。此项仍是 PR #205 财务阻断项；本轮仅增加审计证据，没有修改业务代码、没有新增 migration，也没有执行真实 MySQL 并发测试。

### 36. 第十一阶段源码复核：Redis 扣量计数在 MySQL 提交失败后无法回滚

本轮沿真实 Postback 调用链复核以下文件：`app/core/deduction/deduction_manager.py`、`app/core/postback/checks/discount_checker.py`、`app/core/postback/pipeline.py`、`app/core/postback/processor.py`。

#### 36.1 决策计数在数据库事务提交前已经写入 Redis

`DeductionManager._get_stats_for_decision()` 调用 `_DECISION_STATS_LUA`：
- 初始化 `decision_deducted` baseline；
- 对 `decision_seq` 执行 INCR；
- 对首次创建的 key 设置 48 小时 TTL；
- 将 Redis 返回值用于构造本次 `ConversionStats`。

随后随机/哈希策略命中扣量时：
- 有窗口总量时调用 `_reserve_volume_deduction()`，由 Lua 对 `decision_deducted` 执行 INCR；
- 无窗口总量时调用 `_incr_decision_deducted()`，同样递增 Redis 计数。

以上 Redis 写入均发生在 Postback MySQL 事务提交之前，且没有与 MySQL 事务共享的持久化 reservation/恢复账本。

#### 36.2 命中扣量分支的实际提交路径没有 Redis 结果协调

真实调用链如下：
1. `pipeline.step_apply_discount()` 调用 `DiscountChecker.calculate()`；
2. `DiscountChecker.calculate()` 调用 `apply_deduction()`，先更新 Redis 决策序号/扣量计数；
3. 命中 volume deduction 后调用 `log_deduction()`，将 `ConversionDeductionLog` 加入当前 SQLAlchemy Session 并 flush；
4. 返回 `skip_save_and_forward=True`；
5. `PostbackProcessor.process()` 在该分支直接执行 `await db.commit()`，提交扣量日志和事件收据；
6. 若该 commit 抛出异常，控制流进入外层异常处理，只尝试 `db.rollback()` 并重新抛出；没有针对上述 Redis decision_seq / decision_deducted 的安全回退或账本恢复。

对照普通转化 Cap reservation：普通转化使用 `_commit_conversion_with_cap_reconciliation()` 和 `CapReservationLedger`，有 MySQL 事务内状态栅栏、commit-unknown 查询及 Redis token finalize/recovery。扣量 Redis 计数目前没有等价机制。不能把 Cap 的恢复能力误认为 CPL 扣量也已具备。

#### 36.3 可复现的错误状态

当 Redis 更新成功、扣量日志 flush 成功，但 MySQL COMMIT 最终回滚或确认未提交时：
- 数据库没有该事件的扣量日志/持久化扣量事实；
- Redis 的 decision_seq 仍然前进；
- 若命中扣量，decision_deducted 仍然增加；
- 同一事件重试可能读取不同 processed/deducted 基线，产生不同决策；后续不同事件也可能受 ghost counter 影响。

若 COMMIT 响应丢失而数据库实际已提交，当前分支同样没有按事件唯一键核对扣量日志/receipt 终态并返回既有结果的专用恢复逻辑。不能仅凭异常就 DECR，因为并发请求可能已经观察或使用这些计数；无条件补偿可能造成计数虚低和超额扣量。

#### 36.4 修复要求

本问题不能以简单 Redis DECR、延长 TTL、捕获 commit exception 后 best-effort 补偿或给 Redis 操作增加重试来关闭。

必须采用第 3–7 节定义的 MySQL 权威事件决策账本：
- 在同一 MySQL 事务中以 canonical event identity 争取唯一事件；
- 锁定唯一 scope，按同一个 decision_now 查询 24 小时滑动窗口；
- 将本次决策结果、窗口快照、扣量日志/转化事实与事件 receipt 一起提交；
- commit-unknown 时通过新 Session 按唯一事件身份恢复已提交终态；
- Redis 仅保留可重建缓存，不再参与扣量决策、序号或名额仲裁。

必须增加真实 MySQL + Redis 集成故障测试：
1. Redis 决策计数成功后，强制 MySQL commit 失败：账本、receipt、扣量日志均回滚，后续事件决策不受 ghost counter 影响。
2. Redis 计数成功后，flush 失败：不产生任何已处理事件状态。
3. COMMIT ACK 丢失但 MySQL 实际提交：重试读取同一事件终态，不重复决策/扣量。
4. COMMIT 确认未提交：重试可以安全重新决策。
5. 同 scope 2/10/50 个并发事件与故障注入组合：窗口统计和扣量额度准确。
6. Redis 停机、重启、清空或 key 过期：已提交财务结果不变化。
7. 并发请求期间禁止使用无条件 DECR 补偿造成计数回退。

**本轮结论：** 已从源码确认 Redis 扣量计数先于 MySQL commit，且 volume-deduction 分支缺少与 Cap reservation 等价的提交协调机制。该缺陷属于财务正确性阻断项。本轮只补充源码证据与测试要求；没有修改业务代码、没有新增 migration、没有执行真实 MySQL/Redis 故障注入测试。PR #205 继续保持 Draft，不得合并。

#### 36.5 现有测试覆盖边界：Cap 有提交协调测试，CPL 扣量没有对应故障测试

对当前分支以下测试文件进行源码核对：

- `tests/test_deduction_stats_accounting.py`：验证统计 SQL 计数来源、时间半开区间和 strict 模式绕过缓存；没有模拟 Redis 计数成功后 MySQL commit 失败。
- `tests/test_deduction_fail_open_semantics.py`：验证 Redis 不可用、Redis eval 失败时跳过不安全扣量；主要通过 Mock 替换统计/Redis 方法，没有覆盖 Redis 已成功递增、随后真实 MySQL 事务回滚的状态。
- `tests/test_discount_checker_deduction_log_fail_closed.py`：验证扣量日志写入失败时 fail-closed；测试的是日志函数抛错，不是日志 flush 成功后 commit 失败。
- `tests/test_postback_event_receipt_mysql_integration.py`：真实 MySQL REPEATABLE READ 测试覆盖 receipt 并发、正常转化 receipt 释放及 rollback 后重试；没有调用真实 DeductionManager，也没有覆盖 Redis decision counter 与扣量日志提交协调。
- 对照 `tests/test_cap_reservation_postback_integration.py`：Cap 路径已有 stage-commit、数据库 commit、ledger finalize 顺序和禁止 stale Redis compensation 的专项测试；这类提交栅栏在 CPL volume deduction 路径尚未建立。

因此，现有测试通过不能证明 CPL Redis/DB 双写一致。后续实现必须新增端到端 MySQL + Redis 故障注入测试，不能只增加对内部 helper 的 Mock 单元测试。

### 37. 第十二阶段源码复核：当前顺序策略已 fail-open 跳过，但哈希策略仍存在同事件重复预留

本节用于校准此前对策略执行范围的描述，以当前源码 `86e0e495eef9156cb5cdf69ec7f3efee58cf888c` 为准。

#### 37.1 当前真正执行的 volume 策略范围

`DeductionManager.apply_deduction()` 当前明确执行以下保护：
- 必须提供经过验证的 `platform + conversion_id + normalized event_name`，否则跳过 volume deduction；
- `proportional`、`round_robin` 等非 `random/hash/deterministic` 策略被主动跳过，日志说明等待 MySQL 事务账本；
- 只有 `random`、`hash`、`deterministic` 进入当前 Redis 统计与名额预留路径；
- `random` 当前由 `RandomDeductionStrategy` 继承确定性 SHA-256 策略，并非真正随机数策略。

因此此前将顺序策略描述为当前仍依赖 Redis processed 序号执行，需要更正：当前调用路径已经将这些策略跳过。相关历史策略代码仍存在，但不能据此认定运行路径会执行。

#### 37.2 事件哈希稳定，不等于 Redis 名额预留幂等

当前事件决策键通过长度前缀编码后 SHA-256：
`event:v1:SHA256(platform, conversion_id, event_name)`。

它只作为 `should_deduct_volume()` 的确定性哈希输入。后续 Redis 名额预留使用 scope 级 `decision_deducted` key：
- `_RESERVE_DEDUCTED_LUA` 只检查 scope 当前计数与 limit，然后 INCR；
- Lua 不接收 event decision key，也没有 per-event reservation token；
- 同一事件重试会再次执行同一个 scope INCR；
- `_incr_decision_deducted()` 同样只对 scope key INCR，不记录事件身份。

所以事件身份虽稳定，名额预留却不是事件幂等操作。Postback receipt 可以阻止已成功提交事件的后续重放，但无法撤销第一次 DB rollback 后遗留的 Redis INCR，也无法保证 commit-unknown 的未提交重试复用同一个预留结果。

#### 37.3 同一事件可能出现决策结果漂移

可复现的逻辑序列：
1. 事件 E 的稳定 hash 命中扣量；
2. Redis `decision_deducted` 成功 INCR；
3. MySQL 扣量日志/receipt COMMIT 失败且确认未提交；
4. E 重试，receipt 因第一次事务回滚而不存在；
5. E 的 hash 仍命中，但 Redis 名额计数已包含第一次失败尝试；
6. 如果该计数已达到 limit，第二次 `_RESERVE_DEDUCTED_LUA` 返回 -1，E 本次不再扣量。

即：相同事件身份、相同配置、相同哈希输入，因第一次失败请求污染 Redis scope counter，最终可能得到不同业务结果。

#### 37.4 24 小时 DB 窗口与 48 小时 Redis key 的源码行为

当前 `get_recent_stats(strict=True)` 使用 `[end_time - 24h, end_time)` 直接查询 MySQL；但 `_get_stats_for_decision()` 随后把统计结果与 Redis 状态合并：
- `decision_seq` 和 `decision_deducted` TTL 均由 `DECISION_SEQ_TTL=48h` 管理；
- Redis key 存在时，不会用每次新查询到的 DB deducted 基线覆盖 Redis deducted；
- Redis `decision_deducted` 只在 key 缺失时初始化为 DB 当前 deducted；
- Redis 名额递增不会按事件离开 24 小时窗口而递减；
- `total=max(seq, base_stats.total)`，`processed=seq-1`，二者语义不同，不能把 seq 直接当作 24 小时内已处理事件数。

因此，严格 DB 查询本身使用 24 小时半开窗口，并不意味着最终决策统计也严格遵守 24 小时窗口。Redis 48 小时存活期间，已离开 DB 窗口的旧扣量仍可能留在 Redis deducted 中。Redis 重启/key 淘汰后又会重新从当前 DB 窗口基线初始化，决策基线可能跳变。

#### 37.5 当前不应做的局部修补

- 不要只把 Redis TTL 从 48h 改为 24h：TTL 从 key 创建时间计算，不是每个事件的滚动窗口清理；key 过期会整体重建基线。
- 不要只在 MySQL rollback 后 Redis DECR：无法安全区分该 INCR 是否已被其他并发请求观察、是否被后续名额判断消费。
- 不要只给 Lua 增加 event key 去重而继续让 Redis 决定财务名额：Redis 去重状态与 MySQL 事件终态仍会在故障/过期时分叉。
- 不要恢复顺序策略的 Redis seq 执行，除非先建立 MySQL 权威的顺序决策序列及 scope 串行化。

正确方向仍是：同一 MySQL 事务中以事件唯一键争取处理权、锁定 scope、读取一致窗口快照、写入不可变决策结果和扣量日志/receipt；Redis 只做非权威缓存。必须先明确同一 scope 的并发串行化和 MySQL REPEATABLE READ 快照策略，再实现，不可只增加一个 scope lock 就宣称解决。

**本节结论：** 当前代码已跳过顺序策略，但 random/hash 的 scope Redis 计数仍可能被同事件失败重试重复消费；且 48h Redis deducted 与 24h MySQL 统计窗口不一致。财务阻断依旧存在。

### 38. 第十三阶段事务隔离复核：Postback 先建立普通一致性读快照，之后加 scope 锁不能自动刷新统计快照

本轮核对 `app/core/database.py` 与当前 Postback 处理顺序。

#### 38.1 当前连接未显式指定 SQLAlchemy isolation_level

`create_async_engine()` 配置了连接池、`pool_pre_ping`、`pool_recycle` 等参数，但没有传入 `isolation_level`。因此应用没有在引擎层显式固定 MySQL 事务隔离级别，实际值由数据库服务端/会话配置决定。

MySQL 8.4 官方文档说明 InnoDB 默认隔离级别为 REPEATABLE READ；在该级别，普通一致性读使用事务第一次一致性读时建立的 read view，后续普通 SELECT 继续读取该快照。参见：
- https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html
- https://dev.mysql.com/doc/refman/8.4/en/glossary.html

生产环境不能仅凭代码假设隔离级别；必须在连接池实际连接上采集 `@@transaction_isolation`、`@@session.transaction_isolation`，并在 CI MySQL 服务中断言。

#### 38.2 Postback 在扣量统计之前已经执行普通 SELECT

当前 `PostbackProcessor.process()` 先执行 Click 关联、Offer 状态检查和重复检测，再进入扣量计算。
其中 `DuplicateChecker.is_duplicate()` 在插入 receipt 前先执行普通 `SELECT PostbackConversion.id ...`；ClickAssociator、Offer 状态检查等路径也有普通查询。

在 MySQL 默认 REPEATABLE READ 下，这些普通 SELECT 可能已经建立当前事务的一致性读快照。之后即使在扣量计算阶段新增 `SELECT scope_lock ... FOR UPDATE` 并等待另一个请求提交，后续普通 `get_recent_stats()` 聚合查询仍可能读取之前建立的旧快照，而不是 scope 锁释放时的最新已提交统计。

MySQL 官方文档还明确指出，在 REPEATABLE READ 事务中混合 locking read 与 nonlocking consistent read 时，两者可能看到不同数据库状态；locking read 使用较新的状态，普通 SELECT 使用既有 read view。参见：
- https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html

#### 38.3 为什么单加 scope lock 不足以证明无幻读/无漏计

scope lock 可以串行化遵守同一锁协议的写入者，但不能自动改变当前事务已经建立的一致性读快照。若事务 A 在建立旧快照后等待 scope lock，而事务 B 持锁写入新决策并提交，A 获锁后继续用普通 SELECT 汇总，可能看不到 B 的新记录，仍然基于旧 total/deducted 作决策。

因此，未来实现必须在以下方案中明确选择并进行真实 MySQL 验证：
- 在 Postback 事务开始之前就为专用处理事务明确设置 READ COMMITTED，并证明设置发生在任何隐式 autobegin/查询之前；不能在事务已经开始后才尝试修改当前事务隔离级别。
- 使用可证明为 current read 的账本/计数行更新协议，所有事件和配置写入均遵循同一 scope 锁顺序；不能混用旧快照聚合和当前读结果。
- 采用独立、事务化的 scope 统计/窗口桶表，在 scope 锁内以原子 SQL 更新与过期桶清理，证明窗口边界、重试和崩溃恢复语义。

不能仅因代码出现 `with_for_update()` 就声称解决了 RR 快照、幻读或并发统计。

#### 38.4 必须加入的真实 MySQL 隔离测试

1. 测试启动时记录并断言 `@@session.transaction_isolation`，不允许 CI 环境悄悄使用不同隔离级别。
2. A 事务先执行普通 SELECT 建立快照；B 获取 scope 锁、写入 ledger 并提交；A 再获取 scope 锁后查询统计，验证所选方案确实看到 B 的提交。
3. 反向顺序：A 先锁 scope，B 等待；A 提交后 B 必须读取包含 A 的新窗口统计。
4. 同一 scope 2/10/50 并发，验证无漏计、重复计数和额度超发。
5. 同时覆盖窗口边界事件滚入/滚出、commit-unknown、死锁 1213、锁等待超时 1205、事务重试。
6. 配置创建/启用/禁用与 Postback 并发时，验证配置版本和统计窗口快照属于同一决策时点。

**本节结论：** 当前代码未显式固定 MySQL 隔离级别；Postback 在扣量前已执行普通 SELECT。若数据库使用 InnoDB 默认 REPEATABLE READ，未来只增加 scope 锁仍可能基于旧 read view 决策。此项是账本重构的设计约束，必须先解决再编码。
