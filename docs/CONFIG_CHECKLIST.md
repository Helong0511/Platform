# 生产环境配置检查清单

本文档用于检查生产环境配置是否完整和正确。

## 快速检查

使用以下命令快速生成 SECRET_KEY：

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

## 必填配置项检查

### ✅ 环境配置
- [ ] `PRODUCTION_ENV` 设置为 `production` 或 `prod`

### ✅ 安全配置
- [ ] `SECRET_KEY` 已设置，长度至少32个字符
- [ ] `SECRET_KEY` 不是默认值或示例值
- [ ] `SECRET_KEY` 已安全保存（不要泄露）

### ✅ 数据库配置
- [ ] `DATABASE_URL` 已设置
- [ ] 数据库密码不是默认密码（`He800407` 或 `admin123`）
- [ ] 数据库连接信息正确（主机、端口、数据库名）
- [ ] 数据库用户有足够的权限

### ✅ CORS配置
- [ ] `BACKEND_CORS_ORIGINS` 已设置
- [ ] 所有域名使用 HTTPS（生产环境）
- [ ] 不包含 `localhost` 或 `127.0.0.1`

### ✅ 管理员账户配置
- [ ] `FIRST_SUPERUSER` 已设置（建议不使用默认值 `admin`）
- [ ] `FIRST_SUPERUSER_PASSWORD` 已设置
- [ ] 密码长度至少12个字符
- [ ] 密码不是默认值 `admin123`
- [ ] 密码包含大小写字母、数字、特殊字符（推荐）

### ✅ Telegram Bot配置（如果启用）
- [ ] `TELEGRAM_ENABLE` 已设置（`true` 或 `false`）
- [ ] 如果启用：`TELEGRAM_TOKEN` 已设置
- [ ] 如果启用：`TELEGRAM_ADMIN` 已设置

## 推荐配置项检查

### 📋 性能配置
- [ ] `DB_POOL_SIZE` 根据服务器性能调整（默认15）
- [ ] `DB_MAX_OVERFLOW` 根据服务器性能调整（默认10）
- [ ] `API_RATE_LIMIT` 根据业务需求调整（默认100）
- [ ] `WORKERS` 根据CPU核心数调整（可选，会自动计算）

### 📋 安全配置
- [ ] `ENABLE_CSRF` 已启用（默认 `true`）
- [ ] `LOGIN_RATE_LIMIT` 已设置（默认5，防止暴力破解）
- [ ] `ACCESS_TOKEN_EXPIRE_MINUTES` 根据安全需求调整（默认240分钟）

### 📋 日志配置
- [ ] `LOG_LEVEL` 设置为 `INFO` 或 `WARNING`（生产环境）
- [ ] `LOG_FILE` 路径正确且可写
- [ ] `AUDIT_LOG_RETENTION_DAYS` 根据需求调整（默认90天）

## 配置验证

### 1. 检查配置文件格式
```bash
# 检查 .env 文件是否存在
ls -la .env

# 检查文件权限（应该是 600）
chmod 600 .env
```

### 2. 验证配置加载
```bash
# 启动应用，检查配置是否正确加载
# 查看日志中是否有配置错误或警告
tail -f logs/app.log
```

### 3. 测试数据库连接
```bash
# 在应用启动后，检查数据库连接是否正常
# 查看日志中是否有数据库连接错误
```

### 4. 测试Redis连接（如果使用）
```bash
# 检查Redis是否可访问
redis-cli ping
```

## 常见问题

### 问题1：SECRET_KEY 长度不足
**错误信息**：`生产环境SECRET_KEY长度必须至少32个字符`

**解决方法**：
```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```
将生成的密钥设置到 `SECRET_KEY` 环境变量。

### 问题2：CORS配置包含localhost
**错误信息**：`生产环境CORS配置不能包含localhost`

