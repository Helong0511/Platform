# Ubuntu 上查看 Redis 信息指南

## 概述

本文档介绍在 Ubuntu 系统上查看和管理 Redis 信息的各种方法。

## 前提条件

### 1. 检查 Redis 是否安装

```bash
# 检查 Redis 是否安装
redis-cli --version

# 或者
redis-server --version
```

### 2. 检查 Redis 服务状态

```bash
# 使用 systemd（推荐）
sudo systemctl status redis

# 或者
sudo systemctl status redis-server

# 检查 Redis 是否运行
ps aux | grep redis
```

### 3. 启动/停止 Redis 服务

```bash
# 启动 Redis
sudo systemctl start redis
# 或
sudo systemctl start redis-server

# 停止 Redis
sudo systemctl stop redis

# 重启 Redis
sudo systemctl restart redis

# 设置开机自启
sudo systemctl enable redis
```

## 连接 Redis

### 1. 本地连接（无密码）

```bash
# 连接到本地 Redis（默认端口 6379）
redis-cli

# 指定端口连接
redis-cli -p 6379

# 指定主机和端口
redis-cli -h 127.0.0.1 -p 6379
```

### 2. 连接带密码的 Redis

```bash
# 方式1：使用 -a 参数
redis-cli -a your-password

# 方式2：连接后使用 AUTH 命令
redis-cli
> AUTH your-password

# 方式3：在命令行中指定
redis-cli -h 127.0.0.1 -p 6379 -a your-password
```

### 3. 连接远程 Redis

```bash
# 连接远程 Redis 服务器
redis-cli -h redis.example.com -p 6379 -a your-password
```

### 4. Docker 环境连接

```bash
# 如果 Redis 运行在 Docker 容器中
docker exec -it platform_redis redis-cli

# 带密码连接
docker exec -it platform_redis redis-cli -a your-password

# 或者进入容器后连接
docker exec -it platform_redis sh
redis-cli -a your-password
```

## 查看 Redis 信息

### 1. 基本连接测试

```bash
# 测试连接（在 redis-cli 中）
redis-cli
> PING
# 返回 PONG 表示连接成功

# 或者直接执行
redis-cli PING
```

### 2. 查看服务器信息

```bash
# 查看所有服务器信息
redis-cli INFO

# 查看特定部分的信息
redis-cli INFO server      # 服务器信息
redis-cli INFO memory      # 内存使用情况
redis-cli INFO clients     # 客户端连接信息
redis-cli INFO stats       # 统计信息
redis-cli INFO replication # 复制信息
redis-cli INFO cpu         # CPU 使用情况
redis-cli INFO keyspace    # 键空间信息
```

### 3. 查看内存使用情况

```bash
# 查看内存详细信息
redis-cli INFO memory

# 查看内存使用摘要
redis-cli INFO memory | grep used_memory_human

# 查看内存峰值
redis-cli INFO memory | grep used_memory_peak_human

# 查看内存配置
redis-cli CONFIG GET maxmemory
redis-cli CONFIG GET maxmemory-policy
```

### 4. 查看客户端连接信息

```bash
# 查看客户端连接信息
redis-cli INFO clients

# 查看当前连接的客户端
redis-cli CLIENT LIST

# 查看客户端连接数
redis-cli INFO clients | grep connected_clients

# 查看客户端最大连接数
redis-cli CONFIG GET maxclients
```

### 5. 查看键空间信息

```bash
# 查看所有数据库的键空间信息
redis-cli INFO keyspace

# 查看当前数据库的键数量
redis-cli DBSIZE

# 查看所有键（谨慎使用，可能很慢）
redis-cli KEYS *

# 查看特定模式的键
redis-cli KEYS "rate_limit:*"
redis-cli KEYS "csrf_token:*"

# 统计键的数量（使用模式）
redis-cli --scan --pattern "rate_limit:*" | wc -l
```

### 6. 查看统计信息

