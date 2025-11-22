# Redis 密码设置指南

## 概述

本文档介绍如何在 Ubuntu 系统上为 Redis 设置密码，包括临时设置和永久设置两种方式。

## 方法一：通过配置文件设置（推荐，永久生效）

### 1. 找到 Redis 配置文件

```bash
# 查找 Redis 配置文件位置
sudo find /etc -name "redis.conf" 2>/dev/null

# 或者
sudo find /etc -name "redis*.conf" 2>/dev/null

# 常见位置：
# /etc/redis/redis.conf
# /etc/redis/6379.conf
# /etc/redis-server.conf
```

### 2. 编辑配置文件

```bash
# 使用 nano 编辑器（推荐新手）
sudo nano /etc/redis/redis.conf

# 或使用 vim
sudo vim /etc/redis/redis.conf
```

### 3. 设置密码

在配置文件中找到 `# requirepass foobared` 这一行（通常在安全部分），取消注释并设置密码：

```bash
# 找到这一行（大约在第 500 行左右）
# requirepass foobared

# 修改为（将 your-strong-password 替换为您的强密码）
requirepass your-strong-password
```

**示例**：
```bash
# 原配置（注释状态）
# requirepass foobared

# 修改后（取消注释并设置密码）
requirepass MyStr0ng!P@ssw0rd123
```

### 4. 保存并重启 Redis

```bash
# 保存配置文件（nano: Ctrl+O, Enter, Ctrl+X）
# （vim: Esc, :wq, Enter）

# 重启 Redis 服务
sudo systemctl restart redis-server

# 或者
sudo systemctl restart redis
```

### 5. 验证密码设置

```bash
# 尝试无密码连接（应该失败）
redis-cli PING
# 应该返回: (error) NOAUTH Authentication required

# 使用密码连接（应该成功）
redis-cli -a your-strong-password PING
# 应该返回: PONG

# 或者在连接后使用 AUTH
redis-cli
> AUTH your-strong-password
> PING
# 应该返回: PONG
```

## 方法二：通过命令行临时设置（重启后失效）

### 1. 连接 Redis

```bash
redis-cli
```

### 2. 设置密码

```bash
# 在 redis-cli 中执行
CONFIG SET requirepass your-strong-password
```

### 3. 验证设置

```bash
# 测试连接（需要先认证）
AUTH your-strong-password
PING
```

### 4. 保存到配置文件（使永久生效）

```bash
# 在 redis-cli 中执行
CONFIG REWRITE
```

**注意**：`CONFIG REWRITE` 会将当前配置写入配置文件，使密码设置永久生效。

## 方法三：Docker 环境设置密码

### 1. 在 docker-compose.yml 中设置

```yaml
redis:
  image: redis:7-alpine
  container_name: platform_redis
  restart: unless-stopped
  command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD:-redispassword}
  environment:
    - REDIS_PASSWORD=${REDIS_PASSWORD:-redispassword}
```

### 2. 在 .env 文件中设置

```bash
# .env 文件
REDIS_PASSWORD=your-strong-redis-password
```

### 3. 重启容器

```bash
docker-compose restart redis
```

### 4. 验证

```bash
# 连接 Redis 容器
docker exec -it platform_redis redis-cli -a your-strong-redis-password PING
```

## 生成强密码

### 使用项目提供的密码生成工具

```bash
# 生成 Redis 密码（16字符）
python scripts/generate_password.py --type redis

# 或生成自定义长度的密码
python scripts/generate_password.py --length 20
```

### 使用 OpenSSL

```bash
# 生成随机密码
openssl rand -base64 32
```

### 使用 Python

