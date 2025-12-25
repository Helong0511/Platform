# JWT 配置详细指南

## 目录
1. [JWT 概述](#jwt-概述)
2. [算法选择](#算法选择)
3. [配置参数说明](#配置参数说明)
4. [配置方法](#配置方法)
5. [生产环境配置](#生产环境配置)
6. [测试环境配置](#测试环境配置)
7. [配置验证](#配置验证)
8. [常见问题](#常见问题)

---

## JWT 概述

JWT (JSON Web Token) 用于用户身份验证和授权。本项目支持两种算法：
- **RS256**: 非对称加密算法（推荐用于生产环境）
- **HS256**: 对称加密算法（适合开发环境）

---

## 算法选择

### RS256（推荐用于生产环境）

**优点：**
- ✅ 更安全：使用公钥/私钥对，私钥不会泄露
- ✅ 可扩展：公钥可以安全地分发给多个服务
- ✅ 符合 OAuth 2.0 和 OpenID Connect 标准
- ✅ 支持密钥轮换

**缺点：**
- ⚠️ 需要管理 RSA 密钥对
- ⚠️ 性能略低于 HS256（但影响很小）

**适用场景：**
- 生产环境
- 多服务架构
- 需要密钥轮换的场景

### HS256（适合开发环境）

**优点：**
- ✅ 配置简单：只需要一个 SECRET_KEY
- ✅ 性能略好
- ✅ 适合单服务应用

**缺点：**
- ⚠️ 安全性较低：所有服务需要共享同一个密钥
- ⚠️ 密钥泄露风险高
- ⚠️ 不支持密钥轮换

**适用场景：**
- 开发/测试环境
- 单服务应用
- 快速原型开发

---

## 配置参数说明

### 1. JWT 算法配置

```bash
# JWT 算法：RS256 或 HS256
# 默认值：RS256
JWT_ALGORITHM=RS256
```

**参数说明：**
- `RS256`: 使用 RSA 非对称加密（推荐）
- `HS256`: 使用 HMAC 对称加密

### 2. 访问令牌过期时间

```bash
# 访问令牌过期时间（分钟）
# 默认值：240 分钟（4小时）
ACCESS_TOKEN_EXPIRE_MINUTES=240
```

**建议值：**
- **开发环境**: 60-120 分钟
- **生产环境**: 60-240 分钟（根据安全需求调整）
- **高安全要求**: 30-60 分钟

### 3. RSA 密钥配置（仅 RS256 算法需要）

#### 方法1：使用文件路径（推荐）

```bash
# RSA 私钥文件路径
RSA_PRIVATE_KEY_PATH=/data/Platform/keys/private_key.pem

# RSA 公钥文件路径
RSA_PUBLIC_KEY_PATH=/data/Platform/keys/public_key.pem
```

#### 方法2：使用环境变量（适合容器部署）

```bash
# RSA 私钥内容（PEM 格式，包含换行符）
RSA_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC...
-----END PRIVATE KEY-----"

# RSA 公钥内容（PEM 格式）
RSA_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...
-----END PUBLIC KEY-----"
```

**优先级：**
1. 环境变量中的密钥内容（`RSA_PRIVATE_KEY` / `RSA_PUBLIC_KEY`）
2. 文件路径（`RSA_PRIVATE_KEY_PATH` / `RSA_PUBLIC_KEY_PATH`）
3. 如果都未配置，系统会生成临时测试密钥（仅开发环境）

### 4. SECRET_KEY（HS256 算法或备用）

```bash
# JWT 签名密钥（HS256 算法使用，或作为备用）
# 生产环境必须设置，长度至少 32 个字符
# 建议使用 64 字符以上的随机字符串
SECRET_KEY=your_secret_key_here_at_least_32_characters_long
```

**生成方式：**
```bash
# Python 生成
python -c "import secrets; print(secrets.token_urlsafe(64))"

# 或使用 OpenSSL
openssl rand -hex 32
```

---

## 配置方法

### 步骤 1: 选择算法

在 `.env` 文件中设置：

```bash
# 生产环境推荐使用 RS256
JWT_ALGORITHM=RS256

# 或开发环境使用 HS256
JWT_ALGORITHM=HS256
```

### 步骤 2: 配置密钥

#### 如果使用 RS256 算法：

**选项 A: 使用自动生成脚本（最简单）**

```bash
# 生产环境（Ubuntu）
cd /data/Platform
python3 scripts/generate_rsa_keys.py --output-dir /data/Platform/keys

# 测试环境（Windows）
cd E:\data\Platform
python scripts/generate_rsa_keys.py --output-dir keys
```

**选项 B: 使用 OpenSSL 手动生成**

```bash
# 生成私钥（2048 位）
openssl genrsa -out private_key.pem 2048

# 从私钥生成公钥
openssl rsa -in private_key.pem -pubout -out public_key.pem
```

**选项 C: 使用 Python 生成**

```python
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

# 生成密钥对
private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
    backend=default_backend()
)

# 序列化私钥
private_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
)

# 序列化公钥
public_pem = private_key.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
)

# 保存到文件
with open('private_key.pem', 'wb') as f:
    f.write(private_pem)
with open('public_key.pem', 'wb') as f:
    f.write(public_pem)
```

#### 如果使用 HS256 算法：

```bash
# 生成 SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

### 步骤 3: 在 .env 文件中配置

#### RS256 配置示例（使用文件路径）

```bash
# JWT 算法
JWT_ALGORITHM=RS256

# 访问令牌过期时间（分钟）
ACCESS_TOKEN_EXPIRE_MINUTES=240

# RSA 密钥路径（生产环境使用绝对路径）
RSA_PRIVATE_KEY_PATH=/data/Platform/keys/private_key.pem
RSA_PUBLIC_KEY_PATH=/data/Platform/keys/public_key.pem
```

#### RS256 配置示例（使用环境变量）

```bash
# JWT 算法
JWT_ALGORITHM=RS256

# 访问令牌过期时间（分钟）
ACCESS_TOKEN_EXPIRE_MINUTES=240

# RSA 密钥内容（注意：需要包含完整的 PEM 格式，包括换行符）
RSA_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC...
（完整的私钥内容）
-----END PRIVATE KEY-----"

RSA_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...
（完整的公钥内容）
-----END PUBLIC KEY-----"
```

#### HS256 配置示例

```bash
# JWT 算法
JWT_ALGORITHM=HS256

# 访问令牌过期时间（分钟）
ACCESS_TOKEN_EXPIRE_MINUTES=120

# SECRET_KEY（至少 32 个字符）
SECRET_KEY=your_secret_key_here_at_least_32_characters_long_use_random_string
```

### 步骤 4: 设置文件权限（仅生产环境，RS256 使用文件路径时）

```bash
# Ubuntu 生产环境
sudo chown www-data:www-data /data/Platform/keys/private_key.pem
sudo chmod 600 /data/Platform/keys/private_key.pem
sudo chown www-data:www-data /data/Platform/keys/public_key.pem
sudo chmod 644 /data/Platform/keys/public_key.pem
```

---

## 生产环境配置

### Ubuntu 生产环境完整配置示例

```bash
# ==============================================================================
# JWT 配置
# ==============================================================================

# JWT 算法（推荐使用 RS256）
JWT_ALGORITHM=RS256

# 访问令牌过期时间（分钟）
# 生产环境建议：60-240 分钟
ACCESS_TOKEN_EXPIRE_MINUTES=240

# RSA 密钥路径（使用绝对路径）
RSA_PRIVATE_KEY_PATH=/data/Platform/keys/private_key.pem
RSA_PUBLIC_KEY_PATH=/data/Platform/keys/public_key.pem

# SECRET_KEY（备用，HS256 或系统其他用途）
SECRET_KEY=your_production_secret_key_at_least_64_characters_long
```

### 部署步骤

1. **生成 RSA 密钥对**
   ```bash
   cd /data/Platform
   python3 scripts/generate_rsa_keys.py --output-dir /data/Platform/keys
   ```

2. **配置 .env 文件**
   ```bash
   # 编辑 .env 文件
   nano /data/Platform/.env
   
   # 添加 JWT 配置
   JWT_ALGORITHM=RS256
   ACCESS_TOKEN_EXPIRE_MINUTES=240
   RSA_PRIVATE_KEY_PATH=/data/Platform/keys/private_key.pem
   RSA_PUBLIC_KEY_PATH=/data/Platform/keys/public_key.pem
   ```

3. **设置文件权限**
   ```bash
   # 密钥文件权限
   sudo chown www-data:www-data /data/Platform/keys/private_key.pem
   sudo chmod 600 /data/Platform/keys/private_key.pem
   sudo chown www-data:www-data /data/Platform/keys/public_key.pem
   sudo chmod 644 /data/Platform/keys/public_key.pem
   
   # .env 文件权限
   sudo chown www-data:www-data /data/Platform/.env
   sudo chmod 640 /data/Platform/.env
   ```

4. **验证配置**
   ```bash
   cd /data/Platform
   python3 scripts/check_config.py
   ```

5. **重启服务**
   ```bash
   sudo systemctl restart Platform-backend.service
   ```

---

## 测试环境配置

### Windows 测试环境完整配置示例

```bash
# ==============================================================================
# JWT 配置
# ==============================================================================

# JWT 算法（可以使用 HS256 简化配置，或 RS256 与生产环境保持一致）
JWT_ALGORITHM=RS256

# 访问令牌过期时间（分钟）
# 测试环境可以使用较长时间，方便调试
ACCESS_TOKEN_EXPIRE_MINUTES=240

# RSA 密钥路径（使用相对路径）
RSA_PRIVATE_KEY_PATH=keys/private_key.pem
RSA_PUBLIC_KEY_PATH=keys/public_key.pem

# 或使用绝对路径
# RSA_PRIVATE_KEY_PATH=E:\data\Platform\keys\private_key.pem
# RSA_PUBLIC_KEY_PATH=E:\data\Platform\keys\public_key.pem

# SECRET_KEY（备用）
SECRET_KEY=your_test_secret_key_at_least_32_characters_long
```

### 部署步骤

1. **生成 RSA 密钥对**
   ```bash
   cd E:\data\Platform
   python scripts/generate_rsa_keys.py --output-dir keys
   ```

2. **配置 .env 文件**
   ```bash
   # 编辑 .env 文件
   # 添加 JWT 配置
   JWT_ALGORITHM=RS256
   ACCESS_TOKEN_EXPIRE_MINUTES=240
   RSA_PRIVATE_KEY_PATH=keys/private_key.pem
   RSA_PUBLIC_KEY_PATH=keys/public_key.pem
   ```

3. **验证配置**
   ```bash
   cd E:\data\Platform
   python scripts/check_config.py
   ```

---

## 配置验证

### 方法 1: 使用配置检查工具

```bash
# 生产环境
cd /data/Platform
python3 scripts/check_config.py

# 测试环境
cd E:\data\Platform
python scripts/check_config.py
```

检查工具会验证：
- ✅ JWT 算法配置
- ✅ 访问令牌过期时间
- ✅ RSA 密钥配置（如果使用 RS256）
- ✅ 密钥文件是否存在
- ✅ 密钥文件权限（Linux）

### 方法 2: 测试 JWT 功能

1. **启动应用**
   ```bash
   # 生产环境
   sudo systemctl start Platform-backend.service
   
   # 测试环境
   python -m uvicorn app.main:app --reload
   ```

2. **测试登录**
   ```bash
   curl -X POST "http://localhost:8960/api/v1/auth/login" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "username=admin&password=your_password"
   ```

3. **验证返回的 Token**
   - 应该返回 `access_token` 字段
   - Token 格式：`eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...`（RS256）
   - 或 `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`（HS256）

### 方法 3: 手动验证 RSA 密钥

```bash
# 检查私钥格式
openssl rsa -in private_key.pem -text -noout

# 检查公钥格式
openssl rsa -in public_key.pem -pubin -text -noout

# 验证密钥对匹配
openssl rsa -in private_key.pem -pubout | diff - public_key.pem
# 如果输出为空，说明密钥匹配
```

---

## 常见问题

### Q1: RS256 算法但未配置 RSA 私钥/公钥

**问题：**
```
警告: RS256 算法但未配置 RSA 私钥
警告: RS256 算法但未配置 RSA 公钥
```

**解决方案：**

1. **生成密钥对**
   ```bash
   python scripts/generate_rsa_keys.py --output-dir keys
   ```

2. **在 .env 文件中配置**
   ```bash
   RSA_PRIVATE_KEY_PATH=keys/private_key.pem
   RSA_PUBLIC_KEY_PATH=keys/public_key.pem
   ```

3. **验证配置**
   ```bash
   python scripts/check_config.py
   ```

### Q2: 密钥文件找不到

**问题：**
```
错误: 加载RSA 私钥文件失败: [Errno 2] No such file or directory
```

**解决方案：**

1. **检查文件路径是否正确**
   ```bash
   # 检查文件是否存在
   ls -la /data/Platform/keys/private_key.pem
   ```

2. **检查路径配置**
   ```bash
   # 确保 .env 中的路径正确
   cat .env | grep RSA_PRIVATE_KEY_PATH
   ```

3. **使用绝对路径（推荐）**
   ```bash
   RSA_PRIVATE_KEY_PATH=/data/Platform/keys/private_key.pem
   ```

### Q3: 密钥文件权限错误

**问题：**
```
错误: 无法读取密钥文件：权限被拒绝
PermissionError: [Errno 13] Permission denied: '/data/Platform/keys/private_key.pem'
```

**解决方案：**

**方法1：使用自动修复脚本（推荐）**
```bash
cd /data/Platform
sudo bash scripts/fix_rsa_keys_permissions.sh
```

**方法2：手动修复权限**
```bash
# Ubuntu 生产环境
# 设置密钥目录权限
sudo chown -R www-data:www-data /data/Platform/keys
sudo chmod 750 /data/Platform/keys

# 设置私钥文件权限（仅所有者可读）
sudo chown www-data:www-data /data/Platform/keys/private_key.pem
sudo chmod 600 /data/Platform/keys/private_key.pem

# 设置公钥文件权限（所有人可读）
sudo chown www-data:www-data /data/Platform/keys/public_key.pem
sudo chmod 644 /data/Platform/keys/public_key.pem

# 验证权限
ls -la /data/Platform/keys/

# 测试 www-data 用户是否可以读取
sudo -u www-data test -r /data/Platform/keys/private_key.pem && echo "✓ 权限正确" || echo "✗ 权限错误"

# 重启服务
sudo systemctl restart Platform-backend.service
```

### Q4: JWT Token 验证失败

**可能原因：**
1. 密钥不匹配（RS256：公钥和私钥不匹配）
2. 算法配置不一致（创建和验证使用不同算法）
3. Token 已过期
4. SECRET_KEY 不匹配（HS256）

**解决方案：**

1. **检查算法配置**
   ```bash
   # 确保创建和验证使用相同的算法
   cat .env | grep JWT_ALGORITHM
   ```

2. **验证密钥匹配（RS256）**
   ```bash
   # 从私钥生成公钥，与现有公钥对比
   openssl rsa -in private_key.pem -pubout > public_key_new.pem
   diff public_key.pem public_key_new.pem
   ```

3. **检查 Token 过期时间**
   ```bash
   # 增加过期时间用于测试
   ACCESS_TOKEN_EXPIRE_MINUTES=1440  # 24小时
   ```

### Q5: 开发环境使用临时密钥

**问题：**
```
警告: 未配置RSA 私钥 密钥，生成临时测试密钥
```

**说明：**
- 这是正常行为（仅开发环境）
- 每次启动可能生成不同的密钥
- 生产环境必须配置固定密钥

**解决方案：**
按照本文档配置固定的 RSA 密钥对。

### Q6: 如何切换算法（RS256 ↔ HS256）

**从 RS256 切换到 HS256：**

1. **修改 .env 文件**
   ```bash
   JWT_ALGORITHM=HS256
   SECRET_KEY=your_secret_key_here
   ```

2. **重启服务**
   ```bash
   sudo systemctl restart Platform-backend.service
   ```

**从 HS256 切换到 RS256：**

1. **生成 RSA 密钥对**
   ```bash
   python scripts/generate_rsa_keys.py --output-dir keys
   ```

2. **修改 .env 文件**
   ```bash
   JWT_ALGORITHM=RS256
   RSA_PRIVATE_KEY_PATH=keys/private_key.pem
   RSA_PUBLIC_KEY_PATH=keys/public_key.pem
   ```

3. **重启服务**
   ```bash
   sudo systemctl restart Platform-backend.service
   ```

**注意：** 切换算法后，所有现有的 Token 将失效，用户需要重新登录。

---

## 安全建议

### 生产环境

1. ✅ **使用 RS256 算法**
2. ✅ **使用 2048 位或更大的 RSA 密钥**
3. ✅ **定期轮换密钥**（建议每 6-12 个月）
4. ✅ **保护私钥文件**（权限 600，仅所有者可读）
5. ✅ **不要将密钥提交到版本控制系统**
6. ✅ **使用强 SECRET_KEY**（至少 64 字符）
7. ✅ **设置合理的 Token 过期时间**（60-240 分钟）

### 测试环境

1. ✅ **可以使用 HS256 简化配置**
2. ✅ **或使用 RS256 与生产环境保持一致**
3. ✅ **使用相对路径便于迁移**
4. ⚠️ **不要使用生产环境的密钥**

---

## 相关文档

- [环境配置说明](./环境配置说明.md)
- [Ubuntu 路径配置参考](./Ubuntu路径配置参考.md)
- [配置检查工具说明](../README_CHECK_CONFIG.md)
- [RSA 密钥生成工具](../scripts/generate_rsa_keys.py)

---

## 快速参考

### 生产环境（Ubuntu）

```bash
# 1. 生成密钥
cd /data/Platform
python3 scripts/generate_rsa_keys.py --output-dir /data/Platform/keys

# 2. 配置 .env
JWT_ALGORITHM=RS256
ACCESS_TOKEN_EXPIRE_MINUTES=240
RSA_PRIVATE_KEY_PATH=/data/Platform/keys/private_key.pem
RSA_PUBLIC_KEY_PATH=/data/Platform/keys/public_key.pem

# 3. 设置权限
sudo chown www-data:www-data /data/Platform/keys/private_key.pem
sudo chmod 600 /data/Platform/keys/private_key.pem

# 4. 验证
python3 scripts/check_config.py
```

### 测试环境（Windows）

```bash
# 1. 生成密钥
cd E:\data\Platform
python scripts/generate_rsa_keys.py --output-dir keys

# 2. 配置 .env
JWT_ALGORITHM=RS256
ACCESS_TOKEN_EXPIRE_MINUTES=240
RSA_PRIVATE_KEY_PATH=keys/private_key.pem
RSA_PUBLIC_KEY_PATH=keys/public_key.pem

# 3. 验证
python scripts/check_config.py
```

