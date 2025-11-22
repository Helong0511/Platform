# Redis 快速检查命令

## 根据您的 Redis 状态

从您的服务状态可以看到：
- ✅ Redis 正在运行
- 📍 绑定地址：`127.0.0.1:6379`
- 💾 内存使用：3.1M
- ⏱️ 运行时间：8小时

## 快速检查命令

### 1. 基本连接测试

```bash
# 测试连接（如果设置了密码，需要添加 -a password）
redis-cli PING

# 如果设置了密码
redis-cli -a your-password PING
```

### 2. 查看基本信息

```bash
# 查看服务器信息
redis-cli INFO server

# 查看内存使用
redis-cli INFO memory

# 查看客户端连接
redis-cli INFO clients

# 查看统计信息
redis-cli INFO stats

# 查看键空间信息
redis-cli INFO keyspace
```

### 3. 查看项目相关数据

```bash
# 查看限流键数量
redis-cli --scan --pattern "rate_limit:*" | wc -l

# 查看 CSRF 令牌键数量
redis-cli --scan --pattern "csrf_token:*" | wc -l

# 查看所有限流键
redis-cli KEYS "rate_limit:*"

# 查看所有 CSRF 令牌键
redis-cli KEYS "csrf_token:*"
```

### 4. 查看配置

```bash
# 查看是否设置了密码
redis-cli CONFIG GET requirepass

# 查看内存限制
redis-cli CONFIG GET maxmemory

# 查看所有配置
redis-cli CONFIG GET "*"
```

### 5. 查看键的详细信息

```bash
# 查看键的数量
redis-cli DBSIZE

# 查看特定键的值
redis-cli GET "rate_limit:192.168.1.100:1234567890"

# 查看键的 TTL（剩余过期时间）
redis-cli TTL "csrf_token:xxx"

# 查看键的类型
redis-cli TYPE "rate_limit:xxx"
```

### 6. 监控 Redis

```bash
# 实时监控命令执行
redis-cli MONITOR

# 实时监控统计信息
redis-cli --stat

# 查看慢查询
redis-cli SLOWLOG GET 10
```

### 7. 查看日志

```bash
# 查看 Redis 服务日志
sudo journalctl -u redis-server -f

# 查看最近的日志
sudo journalctl -u redis-server -n 100

# 查看特定时间的日志
sudo journalctl -u redis-server --since "2025-11-13 18:00:00"
```

## 一键检查脚本

使用提供的检查脚本：

```bash
# 添加执行权限
chmod +x scripts/check_redis_status.sh

# 运行脚本
./scripts/check_redis_status.sh
```

## 常见问题

### 问题1：连接被拒绝

如果看到 `Connection refused`：

```bash
# 检查 Redis 是否运行
sudo systemctl status redis-server

# 检查端口是否监听
sudo netstat -tuln | grep 6379
# 或
sudo ss -tuln | grep 6379
```

### 问题2：需要密码

如果看到 `NOAUTH Authentication required`：

```bash
# 使用密码连接
redis-cli -a your-password

# 或者在连接后使用 AUTH
redis-cli
> AUTH your-password
```

### 问题3：查看密码配置

```bash
# 查看 Redis 配置文件
sudo cat /etc/redis/redis.conf | grep requirepass

# 或者通过 Redis 命令查看
redis-cli CONFIG GET requirepass
```

## 根据您的配置

由于您的 Redis 绑定到 `127.0.0.1:6379`，这意味着：

1. **只能本地连接**：只能从本机连接，外部无法访问（安全）
2. **连接方式**：
   ```bash
   redis-cli -h 127.0.0.1 -p 6379
   # 或直接
   redis-cli
   ```

3. **项目配置**：在 `.env` 文件中应该设置：
   ```bash
   REDIS_HOST=127.0.0.1
   REDIS_PORT=6379
   ```

## 实用命令组合

```bash
# 快速查看 Redis 健康状态
echo "=== Redis 健康检查 ===" && \
redis-cli PING && \
echo "内存使用:" && redis-cli INFO memory | grep used_memory_human && \
echo "连接数:" && redis-cli INFO clients | grep connected_clients && \
echo "键数量:" && redis-cli DBSIZE

# 查看项目相关键的统计
echo "限流键:" && redis-cli --scan --pattern "rate_limit:*" | wc -l && \
echo "CSRF令牌键:" && redis-cli --scan --pattern "csrf_token:*" | wc -l
```

## 下一步

1. **测试连接**：运行 `redis-cli PING` 确认可以连接
2. **检查配置**：查看是否设置了密码 `redis-cli CONFIG GET requirepass`
3. **查看数据**：检查项目相关的键 `redis-cli KEYS "rate_limit:*"`
4. **监控性能**：使用 `redis-cli INFO memory` 查看内存使用

