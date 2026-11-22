# Telegram polling Supervisor 与健康心跳审计（2026-11-22）

## 范围

- `app/core/telegram/polling_manager.py`
- `app/core/telegram/polling_exception_handler.py`
- `app/main.py`：`/api/v1/health/telegram`
- 关联 Issue：#132
- 修复 PR：[ #151 ](https://github.com/Helong0511/Platform/pull/151)

## PTB 22.8 行为边界

官方 PTB 22.8 文档明确：`Application.run_polling(bootstrap_retries=...)` 的重试只覆盖初始化和 Updater 启动轮询的 bootstrap 阶段，不是整个运行期的应用级 supervisor。Updater 文档还明确 `error_callback` 用于接收轮询期间 `get_updates()` 的 TelegramError。

官方文档：
- Application.run_polling：https://docs.python-telegram-bot.org/en/v22.8/telegram.ext.application.html
- Updater.start_polling：https://docs.python-telegram-bot.org/en/v22.8/telegram.ext.updater.html

项目仍保留 PTB 自身对临时运行期网络错误的处理，不把所有网络错误都视为线程退出。

## 新增监督策略

- 唯一 `TelegramBot` supervisor 线程负责 polling 生命周期。
- 临时网络错误、意外正常返回、未预期异常：指数退避 + jitter，最多 5 次应用层重启；退避上限 60 秒，超过次数进入熔断并告警。
- HTTP 401、InvalidToken/Unauthorized：永久认证失败，停止自动重试并告警。
- Telegram 409 getUpdates 冲突：停止当前轮询并告警，不自动重启，避免和另一个 poller 竞争。
- 禁用配置、缺少 Token、依赖不可用：停止重试并告警。
- 未取得 OS 文件锁：认为其他进程拥有轮询权或本进程无法取得锁，不在本进程形成竞争重启风暴。
- 每次重新启动仍必须重新取得既有 OS 文件锁；旧线程退出前不提前释放锁。
- `stop_polling_application` 设置 supervisor stop event；退避等待可被立即打断。restart 必须 join 旧线程后才创建新线程。

## 健康监测

- 使用自定义 ExtBot 子类覆盖 `get_updates`，成功返回时记录时间。PTB Bot 实例使用 `__slots__`，不能依赖实例级 monkeypatch。
- 增加 group=-1 的 TypeHandler，记录最后一次收到 Update 的时间，不抢占业务 Handler。
- `get_polling_health_status()` 以 OS 文件锁句柄确认本进程是否为 owner，同时核对 supervisor 线程存活和最近成功 getUpdates 心跳；共享状态用于识别其它存活 owner。
- 线程存活但 180 秒没有成功 getUpdates 时，由 watchdog 发出一次去重告警；恢复后重新允许后续告警。
- 新增 `GET /api/v1/health/telegram`：
  - `disabled`：Telegram 功能禁用；
  - `not_owner`：当前进程不是 polling owner，且共享状态显示另一个 owner 进程仍存活；
  - `ok`：线程存活且 getUpdates 心跳未过期；
  - `degraded`：未启动、线程已退出或心跳超时。
- API 基础存活探针 `/api/v1/health` 保持原样，不把 Telegram 降级误判为整个 API 进程死亡。

## 测试覆盖

- 临时 bootstrap 失败后有限重试。
- 409 冲突不重启。
- 401/InvalidToken 永久认证错误熔断。
- 超过最大重试次数进入 circuit-open。
- 成功 getUpdates 心跳与 Update 收到时间。
- 线程仍存活但 getUpdates 心跳过期时，健康状态为 degraded。
- 原有 OS 锁生命周期、restart fail-closed 测试继续执行。

## 明确未改变

- 没有修改 `drop_pending_updates=True`。停机期间 Telegram callback 更新的恢复语义仍由 Issue #133 处理，需业务确认。
- 没有绕过 OS 文件锁，也没有让未持锁 worker 自动竞争。
- supervisor 仅管理单进程 polling thread；进程崩溃后的进程级重启仍由 systemd/Gunicorn/进程管理器负责。
