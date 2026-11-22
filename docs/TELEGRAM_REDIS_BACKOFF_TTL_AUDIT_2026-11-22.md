# Telegram Redis 429 共享退避 TTL 审计（2026-11-22）

## 原问题

`app/core/telegram/message_sender.py:_note_rate_limited` 对全局和 per-chat 429 backoff 使用无条件 `SETEX`。Redis 会覆盖原 TTL，因此后到达的较短 `retry_after` 可以缩短先前已经记录的较长退避时间。

示例：先记录 120 秒，再记录 5 秒，旧逻辑会把共享 backoff 改为 5 秒；其它 worker 可能在最长服务端限流窗口结束前恢复发送。

## 修复

- 新增 `_UPDATE_BACKOFF_MAX_TTL_LUA`，通过单条 Lua 原子比较并更新 key 的剩余 TTL。
- key 不存在时设置新值和 TTL。
- 已有 TTL 大于新请求时保持不变。
- 新请求 TTL 更长时才延长 TTL。
- 永久 key（PTTL=-1）保持永久，不被短退避改成有限 TTL。
- 全局 backoff 与 per-chat backoff 均使用相同原子脚本。
- 最大 TTL 仍由 `MAX_SERVER_BACKOFF_SECONDS` 限制。

## 测试

- 单元测试覆盖 120 秒后写入 5 秒不得缩短、随后写入 180 秒必须延长。
- 真实 Redis 集成测试在隔离 DB14 中验证 Lua 原子脚本及 PTTL 语义。
- 集成测试沿用仓库现有的 loopback DB14 安全门禁，不会连接生产 Redis。

## 业务边界

这项修复只确保共享退避遵守“最长等待时间优先”，不改变发送队列、消息幂等或 Redis 故障时的既有降级策略。
