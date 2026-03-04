# 自动环境配置生成脚本使用说明

## 脚本功能

`auto_generate_env_config.py` 是一个智能的环境配置生成脚本，具有以下功能：

1. **自动检测操作系统**
   - Windows → 推荐开发模式（development）
   - Ubuntu → 推荐生产模式（production）
   - 其他Linux → 推荐开发模式

2. **根据模式生成推荐配置值**
   - 自动生成强随机 SECRET_KEY
   - 根据环境类型设置合适的配置值
   - 生产环境：启用安全检查、使用RS256算法、启用Telegram等
   - 开发环境：关闭安全检查、使用HS256算法、关闭Telegram等

3. **Ubuntu系统自动设置文件权限**
   - 自动设置文件权限为 600（仅所有者可读写）
   - 如果以root权限运行，自动设置所有者为 www-data:www-data，权限为 640
   - 提供手动设置权限的提示

## 使用方法

### 方式1：自动检测（推荐）

```bash
# 自动检测系统并生成配置（交互式）
python scripts/auto_generate_env_config.py

# 非交互模式（直接使用系统推荐值）
python scripts/auto_generate_env_config.py --no-interactive
```

### 方式2：强制指定环境模式

```bash
# 强制使用生产模式
python scripts/auto_generate_env_config.py --env production

# 强制使用开发模式
python scripts/auto_generate_env_config.py --env development

# 强制使用测试模式
python scripts/auto_generate_env_config.py --env test
```

### 方式3：指定输出文件

```bash
# 输出到指定文件
python scripts/auto_generate_env_config.py --output .env.production

# 组合使用
python scripts/auto_generate_env_config.py --env production --output .env.prod --no-interactive
```

## 使用示例

### Windows系统（开发环境）

```bash
# 1. 运行脚本
python scripts/auto_generate_env_config.py

# 输出示例：
# 🔍 检测到操作系统: Windows (windows)
# 💡 系统推荐环境模式: DEVELOPMENT
# 
# 推荐环境模式: DEVELOPMENT
# 请选择环境模式：
#   1. development (开发模式)
#   2. production (生产模式)
#   3. test (测试模式)
#   默认: development (直接回车)
# 
# 请输入选项 (1/2/3) 或直接回车使用推荐值: [直接回车]
# 
# 📝 已选择环境模式: DEVELOPMENT
# 🚀 正在生成配置文件...
# ✅ 配置已生成: .env
#   环境类型: development
#   操作系统: windows
#   请根据实际情况修改配置项
# ℹ️  Windows系统：请确保 .env 文件不被共享
```

### Ubuntu系统（生产环境）

```bash
# 1. 运行脚本（需要root权限以设置文件所有者）
sudo python3 scripts/auto_generate_env_config.py

# 输出示例：
# 🔍 检测到操作系统: Ubuntu (ubuntu)
# 💡 系统推荐环境模式: PRODUCTION
# 
# 推荐环境模式: PRODUCTION
# 请选择环境模式：
#   1. development (开发模式)
#   2. production (生产模式)
#   3. test (测试模式)
#   默认: production (直接回车)
# 
# 请输入选项 (1/2/3) 或直接回车使用推荐值: [直接回车]
# 
# 📝 已选择环境模式: PRODUCTION
# 🚀 正在生成配置文件...
# ✅ 已设置文件权限: chmod 600 .env
# ✅ 已设置文件所有者和权限:
#    chown www-data:www-data .env
#    chmod 640 .env
# ✅ 配置已生成: .env
#   环境类型: production
#   操作系统: ubuntu
#   请根据实际情况修改配置项
```

### 非交互模式（适合自动化脚本）

```bash
# 直接使用系统推荐值，不询问
python scripts/auto_generate_env_config.py --no-interactive

# 或指定环境模式
python scripts/auto_generate_env_config.py --env production --no-interactive
```

## 配置说明

### 生产环境配置特点

- **JWT算法**: RS256（非对称加密，更安全）
- **RSA密钥路径**: `/data/Platform/keys/private_key.pem`（绝对路径）
- **访问令牌过期时间**: 240分钟（4小时）
- **CSRF防护**: 启用
- **日志级别**: INFO
- **Telegram通知**: 启用
- **API限流**: 100次/分钟
- **登录限流**: 5次/分钟
- **数据库连接池**: 15个连接
- **Redis连接数**: 30个

### 开发环境配置特点

- **JWT算法**: HS256（对称加密，配置简单）
- **RSA密钥路径**: `keys/private_key.pem`（相对路径）
- **访问令牌过期时间**: 120分钟（2小时）
- **CSRF防护**: 禁用（方便测试）
- **日志级别**: DEBUG（详细日志）
- **Telegram通知**: 禁用
- **API限流**: 1000次/分钟（宽松）
- **登录限流**: 100次/分钟（宽松）
- **数据库连接池**: 5个连接
- **Redis连接数**: 5个

