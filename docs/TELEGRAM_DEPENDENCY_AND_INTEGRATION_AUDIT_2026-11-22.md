# Telegram 与调度依赖专项审计（2026-11-22）

## 结论

当前 Telegram 主依赖选择正确，无需更换 SDK。完成本次补丁更新后，依赖基线为：

| 依赖 | 项目版本 | 审计结论 |
|---|---:|---|
| python-telegram-bot | 22.8 | 当前稳定版；支持 Bot API 10.0；Python 3.10+；保留 |
| HTTPX | 0.28.1 | 满足 PTB 22.8 的 `>=0.27,<0.29` 约束；保留 |
| redis-py | 8.1.0 | 当前稳定版；支持 `Redis.from_url`、TLS、ACL、DB path；保留 |
| APScheduler | 3.11.3 | 从 3.11.0 更新到当前 3.11 稳定补丁版；保留 3.x，不升级 4.0 alpha |

## 依赖兼容性

### python-telegram-bot 22.8

- 官方文档将其标记为 production/stable，并支持 Bot API 10.0。
- 唯一必需依赖是 HTTPX，约束为 `httpx >=0.27,<0.29`；项目固定的 0.28.1 在允许范围内。
- Python 3.10+；项目 CI 的 Python 3.11/3.13 均在支持范围内。
- PyPI 发布文件有 Sigstore provenance；官方发布流程提供签名验证。
- License 为 LGPL-3.0-only。仅在服务端运行与向客户分发组合软件的义务不同；若向客户分发程序或修改 PTB 本身，应由合规人员核查 LGPL 通知、替换/重新链接及修改源码义务。

### HTTPX 0.28.1

- PTB 22.8 要求 `>=0.27,<0.29`，0.28.1 完全满足。
- 当前无需升级到不兼容主版本，也不需要额外安装 `http2` 或 `socks` extra。
- 默认 TLS 证书校验保持启用；不得为绕过证书问题设置 `verify=False`。
- License 为 BSD-3-Clause；当前 PyPI 0.28.1 的 sdist/wheel 均没有 provenance attestation，发布文件提供 SHA-256。缺少 provenance 不等于包恶意，但供应链可验证性弱于 PTB/新 APScheduler 版本。

### redis-py 8.1.0

- 与项目的同步 `Redis.from_url` 发送限流器兼容。
- 支持 `redis://`、`rediss://`、URL ACL 用户名/密码、DB path；项目另外支持显式密码覆盖和 legacy host 配置。
- License 为 MIT。当前公开漏洞数据库未发现 8.1.0 的直接已知漏洞；PyPI 此版本未提供 provenance attestation，这是供应链可验证性方面的注意项，不等同于发现恶意包。
- Redis 不可用时跨进程限流无法保证，发送器保留 best-effort 降级；生产必须监控 Redis 连接状态。

### APScheduler 3.11.3

- 项目调度器使用 `AsyncIOScheduler`、`CronTrigger`、`IntervalTrigger`、`AsyncIOExecutor` 和 `MemoryJobStore`。
- 官方 3.11.3 修复了 ZoneInfo 时区下 DST 春季跳时期间子分钟 interval job 停滞，以及导入任务后 scheduler/jobstore 链接缺失的问题。
- 3.11.1/3.11.2 还修复了异步 scheduler shutdown 和 DST 重复时段 CronTrigger 无限循环问题。
- License 为 MIT；3.11.3 发布文件有 PyPI provenance attestation。
- 3.11.3 是 3.x 稳定版本；4.0.0a6 属于 alpha 预发布版，不采用。
- 3.11.3 仍满足 PTB JobQueue 的 APScheduler 3.x 兼容范围；但本项目不使用 PTB JobQueue，已显式 `.job_queue(None)`，避免 APScheduler 被 PTB 自动识别后重复创建调度器。

## 不安装的可选 extras

- 不安装 `python-telegram-bot[all]`，避免引入不需要的额外依赖。
- 不安装 `[rate-limiter]`：项目已有 Redis 全局/单 Chat 限流，不需要再叠加 AIORateLimiter。
- 不安装 `[job-queue]`：项目调度由自身 APScheduler 模块管理，PTB JobQueue 已禁用。
- 不安装 `[http2]`：目前没有 HTTP/2 必要性，HTTP/1.1 更简单稳定。
- 不安装 `[socks]`：当前没有 SOCKS 代理配置；若生产网络必须经代理访问 Telegram，应单独增加 HTTPS/SOCKS 代理配置与凭据脱敏，不要盲装 extras。
- 不安装 Pyrogram、Telethon、pyTelegramBotAPI 或名为 `telegram` 的冲突包；当前只使用官方 `python-telegram-bot` 的 `telegram.*` 命名空间。

