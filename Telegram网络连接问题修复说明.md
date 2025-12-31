# Telegram Bot 网络连接问题修复说明

## 🔍 问题描述

错误日志显示：
```
OSError: [Errno 101] Network is unreachable
HTTPSConnectionPool(host='api.telegram.org', port=443): Max retries exceeded
```

**问题原因**: 服务器无法连接到 `api.telegram.org`，导致 Telegram Bot 无法启动。

---

## ✅ 已实施的修复

### 1. 添加重试机制 ✅

**位置**: `app/core/auto_bot.py` (第 312-360 行)

**修复内容**:
- ✅ 连接失败时自动重试（最多 3 次）
- ✅ 使用指数退避策略（5秒、10秒、20秒）
- ✅ 区分网络错误和其他错误（如 Token 错误）

**修复代码**:
```python
max_retries = 3
retry_delay = 5  # 秒

for attempt in range(1, max_retries + 1):
    try:
        bot_info = bot.get_me()
        connection_success = True
        break
    except Exception as test_error:
        if attempt < max_retries:
            time.sleep(retry_delay)
            retry_delay *= 2  # 指数退避
```

### 2. 改进错误诊断 ✅

**修复内容**:
- ✅ 识别网络错误类型
- ✅ 提供详细的错误诊断信息
- ✅ 给出修复建议

**错误类型识别**:
- `Network is unreachable` - 网络不可达
- `Connection refused` - 连接被拒绝
- `Connection timeout` - 连接超时
- `Name resolution failed` - DNS 解析失败
- `Max retries exceeded` - 重试次数超限

### 3. 优雅降级 ✅

**修复内容**:
- ✅ 网络连接失败时，Bot 轮询不会启动
- ✅ 应用继续运行（不影响其他功能）
- ✅ 记录清晰的警告信息

---

## 🛠️ 解决方案

### 方案 1: 检查网络连接

**测试连接**:
```bash
# 测试 DNS 解析
nslookup api.telegram.org

# 测试网络连接
ping api.telegram.org

# 测试 HTTPS 连接
curl -v https://api.telegram.org
```

### 方案 2: 配置代理（如果需要）

如果服务器在中国大陆或其他受限地区，可能需要配置代理。

**方法 1: 使用环境变量（推荐）**

在 `.env` 文件中添加：
```bash
# HTTP 代理
HTTP_PROXY=http://proxy.example.com:8080
HTTPS_PROXY=http://proxy.example.com:8080

# 或 SOCKS5 代理
HTTP_PROXY=socks5://proxy.example.com:1080
HTTPS_PROXY=socks5://proxy.example.com:1080
```

**方法 2: 在代码中配置代理**

修改 `app/core/auto_bot.py`，在初始化 Bot 时添加代理：

```python
import telebot
from telebot import apihelper

# 设置代理
apihelper.proxy = {
    'http': 'http://proxy.example.com:8080',
    'https': 'http://proxy.example.com:8080'
}

bot = telebot.TeleBot(token=token)
```

### 方案 3: 检查防火墙设置

**检查防火墙规则**:
```bash
# 检查防火墙状态
sudo ufw status
# 或
sudo iptables -L

# 允许出站 HTTPS 连接
sudo ufw allow out 443/tcp
```

### 方案 4: 检查 DNS 设置

**检查 DNS 配置**:
```bash
# 查看 DNS 配置
cat /etc/resolv.conf

# 测试 DNS 解析
dig api.telegram.org
```

---

## 📊 修复效果

### 修复前
- ❌ 连接失败时直接退出
- ❌ 没有重试机制
- ❌ 错误信息不清晰
- ❌ 无法区分错误类型

### 修复后
- ✅ 自动重试（最多 3 次）
- ✅ 指数退避策略
- ✅ 详细的错误诊断
- ✅ 优雅降级（应用继续运行）
- ✅ 清晰的修复建议

---

## 🔧 诊断步骤

### 步骤 1: 查看日志

检查日志中的错误信息：
- 是否显示 "网络连接问题"
- 重试次数和结果
- 错误类型和建议

### 步骤 2: 测试网络连接

```bash
# 测试 DNS
nslookup api.telegram.org

# 测试连接
ping api.telegram.org

# 测试 HTTPS
curl -v https://api.telegram.org/bot<TOKEN>/getMe
```

### 步骤 3: 检查代理设置

如果使用代理，检查：
- 代理服务器是否可用
- 代理配置是否正确
- 代理是否需要认证

### 步骤 4: 检查防火墙

检查防火墙是否阻止出站 HTTPS 连接。

---

## 💡 使用建议

### 1. 如果网络暂时不可用

- ✅ Bot 会自动重试
- ✅ 应用会继续运行
- ✅ 网络恢复后，重启应用即可

### 2. 如果需要配置代理

- ✅ 在 `.env` 文件中设置 `HTTP_PROXY` 和 `HTTPS_PROXY`
- ✅ 或在代码中配置代理（见方案 2）

### 3. 如果网络永久不可用

- ✅ 可以禁用 Telegram 功能（设置 `TELEGRAM_ENABLE=false`）
- ✅ 应用的其他功能不受影响

---

## ✅ 修复完成

所有修复已完成，包括：
- ✅ 添加重试机制
- ✅ 改进错误诊断
- ✅ 优雅降级处理
- ✅ 提供修复建议

**下一步**: 
1. 检查网络连接
2. 如果需要，配置代理
3. 重启应用，查看日志

---

**修复完成时间**: 2024年
**修复状态**: ✅ 已完成

