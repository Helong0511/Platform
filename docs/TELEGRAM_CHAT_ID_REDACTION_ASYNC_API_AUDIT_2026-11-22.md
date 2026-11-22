# Telegram Chat ID 脱敏与管理 API 异步发送审计（2026-11-22）

## 审计结论

- Telegram SDK 依赖组合保持不变：`python-telegram-bot==22.8` 与 `httpx==0.28.1` 满足 PTB 22.8 的官方依赖约束 `httpx>=0.27,<0.29`。
- 本轮没有发现需要改用 pyTelegramBotAPI、Telethon 或 Pyrogram 的技术理由；项目使用 PTB 的 `telegram.*` 命名空间，依赖清单只声明 `python-telegram-bot`。
- 发现并修复了 Chat ID 在发送日志、命令日志、统计回调日志和管理 API 审计详情中的明文暴露。
- 发现并修复了两个 async 管理 API 端点直接执行同步 Telegram 发送的问题。
- 修复管理路由静态导入 `bot_initialized` 布尔值导致无法读取初始化后实时状态的问题。

## 修复内容

### 1. Chat ID 日志与审计脱敏

新增 `mask_telegram_chat_id`：
- 普通用户 ID 仅保留前 2 位和后 4 位；
- 群组 ID 保留 `-100` 类型前缀及后 4 位；
- 支持逗号分隔的多个 ID；
- 非法值统一显示为 `[已隐藏]`，空值显示为 `[未提供]`。

应用位置：
- 普通消息发送器；
- 带按钮消息发送器；
- `/start`、`/help`、`/id` 命令日志；
- 统计菜单回调日志；
- `/start`、`/help`、`/id` 的消息发送统一经过共享 Redis 限流发送器；
- `POST /telegram/send` 的审计详情。

注意：`/id` 命令仍会把 Chat ID 返回给发起命令的 Telegram 聊天，这是该命令的既定功能；只是不再将完整 ID 写入服务端日志。审计记录保存脱敏值，不保存原始值。

### 2. Redis 限流键不再包含原始 Chat ID

原先 per-chat backoff/gate Redis key 直接拼接 Chat ID。虽然不是日志，但 Redis 运维查看、慢查询诊断、键扫描和备份元数据均可能暴露完整聊天标识。

现使用应用 `SECRET_KEY` 对 Chat ID 计算 HMAC-SHA256 后再生成 Redis key；未配置密钥的测试环境退回 SHA-256，仍不写入原始 ID。限流语义与 TTL 不变；已有旧格式键会自然按 TTL 过期，不再继续刷新。

### 3. 发送 Bot 使用统一 HTTPX 超时配置

原先 `get_send_bot` 按 Token 缓存单例，但各调用点传入不同 read timeout。应用启动时 `initialize_bot` 先以 5 秒创建发送 Bot，正式发送路径随后请求 30 秒；由于缓存只按 Token 命中，后续 30 秒参数被忽略，实际发送仍可能只有 5 秒超时。

现将发送 Bot 的 HTTPX 超时集中为 connect=3 秒、read/write=30 秒，移除调用点的分散超时参数。诊断请求仍可通过 `run_on_send_loop` 的外层等待上限控制自身响应时间，不再污染进程级发送 Bot 的传输配置。`run_on_send_loop` 在外层等待超时时现在会取消底层 Future，避免调用方超时后底层发送协程继续执行；Bot 初始化等待预算为 40 秒，略高于 3 秒连接 + 30 秒读取超时。

### 4. 管理路由读取实时 Bot 状态

路由模块此前通过 `from ...bot_state import bot_initialized` 导入不可变布尔值。应用生命周期在路由导入后执行初始化，`set_bot_state` 重新赋值不会更新路由模块已绑定的旧布尔值，可能造成 Bot 已初始化但管理 API 仍返回 503。

现改为引用 `telegram_bot_state.bot_initialized` 和 `telegram_bot_state.TELEBOT_AVAILABLE`，在每次请求时读取模块当前值。 同时在 `app.core.telegram.__init__` 对历史兼容导出的布尔快照增加明确警告：新代码必须使用 `is_bot_available()` 或 `bot_state` 模块实时读取，不能继续 `from-import` 后缓存。

### 5. 所有 Telegram 管理路由的阻塞等待移出 FastAPI 事件循环

除 `/send` 与 `/test` 外，`/status` 同步调用状态探测，`/diagnostic` 和 `/reset_webhook` 也直接调用同步 `run_on_send_loop`。这些同步等待都可能阻塞 ASGI 事件循环。

新增 `run_on_send_loop_async`，通过工作线程等待发送 loop；状态探测也通过 `asyncio.to_thread` 执行。管理路由中的 Telegram API 网络等待均改为异步等待，不在请求事件循环中直接执行同步等待。异步 `send_admin_notification` 也改为 await 异步发送器；应用关闭阶段的服务停止通知移至工作线程，避免 lifespan 事件循环被同步网络发送阻塞。BFT fire-and-forget 通知增加 task done callback，发送返回 False 或抛出异常时记录安全的 error_type 日志。

`POST /telegram/send` 与 `POST /telegram/test` 是异步路由，但此前直接调用同步发送函数。同步发送会通过线程安全事件循环等待网络请求，并可能执行多轮退避与重试；直接在 async 路由中调用会占住当前 FastAPI 事件循环。

现改为 await 已有的 `send_telegram_message_async` 包装器。该包装器通过 `asyncio.to_thread` 将同步兼容发送路径放入工作线程，不改变既有发送限流、重试和失败返回语义。

## 依赖与兼容性核验