## 本轮已完成的 Telegram 集成修复

- 普通 Bot API request 与 getUpdates 独立 request 超时分别配置；长轮询 10 秒，getUpdates read timeout 65 秒。
- 显式关闭未使用的 PTB JobQueue。
- 私聊、群组和全局限流按 Telegram 官方限制保守配置。
- Redis URL 统一支持 TLS/ACL/DB path。
- 长 RetryAfter 不再截短后提前重试；超出 120 秒单次等待预算时 fail closed，Redis 共享 backoff 保留至多 7 天。
- Token、代理凭据和管理员标识不再出现在诊断报告或初始化日志中。
- 轮询停止改为事件循环线程安全调用 `stop_running()`；旧线程未退出时拒绝启动第二个 polling consumer。
- 文件锁使用 Linux `flock` / Windows `msvcrt.locking`，不再依赖时间戳或 unlink 锁文件。

## 仍需业务/运维决策的风险

1. `drop_pending_updates=True` 会丢弃 Bot 停机期间积压的消息和 callback query；当前保留原策略，是否改为保留更新需业务确认。
2. OS 文件锁只协调同一主机。若同一个 Bot Token 部署在多台主机，必须使用 Redis 分布式锁（owner token、租约续期、比较删除/fencing），不能把本地文件锁当成跨主机锁。
3. Telegram 网络在启动阶段持续不可用并耗尽 3 次 bootstrap retry 时，polling thread 可能退出；需要线程级健康监控/恢复，单靠 systemd 监控 Web 进程不够。
4. 当前没有 `TELEGRAM_PROXY` 配置。生产主机若不能直连 `api.telegram.org`，需增加代理配置并对 URL userinfo 做日志脱敏。
5. Telegram sendMessage 在服务端已接收、但客户端响应超时的情况下无法提供严格 exactly-once；重试可能重复通知，停止重试又可能丢消息，需要接受 best-effort 语义或设计 outbox/人工核对。
6. 消息截断函数对 HTML/Markdown 格式化消息直接按字符串切片，超长内容可能切断标签/转义序列；目前常规通知较短，若开放格式化长消息入口，应增加 parse-mode-aware truncation 或超长拒绝策略。
7. 发送日志仍需完成 Chat ID 脱敏；不得把 Telegram 用户/群组 ID 当作普通无敏感性日志字段。

## 验收要求

- 完整 backend/frontend CI 全部成功后才合并。
- 必须通过现有 scheduler 注册、任务同步、时区和 Telegram polling/限流回归测试。
- 生产发布前用专用测试 Bot 验证 getUpdates、群组发送、429 RetryAfter、409 冲突恢复和 Redis 中断降级；不能在生产 Bot 上进行压测。


## 官方核验来源

- PTB 22.8 总览、Bot API 10.0、Python 支持范围与依赖约束：https://docs.python-telegram-bot.org/en/v22.8/
- PTB ApplicationBuilder 的 request/getUpdates request 与 JobQueue 配置：https://docs.python-telegram-bot.org/en/v22.8/telegram.ext.applicationbuilder.html
- PTB 官方发布与版本记录：https://github.com/python-telegram-bot/python-telegram-bot/releases
- APScheduler 3.x 官方版本历史：https://apscheduler.readthedocs.io/en/3.x/versionhistory.html
- APScheduler 3.11.3 PyPI 发布及 provenance：https://pypi.org/project/APScheduler/3.11.3/
- HTTPX 0.28.1 PyPI 元数据、依赖、许可证、发布文件与 SHA-256：https://pypi.org/project/httpx/0.28.1/
- redis-py 8.1.0 PyPI 发布元数据：https://pypi.org/project/redis/8.1.0/
- Telegram Bot API 官方文档：https://core.telegram.org/bots/api
- Telegram Bot FAQ 与速率限制说明：https://core.telegram.org/bots/faq
