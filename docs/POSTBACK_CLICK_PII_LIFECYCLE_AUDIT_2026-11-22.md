# Postback 与点击归档 PII 生命周期专项审计（2026-11-22）

## 1. 审计范围与结论

本次审计基于 `main` 提交 `2a7cfbc0ae14d29e2a4f00cd8a3514cd14ca24f0` 的模型、接收/审批服务、API 响应模型、PII 定时清理服务及点击归档服务进行静态核查。

**结论：待审批终态记录已有默认关闭的 PII 清理能力，但正式转化表与点击归档表尚未纳入完整的数据生命周期策略。当前不能认定 Postback/Click PII 生命周期已闭环。**

本报告只记录已核实的数据流与缺口，不自行设定保留期限，不触发任何生产数据删除或脱敏。

## 2. 已核实的数据流

### 2.1 非白名单 Postback 待审批 → 正式转化

审批服务 `app/services/cpl/postback_pending_service.py` 的构造逻辑将以下字段从 `PendingPostbackConversion` 复制到 `PostbackConversion`：

- `click_id`、`click_time`
- `devad_id`、`os`、`carrier`
- `ip`、`gid`
- `raw_data`（再次经过 `sanitize_postback_raw_data`）
- 转化金额、平台、转化 ID、事件名称及归因关联字段

因此，PR #96 对待审批表的终态清理**不会同步清除正式转化表中的副本**。待审批记录被清理后，正式转化表仍可能保留设备标识、IP、Click ID 与原始回调载荷。

### 2.2 正式转化表 `postback_conversions`

模型 `app/models/postback.py` 当前包含：

| 字段 | 数据性质/用途 |
|---|---|
| `devad_id` | 设备广告标识（IDFA/GAID） |
| `ip` | 点击/用户 IP |
| `os`、`carrier` | 设备/运营商信息 |
| `click_id`、`click_time` | 点击关联及归因 |
| `raw_data` | 原始回调 JSON |
| `conversion_id`、`transaction_id`、`request_id` | 幂等、去重、防重放 |
| `payout`、`original_payout`、`event_value`、扣减字段 | 财务/业务核对 |

现有 `scrub_expired_third_party_report_pii` 和 `scrub_expired_pending_postback_pii` 均未选择或更新 `PostbackConversion`。当前仓库未发现正式转化表的独立 PII 到期清理任务或专用保留配置。

### 2.3 点击归档表 `clicks_archive`

`app/services/tracking/clicks_archive_service.py` 的 `archive_old_clicks(days=90)` 会将 `click_time` 早于阈值的 `clicks` 记录复制到 `clicks_archive`，然后删除主表记录。

归档表结构/复制 SQL 明确保留以下字段：

- `ip`、`user_agent`、`referer`
- `url_params`、`all_headers`
- `original_request_url`、`final_redirect_url`（已在 2026-11-22 后续归档字段复核中发现原归档映射遗漏，PR #100 补齐新建表 DDL、复制 SQL、全量基线及既有表增量迁移）

注意：增量迁移只新增可空列，不可能自动还原过去归档时未复制的 URL 值；既有归档行对应新列将为 `NULL`。如业务确需恢复，必须单独核查可用备份/binlog，不能从当前归档表推断或伪造。
- `device`、`country`、`os`、`os_version`
- `browser`、`browser_version`、`accept_language`、`accept_encoding`
- `device_type`、`device_brand`、`device_model`
- `click_id`、`conversion_id`、广告/渠道/短链关联 ID

90 天在这里是**主表转归档表的迁移阈值，不是数据删除期限**。当前归档逻辑没有对 `clicks_archive` 做 PII 清理或过期删除，故不能将“90 天归档”表述为“90 天保留”。

### 2.4 API 响应暴露面

`app/schemas/postback.py` 的 `PostbackConversionResponse` 包含 `devad_id`、`ip`、`click_id`、`click_time` 等字段；`app/services/cpl/postback_conversion_service.py` 将 ORM 记录序列化为该响应模型。

这说明管理端查询响应会携带这些字段。当前已核实原始 Postback 查询路由为 ADMIN-only，客户转化汇总有 Client/Publisher 范围过滤与字段裁剪；但管理员最小权限、导出接口、其他异步报表和备份副本仍需单独核验。不能仅凭响应模型断言所有用户均可访问。

## 3. 风险与优先级

