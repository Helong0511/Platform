# Redis 配置详细说明

## 概述

Redis 在本项目中主要用于：
1. **API 限流**：存储限流计数器，支持多进程/多实例环境
2. **CSRF 令牌存储**：存储 CSRF 令牌，支持多进程环境下的令牌共享
3. **缓存**：未来可扩展用于缓存常用数据

## 配置项说明

### 环境变量配置

在 `.env` 文件中配置以下 Redis 相关环境变量：

| 配置项 | 说明 | 默认值 | 是否必须 | 示例 |
|--------|------|--------|----------|------|
| `REDIS_HOST` | Redis 主机地址 | `None` | 生产环境建议 | `127.0.0.1` 或 `redis` |
| `REDIS_PORT` | Redis 端口 | `6379` | 否 | `6379` |
| `REDIS_DB` | Redis 数据库编号 | `0` | 否 | `0` (0-15) |
| `REDIS_PASSWORD` | Redis 密码 | `None` | 生产环境建议 | `your-strong-password` |
| `REDIS_MAX_CONNECTIONS` | 连接池最大连接数 | `10` | 否 | `10` |

### 配置示例

#### Docker Compose 环境

```bash
# .env 文件
REDIS_HOST=redis          # Docker Compose 服务名
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your-strong-redis-password
REDIS_MAX_CONNECTIONS=10
```

#### 本地开发环境

```bash
# .env 文件
REDIS_HOST=127.0.0.1      # 本地 Redis
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=           # 开发环境可以不设置密码
REDIS_MAX_CONNECTIONS=10
```

#### 生产环境（外部 Redis）

```bash
# .env 文件
REDIS_HOST=redis.example.com    # 外部 Redis 服务器
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your-strong-redis-password  # 必须设置强密码
REDIS_MAX_CONNECTIONS=20        # 生产环境建议增加连接数
```

## 配置详解

### 1. REDIS_HOST（Redis 主机地址）

**说明**：Redis 服务器的主机地址或 IP

**配置建议**：
- **Docker Compose 环境**：使用服务名 `redis`（Docker 内部网络）
- **本地开发**：使用 `127.0.0.1` 或 `localhost`
- **生产环境**：使用实际的 Redis 服务器地址或 IP

**示例**：
```bash
# Docker Compose
REDIS_HOST=redis

# 本地开发
REDIS_HOST=127.0.0.1

# 生产环境
REDIS_HOST=redis.example.com
```

**注意事项**：
- 如果未配置 `REDIS_HOST`，应用将使用内存存储（多进程环境下可能不一致）
- 生产环境强烈建议配置 Redis，以确保多进程/多实例环境下的数据一致性

### 2. REDIS_PORT（Redis 端口）

**说明**：Redis 服务器的端口号

**默认值**：`6379`（Redis 默认端口）

**配置示例**：
```bash
REDIS_PORT=6379
```

**注意事项**：
- 如果使用非标准端口，需要修改此配置
- 确保防火墙允许访问此端口

### 3. REDIS_DB（Redis 数据库编号）

**说明**：Redis 数据库编号（0-15）

**默认值**：`0`

**配置示例**：
```bash
REDIS_DB=0    # 默认数据库
REDIS_DB=1    # 使用数据库1
```

**用途**：
- 可以用于区分不同环境（开发、测试、生产）
- 可以用于区分不同应用（如果多个应用共享同一个 Redis 服务器）

**注意事项**：
- Redis 默认有 16 个数据库（0-15）
- 生产环境建议使用不同的数据库编号区分环境

### 4. REDIS_PASSWORD（Redis 密码）

**说明**：Redis 服务器密码（如果设置了密码）

**默认值**：`None`（无密码）

**配置示例**：
```bash
# 开发环境（可以不设置）
REDIS_PASSWORD=

# 生产环境（必须设置强密码）
REDIS_PASSWORD=your-strong-redis-password
```

**安全建议**：
- **生产环境必须设置密码**
- 密码长度建议至少 16 字符
- 使用强密码（包含大小写字母、数字和特殊字符）
- 定期轮换密码（建议每3-6个月）

**生成 Redis 密码**：
```bash
# 使用密码生成工具
python scripts/generate_password.py --type redis
```

### 5. REDIS_MAX_CONNECTIONS（连接池最大连接数）

**说明**：Redis 连接池的最大连接数

**默认值**：`10`

**配置建议**：
- **开发环境**：`10`（足够）
- **生产环境**：`20-50`（根据并发量调整）

**配置示例**：
```bash
# 开发环境
REDIS_MAX_CONNECTIONS=10

# 生产环境（高并发）
REDIS_MAX_CONNECTIONS=50
```

