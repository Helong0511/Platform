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
| [#64](https://github.com/Helong0511/Platform/pull/64) | `26fd39c73ec46355a20fd37205b278a6f0531d1a` | Postback 转发通知及通知历史不再保存目标 URL、响应正文、原始异常和点击参数。 |
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

### 2.5 Telegram 告警与发送链路隐私

- Telegram 运行时告警只保留服务标识、异常类型和受限代码定位；不向群聊发送异常正文、上下文、traceback、主机名、PID 或绝对路径。
- Postback 转发通知不展示目标 URL、原始异常、点击参数和对端响应正文；通知历史同步避免保存这些敏感字段。
- 普通消息/按钮发送失败只记录异常类型；发送函数不再把 Chat ID 与原始 API 异常正文拼接返回。
- Bot 初始化、轮询、兼容异常处理、告警发送失败、命令/回调/统计查询、文件锁和共享状态异常日志均已逐步改为记录异常类型。
- 旧版系统告警模板不再把原始 error_message/context 放入 Telegram；转化通知动态字段进行 HTML 转义。
- 异常分类仍可在进程内读取异常文本；该文本不得再被写入日志、Telegram 消息或持久化通知正文。

### 2.6 行锁并发保护的验证边界

- PR #61 已为 Web 手动批准/拒绝、Telegram 审批及按 IP 自动批准路径加入行锁查询。
- 当前回归测试证明 SQL 编译结果包含 `FOR UPDATE` 与 pending 状态条件。
- 该测试不等于真实 MySQL/InnoDB 并发验证；仍需覆盖人工批准与拒绝竞争、自动批准与人工审批竞争、锁等待/超时、死锁回滚和事务边界。


## 3. CI 验证记录

截至本文所记录的 main HEAD，PR #60–#72 均已完成合并；每个 PR 的最终 head SHA 均分别通过 Full Audit CI 与 Emergency Security CI。不得使用早期失败/取消尝试或旧 SHA 的检查结果替代最终提交验证。

- Full Audit 覆盖后端单元测试、Python 3.13 password hash compatibility、前端依赖安装/Lint/Build，以及 Playwright Browser E2E（mock APIs）。
- Emergency Security 覆盖后端安全配置测试、前端 Lint/Build。
- PR #58 的 Full Audit 记录为后端 899 passed、1 skipped；该数字仅对应当时 PR #58，不应误写为当前 main 的测试总数。
- PR #68 初次新增测试曾失败，修正测试前置条件后，最终 SHA `ef2f7f10822ab7299507c6b37c7c551882a5111b` 的 Full Audit 与 Emergency Security 均通过。
- PR #70 初次新增测试曾因测试夹具未触发群聊分支而失败；修正后，最终 SHA `4e51c715b6b058976670ae056d506b86eb679a8f` 的 Full Audit 与 Emergency Security 均通过。
- PR #71 初次 Full Audit 暴露既有测试仍要求日志包含 Chat ID；按隐私要求更新断言后，最终 SHA `5b75a4580c1d0dd61acb2e297704819824814292` 的 Full Audit 与 Emergency Security 均通过。
- PR #72 最终 SHA `fdf31f5657618d1e97c56924696e85877eea4edc` 的 Full Audit 与 Emergency Security 均通过。

CI 通过代表对应代码提交的自动化检查通过，不等同于生产密钥轮换、生产迁移演练或真实 Telegram/MySQL 环境验收。

## 4. 仍然存在的上线阻断项

### P0：公开仓库仍跟踪敏感凭据文件

截至本次核验，仓库仍为 Public，当前 `main` 仍跟踪：

- `keys/private_key.pem`
- `nginx/btfrx.online/client.btfrx.online.key`
- `secrets/gam-23347342743.json`
- `secrets/gam-23348711678.json`

**本轮没有轮换、吊销或验证任何生产凭据。** 代码增加 fail-closed 防护不等于凭据已失效。

必须按顺序完成：

1. 由凭据所有者在对应官方控制台轮换/吊销 JWT RSA 私钥、公网 TLS 私钥及 GAM Service Account 凭据。
2. 将生产运行时切换到仓库外的密钥管理服务或受限文件路径，并验证服务启动、签名、TLS 和 GAM API 调用。
3. 轮换确认后，才从 Git index/current tree 移除敏感文件。
4. 规划 Git 历史重写，清理所有分支、标签和可达历史对象，并对全部 refs/objects 重新扫描。
5. 说明历史副本无法通过仓库历史重写收回；不能把历史清理当作凭据轮换的替代品。

在上述步骤完成前，不得宣布生产可安全上线。

### P1：main 分支保护未启用

本次核验 `main.protected=false`。需由仓库管理员在 GitHub Settings 配置：

- 通过 PR 合并；
- Full Audit / Emergency Security 必需检查；
- 禁止 force push；
- 禁止删除 main；
- 限制直接 push。

当前集成没有可用的分支保护写入权限，因此不能在本次整改中代为启用。

### P1：Telegram 审批的持久化审计轨迹

当前 Telegram 审批回调校验操作者，并在应用日志记录回调用户 ID；但 Telegram 线程处理路径尚未写入独立、持久化的数据库审计事件。若业务合规要求追溯“谁在何时批准/拒绝了哪条记录”，应补充数据库审计记录，并与审批状态更新保持同一事务。

### P1：Migration Runner 生产等价演练

仍需完成生产等价 MySQL DDL 演练、备份恢复、失败/中断恢复流程演练及最小权限迁移账号实操。MySQL DDL 存在隐式提交，不能把普通事务回滚测试当作生产恢复验证。

## 5. 旧 master 分支处理原则

- `master` 与 `main` 无共同祖先，禁止直接合并。
- 旧 API 聚合、Telegram Bot、短链接路由和响应封装已由主线新架构替代；不要把旧文件整体搬回。
- 旧转化日志筛选的历史归因缺口已由 PR #56 修复。
- 旧 `query_monitor.py` 使用无界内存列表存储每次查询耗时，不应直接恢复；如确需 SQL 查询级指标，应使用有界指标/Prometheus 方案并明确采样与脱敏。
- 旧 `query_optimizer.py`、`query_helpers.py` 无需为追求文件路径一致而整体恢复；主线已有 QueryBuilder、分页工具及服务层显式批量加载。
- 旧响应封装与主线 Pydantic v2 Schema 响应结构不同，禁止混用旧响应格式。

旧分支差异与凭据处置背景另见 `docs/CREDENTIAL_EXPOSURE_RESPONSE_2026-11-16.md`。

## 6. 验收结论

本轮四项代码整改已合并，PR #58 的 Full Audit 与 Emergency Security 全部通过。**这只代表本轮代码与 CI 检查通过，不代表生产上线条件已满足。**

在 P0 凭据轮换/吊销、生产密钥迁移、Git 历史清理，以及分支保护和生产等价迁移演练完成前，项目状态仍为“代码整改持续进行中 / 不允许宣告安全上线”。
