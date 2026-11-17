# Third-party Report Outbox 租约与重试可靠性审计（2026-11-16）

## 本次发现：Outbox 租约使用 Worker 本机时钟

### 风险

此前 _claim_report_log() 与 _renew_report_log_lease() 使用 get_app_now_naive() 生成租约时间并判断租约是否过期。多台 Worker 的系统时钟可能存在偏差：

- 快时钟 Worker 可能把慢时钟 Worker 尚有效的 report_start_time 误判为过期并提前接管，导致两个 Worker 同时向第三方发送同一事件。
- 慢时钟 Worker 可能延迟认领真正已到期的任务，影响队列恢复时效。
- 租约令牌、过期判断和重试时间如果分别受不同 Worker 本机时钟影响，会扩大边界不确定性。

### 修复

提交 3ae743935d019b2525e5a6bd1eebedde64d6ba84：
- 认领时的 report_start_time 写入使用 get_app_now_sql_expression()，由数据库统一时钟产生。
- 租约过期判断、next_retry_time 到期判断使用同一数据库时钟表达式。
- 早期实现曾回读数据库秒级 DATETIME 作为 fencing token；该方案已由后续独立随机令牌方案替代。
- 续租同时使用数据库时钟判断有效期，且要求旧令牌不晚于数据库当前时间；已过期令牌不能复活。
- 重试时间、租约释放时间、Outbox 扫描和 PII 租约过期判断统一使用数据库时钟表达式。

提交 87121eaec9f77ef96d1d7e8bfb0d40ebbf5a8c52：
- 更新 MySQL 隔离集成测试。
- 模拟 Worker A 本机时钟慢一天、Worker B 本机时钟快一天。
- 验证快时钟 Worker 不能提前接管有效租约；只有数据库时间确认原租约过期后才能接管。
- 验证旧 Worker 不能续租或修改新 Worker 已接管的记录。

## 2026-11-16 后续整改：独立随机 fencing token

### 已实现的代码与结构

- 新增 ORM 字段 `ThirdPartyReportLog.lease_token`：`CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL`。
- 新增前向迁移 `20261116_third_party_report_random_lease_token`，加入迁移清单并登记 SHA-256；不修改任何既有迁移文件或 checksum。
- 每次原子认领通过 `secrets.token_hex(16)` 生成独立 128-bit 随机令牌，并与 DB 生成的 `report_start_time` 一起写入。
- `report_start_time` 只用于租约时效判断；不再作为 fencing token，也不再以秒级 DATETIME 相等来识别 Worker。
- 续租、发送前核验、Pixel 目的地绑定、终态更新都按随机令牌匹配；终态更新会清除令牌。
- 失败重试、手动重试和耗尽状态归一化会释放/清除旧令牌；旧 Worker 的令牌不能更新新 Worker 的记录。
- 管理端修改身份/载荷时的活动租约判断也改用数据库当前时间。
- 旧记录保持 `lease_token=NULL`；下一次成功认领时才生成新令牌，不把旧时间戳伪装成随机令牌。

### 迁移与部署注意事项

- 新迁移把列追加到表尾，尽量利用 MySQL 8.0.29+ 的 INSTANT ADD COLUMN；MySQL 8.0.16–8.0.28 的实际 DDL 算法仍需在目标版本验证。
- CHECK 约束添加仍可能需要扫描/验证现有数据；上线前必须在相同 MySQL 版本、相近数据量副本测量锁等待、耗时和磁盘影响。
- 部署新代码前必须停止并排空所有旧版 API / Scheduler / Worker。旧版进程不知道 `lease_token`，不能与新版混合运行，否则旧 Worker 可能绕过新令牌条件。
- migration runner 必须先于应用启动执行；应用账号不得自行执行 DDL。生产账号 grants、真实迁移 job 演练仍是上线验收项。

## 仍需保留的边界

