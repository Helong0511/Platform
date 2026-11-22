# Telegram 429 RetryAfter 长等待审计（2026-11-22）

## 问题

旧实现把 Telegram 返回的 `retry_after` 强制截断到 `MAX_RATE_LIMIT_WAIT=120` 秒，再在持有发送互斥锁时等待 120 秒后重试。若 Telegram 明确要求 300 秒或更长，当前 worker 会早于服务端允许时间再次发送，可能持续触发 429；Redis 共享 backoff 也只设置 120 秒，其他 worker 同样会过早恢复。

## 修复

- 区分“单次调用内同步等待预算”与“服务端共享 backoff TTL”。
- 单次调用仍最多同步等待 120 秒，避免业务请求无限挂起。
- Redis backoff 按服务端原始 `retry_after` 保存，最大安全上限 24 小时。
- 当服务端要求等待超过 120 秒时，当前发送请求立即停止重试并返回失败，不再提前 sleep 120 秒后重试。
- 其它 worker 读取完整 Redis TTL；如果等待超过互斥锁预算，获取锁超时并 fail closed，不会提前发送。
- 普通消息、带按钮消息、通用 PTB API 调用都不再截短服务端 RetryAfter。

## 回归测试

- 验证 300 秒 retry_after 写入全局和 per-chat Redis backoff 时仍保留 300 秒。
- 使用 `timedelta(seconds=300)` 模拟 Telegram 429，断言只发送一次、不 sleep、不提前重试，并释放发送互斥锁。

## 降级边界

Redis 不可用时跨进程共享 backoff 无法保证；当前发送器保留 best-effort 本地降级行为。生产多 worker 应将 Redis 可用性纳入监控。
