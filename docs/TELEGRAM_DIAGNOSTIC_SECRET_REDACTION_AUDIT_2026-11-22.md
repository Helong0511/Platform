# Telegram 诊断输出敏感信息审计（2026-11-22）

## 问题

`TelegramBotDiagnostics` 是运维诊断工具，旧实现存在多处原始敏感值输出：

- 配置状态输出 Token 前缀、Bot ID、管理员 Chat ID。
- 系统环境诊断将所有 `TELEGRAM_*` 环境变量的原始值写入报告，可能包含 Bot Token、代理 URL 用户名/密码、管理员 ID、锁路径等。
- 网络探测、重新初始化和文件权限异常把 `str(exception)` 返回诊断结果，HTTPX/PTB 异常可能包含含 Token 的 Telegram Bot API URL。
- Bot 初始化日志输出 Token 前四位，虽不等于完整 Token，但没有必要暴露任何片段。

## 修复

- 配置诊断只保留 Token/管理员/Chat ID 是否配置，不输出值、前缀或 Bot ID。
- 环境变量诊断只显示 `TELEGRAM_ENABLE` 开关原值；其他 Telegram 环境变量统一显示 `[已设置]` / `[未设置]`。
- 网络探测、重新初始化和文件权限错误只返回异常类型，不透传异常正文。
- Bot 初始化日志只记录 Token 已配置/未配置，不记录任何 Token 片段。

## 回归测试

- 伪造 Bot Token、管理员 Chat ID、代理 URL 凭据，断言诊断结构和环境报告均不包含原值。
- 伪造包含 Telegram Bot API URL 的异常，断言诊断结果只含异常类型。

## 运维提示

诊断报告仍可能包含 Python 路径、运行目录和 Bot 用户名等环境信息，分享报告前仍应按内部运维数据处理；本次重点阻断凭据和聊天标识泄露。
