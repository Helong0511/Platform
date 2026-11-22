# Telegram Chat ID 日志脱敏专项审计（2026-11-22）

## 问题

`message_sender.py` 的普通消息发送成功日志、429 限流日志、带按钮发送成功日志和无效 Chat ID 日志原样输出 Telegram Chat ID。Chat ID 是可关联到个人私聊或业务群组的标识，不应作为普通应用日志字段长期留存。

此前 Token/代理凭据和管理员 ID 已从诊断报告与初始化日志中移除，但发送路径仍有这几处标识泄露。

## 修复

- 新增 `_chat_target_type_for_log()`，只返回 `group_or_channel`、`private_user` 或 `unknown`。
- 普通消息成功日志不再输出 chat_id。
- 429 限流日志不再输出 chat_id。
- 带按钮消息成功日志不再输出 chat_id。
- 无效 Chat ID 日志不再输出输入原文。
- 不改变发送目标、限流 key、Redis backoff key 或 Bot API 参数；只调整日志字段。

## 回归测试

- 验证 helper 只输出目标类别，不返回原始标识。
- 捕获普通消息成功日志，确认原始群组 ID 不出现。
- 捕获带按钮成功日志，确认原始群组 ID 不出现。
- 捕获无效 Chat ID 日志，确认原始输入不出现。

## 注意

Redis 限流键仍使用真实 Chat ID，这是实现 per-chat 限流所必需；这些值只作为 Redis key，不得写入应用日志。Redis keyspace、监控标签和异常追踪也不应把原始 Chat ID 作为 metric label。
