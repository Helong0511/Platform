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
- 认领成功后回读数据库实际写入的秒级 DATETIME，作为 fencing token 返回调用方。
- 续租同时使用数据库时钟判断有效期，且要求旧令牌不晚于数据库当前时间；已过期令牌不能复活。
- 同一秒更新返回 changed-rows=0 时，只有数据库确认原令牌仍有效才返回原 token，不伪造续租。

提交 87121eaec9f77ef96d1d7e8bfb0d40ebbf5a8c52：
- 更新 MySQL 隔离集成测试。
- 模拟 Worker A 本机时钟慢一天、Worker B 本机时钟快一天。
- 验证快时钟 Worker 不能提前接管有效租约；只有数据库时间确认原租约过期后才能接管。
- 验证旧 Worker 不能续租或修改新 Worker 已接管的记录。

## 仍需保留的边界

- 数据库时钟成为租约判定权威；部署环境仍应保持 MySQL 主从节点时间同步，并监控数据库时钟异常。
- report_start_time 目前兼作租约令牌和历史发送时间字段；秒级 DATETIME 令牌存在同秒复用边界。当前通过原子条件 UPDATE、唯一当前值及 lease fencing 缓解，但未来如需更强 fencing，可新增独立随机 lease_token 列并以条件更新比较。
- 外部平台已接收事件而本地 ACK 丢失时，仍可能发生重试；稳定 event_id 用于第三方幂等去重，不能把系统描述为严格 exactly-once。
- 本地 CI/隔离 MySQL 故障注入通过后，仍需在与生产相同的 MySQL 版本、时区设置和多 Worker 部署形态下演练。

## 验收

验收以最新代码 SHA 对应的 GitHub Actions 最终结果为准，必须同时通过 Backend 与 Frontend；Backend 必须执行 MySQL/Redis 集成测试，不能只以静态编译或 SQLite 单测替代。历史上因连续提交而取消的运行不计入验收。
