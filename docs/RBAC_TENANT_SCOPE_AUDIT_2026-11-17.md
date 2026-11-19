# RBAC 与多租户 API 范围审计记录（2026-11-17）

## 审计范围

本记录针对分支 `fix/non-credential-hardening-2026-11` 的当前代码快照进行静态审查，重点检查对象级授权（IDOR）、客户主体多重关联、列表/详情/导出范围、统计接口和管理写接口。

本记录不是全仓库安全认证，也不代表生产环境渗透测试已完成。

## 已检查代码

- `app/core/security.py`：`get_current_user`、`require_admin`、`require_admin_or_self`、`require_publisher_or_admin`
- `app/core/permission_cache.py`：用户权限缓存及失效辅助函数
- `app/api_v1/clients/clients.py`
- `app/api_v1/cpl/publishers.py`
- `app/api_v1/cpl/advertisers.py`
- `app/api_v1/cpl/offers.py`
- `app/api_v1/products/products.py`
- `app/api_v1/products/assignments.py`
- `app/api_v1/users/users.py`
- `app/api_v1/dashboard.py`
- `app/api_v1/cpl/conversions/summary.py`
- `app/api_v1/cpl/conversions/deductions.py`
- `app/services/client_service.py`
- `app/services/cpl/publisher_service.py`
- `app/services/cpl/advertiser_service.py`
- `app/services/product_service.py`
- `app/services/product_assignment_service.py`
- `app/services/dashboard_service.py`
- `app/services/cpl/conversion_service.py`

## 已确认的保护措施

### 1. 身份与角色

- 当前认证流程每次从数据库读取 User 行，不依赖 Redis 权限缓存中的旧角色/状态作最终认证判断。
- 已停用用户、受限登录用户会被拒绝。
- 客户角色在认证时还会确认至少存在一个启用中的 Client 主体。
- 管理员路由使用 `require_admin`；客户与管理员共用的读取路由在服务层按当前用户范围过滤。
- `require_admin_or_self` 对客户详情以 `Client.user_id == current_user.id`、目标 `client_id` 和启用状态共同约束。

### 2. 多 Client 账号

- PublisherService 与 AdvertiserService 均查询当前用户全部启用 Client ID，不只取一条关联记录。
- Publisher 列表、详情以 Client ID 集合过滤；客户响应对邮箱、Postback URL 等敏感字段进行脱敏。
- Advertiser 可见范围由当前客户主体下启用的 Publisher 与有效 Offer 分配关系推导；客户响应进行敏感字段脱敏。
- ConversionService 的客户统计范围由当前用户全部启用 Client 及其启用 Publisher 推导；无可用主体/渠道时返回空集，不回退全局范围。
- ProductService 对非管理员查询通过 Client.user_id 与 Client.is_active 过滤；请求参数中的 client_id 不会替代服务端身份范围。

### 3. 统计和缓存

- Dashboard 统计和趋势缓存键包含当前用户 ID 与统计周期，避免不同用户共用同一用户范围缓存。
- Dashboard 主统计、趋势和最近广告数据的非管理员查询均按当前用户所属启用 Client 过滤。
- ConversionSummary 路由有 Publisher/Admin 角色依赖，服务层再次按客户 Publisher 集合过滤；请求中的 offer_id、publisher_id、advertiser_id 是附加筛选，不替代授权范围。
- 扣减规则属于管理员商业配置，相关 API 路由要求管理员权限。

### 4. 产品分配历史

- 产品分配历史查询对非管理员同时约束 Product ID、Client.user_id 和 Client.is_active。
- 客户按 Client ID 查询全量分配历史的端点要求管理员权限。
- 分配历史校验、清理、日期变更和批量日期变更均要求管理员权限。

### 5. 客户数据导出与 API 密钥

- 客户列表导出端点要求管理员权限。
- 客户 API 密钥读取端点要求管理员权限；该端点仍属于高敏感管理操作，生产环境应确保后台管理员账号强 MFA、访问审计和最小授权。
- 普通客户详情响应移除密钥字段，仅返回是否配置密钥的状态。

