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

