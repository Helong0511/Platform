# Telegram SDK 22.8 集成专项审计与修复记录（2026-11-22）

## 审计范围

- Python Telegram SDK：`python-telegram-bot`
- HTTP 传输：`httpx` / PTB `HTTPXRequest`
- Bot 初始化、发送专用事件循环、Application 长轮询、限流/重试、连接诊断
- 依赖声明、回归测试与 CI

## 依赖结论

当前 `requirements.txt` 声明 `python-telegram-bot==22.8` 与 `httpx==0.28.1`。截至本次审计，PTB 官方发布页将 22.8 标记为最新版本；官方文档要求核心 HTTPX 版本满足 `>=0.27,<0.29`，因此当前组合兼容。项目使用 `Bot`、`HTTPXRequest`、`Application`、`CommandHandler`、`CallbackQueryHandler` 等核心 API，没有证据要求安装 `[all]` 或 `[ext]` 可选依赖。若未来使用 PTB 的 `AIORateLimiter`、JobQueue、Webhook 或 SOCKS 代理，再按实际功能启用对应 extra，避免无用依赖。

官方参考：
- https://github.com/python-telegram-bot/python-telegram-bot/releases
- https://docs.python-telegram-bot.org/en/v22.8/
- https://docs.python-telegram-bot.org/en/v22.8/telegram.error.html
- https://docs.python-telegram-bot.org/en/v22.8/telegram.request.httpxrequest.html

## 本次确认并修复

### 1. RetryAfter 对 timedelta 的兼容

PTB 22.2 起，`RetryAfter.retry_after` 除整数外也接受 `datetime.timedelta`，并允许通过 `PTB_TIMEDELTA=1` 提前切换该类型；官方说明未来大版本将把该属性改为 timedelta。旧代码直接执行 `int(retry_after)`，对 timedelta 会抛出 TypeError，随后把异常文本交给只识别 “retry after N” 的正则，最终错误地回退到 60 秒。

影响：当 Telegram 要求的等待时间小于 60 秒时，可能无谓延迟；大于 60 秒时可能提前重试，再次触发 429。

修复：识别 timedelta 并用 `total_seconds()` 转换；数值向上取整，避免毫秒级等待被向下截断；拒绝 bool、非有限值和无法识别的类型，保留文本兼容回退。

回归测试覆盖整数、整秒 timedelta、毫秒 timedelta 和零时长。

### 2. Bot 状态诊断异常正文泄露

旧的 `_probe_telegram_connection()` 将异常正文 `str(e)` 返回给管理端。HTTPX/PTB 异常可能包含请求 URL，而 Telegram Bot API URL 的路径中含完整 Bot Token。该返回值会进入状态信息和管理端响应。

修复：只返回异常类型，不再返回异常正文；新增测试使用带伪造 Token 的异常 URL，断言输出不含 URL 和 Token。

## 仍需持续关注的风险（本次不擅自改变业务语义）

1. **轮询启动会丢弃待处理 Updates**：`_post_init` 调用 `delete_webhook(drop_pending_updates=True)`，`run_polling` 也设置 `drop_pending_updates=True`。服务重启/故障恢复时，尚未处理的命令和 callback_query 可能被丢弃。特别是审批按钮，需要确认业务是否允许丢弃；建议明确区分普通旧消息与审批动作，设计持久化审批状态和可恢复通知后再调整。
2. **429 最大等待上限**：当前发送器将 RetryAfter 截断到 120 秒；如果 Telegram 返回更长等待时间，会早于服务端建议时间再次请求。应在后续单独设计长等待预算、锁 TTL、调用方超时与队列化发送，不能只增大 sleep。
3. **发送超时后的结果不确定性**：消息可能已被 Telegram 接收，但客户端在收到响应前超时。直接重试可能产生重复通知；Telegram sendMessage 没有通用幂等键。对审批、财务告警应采用业务通知 outbox、去重键、状态核对或明确的“结果未知”处理。
4. **多进程部署**：Redis 发送互斥和限流是跨进程关键路径；Redis 故障时当前实现会降级到进程内限流，多个 worker 仍可能并发发送并触发 429。需要监控 Redis 降级次数，并确认生产 Redis 与应用使用相同实例/命名空间。
5. **Bot 单实例约束**：Telegram getUpdates 同一 Bot Token 同时只能有一个 polling consumer。文件锁/共享状态应在多主机部署时使用真正共享且具备租约/故障恢复的协调机制；本地文件锁不等价于跨主机锁。
6. **待处理更新策略**：上线前确认是否需要保留 callback_query、审批动作和告警命令。不要把 `drop_pending_updates=True` 当作无风险清理。
7. **消息内容与解析模式**：使用 HTML/Markdown 时，动态字段必须转义；消息长度应按 Telegram 限制处理，避免截断破坏实体标签。应对各类通知模板做真实 API 兼容验证。
8. **生命周期**：发送专用 event loop、Bot HTTPXRequest、轮询 Application 应在进程关闭时有序 shutdown；检查热重启、worker reload、测试进程退出和重复初始化，避免 daemon 线程及连接资源泄漏。

## 验证要求

- 运行 Telegram 专项测试：`pytest tests/test_telegram_message_sender_rate_limit.py tests/test_telegram_message_sender_redaction.py tests/test_telegram_bot_state_error_redaction.py -q`
- 运行完整后端测试与 CI。
- 不在 CI 中使用真实 Telegram Token；网络集成测试必须使用独立测试 Bot 和显式 opt-in。
- 依赖升级时运行 `pip check`，核验实际安装的 PTB/HTTPX 版本，并检查官方 changelog。
- 不记录 Token、完整 API URL、用户隐私字段或异常正文。