## 关联测试证据

当前代码树包含以下针对性测试：

- `tests/test_security_permission_cache_freshness.py`：权限缓存过期不能维持已停用用户、登录受限用户的有效身份；停用全部 Client 后旧 Access Token 被拒绝。
- `tests/test_client_user_multi_membership.py`：一个用户关联多个 Client 时 Publisher 详情和列表按全部启用主体过滤。
- `tests/test_conversion_saver_tenant_attribution.py`：Postback 回调伪造 client/product 归属不能覆盖可信服务端归因。
- `tests/test_conversion_client_scope.py`：转化查询客户范围隔离。
- `tests/test_cpl_offer_multi_client_scope.py`：Offer 多 Client 关联范围。
- `tests/test_security_client_scope.py`：客户资源访问范围。
- `tests/test_client_api_key_multi_client.py`：客户 API 多主体关联。
- `tests/test_client_reconciliation_db_scope.py`：客户对账数据范围。

这些测试名和源码路径证明测试资产存在，不等同于本轮对所有测试重新执行成功。最近完整通过的 CI SHA 与当前分支 HEAD 不一致，必须以当前 HEAD 的成功 CI 重新验收。

## 本轮结论

本轮检查的上述路由与服务层中，未确认一个可直接复现的跨 Client 越权漏洞，因此没有为制造代码改动而修改业务代码。

以下事项仍未完成，不能标记为全量 RBAC 验收通过：

1. 全量枚举所有 API 路由并将每个路由映射到角色、资源范围、读写级别和敏感字段。
2. 对每个对象 ID 接口执行跨用户、跨 Client、跨 Publisher、跨 Advertiser 的负向 API 集成测试。
3. 对批量更新、批量删除、导入、导出、异步任务、WebSocket 和后台任务逐一核验授权上下文是否传递。
4. 核验所有查询缓存键、导出文件缓存、报表缓存是否包含用户/租户范围。
5. 核验管理员修改 Client.user_id、Publisher.client_id、产品归属和 Offer 分配时的并发与审计完整性。
6. 核验生产 JWT 密钥、管理员 MFA、会话撤销、Redis ACL 与数据库最小权限。

## 验收规则

- 未登录：拒绝。
- 普通客户访问其他客户资源：拒绝或返回不泄漏资源存在性的 404。
- 客户访问自己的多个启用 Client：允许，但仅限这些主体。
- 客户主体被停用：不得继续通过旧 token 访问该主体数据。
- 列表、详情、统计、导出、批量接口必须使用同一服务端授权范围。
- 客户提交的 client_id、publisher_id、advertiser_id、product_id 只能作为筛选输入，不能作为授权凭证。
- 所有写接口必须检查资源当前归属和目标归属，不能只校验操作者角色。
- 任何权限查询异常不得退化为全局数据访问。

## 后续审计优先级

下一轮应继续检查尚未逐项核验的 API：广告数据查询/导出、外部 Client API、短链接管理、Postback 管理与重试、系统配置、定时任务、Excel 导入导出，以及所有 batch 路由。优先寻找对象级授权缺失、查询 count 与 data 条件不一致、缓存键遗漏租户维度和批量接口部分越权。


## 2026-11-17 外部 Client API 补充审计

### 检查范围

- `app/core/api_auth.py`
- `app/api_v1/external/client_api.py`
- `app/services/ad_data/queries/client_api_query.py`
- `tests/test_client_api_ip_allowlist.py`
- `tests/test_client_api_key_multi_client.py`

### 已确认的租户范围