**注意事项**：
- 每个 worker 进程会创建独立的连接池
- 总连接数 = `REDIS_MAX_CONNECTIONS × WORKERS`
- 例如：`10 × 3 workers = 30` 个连接

## Redis 连接参数

### 连接超时设置

在 `app/core/redis_client.py` 中，Redis 连接使用以下参数：

```python
_redis_client = aioredis.Redis(
    host=redis_host,
    port=redis_port,
    db=redis_db,
    password=redis_password,
    decode_responses=True,          # 自动解码响应为字符串
    socket_connect_timeout=5,       # 连接超时5秒
    socket_timeout=5,               # 操作超时5秒
    retry_on_timeout=True,          # 超时重试
    health_check_interval=30,       # 健康检查间隔30秒
)
```

**参数说明**：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `decode_responses` | 自动解码响应为字符串 | `True` |
| `socket_connect_timeout` | 连接超时时间（秒） | `5` |
| `socket_timeout` | 操作超时时间（秒） | `5` |
| `retry_on_timeout` | 超时时是否重试 | `True` |
| `health_check_interval` | 健康检查间隔（秒） | `30` |

## Redis 在项目中的用途

### 1. API 限流（Rate Limiting）

**用途**：存储每个 IP 地址的请求计数，实现 API 限流

**存储格式**：
```
Key: rate_limit:{IP地址}:{时间窗口}
Value: 请求计数（整数）
TTL: 时间窗口（秒）
```

**示例**：
```
rate_limit:192.168.1.100:1234567890 → 15
```

**优势**：
- 支持多进程/多实例环境
- 自动过期（使用 TTL）
- 高性能（内存存储）

**代码位置**：`app/core/middleware.py` (RateLimitMiddleware)

### 2. CSRF 令牌存储

**用途**：存储 CSRF 令牌，防止跨站请求伪造攻击

**存储格式**：
```
Key: csrf_token:{会话ID}
Value: CSRF 令牌（字符串）
TTL: CSRF_TOKEN_EXPIRE_SECONDS（默认3600秒）
```

**示例**：
```
csrf_token:192.168.1.100:1234567890 → abc123xyz...
```

**优势**：
- 支持多进程环境下的令牌共享
- 自动过期（使用 TTL）
- 防止令牌泄露（存储在服务器端）

**代码位置**：`app/core/csrf.py` (CSRFMiddleware)

## Docker Compose 配置

### Redis 服务配置

在 `docker-compose.yml` 中，Redis 服务配置如下：

```yaml
redis:
  image: redis:7-alpine
  container_name: platform_redis
  restart: unless-stopped
  ports:
    - "${REDIS_PORT:-6379}:6379"
  volumes:
    - redis_data:/data
  command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD:-redispassword}
  healthcheck:
    test: ["CMD", "redis-cli", "--raw", "incr", "ping"]
    interval: 10s
    timeout: 3s
    retries: 5
  networks:
    - platform_network
```

**配置说明**：

| 配置项 | 说明 |
|--------|------|
| `image` | Redis 镜像版本（使用 Alpine 版本，体积小） |
| `restart` | 自动重启策略 |
| `ports` | 端口映射（外部:内部） |
| `volumes` | 数据持久化卷 |
| `command` | Redis 启动命令 |
|   | `--appendonly yes`：启用 AOF 持久化 |
|   | `--requirepass`：设置密码 |
| `healthcheck` | 健康检查配置 |

### 持久化配置

**AOF（Append Only File）**：
- 启用：`--appendonly yes`
- 优点：数据更安全，可以恢复所有写操作
- 缺点：文件较大，恢复速度较慢

**RDB（Redis Database）**：
- 默认启用（定期快照）
- 优点：文件小，恢复速度快
- 缺点：可能丢失最后一次快照后的数据

**生产环境建议**：
- 同时启用 AOF 和 RDB
- 定期备份 Redis 数据文件

## 故障排查

### 问题1：Redis 连接失败

**错误信息**：
```
Redis连接失败: Connection refused
```

**可能原因**：
1. Redis 服务未启动
2. Redis 主机地址或端口配置错误
3. 防火墙阻止连接

**解决方案**：

1. **检查 Redis 服务状态**：
   ```bash
   # Docker Compose
   docker-compose ps redis
   
   # 系统服务
   systemctl status redis
   ```

2. **检查连接配置**：
   ```bash
   # 测试连接
   redis-cli -h 127.0.0.1 -p 6379 ping
   ```

3. **检查防火墙**：
   ```bash
   # 检查端口是否开放
   netstat -tuln | grep 6379
   ```

### 问题2：Redis 认证失败