### 测试环境配置特点

- **JWT算法**: HS256
- **访问令牌过期时间**: 30分钟
- **CSRF防护**: 禁用
- **日志级别**: DEBUG
- **Telegram通知**: 禁用（必须）
- **API限流**: 1000次/分钟
- **登录限流**: 100次/分钟
- **数据库连接池**: 3个连接
- **Redis数据库**: 15（独立测试数据库）

## 文件权限设置

### Windows系统

- 脚本会提示确保文件不被共享
- 无需特殊权限设置

### Ubuntu系统

脚本会自动处理文件权限：

1. **基本权限设置**（所有用户）
   - 自动设置文件权限为 600（仅所有者可读写）

2. **生产环境权限设置**（需要root权限）
   - 如果以root权限运行，会自动：
     - 设置所有者为 `www-data:www-data`
     - 设置权限为 640（所有者可读写，组可读）
   - 如果不是root权限，会提示手动执行：
     ```bash
     sudo chown www-data:www-data .env
     sudo chmod 640 .env
     ```

## 后续步骤

生成配置文件后，需要：

1. **检查配置文件**
   ```bash
   # 查看生成的配置
   cat .env
   ```

2. **修改必要配置项**
   - `DATABASE_URL`: 数据库连接信息
   - `SECRET_KEY`: 生产环境已自动生成，开发环境可保留或修改
   - `FIRST_SUPERUSER_PASSWORD`: 管理员密码（生产环境必须使用强密码）
   - `BACKEND_CORS_ORIGINS`: 跨域来源（生产环境必须设置，使用HTTPS）
   - `TELEGRAM_TOKEN` 和 `TELEGRAM_ADMIN`: 如果启用Telegram
   - `RSA_PRIVATE_KEY_PATH` 和 `RSA_PUBLIC_KEY_PATH`: 如果使用RS256算法，确保密钥文件存在

3. **生产环境检查清单**
   - [ ] `PRODUCTION_ENV=production`
   - [ ] `SECRET_KEY`（强随机密钥，至少32字符，已自动生成）
   - [ ] `DATABASE_URL`（生产数据库，强密码）
   - [ ] `BACKEND_CORS_ORIGINS`（不包含localhost，使用HTTPS）
   - [ ] `FIRST_SUPERUSER_PASSWORD`（至少12字符，不是admin123）
   - [ ] RSA密钥文件（如果使用RS256算法）
   - [ ] 文件权限已正确设置（Ubuntu系统）

4. **生成RSA密钥（如果使用RS256）**
   ```bash
   python scripts/generate_rsa_keys.py --output-dir keys
   # 或
   python scripts/generate_rsa_keys.py --output-dir /data/Platform/keys
   ```

## 常见问题

### Q: 如何在不交互的情况下生成配置？

A: 使用 `--no-interactive` 参数：
```bash
python scripts/auto_generate_env_config.py --no-interactive
```

### Q: Ubuntu系统如何设置文件所有者为www-data？

A: 有两种方式：
1. 以root权限运行脚本（推荐）：
   ```bash
   sudo python3 scripts/auto_generate_env_config.py
   ```

2. 手动设置：
   ```bash
   sudo chown www-data:www-data .env
   sudo chmod 640 .env
   ```

### Q: 生成的SECRET_KEY安全吗？

A: 是的，脚本使用Python的 `secrets.token_urlsafe(64)` 生成强随机密钥，每次运行都会生成不同的密钥。

### Q: 可以修改生成的配置吗？

A: 可以，生成后可以手动编辑 `.env` 文件，修改任何配置项。

### Q: 如何为不同环境生成不同的配置文件？

A: 使用 `--output` 参数指定不同的文件名：
```bash
# 开发环境
python scripts/auto_generate_env_config.py --env dev --output .env.dev

# 生产环境
python scripts/auto_generate_env_config.py --env prod --output .env.prod

# 测试环境
python scripts/auto_generate_env_config.py --env test --output .env.test
```

## 与原有脚本的区别

原有的 `generate_env_config.py` 脚本需要手动指定环境类型，而 `auto_generate_env_config.py` 具有以下优势：

1. **自动检测系统**：根据操作系统自动推荐环境模式
2. **交互式选择**：可以交互式选择或确认环境模式
3. **自动权限设置**：Ubuntu系统自动设置文件权限
4. **更智能的路径处理**：根据操作系统自动调整路径格式

两个脚本可以共存，根据需求选择使用。