```bash
# 生成 URL 安全的随机字符串
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## 密码安全建议

### 1. 密码强度要求

- **长度**：至少 16 字符（推荐 20-32 字符）
- **复杂度**：包含大小写字母、数字和特殊字符
- **示例**：`MyStr0ng!P@ssw0rd123`

### 2. 安全最佳实践

- ✅ 使用强密码
- ✅ 定期轮换密码（建议每 3-6 个月）
- ✅ 不要将密码存储在代码中
- ✅ 使用环境变量或密钥管理服务
- ✅ 限制 Redis 端口访问（仅内网）
- ✅ 使用防火墙限制访问

### 3. 密码管理

```bash
# 将密码存储在 .env 文件中（不要提交到版本控制）
REDIS_PASSWORD=your-strong-password

# 设置文件权限（仅所有者可读）
chmod 600 .env
```

## 使用密码连接 Redis

### 1. 命令行连接

```bash
# 方式1：在命令行中指定密码
redis-cli -a your-strong-password

# 方式2：连接后使用 AUTH
redis-cli
> AUTH your-strong-password
> PING
```

### 2. 执行命令

```bash
# 带密码执行单个命令
redis-cli -a your-strong-password PING
redis-cli -a your-strong-password INFO
redis-cli -a your-strong-password DBSIZE
```

### 3. 在脚本中使用

```bash
#!/bin/bash
REDIS_PASSWORD="your-strong-password"
redis-cli -a "$REDIS_PASSWORD" PING
```

### 4. 环境变量方式

```bash
# 设置环境变量
export REDISCLI_AUTH=your-strong-password

# 然后可以直接使用 redis-cli（不需要 -a 参数）
redis-cli PING
```

## 修改密码

### 1. 连接 Redis

```bash
redis-cli -a old-password
```

### 2. 设置新密码

```bash
# 在 redis-cli 中执行
CONFIG SET requirepass new-strong-password
```

### 3. 保存到配置文件

```bash
CONFIG REWRITE
```

### 4. 验证新密码

```bash
# 退出并重新连接
exit
redis-cli -a new-strong-password PING
```

## 移除密码

### 1. 连接 Redis

```bash
redis-cli -a current-password
```

### 2. 移除密码

```bash
# 在 redis-cli 中执行
CONFIG SET requirepass ""
```

### 3. 保存到配置文件

```bash
CONFIG REWRITE
```

### 4. 验证

```bash
# 退出并重新连接（不需要密码）
exit
redis-cli PING
```

**注意**：生产环境不建议移除密码！

## 故障排查

### 问题1：设置密码后无法连接

**错误**：`NOAUTH Authentication required`

**解决方案**：

1. **检查密码是否正确**：
   ```bash
   redis-cli -a your-password PING
   ```

2. **检查配置文件**：
   ```bash
   sudo grep requirepass /etc/redis/redis.conf
   ```

3. **检查 Redis 是否重启**：
   ```bash
   sudo systemctl status redis-server
   ```

### 问题2：CONFIG REWRITE 失败

**错误**：`CONFIG REWRITE failed`

**可能原因**：
- 配置文件权限不足
- 配置文件路径不正确

**解决方案**：

1. **检查配置文件权限**：
   ```bash
   ls -l /etc/redis/redis.conf
   ```

2. **手动编辑配置文件**：
   ```bash
   sudo nano /etc/redis/redis.conf
   # 添加或修改: requirepass your-password
   sudo systemctl restart redis-server
   ```

### 问题3：忘记密码

**解决方案**：

1. **停止 Redis 服务**：
   ```bash
   sudo systemctl stop redis-server
   ```

2. **编辑配置文件**：
   ```bash
   sudo nano /etc/redis/redis.conf
   # 注释掉或删除 requirepass 行
   # requirepass your-password
   ```

3. **启动 Redis**：
   ```bash
   sudo systemctl start redis-server
   ```

4. **设置新密码**（按照上述步骤重新设置）

## 验证密码设置

### 完整验证脚本

```bash
#!/bin/bash

echo "=== Redis 密码设置验证 ==="

# 1. 检查配置文件
echo "1. 检查配置文件："
if sudo grep -q "^requirepass" /etc/redis/redis.conf; then
    echo "✅ 配置文件中已设置密码"
    sudo grep "^requirepass" /etc/redis/redis.conf | head -1
