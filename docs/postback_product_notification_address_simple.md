# 产品通知地址功能说明

## 📋 概述

系统现在支持在 `products` 表中直接配置通知地址，当产品有转化时，自动发送通知到配置的地址。

---

## 🎯 功能特性

### 通知地址类型

系统会自动识别通知地址类型：

1. **Telegram Chat ID**：纯数字，如 `123456789`
2. **邮箱地址**：包含 `@` 符号，如 `product@example.com`
3. **Webhook URL**：以 `http://` 或 `https://` 开头，如 `https://example.com/webhook`

### 通知流程

```
1. 接收到 Postback 转化事件
   ↓
2. 获取产品信息
   ↓
3. 检查产品是否配置了通知地址
   ↓
4. 自动识别通知地址类型
   ↓
5. 构建通知消息
   ↓
6. 发送通知到配置的地址
   ↓
7. 记录通知历史
```

---

## 🔧 配置方式

### 1. 数据库迁移

首先执行 SQL 脚本添加字段：

```bash
mysql -u username -p database_name < scripts/data/add_product_notification_address.sql
```

### 2. 配置产品通知地址

#### Telegram Chat ID

```sql
-- 为产品配置 Telegram Chat ID
UPDATE products 
SET notification_address = '123456789' 
WHERE id = 1;
```

#### 邮箱地址

```sql
-- 为产品配置邮箱地址
UPDATE products 
SET notification_address = 'product1@example.com' 
WHERE id = 1;
```

#### Webhook URL

```sql
-- 为产品配置 Webhook URL
UPDATE products 
SET notification_address = 'https://example.com/webhook' 
WHERE id = 1;
```

---

## 📝 使用示例

### 场景 1：Telegram 通知

**配置：**
```sql
UPDATE products SET notification_address = '123456789' WHERE id = 1;
```

**结果：**
- 当产品1有转化时，通知发送到 Telegram Chat ID `123456789`
- 通知消息格式：
```
🔔 Postback 转化通知

客户：张三
产品：产品A
平台：MACAN
转化ID：abc123
事件：purchase
价值：$99.99
收益：$10.50
时间：2024-01-15 10:35:00
```

### 场景 2：Webhook 通知

**配置：**
```sql
UPDATE products SET notification_address = 'https://example.com/webhook' WHERE id = 2;
```

**结果：**
- 当产品2有转化时，发送 POST 请求到 Webhook URL
- 请求体格式：
```json
{
  "message": "🔔 Postback 转化通知\n\n客户：...",
  "timestamp": "2024-01-15T10:35:00Z"
}
```

---

## 🔍 通知地址识别逻辑

系统会根据通知地址的格式自动识别类型：

```python
# 1. 如果以 http:// 或 https:// 开头 → Webhook URL
if address.startswith('http://') or address.startswith('https://'):
    channel = 'webhook'

# 2. 如果包含 @ → 邮箱地址
elif '@' in address:
    channel = 'email'

# 3. 其他情况 → Telegram Chat ID
else:
    channel = 'telegram'
```

---

## 📊 通知消息格式

### 单条转化通知

```
🔔 Postback 转化通知

客户：{user_full_name}
产品：{product_name}
平台：{platform}
转化ID：{conversion_id}
事件：{event_name}
价值：${event_value}
收益：${payout}
时间：{timestamp}
```

### 批量汇总通知

```
📊 Postback 转化汇总通知

客户：{user_full_name}
产品：{product_name}

转化数量：{total_count} 条
总价值：${total_value}
总收益：${total_payout}

平台统计：
  • {platform}: {count} 条, ${payout}

时间范围：{start_time} 至 {end_time}
```

---

## 🎯 关键特性

### ✅ 简单配置
- 只需在产品表中配置一个字段
- 无需额外的配置表
- 配置即生效

### ✅ 自动识别
- 自动识别通知地址类型
- 支持多种通知方式
- 无需手动指定渠道

### ✅ 灵活支持
- 支持 Telegram Chat ID
- 支持邮箱地址（待实现）
- 支持 Webhook URL

---

## 🔧 代码实现

### 通知地址检测

```python
@staticmethod
def _detect_notification_channel(address: str) -> str:
    """检测通知地址类型"""
    if address.startswith('http://') or address.startswith('https://'):
        return 'webhook'
    elif '@' in address:
        return 'email'
    else:
        return 'telegram'
```

### 通知发送

```python
@staticmethod
async def _send_to_address(
    address: str,
    channel: str,
    message: str
) -> bool:
    """发送通知到指定地址"""
    if channel == 'telegram':
        # 发送到 Telegram Chat ID
        await send_telegram_message(message, chat_id=address)
    elif channel == 'webhook':
        # 发送到 Webhook URL
        await _send_webhook_notification(url=address, message=message)
    # ...
```

---

## 📝 注意事项

1. **通知地址格式**：确保通知地址格式正确
2. **Telegram Chat ID**：必须是有效的 Chat ID（纯数字）
3. **Webhook URL**：必须是有效的 HTTP/HTTPS URL
4. **邮箱地址**：当前框架已支持，具体实现待完成

---

## 🎉 总结

通过在 `products` 表中添加 `notification_address` 字段，实现了：

- ✅ 简单的配置方式
- ✅ 自动识别通知类型
- ✅ 支持多种通知方式
- ✅ 灵活的通知管理

只需在产品表中配置通知地址，系统会自动识别类型并发送通知！

