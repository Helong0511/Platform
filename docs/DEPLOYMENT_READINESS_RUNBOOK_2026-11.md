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

恢复任务遵循 fail-closed：Redis 状态 UNKNOWN、Total token ABSENT 或 token 存在但 counter 丢失时，保留证据并进入 NEEDS_RECONCILIATION，不进行猜测性扣减。

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

## 7. 本轮验证证据

- 最新通过的跨存储 CI：Run #783，SHA `042026e6c654753ec91b2ec72748c85d94b11f61`。
- Run #783：Backend / Frontend / Playwright Mock API E2E 全部成功；293 passed、1 skipped。
- CI 使用临时 MySQL 8.0 数据库与 Redis DB14，包含真实跨存储孤儿回滚、已提交转化保留、并发 claim 和双恢复 Worker 验证。
- 上述证据仅证明 CI 隔离环境通过，不代表已在生产环境部署或验证。


## 8. 明确保留的范围外风险

CI 的前端 `npm audit --omit=dev` 仍报告 2 个 High 项，均由直接依赖 axios 间接引入 follow-redirects，公告涉及跨域重定向时敏感凭据/请求头的剥离行为。该问题属于用户明确排除的“凭据安全”专项，本轮没有修改相关依赖或重定向逻辑。

因此：
- 不得将当前依赖审计描述为“零漏洞”。
- 该风险必须作为独立的凭据安全事项留档并由发布负责人单独接受/安排修复。
- 本轮其余非凭据安全问题仍按本手册继续验收。
