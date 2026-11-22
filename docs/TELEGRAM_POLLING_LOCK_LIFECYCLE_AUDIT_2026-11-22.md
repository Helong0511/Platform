# Telegram 轮询启动锁生命周期审计与整改（2026-11-22）

## 范围

- `app/core/telegram/polling_manager.py:start_polling`
- `app/core/telegram/polling_manager.py:_start_polling_with_lock`
- `tests/test_telegram_polling_lock_lifecycle.py`

## 原问题

进程成功取得 Telegram Bot OS 文件锁后，部分初始化操作位于原有 `try/finally` 保护范围之外。模块导入、Bot 探测、Application 构建、Handler 注册或 bot_state 设置发生异常时，可能跳过锁释放和共享状态清理。

风险包括：
- 当前进程仍存活但 TelegramBot 线程已退出；
- 文件锁仍被该进程持有，后续启动无法获取；
- 本地或跨进程共享状态残留为运行中；
- 管理端重启流程可能误判服务状态。

## 本次整改

- 将取得锁后的运行阶段提取为 `_start_polling_with_lock`。
- 在公开入口 `start_polling` 中，从取得锁后的第一条业务判断开始建立统一 `try/finally`。
- 不论初始化或轮询阶段是否抛出异常，finally 都会尝试释放本次持有的 OS 文件锁。
- 只有确认本次启动已进入运行阶段，才清理本 Bot 的运行状态，避免“锁已取得但发现另一个 Bot 正在运行”的分支误清除其他实例的共享状态。
- 409 冲突清理函数不再自行释放锁，避免和统一 finally 重复释放。
- finally 清理 bot_state 时采用独立异常保护，防止状态模块本身故障阻断锁释放。
- 新增参数化回归测试，分别注入 Application 构建、Handler 注册、bot_state 设置异常，验证锁释放和状态归零。

## 验收标准

- 每个注入异常场景均只释放一次本次取得的锁。
- `_bot_started` 归零。
- `_active_application` 和 `_polling_loop` 清空。
- 共享状态变为 `bot_running=false` 且 `current_pid=null`。
- 清理 bot_state 自身再次抛错时，不得阻断 OS 锁释放。
- CI 必须执行新增测试、Telegram 相关测试及完整 Backend 单元测试。

## 风险与边界

本次只解决锁的生命周期与启动异常清理，不包含自动重启 supervisor、运行期网络健康度监测或审批 Update 恢复策略；这些分别继续由 Issue #132、#133 跟踪。

未触碰生产 Bot Token、Telegram API 或线上服务。