- 客户 API 先按 `request.client_id` 查询启用的 Client，并检查 `api_enabled`；请求中的 ID 仅用于定位客户主体，不会直接成为数据查询的授权条件。
- 产品列表查询使用服务端验证返回的 `client.id` 过滤 `Product.client_id`。
- 广告数据查询由 `ClientAdDataQuery` 接收已验证的 Client 实体；产品归属过滤使用 `Product.client_id == client.id`，启用分配表时使用按日期解析的唯一归属客户 ID。
- 分配表路径使用确定性归属规则处理重叠脏数据，避免同一条 AdData 因请求客户不同而同时泄漏给多个客户。
- IP 白名单配置错误时 fail-closed；客户 IP 从可信代理边界解析，不直接信任任意请求头。
- HMAC-SHA256 可用；MD5 是否接受由配置解析，未显式设置时生产默认关闭、开发默认开启。

### 已确认的缺口与风险边界

1. `verify_client_request()` 只验证时间戳窗口（默认 ±15 秒）和签名，没有 nonce 或服务端已用签名记录。因此，同一份合法签名请求可在窗口内被重复提交。当前两个客户开放端点（`/client_products`、`/client_data`）均为查询型接口，本轮没有发现该鉴权器被用于扣款、转化写入等非幂等操作；故目前应定性为**查询重放 / 资源放大风险**，不能夸大为已证实的资金或业务状态篡改漏洞。
2. （历史发现，2026-11-17）客户广告数据 API 当时未限制日期跨度，且页码/页大小组合可能产生极大 OFFSET。日期跨度已由 PR #24 限制为 90 天；深分页预算已由 PR #26 增加 100000 行 OFFSET 硬上限并合并 main（`436dfc9163423384b5722453072e8beb92d7b5a4`），PR 与合并后 main CI 均通过。
3. 增加强制 nonce 或请求去重会改变客户重试行为；若直接按签名拒绝重复请求，合法网络重试也会被拒绝。实施前应确定协议升级方案（例如可选 nonce 的过渡期、幂等响应缓存/请求 ID、Redis 不可用时的安全策略），并为旧版客户端制定明确兼容期限。当前没有贸然改变开放 API 协议。

### 当前 CI 证据更新

- PR #1 HEAD：`b34421f5be5ce816f5d0538c2b326e51df6236f6`
- Run #1918 / ID `44018193951`，第二次尝试整体成功。
- Backend：718 passed、1 skipped、1 warning；warning 为 passlib 导入 Python `crypt` 弃用提示。
- Frontend：依赖安装/审计、Lint、Build、Playwright Mock API E2E 全通过。
- CI 使用隔离 MySQL 8.0 / Redis 7.4、合成数据和 Mock API，不证明生产数据库权限、生产代理或第三方真实网络已验收。

本节为 2026-11-17 的历史审查记录；请求重放保护随后已补充 Redis 原子认领，查询资源限额的深分页部分已由 PR #26 修复并合并 main。

### 2026-11-18 请求重放防护修复（PR 验收中）

- `verify_client_request()` 在时间戳与签名验证通过后，新增 Redis 原子 `SET key value NX EX` 请求认领；指纹由 `client_id`、`req_time` 和签名 SHA-256 组成，不把原始签名写入 Redis key。
- TTL 为 `2 * time_tolerance + 1` 秒，覆盖请求时间戳 ±15 秒的完整有效窗口；同一签名请求第二次提交返回 HTTP 409。
- 仅在签名验证通过后写入防重放键，非法签名不会占用 Redis 键。
- Redis 未配置、不可连接或写入失败时返回 HTTP 503，拒绝请求；不降级为进程内集合，避免多 worker / 多实例间出现重放窗口。
- 新增测试覆盖同一请求只能认领一次、Client 维度隔离、Redis 不可用/写入异常 fail-closed、非法签名不消耗防重放键；现有 IP 白名单认证测试改用隔离的 Redis 替身。
- **运行条件限制：** Redis key 若被 maxmemory 淘汰策略提前驱逐，短期重放键可能消失。生产必须为该 Redis 实例/专用实例保留足够内存，并采用 `maxmemory-policy noeviction`（内存耗尽时写入失败并触发 503）；部署前需核验真实 Redis 配置与监控告警。当前 CI 只证明 Redis `SET NX EX` 语义与故障 fail-closed，不证明生产 Redis 的内存策略、持久化或 HA 配置。
- 此方案不增加客户端请求字段，兼容现有签名格式；合法客户端的重试必须重新生成 `req_time` 和签名。若客户端在网络超时后原样重放同一请求，将收到 409，应在客户端按当前时间重新签名后重试。

