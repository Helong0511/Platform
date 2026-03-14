# 🔧 测试 vs 生产环境配置对比

**更新日期：** 2026-03-14  
**版本：** v2.0（统一脚本）

---

## 🚀 使用统一脚本部署

**脚本：** `scripts/deploy.sh`

**用法：**
```bash
# 测试环境
./deploy.sh -e test

# 生产环境
./deploy.sh -e production
```

**详细说明请参考：** `DEPLOYMENT_GUIDE.md`

---

## 📋 快速配置参考

### 测试环境配置

**复制以下内容到 `.env` 文件：**

```bash
# 环境配置
PRODUCTION_ENV=development
ENV_NAME=test

# 安全配置
SECRET_KEY=NeofZ7iF8tNW6GzkyMZfsGmitY6r6Gwn6D5BU433Vu9lkFwciS2PApBkPMurQuexc9ZgWUjxQA6ZBHMx_bdvHQ

# 数据库配置（MySQL 8.0 - 测试）
DATABASE_URL=mysql+aiomysql://platform_user_test:CPL_DB_2026!@localhost:3306/ad_platform_test

# Redis 配置（测试）
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=CPL_Redis_2026!

# CORS（测试）
BACKEND_CORS_ORIGINS=http://159.138.133.34,http://localhost:3310

# Telegram Bot（测试）
TELEGRAM_ENABLE=true
TELEGRAM_TOKEN=8263751942:AAEEBJfiwd4mdwWVNuAB3iTm4ThHo2Bxwvw
TELEGRAM_ADMIN=5312177749

# 调试配置（测试环境开启）
DEBUG=true
LOG_LEVEL=DEBUG
ALLOWED_HOSTS=*

# 性能配置（测试环境）
WORKERS=2
API_RATE_LIMIT=200
LOGIN_RATE_LIMIT=20
```

---

### 生产环境配置

**复制以下内容到 `.env` 文件：**

```bash
# 环境配置
PRODUCTION_ENV=production
ENV_NAME=production

# 安全配置（生产环境使用强密钥）
SECRET_KEY=<使用 python -c "import secrets; print(secrets.token_urlsafe(64))" 生成>

# 数据库配置（MySQL 8.0 - 生产）
DATABASE_URL=mysql+aiomysql://platform_user_prod:CPL_Production_DB_2026!@#Abc@localhost:3306/ad_platform_prod

# Redis 配置（生产）
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=CPL_Production_Redis_2026!@#

# CORS（生产 - HTTPS）
BACKEND_CORS_ORIGINS=https://client.btfrx.online,https://btfrx.online

# Telegram Bot（生产）
TELEGRAM_ENABLE=true
TELEGRAM_TOKEN=8348688058:AAE0CXsgR4iNjzvcPjHOICQp8e3WSKJ5OtQ
TELEGRAM_ADMIN=5312177749

# 调试配置（生产环境必须关闭）
DEBUG=false
LOG_LEVEL=WARNING
ALLOWED_HOSTS=client.btfrx.online,btfrx.online

# 性能配置（生产环境）
WORKERS=8
API_RATE_LIMIT=100
LOGIN_RATE_LIMIT=10
```

---

## 📊 完整配置对比表

| 配置项 | 测试环境 | 生产环境 | 说明 |
|--------|---------|---------|------|
| **PRODUCTION_ENV** | development | production | 环境类型 |
| **ENV_NAME** | test | production | 环境名称 |
| **SECRET_KEY** | 固定密钥 | 随机强密钥 | 生产环境必须随机 |
| **DATABASE_URL** | ad_platform_test | ad_platform_prod | 数据库名 |
| **MYSQL_USER** | platform_user_test | platform_user_prod | 数据库用户 |
| **REDIS_PASSWORD** | CPL_Redis_2026! | CPL_Production_Redis_2026!@# | Redis 密码 |
| **TELEGRAM_TOKEN** | 8263751942:xxx | 8348688058:xxx | Bot Token |
| **DEBUG** | true | false | 生产必须关闭 |
| **LOG_LEVEL** | DEBUG | WARNING | 生产减少日志 |
| **ALLOWED_HOSTS** | * | client.btfrx.online | 生产限制域名 |
| **WORKERS** | 2 | 8 | 生产更多进程 |
| **API_RATE_LIMIT** | 200 | 100 | 生产严格限流 |
| **CORS** | HTTP | HTTPS | 生产强制 HTTPS |
| **CSRF_PROTECTION** | false | true | 生产启用 |
| **自动备份** | ❌ | ✅ | 生产自动备份 |

---

## 🎯 部署脚本自动配置

### 测试环境自动配置

运行 `./deploy.sh -e test` 后自动配置：

```bash
✅ 服务器 IP: 159.138.133.34
✅ 数据库：ad_platform_test
✅ Redis 密码：CPL_Redis_2026!
✅ Telegram Bot: 测试 Bot
✅ WORKERS: 2
✅ DEBUG: true
✅ LOG_LEVEL: DEBUG
```

---

### 生产环境自动配置

运行 `./deploy.sh -e production` 后自动配置：

```bash
✅ 服务器 IP: 43.156.101.243
✅ 数据库：ad_platform_prod
✅ Redis 密码：强随机密码
✅ Telegram Bot: 生产 Bot
✅ WORKERS: 8
✅ DEBUG: false
✅ LOG_LEVEL: WARNING
✅ 自动备份：✅
✅ SECRET_KEY: 随机强密钥
```

---

## ⚠️ 重要提醒

### 测试环境

- ✅ 可以随意修改配置
- ✅ 可以重置数据库
- ✅ 可以开启 Debug
- ✅ 不影响用户

### 生产环境

- ⚠️ **严禁随意修改**
- ⚠️ **必须关闭 Debug**
- ⚠️ **必须使用强密钥**
- ⚠️ **修改前必须备份**
- ⚠️ **影响真实用户**

---

## 🔄 手动切换环境

### 从测试切换到生产

```bash
# 1. 备份当前配置
cp .env .env.test.backup

# 2. 修改配置
vim .env

# 3. 修改关键配置：
# PRODUCTION_ENV=production
# DEBUG=false
# SECRET_KEY=<强密钥>
# DATABASE_URL=<生产数据库>
# TELEGRAM_TOKEN=<生产 Bot>

# 4. 重启服务
systemctl restart platform-backend
```

---

### 从生产切换到测试

```bash
# 1. 备份当前配置
cp .env .env.production.backup

# 2. 修改配置
vim .env

# 3. 修改关键配置：
# PRODUCTION_ENV=development
# DEBUG=true
# DATABASE_URL=<测试数据库>
# TELEGRAM_TOKEN=<测试 Bot>

# 4. 重启服务
systemctl restart platform-backend
```

---

## 📖 相关文档

- `DEPLOYMENT_GUIDE.md` - 完整部署指南
- `QUICK_DEPLOY.md` - 快速部署参考
- `scripts/deploy.sh` - 统一部署脚本
- `.env` - 环境配置文件

---

_文档创建时间：2026-03-14_  
_版本：v2.0_  
_创建人：钳钳 🦀_