```bash
# 查看统计信息
redis-cli INFO stats

# 查看总命令数
redis-cli INFO stats | grep total_commands_processed

# 查看连接数
redis-cli INFO stats | grep total_connections_received

# 查看键命中率
redis-cli INFO stats | grep keyspace_hits
redis-cli INFO stats | grep keyspace_misses
```

### 7. 查看配置信息

```bash
# 查看所有配置
redis-cli CONFIG GET "*"

# 查看特定配置
redis-cli CONFIG GET maxmemory
redis-cli CONFIG GET maxclients
redis-cli CONFIG GET requirepass
redis-cli CONFIG GET port
redis-cli CONFIG GET bind
redis-cli CONFIG GET timeout
```

### 8. 查看持久化信息

```bash
# 查看持久化配置
redis-cli CONFIG GET save
redis-cli CONFIG GET appendonly

# 查看 AOF 信息
redis-cli INFO persistence | grep aof

# 查看 RDB 信息
redis-cli INFO persistence | grep rdb
```

## 常用 Redis 命令

### 1. 键操作

```bash
# 查看键的类型
redis-cli TYPE key_name

# 查看键的 TTL（剩余过期时间）
redis-cli TTL key_name

# 查看键是否存在
redis-cli EXISTS key_name

# 删除键
redis-cli DEL key_name

# 重命名键
redis-cli RENAME old_key new_key

# 查看键的值
redis-cli GET key_name
```

### 2. 查看项目相关的键

```bash
# 查看限流相关的键
redis-cli KEYS "rate_limit:*"

# 查看 CSRF 令牌相关的键
redis-cli KEYS "csrf_token:*"

# 查看所有键的数量
redis-cli DBSIZE

# 使用 SCAN 命令（更安全，不会阻塞）
redis-cli --scan --pattern "rate_limit:*"
redis-cli --scan --pattern "csrf_token:*"
```

### 3. 监控 Redis 命令

```bash
# 实时监控 Redis 执行的命令
redis-cli MONITOR

# 监控特定模式的命令
redis-cli MONITOR | grep "rate_limit"

# 查看慢查询日志
redis-cli SLOWLOG GET 10
```

## 查看 Redis 日志

### 1. 查看系统日志

```bash
# 查看 Redis 系统日志（systemd）
sudo journalctl -u redis -f

# 查看最近的日志
sudo journalctl -u redis -n 100

# 查看特定时间的日志
sudo journalctl -u redis --since "2024-01-01" --until "2024-01-02"
```

### 2. 查看 Redis 日志文件

```bash
# Redis 日志文件位置（通常在以下位置之一）
/var/log/redis/redis-server.log
/var/log/redis.log
/var/log/redis_6379.log

# 查看日志
sudo tail -f /var/log/redis/redis-server.log

# 查看最近的日志
sudo tail -n 100 /var/log/redis/redis-server.log

# 搜索特定内容
sudo grep "error" /var/log/redis/redis-server.log
```

### 3. Docker 环境查看日志

```bash
# 查看 Redis 容器日志
docker logs platform_redis

# 实时查看日志
docker logs -f platform_redis

# 查看最近的日志
docker logs --tail 100 platform_redis
```

## 性能监控

### 1. 实时监控

```bash
# 实时监控 Redis 统计信息
redis-cli --stat

# 实时监控特定指标
watch -n 1 'redis-cli INFO memory | grep used_memory_human'
```

### 2. 查看性能指标

```bash
# 查看延迟统计
redis-cli --latency

# 查看延迟直方图
redis-cli --latency-history

# 查看延迟分布
redis-cli --latency-dist
```

### 3. 基准测试

```bash
# 运行基准测试
redis-benchmark -h 127.0.0.1 -p 6379 -n 100000 -c 100

# 测试特定命令
redis-benchmark -h 127.0.0.1 -p 6379 -t set,get -n 100000
```

## 实用脚本

### 1. 查看 Redis 状态脚本

创建脚本 `check_redis.sh`：