| 编号 | 优先级 | 已核实问题 | 影响 |
|---|---|---|---|
| PB-PII-01 | P1 | 正式转化表保留设备标识、IP、Click ID、raw_data，但没有独立保留/清理策略 | 正式业务数据可能长期保留超出必要范围的 PII |
| CLK-PII-01 | P1 | 点击记录归档 90 天后仍将 IP、UA、Referer、URL 参数、请求头、设备信息复制到归档表；未见归档表 PII 清理机制 | 归档数据可能无限期积累敏感信息 |
| PB-API-01 | P1 范围已缩小 | 已核查的原始 Postback 查询路由为 ADMIN-only；客户汇总有租户范围过滤和财务/广告主字段裁剪 | 管理员字段最小化、所有导出/异步报表及客户 A/B 反向访问仍需逐项验收 |
| PB-PII-02 | P2 | 待审批表与正式表各自保存 PII 副本 | 两份记录的保留、删除、更正与审计关联策略需要一致设计 |
| PB-OPS-01 | P1 待验证 | 当前清理服务主要处理在线业务表 | 还需盘点备份、只读副本、binlog、导出文件、日志与运维快照中的 PII 生命周期 |

## 4. 不应直接删除的字段

实施正式转化或点击归档清理前，必须确认字段用途与替代方案：

- `platform + conversion_id + event_name` 唯一约束和 `transaction_id/request_id` 可能承担幂等、防重放功能；不得因 PII 清理破坏唯一性。
- `click_id` 可能是归因关联键；若需清理，应先设计不可逆/可控的关联替代标识，并验证历史归因查询、补数、争议处理及回传重试。
- `payout`、`original_payout`、`event_value`、扣减状态与扣减量属于业务/财务证据，不应与 PII 载荷一起清除。
- `raw_data` 可能包含 PII、上游业务字段、排障证据；应优先评估字段白名单化、结构化最小快照，而不是无限期保存完整原始 JSON。
- `url_params`、`all_headers`、`referer`、`original_request_url`、`final_redirect_url` 可能携带令牌、邮箱、Click ID、广告参数或其他用户输入，必须按敏感载荷处理。

## 5. 建议实施顺序

1. **数据用途盘点**：确认正式转化、点击主表、点击归档表被哪些页面、API、报表、回传、补数、风控和财务流程读取。
2. **权限验证**：为管理员、客户、广告主、渠道、只读账号分别测试 API 查询、详情、导出、批量下载及后台字段可见性；校验租户/资源范围。
3. **字段分级**：区分直接身份/设备标识、网络标识、归因关联键、财务证据、审计元数据；建立字段级访问和保留矩阵。
4. **业务/合规批准期限**：按数据类别分别确定保留期、起算点、法律保全/争议冻结、删除请求例外及审批责任人。未经批准，所有新清理配置必须保持默认关闭。
5. **设计幂等安全的脱敏**：只对已终态且不再参与重试/争议流程的数据分批处理；保留必要的去重、财务和审计关联字段。
6. **全副本覆盖**：将同一策略扩展到主库、归档表、备份恢复流程、只读副本、导出文件、对象存储、应用日志和监控日志。
7. **可观测与回滚**：先 dry-run 统计候选量，输出字段级计数而非 PII 明文；限制每批行数；记录任务执行 ID、策略版本、阈值、行数和异常；提供停止开关及恢复演练。
8. **隔离 MySQL 验收**：验证锁等待、死锁、并发任务、复制/binlog、迁移前后 schema、查询计划和清理期间业务延迟。

## 6. 上线验收清单

- [ ] 正式转化表数据用途和字段保留矩阵获业务/合规书面批准
- [ ] 点击归档表数据用途和字段保留矩阵获业务/合规书面批准
- [ ] 所有 API/导出接口完成角色权限与租户隔离测试
- [ ] 幂等、去重、历史归因、财务对账、补数和争议处理测试通过
- [ ] 清理配置默认关闭；启用必须显式配置并有审批记录
- [ ] dry-run 统计与小批量演练通过
- [ ] 主库、归档、备份、复制、导出、日志的副本策略已覆盖
- [ ] MySQL/InnoDB 并发、锁、复制格式及恢复演练通过
- [ ] 运维手册包含监控指标、暂停条件、失败告警和恢复步骤

## 7. 当前状态

- PR #96 已合并：只覆盖 `pending_postback_conversions` 中超过独立期限的 `approved/rejected` 记录；默认关闭，不清理 `pending`。
- `THIRD_PARTY_REPORT_PII_RETENTION_DAYS=0` 与 `PENDING_POSTBACK_PII_RETENTION_DAYS=0` 均保持默认关闭。
- 正式转化表与点击归档表尚无本报告定义的独立清理实现。
- 点击归档已改为有界批次并通过 MySQL 双 Worker 并发测试，但这不等于 PII 已按期限清理；归档表仍无获批的 PII 到期清理策略。
- PR #102 已增加真实 FastAPI/ASGI 权限矩阵测试：转化总览 ADMIN/CLIENT/其他角色、无关联 Client/Publisher、Postback 查询路由管理员门禁和客户财务字段裁剪均有覆盖。
- PR #104 为管理员读取 Postback 转化列表、统计、重复检查、下游转发日志、待审批记录和诊断结果增加严格审计：记录管理员身份、HTTP 方法/路径、筛选字段是否出现及分页大小；不记录原始 click_id/conversion_id 值；审计提交失败时不向客户端返回查询结果。
- PR #99 已修复归档事务原子性；PR #100 已补齐归档 URL 字段及既有表迁移；PR #101 已实现有界批次、行锁和死锁重试。
- 正式转化表保留期、备份/binlog/只读副本/导出/日志生命周期仍需业务/合规批准和隔离环境验收。
- 本报告不代表项目已达到生产上线安全标准。


