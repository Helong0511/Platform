# Redis 环境变量连接配置审计与修复（2026-11-22）

## 结论

发现并修复了 Redis 配置模板与实际客户端初始化之间的不一致。

- .env.example 原先只提供 REDIS_URL。
- app/core/config.py 同时定义 REDIS_URL 与拆分配置 REDIS_HOST / REDIS_PORT / REDIS_DB / REDIS_PASSWORD。
- 修复前 app/core/redis_client.py 只读取拆分配置中的 REDIS_HOST，不读取 REDIS_URL。
- 因此，部署人员仅按仓库模板配置 REDIS_URL 时，客户端仍会判定 Redis 未配置，并返回 None。生产环境的缓存、限流、CSRF、Cap 计数等依赖模块可能进入各自的内存降级或 fail-closed 路径；多 Worker 进程之间不会共享进程内状态。

## 修复

当前分支实现以下兼容规则：

1. 若显式配置 REDIS_HOST，继续使用原有拆分配置，保持旧部署兼容。
2. 未配置 REDIS_HOST 时，解析 REDIS_URL。
3. 支持 redis:// 和 rediss://，保留 URL 中的主机、端口、DB、ACL 用户信息、TLS scheme 与查询参数。
4. 单独注入的 REDIS_PASSWORD 优先于 URL 中的密码；不记录完整 URL 或凭据。
5. URL 缺失或格式错误时不猜测默认远程地址，返回不可用并记录受控错误类型。
6. 保留开发环境 loopback Redis 默认跳过连接的既有行为；本机已安装 Redis 时可按原规则设置 REDIS_FORCE=true。

## 回归测试

新增 tests/test_redis_url_config.py：

- 仅设置 REDIS_URL、没有 REDIS_HOST 时，验证生产客户端通过 URL 工厂创建 Redis 连接。
- 验证独立注入的密码、连接池参数和响应解码配置。
- 错误 scheme 的 URL 必须 fail-closed，不得意外创建客户端。
- 现有拆分配置连接测试继续覆盖旧路径。

## 部署注意

- 生产环境优先使用 REDIS_URL 或完整拆分配置，二者至少配置一套；不要仅设置 REDIS_PASSWORD 而不设置连接地址。
- 使用托管 Redis TLS 时采用 rediss://。
- 客户开放 API 的 Redis 防重放键依赖写入成功；生产 Redis 的 maxmemory-policy、内存水位、HA 与告警仍需按部署 Runbook 单独验收，不能由本次配置修复替代。
- 本次不连接、不修改任何生产 Redis，不执行生产数据变更。

## 验收状态

PR CI 尚待运行。只有新增回归测试、Backend 全量测试、Frontend Lint/Build/E2E 和 Security CI 均通过后，才可合并。