# Telegram 发送事件循环并发启动审计（2026-11-22）

## 原问题

`ensure_send_loop()` 原先在启动线程后立即释放 `_loop_start_lock`，然后才在锁外等待共享 READY Event。若 worker 尚未被调度，另一个调用方会看到 `_send_loop is None`，清空 READY Event 并再启动一个线程。

此外，worker 在调用 `loop.run_forever()` 前就设置 READY，调用方可能拿到尚未运行的事件循环。

## 整改

- 在同一启动锁保护范围内完成线程唯一性检查、线程创建和 READY 等待。
- 发现启动线程已存在时，等待同一个 READY Event，不再创建第二个线程。
- worker 通过 `loop.call_soon(_SEND_LOOP_READY.set)` 设置 READY，确保回调只有在 `run_forever()` 已进入运行状态后才执行。
- READY 后再次校验 loop 存在且 `is_running()` 为 True。
- worker 退出时清理全局 loop 引用、清除线程事件循环绑定并关闭 loop，下一次调用可重新启动。

## 测试

`tests/test_telegram_send_loop_startup_concurrency.py` 使用 12 个线程通过 Barrier 同时调用 ensure_send_loop，验证：
- 只创建一个事件循环；
- 所有调用方获得同一个 loop；
- loop 返回时已经处于 running 状态；
- 所有协程确实运行在同一个 loop 和线程；
- 测试结束后线程与 loop 被停止并清理。

## 边界

此修复只覆盖首次启动唯一性和 READY 语义。发送 loop 的生产 lifespan shutdown/drain 仍需单独建设，不将 daemon thread 退出视为完整的资源优雅关闭。