## 8. 2026-11-22 API 权限与字段范围复核补充

本节最初基于 main `4ccc61108386bf6a7bcf36116287e0ea41592dc2` 完成静态复核；后续 PR #102 已在 main `c74a9197f75a11ea423627defa9c0d709b10410c` 增加 FastAPI/ASGI 权限矩阵测试，PR #103 当前 main 为 `61b7633249d118dcc2b9caf44174ad14a56297ae` 并补充客户 Publisher 参数交集测试。

### 8.1 原始 Postback 转化列表

- `GET /postback/conversions` 由 `app/api_v1/postback/routes/conversions.py` 定义，直接依赖 `require_admin`。
- 该路由调用 `postback_conversion_service`，将 ORM 记录序列化为 `PostbackConversionResponse`；该响应包含 `devad_id`、`ip`、`click_id`、`click_time` 等字段。
- 同文件中的 Postback stats、更新状态和重复检查路由也使用 `require_admin`。
- 因此，**在已核查的这组原始 Postback 查询接口中，PII 响应被管理员角色门禁保护**。当前静态证据不支持“普通客户/渠道可以直接调用此接口读取原始 IP/设备标识”的结论。

### 8.2 客户可见的转化总览

- `GET /cpl/conversions/` 与 `GET /cpl/conversions/by-offer` 使用 `require_publisher_or_admin`。
- 该依赖只允许 ADMIN，或至少关联一个启用 Client 且拥有启用 Publisher 的 CLIENT；其它角色返回 403。
- `ConversionService` 对 CLIENT 收集该用户全部启用 Client，再将可见范围限制到这些 Client 关联的启用 Publisher。没有 Client 或 Publisher 时 fail-closed 返回空范围/拒绝访问，不退化为全局统计。
- 对 CLIENT 返回值执行字段裁剪：总览删除 `total_po`、`total_profit`，分组项删除 `po`、`adv_po`、`advertiser_id`、`advertiser_name`；按 Offer 汇总删除 `po`。
- `tests/test_conversion_client_scope.py` 覆盖缺失 Client 时返回空范围、多 Client 归属收集，以及用户指定的 `publisher_id` 必须与自身 Publisher 范围取交集。
- Postback 管理员读取日志已覆盖转化列表、统计、重复检查、下游转发日志、待审批列表和诊断结果六个 GET 接口；只记录筛选字段存在性，不保存原始 Click ID/Conversion ID/IP 筛选值。
- PR #102 的 `tests/test_conversion_api_authorization.py` 使用 FastAPI + ASGITransport 覆盖未认证 401、ADMIN 放行、有效 CLIENT 放行、缺失 Client/Publisher 与其他角色 403，并确认拒绝请求不会调用 Service。

### 8.3 本次复核后的风险定级

- 原始 Postback PII 查询的角色门禁已在静态代码中确认是 ADMIN-only；原报告 PB-API-01 不再作为“客户/渠道可直接访问原始 PII”的已确认缺陷。
- 仍需验证管理员账号自身的最小权限、管理员操作审计、字段展示/导出最小化，以及未来新增导出/批量下载接口是否复用相同权限约束。
- 客户转化总览已有 Publisher 归属范围和敏感财务字段裁剪，FastAPI 层角色矩阵已覆盖；本次另补充 `publisher_id` 参数不能扩大租户范围的 SQL 交集测试。

### 8.4 仍未完成的验收项

- [x] 使用 FastAPI/ASGI 真实路由装配验证转化汇总 ADMIN、CLIENT、其他角色的 401/403/200 行为；Postback 查询路由已验证 ADMIN-only 依赖和 CLIENT 拒绝
- [x] 验证客户指定的 `publisher_id` 与自身 Publisher 范围做 AND 交集，不能通过参数扩大渠道范围；仍需补充完整客户 A/B 数据库端到端反向访问测试
- [x] 验证客户汇总裁剪上游 PO、利润、广告主 ID/名称；原始 `devad_id`、`ip`、`click_id` 查询仍由 ADMIN-only Postback 路由保护
- [ ] 验证管理员查询、详情、导出均有操作者、时间、筛选范围和导出审计记录
- [ ] 搜索并逐项验证所有 Postback/Conversion 导出、下载、异步报表端点及后台任务的数据访问范围

本补充仅更新静态审计证据，不改变 API 行为，不访问生产数据。
