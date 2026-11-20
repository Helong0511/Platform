# Postback 与 Telegram 安全整改记录（2026-11-20）

> 本文记录 2026-11-20 对 `main` 的代码核查、已合并修复、CI 验证和仍未解除的上线阻断项。它是当前状态记录，不代表生产环境凭据已轮换或系统已完成上线验收。

## 1. 当前代码基线

- 仓库：`Helong0511/Platform`
- 当前主线：`main`
- 本文编写时 main HEAD：`e96a51d66f68b4529dcdfec355f4f2c60d09c154`
- 当前主线以 `main` 为唯一后续开发与部署基线；不要把无共同祖先的旧 `master` 直接合并回来。

## 2. 本轮已合并整改

| PR | 合并提交 | 整改内容 |
|---|---|---|
| [#55](https://github.com/Helong0511/Platform/pull/55) | `5731c17ac722aaa95e30cd7c357853b8c7c70241` | 短链接重定向日志不再输出完整 URL、查询参数值、Click ID；公开错误响应不再回显底层异常。 |
| [#56](https://github.com/Helong0511/Platform/pull/56) | `02c94b9d9e05c2d55ac271588c7c90962852937c` | Postback 历史归因筛选回退 Click；Telegram 审批保留点击关联与归因快照；增加重复转化检查和操作者白名单。 |
| [#57](https://github.com/Helong0511/Platform/pull/57) | `d2474da74cdb3d6f32438490019cc988f93770a4` | 移除 Telegram Bot 全量普通消息调试处理器，避免把消息正文写入 INFO 日志。 |
| [#58](https://github.com/Helong0511/Platform/pull/58) | `e96a51d66f68b4529dcdfec355f4f2c60d09c154` | Postback 服务异常脱敏、IP/Click ID 日志收敛、BFT Telegram 通知字段白名单化。 |

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

## 3. CI 验证记录

PR #58 最新提交对应的 Full Audit 和 Emergency Security 均通过：

- Full Audit run：[#44663227358](https://github.com/Helong0511/Platform/actions/runs/44663227358)
  - 后端：899 passed，1 skipped。
  - 前端依赖安装、Lint、Build：通过。
  - Playwright Browser E2E（mock APIs）：通过。
  - Python 3.13 password hash compatibility：通过。
- Emergency Security run：[#44663227241](https://github.com/Helong0511/Platform/actions/runs/44663227241)
  - Backend security configuration tests：通过。
  - Frontend lint and build：通过。

跳过的 1 项为本地核对脚本未检出，CI 注释说明该脚本不作为 CI 依赖；不是失败测试。

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
