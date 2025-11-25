# 配置文件使用指南

本文档说明如何配置生产环境。

## 文件说明

- `env.example` - 配置文件模板，包含所有配置项的说明和示例
- `docs/CONFIG_CHECKLIST.md` - 配置检查清单，用于手动检查配置
- `scripts/check_config.py` - 配置验证脚本，自动检查配置是否正确

## 快速开始

### 1. 创建配置文件

```bash
# 复制模板文件
cp env.example .env

# 设置文件权限（仅所有者可读）
chmod 600 .env
```

### 2. 编辑配置文件

使用文本编辑器打开 `.env` 文件，根据实际情况修改配置项：

```bash
# 使用 vim 编辑
vim .env

# 或使用 nano 编辑
nano .env
```

### 3. 生成 SECRET_KEY

```bash
# 生成64字符的随机密钥
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

将生成的密钥复制到 `.env` 文件中的 `SECRET_KEY` 配置项。

### 4. 验证配置

```bash
# 运行配置验证脚本
python scripts/check_config.py
```

脚本会检查所有必填配置项，并给出详细的检查结果。

## 必填配置项

生产环境必须设置以下配置项：

1. **PRODUCTION_ENV** - 设置为 `production` 或 `prod`
2. **SECRET_KEY** - 至少32字符的随机字符串
3. **DATABASE_URL** - 数据库连接URI
4. **BACKEND_CORS_ORIGINS** - CORS允许的来源（使用HTTPS）
5. **FIRST_SUPERUSER** - 管理员用户名
6. **FIRST_SUPERUSER_PASSWORD** - 管理员密码（至少12字符）

## 配置项说明

### 环境配置

```bash
# 生产环境必须设置为 production 或 prod
PRODUCTION_ENV=production
```

### 安全配置

```bash
# JWT签名密钥，至少32字符，建议64字符
# 生成方式：python -c "import secrets; print(secrets.token_urlsafe(64))"
SECRET_KEY=your-64-character-random-string-here
```

### 数据库配置

```bash
# 格式：mysql+aiomysql://用户名:密码@主机:端口/数据库名
DATABASE_URL=mysql+aiomysql://root:your_password@localhost:3306/platform

# 数据库连接池配置（可选，有默认值）
DB_POOL_SIZE=15
DB_MAX_OVERFLOW=10
DB_POOL_RECYCLE=3600
```

### CORS配置

```bash
# 多个域名用逗号分隔，必须使用HTTPS
BACKEND_CORS_ORIGINS=https://example.com,https://www.example.com
```

**注意**：
- 生产环境不能包含 `localhost` 或 `127.0.0.1`
- 所有域名必须使用 HTTPS

### 管理员账户配置

```bash
# 管理员用户名
FIRST_SUPERUSER=admin

# 管理员密码（至少12字符，不能使用默认密码）
FIRST_SUPERUSER_PASSWORD=your-strong-password-here
```

**密码要求**：
- 长度至少12个字符
- 不能使用默认密码 `admin123`
- 建议包含大小写字母、数字、特殊字符

### Telegram Bot配置（可选）

```bash
# 是否启用 Telegram Bot
TELEGRAM_ENABLE=true

# Telegram Bot Token（从 BotFather 获取）
TELEGRAM_TOKEN=your_telegram_bot_token

# Telegram 管理员 Chat ID
TELEGRAM_ADMIN=your_telegram_chat_id
```

## 配置验证

### 使用验证脚本

```bash
# 运行配置验证脚本
python scripts/check_config.py
```

脚本会检查：
- ✅ 必填配置项是否已设置
- ✅ SECRET_KEY 长度是否符合要求
- ✅ 数据库配置是否正确
- ✅ CORS配置是否包含 localhost
- ✅ 管理员密码是否符合要求
- ✅ Telegram配置是否完整（如果启用）

### 手动检查

参考 `docs/CONFIG_CHECKLIST.md` 进行手动检查。

## 常见问题

### 1. SECRET_KEY 长度不足

**错误**：`SECRET_KEY长度必须至少32个字符`

**解决**：
```bash
# 生成新的密钥
python -c "import secrets; print(secrets.token_urlsafe(64))"
# 将生成的密钥设置到 SECRET_KEY
```

### 2. CORS配置包含 localhost

**错误**：`生产环境CORS配置不能包含localhost`

**解决**：
- 从 `BACKEND_CORS_ORIGINS` 中移除 `localhost` 和 `127.0.0.1`
- 使用实际的域名，且必须使用 HTTPS

### 3. 数据库密码使用默认值

**错误**：`生产环境数据库密码不能使用默认值`

**解决**：
- 修改数据库密码为强密码
- 更新 `DATABASE_URL` 中的密码

### 4. 管理员密码不符合要求

**错误**：`生产环境管理员密码必须至少12个字符`

**解决**：
- 设置 `FIRST_SUPERUSER_PASSWORD` 为至少12个字符的强密码
- 建议包含大小写字母、数字、特殊字符

## 安全建议

1. **定期更换密钥**：建议每3-6个月更换一次 `SECRET_KEY`
2. **使用强密码**：所有密码应包含大小写字母、数字、特殊字符
3. **限制文件权限**：确保 `.env` 文件权限为 `600`
   ```bash
   chmod 600 .env
   ```
4. **不要提交到Git**：确保 `.env` 在 `.gitignore` 中
5. **使用密钥管理工具**：生产环境建议使用 Vault、AWS Secrets Manager 等工具

## 配置示例

### 最小化配置（仅必填项）

```bash
PRODUCTION_ENV=production
SECRET_KEY=<64字符随机字符串>
DATABASE_URL=mysql+aiomysql://user:password@host:3306/database
BACKEND_CORS_ORIGINS=https://your-domain.com
FIRST_SUPERUSER=admin
FIRST_SUPERUSER_PASSWORD=<至少12字符强密码>
```

### 完整配置（推荐）

参考 `env.example` 文件，设置所有配置项以获得最佳性能和安全性。

## 相关文档

- [配置检查清单](CONFIG_CHECKLIST.md) - 详细的配置检查清单
- [env.example](../env.example) - 完整的配置文件模板