| 组件 | 项目固定版本 | 核验结果 |
|---|---:|---|
| python-telegram-bot | 22.8 | 官方当前稳定发布；Python 3.10+；保留 |
| HTTPX | 0.28.1 | 满足 PTB 22.8 的 `>=0.27,<0.29`；保留 |
| redis-py | 8.1.0 | 发送器同步 Redis 限流使用 `Redis.from_url`；保留 |
| APScheduler | 3.11.3 | 项目调度器依赖；PTB JobQueue 显式禁用，不安装 PTB job-queue extra |

不启用 PTB 的 `all`、`ext`、`rate-limiter`、`job-queue`、`http2`、`socks` extras：当前项目没有相应功能需求，且已有 Redis 限流和独立 APScheduler。不要把 APScheduler 4.0 alpha 当作生产升级目标。

### Python 与 Redis 服务端版本边界

- PTB 22.8 官方支持 Python 3.10+；redis-py 8.1.0 是官方仍支持 Python 3.10 的版本线，因此当前依赖组合适合 Python 3.10、3.11、3.13。
- redis-py 官方支持矩阵对 6.0+ 客户端列出的 Redis 服务端起点为 7.2；本仓库 Full Audit CI 固定使用 Redis 7.4.11。另需核验 Redis 服务端 CVE-2026-81934 补丁：7.4 分支至少 7.4.11，7.2 分支至少 7.2.16。生产 Redis 必须同时满足客户端兼容矩阵与服务端安全补丁要求。
- 新增 Telegram 依赖矩阵 CI，在 Python 3.10/3.11/3.13 安装固定的 PTB/HTTPX/redis-py/APScheduler 版本，运行 `pip check` 并导入实际使用的 API。

### PyPI 供应链来源核验

- python-telegram-bot 22.8 的 PyPI wheel/sdist 有 Sigstore provenance，发布仓库与 GitHub Actions workflow 可验证。
- APScheduler 3.11.3 的 PyPI wheel/sdist 也有 provenance。
- HTTPX 0.28.1 与 redis-py 8.1.0 当前 PyPI 发布文件未提供 provenance；PyPI 页面提供 SHA-256 文件校验和，但当前 requirements.txt 仅锁版本、没有全量传递依赖 hashes。
- 不因缺少 provenance 就贸然替换成熟依赖；上线前应建立完整 lockfile（含全部传递依赖与 hashes），并在 CI 使用 `pip install --require-hashes` 验证。当前 CI 的 `pip check` 只验证元数据依赖冲突，不等于供应链完整性验证。
- 如果项目未来统一提升到 Python 3.11+，可评估 redis-py 8.2.x 稳定版本；不要在仍需 Python 3.10 的环境中直接升级到只支持 Python 3.11+ 的 redis-py 版本。

## 仍需运维/业务确认的事项

1. `drop_pending_updates=True` 会丢弃 Bot 停机期间尚未处理的 Updates，可能影响审批 callback。必须由业务确认是否接受；本次不擅自改变。
2. OS 文件锁只协调同一主机。多主机部署同一 Bot Token 时必须增加 Redis 等分布式租约/ fencing 机制，不能依赖本地锁。
3. 启动阶段网络不可用并耗尽 bootstrap retries 后，轮询线程可能退出；生产需要线程级健康检查、告警与恢复策略。
4. Telegram 发送请求超时存在“服务端已接收但客户端未收到响应”的不确定窗口；Bot API sendMessage 没有通用幂等键，通知语义仍是 best effort，不能宣称 exactly-once。
5. 当前 requirements.txt 固定直接依赖，但没有完整锁定所有传递依赖的 lockfile/hash。两条 Python CI workflow 已加入 `python -m pip check`；Full Audit 还使用 `pip-audit==2.10.1` 扫描 requirements.txt 及其传递依赖的已知漏洞。`pip check` 不等于漏洞扫描，`pip-audit` 也不等于哈希/来源验证；生产构建仍应记录解析结果并建立可复现的 hash lock。
6. `/id` 会在聊天消息中显示 Chat ID 和 User ID，这是命令本身的用途；应确保 Bot 仅在预期私聊/群组中使用，避免把命令消息转发到公开频道。
7. BFT 通知仍使用 request-scoped fire-and-forget task，没有持久化队列或 shutdown drain；高峰期可能积累任务，worker 重启时也可能取消未完成通知。通知不得作为转化入库/回调成功的前置条件；后续如需可靠送达，应建设有界队列、限流、重试与可观测的通知 outbox。
8. `send_telegram_message_async` 使用默认线程池执行同步兼容发送器；高并发突发时多个通知可能占用线程等待 Redis 发送锁。若通知量明显增长，应改为有界的单消费者/多消费者发送队列，而不是继续增加线程数。
9. Telegram Bot API 的 `sendMessage` 没有通用幂等键；网络超时可能发生在 Telegram 已接收消息但客户端未收到响应之后，自动重试可能重复通知。当前只能 best effort，不能承诺 exactly-once。
10. 发送专用事件循环和 Bot HTTPX client 当前没有独立的 lifespan shutdown/close 流程；进程退出会回收资源，但优雅停机时应补齐 task drain、Bot.shutdown、loop.stop/join。

## 验收

- 新增测试覆盖 Chat ID 掩码、发送日志不泄露原始群组 ID、管理 API 使用异步发送、审计记录只保存掩码 ID。
- PR CI 必须全部成功后才合并；合并后还需核验 main SHA 的所有 required checks。
- 不使用真实 Telegram Bot Token 做 CI 网络测试。
- 不在生产 Bot 上执行压测。
