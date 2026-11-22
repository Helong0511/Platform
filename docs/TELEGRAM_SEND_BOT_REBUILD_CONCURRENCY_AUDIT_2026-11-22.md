# Telegram 发送 Bot 并发重建审计（2026-11-22）

## 问题

`app/core/telegram/ptb_runtime.py:get_send_bot` 原实现只在读取和发布缓存引用时持有 `_send_bot_lock`，旧 Bot 的 shutdown 与新 Bot 创建发生在锁外。

不同 Token 的并发调用可能同时读取同一个旧 Bot，重复关闭旧实例并各自创建新实例。后发布的调用覆盖前一个实例，造成前一个 HTTPX client 无法再从缓存访问、未被关闭，或在其它调用仍使用时被过早关闭。

## 整改

- 新增独立的 `_send_bot_rebuild_lock`，串行化旧实例关闭、新实例创建和缓存发布的完整生命周期。
- 保留 `_send_bot_lock` 作为短时缓存引用锁，不在持有缓存锁时等待事件循环 Future。
- 重建开始时先清除旧缓存引用，避免旧实例已关闭但新实例构建失败时继续把旧 Bot 当作可用缓存返回。
- 新实例成功创建后才发布到缓存。
- 旧实例关闭失败只记录异常类型，不记录异常正文或 Token。
- 同 Token 并发调用复用同一实例；不同 Token 并发调用按顺序完成实例切换。

## 回归测试

`tests/test_telegram_send_bot_rebuild_concurrency.py` 覆盖：
- 相同 Token 并发请求只创建一个实例；
- 不同 Token 并发切换时旧实例先关闭，新实例后发布；
- 新实例构建失败后不残留已关闭的旧实例缓存，后续调用仍可恢复。

## 边界

此修复只处理进程内 Bot 实例缓存并发，不替代跨主机 polling OS 锁，也不实现发送队列的持久化和优雅停机 drain。