**错误信息**：
```
Redis连接失败: NOAUTH Authentication required
```

**可能原因**：
1. Redis 设置了密码，但配置文件中未提供密码
2. Redis 密码配置错误

**解决方案**：

1. **检查密码配置**：
   ```bash
   # 查看 .env 文件中的 REDIS_PASSWORD
   grep REDIS_PASSWORD .env
   ```

2. **测试连接**：
   ```bash
   # 使用密码连接
   redis-cli -h 127.0.0.1 -p 6379 -a your-password ping
   ```

### 问题3：Redis 内存不足

**错误信息**：
```
Redis连接失败: OOM command not allowed when used memory > 'maxmemory'
```

**可能原因**：
1. Redis 内存使用达到上限
2. 限流数据或 CSRF 令牌过多

**解决方案**：

1. **检查内存使用**：
   ```bash
   redis-cli INFO memory
   ```

2. **清理过期数据**：
   ```bash
   # Redis 会自动清理过期数据（TTL）
   # 如果仍有问题，可以手动清理
   redis-cli FLUSHDB
   ```

3. **增加 Redis 内存限制**：
   ```bash
   # 在 redis.conf 中设置
   maxmemory 256mb
   maxmemory-policy allkeys-lru
   ```

### 问题4：多进程环境下限流不一致

**错误信息**：
```
生产环境未配置Redis，将使用内存存储（多进程环境下可能不一致）
```

**可能原因**：
1. 未配置 `REDIS_HOST`
2. Redis 连接失败，回退到内存存储

**解决方案**：

1. **配置 Redis**：
   ```bash
   # 在 .env 文件中设置
   REDIS_HOST=redis  # 或实际的 Redis 地址
   ```

2. **检查 Redis 连接**：
   ```bash
   # 查看应用日志
   docker-compose logs backend | grep Redis
   ```

## 最佳实践

### 1. 生产环境配置

```bash
# .env 文件
REDIS_HOST=redis.example.com
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your-strong-redis-password  # 必须设置
REDIS_MAX_CONNECTIONS=20
```

### 2. 安全建议

1. **设置强密码**：
   - 至少 16 字符
   - 包含大小写字母、数字和特殊字符
   - 定期轮换（每3-6个月）

2. **限制网络访问**：
   - 仅允许内网访问
   - 使用防火墙限制端口访问
   - 考虑使用 Redis ACL（Redis 6.0+）

3. **启用持久化**：
   - 启用 AOF 持久化
   - 定期备份数据文件

4. **监控 Redis**：
   - 监控内存使用
   - 监控连接数
   - 监控命令执行时间

### 3. 性能优化

1. **连接池配置**：
   - 根据并发量调整 `REDIS_MAX_CONNECTIONS`
   - 避免连接数过多或过少

2. **数据过期策略**：
   - 合理设置 TTL（限流窗口、CSRF 令牌过期时间）
   - 避免数据无限增长

3. **内存管理**：
   - 设置 `maxmemory` 限制
   - 使用 `allkeys-lru` 策略自动清理

### 4. 高可用配置

1. **Redis Sentinel**：
   - 配置 Redis Sentinel 实现高可用
   - 自动故障转移

2. **Redis Cluster**：
   - 大规模部署使用 Redis Cluster
   - 分片存储，提高性能

## 监控和调试

### 查看 Redis 信息

```bash
# 连接 Redis
redis-cli -h 127.0.0.1 -p 6379 -a your-password

# 查看服务器信息
INFO server

# 查看内存使用
INFO memory

# 查看客户端连接
INFO clients

# 查看键空间
INFO keyspace

# 查看所有键（谨慎使用）
KEYS *

# 查看特定模式的键
KEYS rate_limit:*

# 查看键的 TTL
TTL csrf_token:xxx
```

### 查看应用日志

```bash
# Docker Compose
docker-compose logs -f backend | grep -i redis

# 查看 Redis 连接日志
docker-compose logs redis
```

## 相关文档

- [生产环境配置指南](生产环境配置指南.md)
- [快速开始指南](快速开始指南.md)
- [Docker 部署指南](../README.Docker.md)

## 总结

Redis 在本项目中主要用于：
1. **API 限流**：确保多进程环境下的限流一致性
2. **CSRF 防护**：存储 CSRF 令牌，防止跨站请求伪造

**关键配置**：
- `REDIS_HOST`：Redis 主机地址（生产环境必须配置）
- `REDIS_PASSWORD`：Redis 密码（生产环境必须设置）
- `REDIS_DB`：数据库编号（可选，默认0）

**重要提示**：
- 生产环境强烈建议配置 Redis
- 必须设置强密码
- 定期监控和备份

