# 修复 .env 文件权限问题

## 问题描述

如果遇到以下错误：
```
PermissionError: [Errno 13] Permission denied: '/data/Platform/.env'
```

这是因为 `.env` 文件的权限设置不正确，导致 systemd 服务（以 `www-data` 用户运行）无法读取该文件。

## 快速修复（推荐）

### 使用诊断脚本（最简单）

```bash
# 运行诊断和修复脚本
sudo bash /data/Platform/scripts/diagnose_env_permissions.sh
```

脚本会自动：
1. 检查 .env 文件是否存在
2. 检查服务用户是否存在
3. 诊断权限问题
4. 自动修复权限
5. 验证修复结果

## 解决方案

### 方法1：使用诊断脚本（最简单，推荐）

```bash
# 运行诊断和修复脚本
sudo bash /data/Platform/scripts/diagnose_env_permissions.sh
```

### 方法2：手动设置正确的文件所有者和权限

```bash
# 1. 将 .env 文件的所有者设置为 www-data
sudo chown www-data:www-data /data/Platform/.env

# 2. 设置文件权限为 640（所有者可读写，组可读）
sudo chmod 640 /data/Platform/.env

# 3. 验证权限
ls -la /data/Platform/.env
# 应该显示：-rw-r----- 1 www-data www-data ... .env
```

### 方法3：设置权限为 644（不推荐，安全性较低）

如果方法1不工作，可以尝试：

```bash
# 设置文件权限为 644（所有用户可读，但只有所有者可写）
sudo chmod 644 /data/Platform/.env

# 注意：这种方法安全性较低，因为所有用户都可以读取敏感信息
```

### 方法4：使用 600 权限但确保所有者正确

```bash
# 1. 确保文件所有者是 www-data
sudo chown www-data:www-data /data/Platform/.env

# 2. 设置权限为 600（仅所有者可读写）
sudo chmod 600 /data/Platform/.env

# 3. 验证权限
ls -la /data/Platform/.env
# 应该显示：-rw------- 1 www-data www-data ... .env
```

## 代码层面的修复

**注意**：代码已经更新，即使无法读取 .env 文件，应用也会继续运行（因为 systemd 已经通过 `EnvironmentFile` 加载了环境变量）。但为了最佳实践，仍然建议修复文件权限。

## 验证修复

修复后，重启服务并检查状态：

```bash
# 重启服务
sudo systemctl restart Platform-backend.service

# 检查服务状态
sudo systemctl status Platform-backend.service

# 查看日志
sudo journalctl -u Platform-backend.service -f
```

## 预防措施

在创建 `.env` 文件时，应该：

```bash
# 1. 创建文件后立即设置正确的所有者和权限
sudo cp env.example /data/Platform/.env
sudo chown www-data:www-data /data/Platform/.env
sudo chmod 640 /data/Platform/.env

# 2. 编辑文件（使用 sudo）
sudo nano /data/Platform/.env
# 或
sudo vim /data/Platform/.env
```

## 权限说明

- **600**: 仅所有者可读写（最安全，但需要确保所有者是 www-data）
- **640**: 所有者可读写，组可读（推荐，如果 www-data 组有权限）
- **644**: 所有者可读写，所有用户可读（不推荐，安全性低）

## 常见问题

### Q: 为什么不能使用 600 权限？

A: 如果 `.env` 文件的所有者不是 `www-data`，那么即使权限是 600，`www-data` 用户也无法读取。解决方法：
1. 将文件所有者改为 `www-data`：`sudo chown www-data:www-data /data/Platform/.env`
2. 或者使用 640 权限，并确保 `www-data` 在文件所属组中

### Q: 如何检查当前权限？

```bash
# 查看文件详细信息
ls -la /data/Platform/.env

# 查看当前用户
whoami

# 查看 www-data 用户信息
id www-data
```

### Q: 如果修改权限后仍然无法读取？

1. 检查 SELinux 或 AppArmor 是否阻止访问
2. 检查文件系统挂载选项（某些文件系统可能限制权限）
3. 检查 systemd 服务的 `ReadWritePaths` 配置

