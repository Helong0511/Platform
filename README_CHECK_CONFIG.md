# 配置文件检查工具

## 简介

`scripts/check_config.py` 是一个用于检查项目配置文件的 Python 工具，可以帮助您验证生产环境配置是否正确设置。

## 功能特性

- ✅ 检查 .env 文件是否存在和有效
- ✅ 验证环境变量配置
- ✅ 检查安全配置（SECRET_KEY、密码等）
- ✅ 验证数据库配置和连接
- ✅ 检查 Redis 配置和连接
- ✅ 验证 CORS 配置
- ✅ 检查管理员账户配置
- ✅ 验证 JWT 配置
- ✅ 检查时区配置
- ✅ 验证文件权限
- ✅ 检查目录结构
- ✅ 检查关键依赖

## 使用方法

### 基本使用

```bash
# 在项目根目录运行
python scripts/check_config.py

# 或使用 python3
python3 scripts/check_config.py
```

### 在虚拟环境中运行

```bash
# 激活虚拟环境
source venv/bin/activate

# 运行检查
python scripts/check_config.py
```

### 在 Ubuntu 服务器上运行

```bash
# 使用项目虚拟环境
/data/Platform/venv/bin/python /data/Platform/scripts/check_config.py

# 或切换到项目目录
cd /data/Platform
source venv/bin/activate
python scripts/check_config.py
```

## 检查项目

### 1. .env 文件检查
- 检查文件是否存在
- 检查文件是否为空
- 检查文件大小

### 2. 环境配置
- 验证 `PRODUCTION_ENV` 设置是否正确

### 3. 安全配置
- 检查 `SECRET_KEY` 是否设置
- 验证 `SECRET_KEY` 长度（生产环境至少32字符）
- 检查是否使用默认值

### 4. 数据库配置
- 解析数据库 URL
- 验证主机、端口、数据库名、用户名、密码
- 测试数据库连接（如果可能）
- 检查是否使用默认密码

### 5. Redis 配置
- 检查 Redis 配置是否存在
- 测试 Redis 连接（如果可能）

### 6. CORS 配置
- 检查是否配置 CORS
- 验证生产环境是否包含 localhost
- 检查是否使用 HTTPS

### 7. 管理员账户配置
- 检查管理员用户名和密码
- 验证密码长度（生产环境至少12字符）
- 检查是否使用默认密码

### 8. JWT 配置
- 检查访问令牌过期时间
- 验证 JWT 算法
- 检查 RSA 密钥配置（如果使用 RS256）

### 9. 时区配置
- 验证时区字符串是否有效
- 检查系统时区与应用时区是否一致

### 10. 文件权限
- 检查 .env 文件权限（建议 640）
- 检查日志目录权限

### 11. 目录结构
- 检查必需的目录是否存在
- 检查关键文件是否存在

### 12. 依赖检查
- 检查 Python 版本（需要 3.10+）
- 验证关键 Python 包是否安装

## 输出说明

### 颜色编码
- 🟢 **绿色 (✓)**: 检查通过
- 🔴 **红色 (✗)**: 错误，必须修复
- 🟡 **黄色 (⚠)**: 警告，建议修复
- 🔵 **蓝色 (ℹ)**: 信息提示

### 退出码
- `0`: 所有检查通过（可能有警告）
- `1`: 发现错误，需要修复
- `130`: 用户中断（Ctrl+C）

## 示例输出

```
============================================================
项目配置文件检查工具
============================================================

ℹ 项目路径: /data/Platform
ℹ 环境类型: 生产环境
ℹ .env 文件: /data/Platform/.env

============================================================
1. 检查 .env 文件
============================================================

✓ .env 文件存在
✓ .env 文件大小: 1234 字节

============================================================
2. 检查环境配置
============================================================

✓ PRODUCTION_ENV=production

...

============================================================
检查总结
============================================================

✓ 所有检查通过！配置正确。
```

## 常见问题

### Q: 如何修复 "SECRET_KEY 未设置" 错误？

A: 在 `.env` 文件中设置 `SECRET_KEY`，至少32个字符：
```bash
SECRET_KEY=your_very_long_and_secure_secret_key_here_at_least_32_characters
```

### Q: 如何修复 "数据库连接失败" 警告？

A: 
1. 检查数据库服务是否运行：`sudo systemctl status mysql`
2. 验证 `.env` 中的 `DATABASE_URL` 是否正确
3. 测试数据库连接：`mysql -u username -p -h host database`

### Q: 如何修复 "CORS 配置包含 localhost" 错误？

A: 在生产环境的 `.env` 中，`BACKEND_CORS_ORIGINS` 不能包含 localhost：
```bash
# 错误
BACKEND_CORS_ORIGINS=https://localhost,https://your-domain.com

# 正确
BACKEND_CORS_ORIGINS=https://your-domain.com,https://www.your-domain.com
```

### Q: 如何修复文件权限警告？

A: 设置正确的文件权限：
```bash
# .env 文件
sudo chmod 640 /data/Platform/.env
sudo chown www-data:www-data /data/Platform/.env

# 日志目录
sudo chmod 750 /data/Platform/logs
sudo chown www-data:www-data /data/Platform/logs
```

## 集成到部署流程

### 在部署脚本中使用

```bash
#!/bin/bash
# 部署前检查配置
python scripts/check_config.py
if [ $? -ne 0 ]; then
    echo "配置检查失败，请修复错误后重试"
    exit 1
fi
```

### 在 CI/CD 中使用

```yaml
# GitHub Actions 示例
- name: Check Configuration
  run: |
    python scripts/check_config.py
```

## 注意事项

1. **生产环境检查**: 工具会根据 `PRODUCTION_ENV` 环境变量自动调整检查严格程度
2. **数据库连接测试**: 如果数据库服务未运行，连接测试会失败，但不会阻止其他检查
3. **Redis 连接测试**: Redis 是可选的，未配置不会报错，只会显示警告
4. **权限检查**: 在某些系统上可能无法准确检测文件权限

## 更新日志

- v1.0.0: 初始版本，包含所有基本检查功能