```bash
#!/bin/bash

echo "=== Redis 状态检查 ==="
echo ""

# 检查服务状态
echo "1. 服务状态："
sudo systemctl status redis --no-pager | head -5
echo ""

# 检查连接
echo "2. 连接测试："
redis-cli PING
echo ""

# 查看内存使用
echo "3. 内存使用："
redis-cli INFO memory | grep -E "used_memory_human|used_memory_peak_human|maxmemory_human"
echo ""

# 查看客户端连接
echo "4. 客户端连接："
redis-cli INFO clients | grep -E "connected_clients|blocked_clients"
echo ""

# 查看键数量
echo "5. 键数量："
redis-cli DBSIZE
echo ""

# 查看项目相关键
echo "6. 限流键数量："
redis-cli --scan --pattern "rate_limit:*" | wc -l
echo ""

echo "7. CSRF 令牌键数量："
redis-cli --scan --pattern "csrf_token:*" | wc -l
echo ""

echo "=== 检查完成 ==="
```

使用脚本：

```bash
# 添加执行权限
chmod +x check_redis.sh

# 运行脚本
./check_redis.sh
```

### 2. 清理过期键脚本

```bash
#!/bin/bash

echo "清理 Redis 过期键..."

# 清理限流键（保留最近1小时的）
redis-cli --scan --pattern "rate_limit:*" | while read key; do
    ttl=$(redis-cli TTL "$key")
    if [ "$ttl" -lt 0 ]; then
        redis-cli DEL "$key"
        echo "删除过期键: $key"
    fi
done

echo "清理完成"
```

## 常见问题排查

### 问题1：无法连接 Redis

```bash
# 检查 Redis 是否运行
sudo systemctl status redis

# 检查端口是否监听
sudo netstat -tuln | grep 6379
# 或
sudo ss -tuln | grep 6379

# 检查防火墙
sudo ufw status
```

### 问题2：内存使用过高

```bash
# 查看内存使用
redis-cli INFO memory

# 查看最大的键
redis-cli --bigkeys

# 查看内存使用详情
redis-cli MEMORY STATS
```

### 问题3：连接数过多

```bash
# 查看客户端连接
redis-cli CLIENT LIST

# 查看连接数
redis-cli INFO clients | grep connected_clients

# 断开空闲连接
redis-cli CLIENT KILL TYPE normal
```

### 问题4：性能问题

```bash
# 查看慢查询
redis-cli SLOWLOG GET 10

# 查看命令统计
redis-cli INFO commandstats

# 监控命令执行
redis-cli MONITOR
```

## 安全建议

### 1. 检查密码配置

```bash
# 检查是否设置了密码
redis-cli CONFIG GET requirepass

# 如果返回空，说明未设置密码（不安全）
```

### 2. 检查网络绑定

```bash
# 检查 Redis 绑定的 IP
redis-cli CONFIG GET bind

# 如果绑定到 0.0.0.0，说明允许所有 IP 连接（不安全）
# 生产环境应该绑定到特定 IP 或使用防火墙限制
```

### 3. 检查命令重命名

```bash
# 查看重命名的命令
redis-cli CONFIG GET rename-command

# 生产环境建议重命名危险命令（如 FLUSHALL, CONFIG）
```

## 快速参考命令

```bash
# 连接 Redis
redis-cli -h 127.0.0.1 -p 6379 -a password

# 查看基本信息
redis-cli INFO

# 查看内存
redis-cli INFO memory

# 查看连接
redis-cli INFO clients

# 查看键数量
redis-cli DBSIZE

# 查看项目相关键
redis-cli KEYS "rate_limit:*"
redis-cli KEYS "csrf_token:*"

# 查看服务状态
sudo systemctl status redis

# 查看日志
sudo journalctl -u redis -f
```

## 相关文档

- [Redis 配置详细说明](Redis配置详细说明.md)
- [生产环境配置指南](生产环境配置指南.md)
- [Docker 部署指南](../README.Docker.md)