**解决方法**：
- 移除 `BACKEND_CORS_ORIGINS` 中的 `localhost` 和 `127.0.0.1`
- 使用实际的域名，且必须使用 HTTPS

### 问题3：数据库密码使用默认值
**错误信息**：`生产环境数据库密码不能使用默认值`

**解决方法**：
- 修改数据库密码为强密码
- 更新 `DATABASE_URL` 中的密码

### 问题4：管理员密码不符合要求
**错误信息**：`生产环境管理员密码必须至少12个字符`

**解决方法**：
- 设置 `FIRST_SUPERUSER_PASSWORD` 为至少12个字符的强密码
- 建议包含大小写字母、数字、特殊字符

## 安全建议

1. **定期更换密钥**：建议每3-6个月更换一次 `SECRET_KEY`
2. **使用强密码**：所有密码应包含大小写字母、数字、特殊字符
3. **限制访问**：确保 `.env` 文件权限为 `600`，只有所有者可读
4. **不要提交到Git**：确保 `.env` 在 `.gitignore` 中
5. **使用密钥管理工具**：生产环境建议使用 Vault、AWS Secrets Manager 等工具管理敏感配置

## 配置示例

### 最小化生产配置（必填项）
```bash
PRODUCTION_ENV=production
SECRET_KEY=<64字符随机字符串>
DATABASE_URL=mysql+aiomysql://user:password@host:3306/database
BACKEND_CORS_ORIGINS=https://your-domain.com
FIRST_SUPERUSER=admin
FIRST_SUPERUSER_PASSWORD=<至少12字符强密码>
```

### 完整生产配置（推荐）
参考 `env.example` 文件，设置所有配置项。

## 配置验证脚本

可以创建一个简单的验证脚本来检查配置：

```python
#!/usr/bin/env python3
"""配置验证脚本"""
import os
from dotenv import load_dotenv

load_dotenv()

def check_required(key, description):
    value = os.getenv(key)
    if not value:
        print(f"❌ {key}: {description} - 未设置")
        return False
    print(f"✅ {key}: 已设置")
    return True

def check_production():
    env = os.getenv("PRODUCTION_ENV", "").lower()
    if env not in ["production", "prod"]:
        print("❌ PRODUCTION_ENV: 不是生产环境")
        return False
    print("✅ PRODUCTION_ENV: 生产环境")
    return True

# 检查必填项
print("=== 检查必填配置项 ===")
check_production()
check_required("SECRET_KEY", "JWT签名密钥")
check_required("DATABASE_URL", "数据库连接URI")
check_required("BACKEND_CORS_ORIGINS", "CORS允许来源")
check_required("FIRST_SUPERUSER", "管理员用户名")
check_required("FIRST_SUPERUSER_PASSWORD", "管理员密码")

print("\n=== 检查配置值 ===")
secret_key = os.getenv("SECRET_KEY", "")
if len(secret_key) < 32:
    print(f"❌ SECRET_KEY: 长度不足32字符（当前: {len(secret_key)}）")
else:
    print(f"✅ SECRET_KEY: 长度符合要求（{len(secret_key)}字符）")

password = os.getenv("FIRST_SUPERUSER_PASSWORD", "")
if len(password) < 12:
    print(f"❌ FIRST_SUPERUSER_PASSWORD: 长度不足12字符（当前: {len(password)}）")
elif password == "admin123":
    print("❌ FIRST_SUPERUSER_PASSWORD: 不能使用默认密码")
else:
    print(f"✅ FIRST_SUPERUSER_PASSWORD: 长度符合要求（{len(password)}字符）")

cors = os.getenv("BACKEND_CORS_ORIGINS", "")
if "localhost" in cors.lower() or "127.0.0.1" in cors.lower():
    print("❌ BACKEND_CORS_ORIGINS: 包含 localhost 或 127.0.0.1")
else:
    print("✅ BACKEND_CORS_ORIGINS: 不包含 localhost")

print("\n配置检查完成！")
```

