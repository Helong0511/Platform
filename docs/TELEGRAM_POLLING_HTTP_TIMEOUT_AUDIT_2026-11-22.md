# Telegram 长轮询 HTTP 超时专项审计（2026-11-22）

## 问题

`polling_manager.start_polling()` 原来只通过 `Application.builder().request(HTTPXRequest(...))` 设置普通 Bot API 请求的超时，但 PTB 的 `getUpdates` 使用独立的 `get_updates_request`。未显式设置时，PTB 22.8 的 `ApplicationBuilder.get_updates_read_timeout` 默认只有 5 秒，而 `run_polling` 的长轮询 timeout 默认 10 秒。

因此长轮询请求的 HTTP read timeout 小于服务端 long-poll timeout，网络正常时也可能先由 HTTP 客户端超时，导致无意义的轮询失败/重试、日志噪声和更新处理延迟。

## 修复

- 抽出 `_build_polling_application`，集中构建 Application。
- 普通 Bot API 请求继续使用 connect=3s、read/write=60s、pool=5s。
- 对独立 getUpdates request 显式设置 connect=3s、read=65s、write=60s、pool=5s。
- `run_polling` 显式设置长轮询 timeout=10s，read timeout 至少比它多 55 秒。
- 设置有限的 `bootstrap_retries=3`，降低启动瞬间 Telegram 网络抖动导致一次性启动失败的概率；不是无限重试，持续不可用仍需进程管理器监控和重启。

## 依赖与官方 API 核验

PTB 22.8 的 ApplicationBuilder 明确区分 `request()` 与 `get_updates_request()`，并提供独立的 `get_updates_read_timeout()`、`get_updates_connect_timeout()`、`get_updates_write_timeout()`、`get_updates_pool_timeout()`。本项目保留默认 HTTP/1.1，不安装不需要的 HTTP/2 extra。

官方参考：
- https://docs.python-telegram-bot.org/en/v22.8/telegram.ext.applicationbuilder.html
- https://docs.python-telegram-bot.org/en/v22.8/telegram.ext.application.html

## 回归测试

静态 AST 回归测试确认 getUpdates read timeout 为 65 秒、run_polling timeout 为 10 秒、bootstrap retries 为 3，并确保超时关系不会被后续改动意外破坏。

## 仍需运维确认

- Telegram 网络持续不可达超过 bootstrap 重试预算时，轮询线程仍可能退出；生产必须有 systemd/supervisor 等进程级存活监控和告警。
- 本次不更改 `drop_pending_updates=True` 行为；该配置会清除服务端待处理 Updates，审批 callback 是否允许丢弃需单独确认。
