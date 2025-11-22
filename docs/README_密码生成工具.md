# 密码生成工具使用说明

## 概述

项目提供了两个密码生成工具：
1. **`scripts/generate_password.py`** - 独立的密码生成工具
2. **`scripts/generate_env.py`** - 配置文件生成工具（已集成自动密码生成）

## 快速开始

### 方式1：使用独立的密码生成工具

```bash
# 生成默认密码（16字符）
python scripts/generate_password.py

# 生成MySQL密码
python scripts/generate_password.py --type mysql

# 生成Redis密码
python scripts/generate_password.py --type redis

# 生成管理员密码
python scripts/generate_password.py --type admin

# 生成SECRET_KEY
python scripts/generate_password.py --type secret_key
```

### 方式2：使用配置文件生成工具（自动生成所有密码）

```bash
# 运行配置文件生成工具
python scripts/generate_env.py

# 当提示"是否自动生成所有密码？"时，输入 Y（或直接回车）
# 工具会自动生成：
# - SECRET_KEY（64字符）
# - MySQL 根密码（16字符）
# - MySQL 应用用户密码（16字符）
# - Redis 密码（16字符）
# - 管理员密码（16字符）
```

## 详细用法

### 生成单个密码

```bash
# 生成16字符的密码（默认）
python scripts/generate_password.py

# 生成32字符的密码
python scripts/generate_password.py --length 32

# 生成仅包含字母和数字的密码
python scripts/generate_password.py --no-special

# 生成包含相似字符的密码
python scripts/generate_password.py --include-similar
```

### 批量生成密码

```bash
# 生成5个密码
python scripts/generate_password.py --count 5

# 生成10个32字符的密码
python scripts/generate_password.py --length 32 --count 10
```

### 使用预设配置

```bash
# MySQL 密码（16字符，包含大小写字母、数字和特殊字符）
python scripts/generate_password.py --type mysql

# Redis 密码（16字符）
python scripts/generate_password.py --type redis

# 管理员密码（16字符）
python scripts/generate_password.py --type admin

# SECRET_KEY（64字符，URL安全）
python scripts/generate_password.py --type secret_key
```

### 复制到剪贴板

```bash
# 生成密码并复制到剪贴板（需要安装 pyperclip）
python scripts/generate_password.py --copy

# 安装 pyperclip：pip install pyperclip
```

## 密码特性

### 默认密码特性

- **长度**：16字符（可自定义）
- **字符集**：
  - 大写字母（A-Z，排除 O、I）
  - 小写字母（a-z，排除 l、i）
  - 数字（0-9，排除 0）
  - 特殊字符（!@#$%^&*()_+-=[]{}|;:,.<>?）
- **安全性**：
  - 使用 `secrets` 模块（加密安全的随机数生成器）
  - 确保包含每种类型的字符
  - 排除相似字符（0、O、l、I）避免混淆
  - 随机打乱字符顺序

### SECRET_KEY 特性

- **长度**：64字节（实际字符数约86字符）
- **格式**：URL安全的Base64编码
- **用途**：JWT签名密钥、加密密钥等
- **生成方式**：`secrets.token_urlsafe(64)`

## 命令行参数

### 基本参数

| 参数 | 简写 | 说明 | 默认值 |
|------|------|------|--------|
| `--length` | `-l` | 密码长度 | 16 |
| `--count` | `-c` | 生成密码数量 | 1 |
| `--type` | `-t` | 预设类型（mysql/redis/admin/secret_key） | - |

### 字符集控制

| 参数 | 说明 |
|------|------|
| `--no-uppercase` | 不包含大写字母 |
| `--no-lowercase` | 不包含小写字母 |
| `--no-digits` | 不包含数字 |
| `--no-special` | 不包含特殊字符 |
| `--include-similar` | 包含相似字符（0、O、l、I） |

### 其他参数

| 参数 | 说明 |
|------|------|
| `--copy` | 复制第一个密码到剪贴板 |

## 使用示例

### 示例1：生成生产环境所需的所有密码

```bash
# 1. 生成 SECRET_KEY
python scripts/generate_password.py --type secret_key

# 2. 生成 MySQL 根密码
python scripts/generate_password.py --type mysql

# 3. 生成 MySQL 应用用户密码
python scripts/generate_password.py --type mysql

# 4. 生成 Redis 密码
python scripts/generate_password.py --type redis

# 5. 生成管理员密码
python scripts/generate_password.py --type admin
```

### 示例2：批量生成密码用于测试

```bash
# 生成10个测试密码
python scripts/generate_password.py --count 10 --length 12
```

### 示例3：生成特定格式的密码

```bash
# 生成仅包含字母和数字的密码（某些系统不支持特殊字符）
python scripts/generate_password.py --no-special --length 20

# 生成超长密码
python scripts/generate_password.py --length 64
```

## 安全建议

1. **密码长度**：
   - 数据库密码：至少16字符
   - 管理员密码：至少12字符
   - SECRET_KEY：64字符（推荐）

2. **密码复杂度**：
   - 包含大小写字母、数字和特殊字符
   - 避免使用字典词汇
   - 避免使用个人信息

3. **密码管理**：
   - 使用密码管理器存储密码
   - 不要将密码存储在代码或配置文件中（除非加密）
   - 定期轮换密码（建议每3-6个月）

4. **密码存储**：
   - 生产环境密码应存储在密钥管理服务中
   - 不要将密码提交到版本控制系统
   - 使用环境变量或加密配置文件

## 故障排查

### 问题1：无法生成密码

**错误**：`至少需要选择一种字符类型`

**解决方案**：确保至少选择一种字符类型（大写字母、小写字母、数字或特殊字符）

### 问题2：密码长度不足

**错误**：`密码长度必须至少 X 个字符`

**解决方案**：使用 `--length` 参数指定更长的密码长度

### 问题3：无法复制到剪贴板

**错误**：`需要安装 pyperclip 库`

**解决方案**：
```bash
pip install pyperclip
```

## 相关工具

- **配置文件生成工具**：`scripts/generate_env.py`
- **生产环境配置指南**：`docs/生产环境配置指南.md`

## 技术说明

### 密码生成算法

1. **字符集构建**：根据参数构建可用字符集
2. **强制包含**：确保密码包含每种类型的字符
3. **随机填充**：使用加密安全的随机数生成器填充剩余长度
4. **随机打乱**：使用 `secrets.SystemRandom().shuffle()` 打乱字符顺序

### 安全性

- 使用 Python `secrets` 模块（加密安全的随机数生成器）
- 不依赖伪随机数生成器（`random` 模块）
- 适合生成密码、密钥等敏感信息

## 许可证

本工具为项目内部工具，遵循项目许可证。

