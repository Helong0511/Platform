# Postback 与 Telegram 安全整改记录（2026-11-20）

> 本文记录 2026-11-20 对 `main` 的代码核查、已合并修复、CI 验证和仍未解除的上线阻断项。它是当前状态记录，不代表生产环境凭据已轮换或系统已完成上线验收。

## 1. 当前代码基线

- 仓库：`Helong0511/Platform`
- 当前主线：`main`
- 本文编写时 main HEAD：`95f66409a08c760e06049504575d4550d3951deb`
- 当前主线以 `main` 为唯一后续开发与部署基线；不要把无共同祖先的旧 `master` 直接合并回来。

## 2. 本轮已合并整改

| PR | 合并提交 | 整改内容 |
|---|---|---|
| [#55](https://github.com/Helong0511/Platform/pull/55) | `5731c17ac722aaa95e30cd7c357853b8c7c70241` | 短链接重定向日志不再输出完整 URL、查询参数值、Click ID；公开错误响应不再回显底层异常。 |
| [#56](https://github.com/Helong0511/Platform/pull/56) | `02c94b9d9e05c2d55ac271588c7c90962852937c` | Postback 历史归因筛选回退 Click；Telegram 审批保留点击关联与归因快照；增加重复转化检查和操作者白名单。 |
| [#57](https://github.com/Helong0511/Platform/pull/57) | `d2474da74cdb3d6f32438490019cc988f93770a4` | 移除 Telegram Bot 全量普通消息调试处理器，避免把消息正文写入 INFO 日志。 |
| [#58](https://github.com/Helong0511/Platform/pull/58) | `e96a51d66f68b4529dcdfec355f4f2c60d09c154` | Postback 服务异常脱敏、IP/Click ID 日志收敛、BFT Telegram 通知字段白名单化。 |
| [#60](https://github.com/Helong0511/Platform/pull/60) | `7eb9671c659f4ead13d8d842e7caea17a72fc2de` | Telegram 拒绝审批通知不再暴露来源 IP。 |
| [#61](https://github.com/Helong0511/Platform/pull/61) | `8bb9a0087317ec0b60e1bf9f1f594d2b69a69220` | Web/Telegram 待审批路径增加 `SELECT ... FOR UPDATE` 行锁；尚需真实 MySQL 并发竞争测试。 |
| [#62](https://github.com/Helong0511/Platform/pull/62) | `6dd1b0db03150bfa6dd96d177818a65546a1de79` | 待审批 Telegram 模板遮蔽 IPv4/IPv6 来源地址并转义 HTML 字段。 |
| [#63](https://github.com/Helong0511/Platform/pull/63) | `9b96451f4057bf3dcb8f2e48251bdad17e24214b` | Telegram 运行时告警不再发送异常正文、上下文、堆栈和绝对路径。 |
| [#64](https://github.com/Helong0511/Platform/pull/64) | `26fd39c73ec46355a20fd37205b278a6f0531d1a` | Postback 转发成功/失败通知及通知历史不再保存目标 URL、响应正文、原始异常和点击参数。 |
| [#65](https://github.com/Helong0511/Platform/pull/65) | `f3073a996d7df0694a72d441087218aa879e1a43` | 修复 Telegram 运行时告警换行符显示错误，并清理重复过滤项/无用 import。 |
| [#66](https://github.com/Helong0511/Platform/pull/66) | `109c57d28d1a0cbcbe15b384df1e3ebf56fe15a7` | Telegram 轮询异常路径不再记录异常正文或 traceback。 |
| [#67](https://github.com/Helong0511/Platform/pull/67) | `6150548cc0c373842c1c5c523d602e2ea6ec8abb` | 兼容轮询异常处理器、Bot 初始化和运行时告警发送失败日志脱敏。 |
| [#68](https://github.com/Helong0511/Platform/pull/68) | `d0e8eb0ef500a4138196218245f425b324ebdfcd` | Telegram 普通/按钮消息发送日志与失败返回值不再泄露 API 异常正文、Token、URL 或完整 Chat ID。 |
| [#69](https://github.com/Helong0511/Platform/pull/69) | `dbe9d81b563d38a7d325417aca43a2d0eb1fbebc` | 系统告警消息和历史记录只保留固定安全描述、异常类型及受限代码定位；通知服务异常日志脱敏。 |
| [#70](https://github.com/Helong0511/Platform/pull/70) | `c88ab40325e8ed576f5afa6299d65e874d06e57b` | Telegram 命令、菜单回调、统计回调及统计查询异常日志脱敏。 |
| [#71](https://github.com/Helong0511/Platform/pull/71) | `95f66409a08c760e06049504575d4550d3951deb` | Telegram 命令回复、文件锁和跨进程共享状态异常日志脱敏。 |
| [#72](https://github.com/Helong0511/Platform/pull/72) | `0bd5d009008cd71b2a11b75206216474b89a0fae` | 旧版 Telegram 通知模板不再发送异常正文/上下文，动态 HTML 字段统一转义。 |

### 2.1 短链接日志与错误响应

- 只记录短码和必要业务 ID，不记录原始请求 URL、最终跳转 URL、查询参数值或 Click ID。
- 不记录底层异常文本和 traceback。
- 对公开访问者返回通用错误信息，避免泄露数据库连接串、SQL 或内部服务信息。
- 重定向 URL 构建、点击归因、点击持久化和缓存流程未在该整改中改变。

### 2.2 Postback 历史归因和 Telegram 审批

- 新转化优先按 `postback_conversions` 快照字段筛选。
- 快照字段为空的历史记录，通过 `click_id` 使用关联 `EXISTS` 查询回退到 `clicks` 表；避免 JOIN 造成分页和 COUNT 重复。
- Telegram 批准待确认转化时，保留 `click_id`、`click_time`，并从签名点击令牌或 Click 行补齐 Offer、Publisher、Advertiser 快照。
- Telegram 审批路径增加正式转化重复检查，已存在正式记录时不重复插入。
- Telegram 回调校验实际操作者：
  - 私聊兼容：未设置新白名单时，仅当操作者 User ID 与 `TELEGRAM_ADMIN` 中的私聊 Chat ID 一致才允许审批。
  - 群聊审批：必须设置 `TELEGRAM_ADMIN_USER_IDS`，值为逗号分隔的正整数 Telegram 用户 ID。
  - 群聊未配置白名单时拒绝审批。

部署时如审批按钮发送到群聊，必须在密钥/环境配置中设置 `TELEGRAM_ADMIN_USER_IDS`，不要把群 Chat ID 当作操作者身份。

### 2.3 Telegram 消息隐私

- 移除仅供调试的全量 `MessageHandler`，保留 `/start`、`/help`、`/id`、`/stats` 和现有回调处理器。
- 普通消息正文不再被通用调试处理器写入 INFO 日志。
- Postback 审批回调现在校验用户身份；未授权用户不能批准或拒绝待确认转化。

### 2.4 Postback 异常、IP 与 BFT 通知

- 转化、待确认、诊断、重复检测、统计、BFT、IP 白名单和 Telegram 审批路径不再向客户端返回原始后端异常。
- 日志保留异常类型，不保留数据库异常原文和 traceback。
- 自动批准与 IP 白名单运维日志不再记录完整来源 IP。
- BFT Telegram 通知只展示白名单业务字段；IP、Click ID、Token、邮箱、电话、转化 ID 等敏感值脱敏，未知字段和结构化原始值省略。
- BFT 实际 Postback 入库数据未因通知脱敏而改变。