本修复仅覆盖 `/client_products` 和 `/client_data` 当前共享的 `verify_client_request()` 认证路径；不等同于全系统 API nonce / webhook 重放保护。日期跨度已由 PR #24 限制；大偏移分页已由 PR #26 增加 100000 行 OFFSET 上限并合并 main。


## 2026-11-19 补充：Client API 深分页资源预算（PR #26 已合并）

- 新增 `CLIENT_API_MAX_OFFSET_ROWS=100000`，API 入口按实际页大小计算 `(page - 1) * page_size`，超过预算时在执行广告数据查询前拒绝。
- `ClientAdDataQuery.fetch()` 同时执行服务层防线，避免内部调用绕过 API 层约束。
- 回归测试覆盖超限拒绝、恰好 100000 行 OFFSET 的边界允许，以及服务层在数据库访问前拒绝。
- PR #26 首轮 Full Audit CI 曾发现错误响应 detail 被误写成单元素 tuple；已修正为字符串并触发新一轮 CI。该问题会影响错误响应结构。
- PR #26 已 squash 合并，main commit `436dfc9163423384b5722453072e8beb92d7b5a4`；PR Full Audit CI #44447565948 与 Emergency Security CI #44447566036 均通过。合并后 main Full Audit CI #44447795340（767 passed、1 skipped、1 warning）与 Security CI #44447795332 均通过。仍需观察真实客户分页调用与慢查询指标，必要时进一步采用游标分页。


## 2026-11-19 补充：通知模块多 Client 用户范围修复（PR #27 已合并）

- 复核发现通知模块的 `get_user_client_id()` 仅取用户关联的第一条 Client，且未限定 `Client.is_active`；这与项目已支持同一客户用户关联多个 Client 的模型不一致。
- 影响范围包括客户/产品通知配置读取、通知记录列表与详情、单条通知补发、批量通知补发，以及按 conversion_id 自动补建通知记录的归属检查。
- 已改为 `get_user_client_ids()`：只查询当前用户全部启用 Client，按 ID 稳定排序；客户数据访问统一使用集合成员校验或 SQL `IN (...)` 条件。
- 批量补发在循环外一次读取 Client 范围，避免每条 conversion 重复查询权限范围。
- 新增测试覆盖多 Client ID 收集、启用状态过滤、通知配置/详情/补发权限、列表 SQL 范围和批量补发第二个 Client 的成功路径。
- 此修复是修正合法客户用户的范围过度收窄；当前没有证据表明此前存在跨客户数据泄露。PR #27 已 squash 合并，main commit `a554a79df7cec91819034199448eb891fccd9786`；PR Full Audit CI #44448656568 与 Emergency Security CI #44448656600 均通过，合并后 main Full Audit CI #44448917902（772 passed、1 skipped、1 warning）与 Security CI #44448917757 均通过。


## 2026-11-19 补充：通知记录列表分页预算与稳定排序（PR 待验收）

- 复核发现通知记录列表此前仅按 `created_at DESC` 排序；相同时间戳的记录没有唯一 tie-breaker，OFFSET 翻页可能出现重复或遗漏。
- 同时服务层没有最大 OFFSET 限制，虽路由限制 page_size 不超过 100，但任意大的 page 仍可能触发深分页。
- 本次增加 `NOTIFICATION_MAX_OFFSET_ROWS=100000`，服务层校验 page/page_size 与 OFFSET，超过预算在执行数据库查询前拒绝。
- 排序改为 `created_at DESC, id DESC`，为相同时间戳提供确定性顺序。
- 新增测试覆盖非法分页/超限拒绝、100000 行边界允许和稳定排序 SQL。等待 PR CI 验收。


