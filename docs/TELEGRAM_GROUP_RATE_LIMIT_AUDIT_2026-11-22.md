# Telegram 群组发送限流审计（2026-11-22）

## 问题

发送器原来对所有 Chat ID 使用 1.1 秒 per-chat 间隔。Telegram 官方 Bot FAQ 指出：私聊应避免超过约 1 条/秒，而群组内 Bot 发送上限约为每分钟 20 条。项目的 `validate_chat_id` 明确允许负数群组 ID，因此群组管理员通知也会走发送器；1.1 秒间隔约等于每分钟 54 条，可能触发群组 429。

## 修复

- 正数私聊继续按 1.1 秒间隔。
- 负数 Chat ID（群组/超级群组/频道 ID）按 3.1 秒间隔，低于 20 条/分钟上限并留出调度余量。
- Redis 跨进程 per-chat gate 与进程内退避统一使用动态间隔。
- 异步外层发送超时预算使用两类间隔中的较大值，避免群组场景低估发送时长。

## 回归测试

- 私聊、群组、超级群组、无 Chat ID 的间隔判定。
- 验证群组的 Redis gate 实际使用 3.1 秒。

官方参考：
- https://core.telegram.org/bots/faq#my-bot-is-hitting-limits-how-do-i-avoid-this
