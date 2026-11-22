# Telegram 同步 Redis 限流配置审计（2026-11-22）

## 问题

Telegram 消息发送器有独立同步 Redis 客户端 `app/core/telegram/message_sender.py::_get_sync_redis`。旧实现只读取 `REDIS_HOST/REDIS_PORT/REDIS_DB/REDIS_PASSWORD`；而项目统一配置和异步 Redis 客户端支持以 `REDIS_URL` 为首选/独立配置，包含 `redis://`、`rediss://`、ACL 用户名、URL 数据库路径及 TLS。

项目示例配置仅声明 `REDIS_URL`。当生产环境按示例只配置 URL、不配置 `REDIS_HOST` 时，Telegram 同步 Redis 客户端会直接返回 `None`，跨进程发送互斥、全局退避和 per-chat 闸门失效，发送器退化为各进程本地限流；多 worker 可能同时向 Telegram 发送并触发 429。

## 修复

- 显式 `REDIS_HOST` 仍优先，保持旧拆分配置兼容。
- 未配置 Host 时改用 `redis.Redis.from_url(REDIS_URL)`。
- 支持 redis/rediss URL、ACL username、DB path 和 TLS。
- 只有显式配置 `REDIS_PASSWORD` 才覆盖 URL 内密码；未设置时保留 URL 凭据。
- 连接失败仍使用已有 30 秒失败退避，异常日志只记录类型，不输出含凭据的 URL。

## 回归测试

- URL-only 配置、rediss、ACL 用户名、DB 路径、显式密码覆盖。
- 未设置显式密码时保留 URL 内凭据。

## 运行时边界

Redis 不可用时当前实现仍会降级到进程内节流；这属于 best-effort fallback，不等同于跨进程限流。生产环境应监控降级状态，并将 Redis 可用性纳入 Telegram 多 worker 的容量/限流验收。