## 2026-11-19 补充：批量通知补发拒绝重复转化 ID（PR 待验收）

- `batch_resend_conversions()` 此前直接遍历原始 `conversion_ids`；重复 ID 会对同一 conversion 再次调用 `PostbackForwarder.forward_to_publisher()`，该函数会真实发送下游 HTTP 请求并写入转发日志。
- 服务层现在在读取权限范围、查询数据库或发起任何外部请求前，验证参数必须为列表、每项必须为正整数、不得包含布尔值或重复 ID，并继续保留最多 50 条限制。
- 新增参数化测试覆盖重复 ID、零/负数、bool、字符串、浮点数、非列表和超出批量上限；所有非法输入必须在数据库访问前拒绝。
- 该修复只阻止同一批次内的重复 ID，不阻止用户通过后续独立请求再次手动补发；是否需要跨请求幂等/冷却策略需结合业务重试需求另行设计。


## 2026-11-19 补充：手动 Postback 补发返回真实结果（PR 待验收）

- 复核发现 `PostbackForwarder.forward_to_publisher()` 在没有 Publisher ID、渠道不存在/未配置 Postback URL 或渠道停用时直接返回；正常请求路径也不返回实际转发日志。
- `ResendNotificationCommand` 此前只判断函数是否抛异常，就返回“通知已补发”或将批量项计入成功，导致跳过发送或下游明确失败时仍显示成功。
- 转发器现在对未执行请求返回 `None`，对已尝试请求返回持久化的 `PostbackForwardLog`；单条、基于转发日志和批量补发均根据日志的 `success` 字段报告结果。
- 批量统计只将下游检查明确成功的项目计入成功；未找到有效渠道或下游未确认成功的项目进入失败列表。
- 新增测试覆盖无目标跳过、真实 HTTP 成功/失败日志返回、单条补发失败/跳过以及批量统计。
- 此项不会改变自动重试队列机制；失败记录仍由现有转发器尝试入队，接口只如实报告已持久化的下游结果。


## 2026-11-19 补充：广告数据列表与每日汇总深分页预算（PR 待验收）

- 复核发现 `/api/v1/ad-data/` 与 `/api/v1/ad-data/daily-summary` 的路由虽限制每页最多 100 条，但页码没有上限；对应服务层直接按 `(page - 1) * page_size` 执行 OFFSET。
- 新增 `AD_DATA_MAX_OFFSET_ROWS=100000`，两个查询服务分别在数据库/缓存访问前校验 page、page_size 与实际 OFFSET，内部调用不能绕过路由限制。
- 新增测试覆盖两条查询路径的非法参数/超限拒绝、100000 行 OFFSET 边界允许，并验证拒绝发生在 DB 或缓存查询之前。
- 这项只限制深分页，不替代真实数据规模下的 MySQL 慢查询、索引和执行计划验收；等待 PR CI 验收。


## 2026-11-19 补充：高流量列表统一 OFFSET 预算（PR 待验收）

- 新增通用 `calculate_pagination_offset()`，默认最大 OFFSET 为 100000 行；`paginate_query()` 也统一使用该校验。
- 已覆盖点击记录、Postback 转发日志、待确认 Postback 转化、短链接列表和 TB 搜索数据列表；其中 Postback 日志/待确认列表保留每页最多 1000 条的既有上限，其余沿用 MAX_PAGE_SIZE。
- 所有新增校验均在数据库查询前执行，TB 搜索列表在产品分配表探测前执行。
- 新增测试覆盖 100000 行边界、超限/非法参数拒绝、通用分页函数及各高流量列表服务的零数据库访问拒绝。
- 仍需继续审查 Client/Product/Publisher/Offer/User、审计日志、会话和扣减列表的独立分页实现；本 PR 不宣称全仓分页风险已经全部关闭。
