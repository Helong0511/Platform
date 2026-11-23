# 短链接点击刷盘账本清理健康状态

## 设计边界

点击入账（Redis pending -> MySQL click_count + 唯一账本 + Redis ACK）与账本历史清理是两个不同的可靠性边界。历史清理失败不能让已经成功入账的点击批次被误报为失败，也不能把 Redis 状态未知时的未 ACK 账本删除。

`_cleanup_click_sync_batch_ledger()` 仍在点击同步流程末尾运行，但它独立记录自己的健康状态，并且不会把清理失败抛成点击主入账失败。Redis 状态检查失败、缓存失效未确认时，保留对应未 ACK 账本；已确认 ACK 的历史记录才允许按保留期清理。

## 持久化状态

增量 Migration：`20261123_click_sync_ledger_cleanup_state`。

表：`short_link_click_sync_ledger_maintenance`，单例行 `id=1`。只存聚合计数、应用时区时间和错误类别，不保存 SQL、连接串、Redis URL、batch_id、short_code 或原始异常文本。

- `status`: `unknown / healthy / degraded / failed`
- `consecutive_failure_count`: 连续异常轮数；成功轮次清零
- `total_failure_count`: 累计异常轮数
- `last_attempt_at`、`last_success_at`、`last_failure_at`: 最近尝试/成功/失败时间
- `last_error_type`: 安全错误类别摘要
- 最近一轮扫描、补 ACK、删除、Redis 检查失败和缓存失效失败计数

如果主清理事务失败，先回滚当前事务，再通过独立 AsyncSession 尝试写入失败状态。若数据库整体不可用，状态写入也可能失败；此时只记录脱敏日志，不伪造持久化成功。

## 监控 API

`GET /api/v1/monitoring/metrics/click-sync-ledger`

保留未 ACK 数量和最老未 ACK 年龄，并增加 `cleanup` 对象，提供清理状态、连续/累计失败次数、最近失败时间、错误类别及最近一轮计数。顶层状态在没有 backlog 但清理状态异常时返回 `degraded`；状态行缺失时返回 `unknown`，不伪装为健康。

数据库查询失败继续向上抛出，不返回健康默认值。监控响应不包含短链代码、batch_id 或原始异常文本。

## 数据库升级与验收

部署前必须通过正式 Migration Runner 应用 `20261123_click_sync_ledger_cleanup_state`；迁移会创建表并初始化单例行。不要只修改 ORM 或手工在生产执行不受控 DDL。全新/可丢弃环境的 `sql/platform.sql` 已同步该表结构。

MySQL 8 集成测试验证：
- Redis `EXISTS` 抛错时状态持久化为 degraded，未 ACK 行仍保留；
- 清理恢复成功时连续失败次数清零，但历史 `last_failure_at` 和累计次数保留；
- 主事务 commit 失败时当前事务回滚，并通过独立 Session 持久化 failed 状态；
- 健康接口读取持久化状态，DB 不可用时不伪报 healthy。