- 数据库时钟成为租约判定权威；部署环境仍应保持 MySQL 主从节点时间同步，并监控数据库时钟异常。
- 外部平台已接收事件而本地 ACK 丢失时，仍可能发生重试；稳定 event_id 用于第三方幂等去重，不能把系统描述为严格 exactly-once。
- 新增迁移尚未在生产等价环境执行；CI/隔离 MySQL 验证通过也不能替代目标 MySQL 版本、时区设置、数据规模和多 Worker 部署形态下的 DDL/故障演练。
- 当前随机令牌改造以最新分支 CI 结果为准；任何尚未通过的 CI 不能作为验收通过依据。

## 验收

验收以最新代码 SHA 对应的 GitHub Actions 最终结果为准，必须同时通过 Backend 与 Frontend；Backend 必须执行 MySQL/Redis 集成测试，不能只以静态编译或 SQLite 单测替代。历史上因连续提交而取消的运行不计入验收。


## 2026-11-16 后续整改：Purchase → ViewContent 关联的 PII fencing

### 风险与修复

- Purchase → ViewContent 关联候选查询必须排除 `pii_scrubbed_at IS NOT NULL` 的历史行。否则已完成保留期清理的 ViewContent 即使其 `adsid` 已被清空，若存在历史部分清理或异常残留，也可能被新 Purchase 再次写入 `conversion_id`，破坏 PII 清理不可逆边界。
- 当前查询同时要求候选 ViewContent 的 `pii_scrubbed_at IS NULL`、`conversion_id IS NULL`，并按 source、adsid、事件类型、身份作用域、平台和 Pixel 限定。
- Purchase 本身在同一事务内锁定并重新校验随机 `lease_token`、数据库租约时效、事件身份、Pixel、作用域及未清理状态。过期或已被接管的 Worker 不得建立关联。
- PII 清理使用 `FOR UPDATE SKIP LOCKED`。关联事务先锁 Purchase 再锁 ViewContent；若清理事务已持有候选行锁，关联事务的 `SELECT ... FOR UPDATE` 会等待该锁释放（关联查询本身没有使用 `SKIP LOCKED`），随后按 InnoDB 当前读重新判断 `pii_scrubbed_at IS NULL`，已提交清理的行不会成为候选。清理与关联事务竞争时，不应恢复已清理数据。

### 回归验证

- 在隔离 MySQL 集成测试中增加已清理 ViewContent 拒绝关联的用例。
- 增加 Purchase 租约已过期的旧 Worker 拒绝关联用例。
- 保留既有双 Purchase 并发争抢同一 ViewContent 的测试，确保同一候选行最多被一个 Purchase 关联。
- 最新相关提交：`d4fe76879a77e73d11576d8ca21015f4f8f00c3d`、`bca65fb3e4ed7c0a977a4b2d8326a0e6c51ab235`。
- 对应 CI Run #1860：Backend、Frontend、Lint、Build、Playwright Mock API E2E 均通过。该结果仅证明 CI 隔离环境覆盖的行为，不代表生产规模故障演练。

### 验收限制

- 已新增 `tests/test_third_party_report_outbox_mysql_integration.py::test_mysql_purchase_link_waits_for_pii_scrub_and_never_restores_link`：使用两个独立 MySQL 事务和可控事件屏障，先让 PII 清理事务取得 ViewContent 行锁，再启动 Purchase 关联并确认其锁定查询确实阻塞；释放清理事务后，断言清理完成、关联返回 False，且 `pii_scrubbed_at`、清空后的 `adsid`、PII 字段和 `conversion_id` 均未被恢复。该测试覆盖确定性交错时序，不等同于高并发压力测试或多实例生产故障演练。
- 不得通过删除 `pii_scrubbed_at`、重新填充 `adsid` 或恢复历史 `conversion_id` 的方式修复关联失败。
- 若未来调整 PII 清理字段或关联流程，必须同步更新本节测试，并验证旧 Worker fencing 和清理不可逆性。