else
    echo "❌ 配置文件中未设置密码"
fi
echo ""

# 2. 测试无密码连接
echo "2. 测试无密码连接："
if redis-cli PING 2>&1 | grep -q "NOAUTH"; then
    echo "✅ 密码保护已启用（无密码连接被拒绝）"
else
    echo "⚠️  密码保护可能未启用"
fi
echo ""

# 3. 提示使用密码连接
echo "3. 使用密码连接："
echo "   redis-cli -a your-password PING"
echo ""

echo "=== 验证完成 ==="
```

## 项目配置更新

设置 Redis 密码后，需要更新项目配置：

### 1. 更新 .env 文件

```bash
# .env 文件
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your-strong-redis-password  # 添加密码
```

### 2. 重启应用

```bash
# Docker Compose
docker-compose restart backend

# 或 systemd
sudo systemctl restart platform-backend
```

### 3. 验证应用连接

```bash
# 查看应用日志
docker-compose logs backend | grep -i redis
# 或
sudo journalctl -u platform-backend -f | grep -i redis
```

应该看到类似以下信息：
```
Redis连接成功: 127.0.0.1:6379/0
```

## 快速设置脚本

创建脚本 `scripts/set_redis_password.sh`：

```bash
#!/bin/bash

if [ -z "$1" ]; then
    echo "用法: $0 <password>"
    echo "示例: $0 MyStr0ng!P@ssw0rd123"
    exit 1
fi

PASSWORD=$1
CONFIG_FILE="/etc/redis/redis.conf"

echo "设置 Redis 密码..."

# 备份配置文件
sudo cp "$CONFIG_FILE" "$CONFIG_FILE.backup.$(date +%Y%m%d_%H%M%S)"

# 检查是否已有密码设置
if sudo grep -q "^requirepass" "$CONFIG_FILE"; then
    # 更新现有密码
    sudo sed -i "s/^requirepass.*/requirepass $PASSWORD/" "$CONFIG_FILE"
    echo "✅ 已更新密码"
else
    # 添加新密码
    sudo sed -i "/^# requirepass/a requirepass $PASSWORD" "$CONFIG_FILE"
    echo "✅ 已添加密码"
fi

# 重启 Redis
echo "重启 Redis 服务..."
sudo systemctl restart redis-server

# 等待服务启动
sleep 2

# 验证密码
if redis-cli -a "$PASSWORD" PING 2>/dev/null | grep -q "PONG"; then
    echo "✅ 密码设置成功！"
    echo "测试连接: redis-cli -a $PASSWORD PING"
else
    echo "❌ 密码设置失败，请检查配置"
    exit 1
fi
```

使用方法：

```bash
# 添加执行权限
chmod +x scripts/set_redis_password.sh

# 运行脚本
sudo ./scripts/set_redis_password.sh "MyStr0ng!P@ssw0rd123"
```

## 总结

### 推荐方法（永久设置）

1. **编辑配置文件**：`sudo nano /etc/redis/redis.conf`
2. **设置密码**：`requirepass your-strong-password`
3. **重启服务**：`sudo systemctl restart redis-server`
4. **验证**：`redis-cli -a your-strong-password PING`

### 快速设置

```bash
# 1. 生成强密码
python scripts/generate_password.py --type redis

# 2. 编辑配置文件
sudo nano /etc/redis/redis.conf
# 添加: requirepass <生成的密码>

# 3. 重启服务
sudo systemctl restart redis-server

# 4. 验证
redis-cli -a <生成的密码> PING
```

### 安全提示

- ✅ 使用强密码（至少16字符）
- ✅ 定期轮换密码
- ✅ 限制 Redis 端口访问
- ✅ 使用防火墙保护
- ✅ 不要将密码提交到版本控制

## 相关文档

- [Redis 配置详细说明](Redis配置详细说明.md)
- [Ubuntu 查看 Redis 信息指南](Ubuntu查看Redis信息指南.md)
- [生产环境配置指南](生产环境配置指南.md)

