# 通知相关数据表说明

## 📋 概述

系统中有三个与通知相关的数据表，它们的设计目的和当前使用情况如下：

---

## 📊 数据表说明

### 1. `client_notification_configs` - 客户通知配置表

**设计目的：**
- 为客户级别的通知提供配置
- 支持客户所有产品的统一通知设置
- 作为产品级别配置的备用方案

**字段说明：**
```sql
- client_id: 客户ID（唯一）
- notification_enabled: 是否启用通知
- notify_on_conversion: 是否通知转化事件
- notify_on_high_value: 是否通知高价值转化
- high_value_threshold: 高价值阈值（金额）
- notify_channels: 通知渠道（JSON格式：["telegram", "email", "sms"]）
- telegram_chat_id: Telegram Chat ID
- email_address: 邮箱地址
- phone_number: 手机号
- notification_frequency: 通知频率（realtime, hourly, daily）
```

**当前状态：**
- ⚠️ **已创建但未使用**
- 当前实现使用产品表中的 `notification_address` 字段
- 保留用于未来高级功能（如批量通知、通知频率控制）

**未来用途：**
- 为客户设置默认通知地址
- 批量通知客户所有产品的转化
- 通知频率控制（每小时/每天汇总）

---

### 2. `product_notification_configs` - 产品通知配置表

**设计目的：**
- 为产品级别的通知提供详细配置
- 支持高级通知功能（高价值转化、通知频率等）
- 优先级高于客户配置

**字段说明：**
```sql
- product_id: 产品ID（唯一）
- notification_enabled: 是否启用通知
- notify_on_conversion: 是否通知转化事件
- notify_on_high_value: 是否通知高价值转化
- high_value_threshold: 高价值阈值（金额）
- notify_channels: 通知渠道（JSON格式）
- telegram_chat_id: Telegram Chat ID
- email_address: 邮箱地址
- phone_number: 手机号
- notification_frequency: 通知频率
```

**当前状态：**
- ⚠️ **已创建但未使用**
- 当前实现使用产品表中的 `notification_address` 字段
- 保留用于未来高级功能

**未来用途：**
- 高价值转化通知（只通知超过阈值的转化）
- 通知频率控制（避免频繁通知）
- 多渠道通知（同时发送到 Telegram、邮箱、短信）

---

### 3. `postback_notifications` - 通知记录表

**设计目的：**
- 记录所有通知发送历史
- 用于通知状态追踪和统计
- 支持通知失败重试

**字段说明：**
```sql
- conversion_id: 转化记录ID
- client_id: 客户ID
- product_id: 产品ID
- notification_type: 通知类型（conversion, high_value, error）
- notification_channel: 通知渠道（telegram, email, sms, webhook）
- notification_status: 通知状态（sent, failed, pending）
- notification_message: 通知消息内容
- error_message: 错误信息（如果失败）
- created_at: 创建时间
```

**当前状态：**
- ✅ **正在使用**
- 每次发送通知都会记录到该表
- 用于追踪通知发送状态和失败原因

**用途：**
- 通知发送历史查询
- 通知失败统计
- 通知重试机制
- 通知效果分析

---

## 🔄 当前实现 vs 原始设计

### 当前简化实现

**使用方式：**
```python
# 直接使用产品表中的 notification_address 字段
product.notification_address = "123456789"  # Telegram Chat ID
product.notification_address = "product@example.com"  # 邮箱
product.notification_address = "https://example.com/webhook"  # Webhook
```

**优点：**
- ✅ 简单直接，易于配置
- ✅ 无需额外的配置表
- ✅ 配置即生效

**限制：**
- ❌ 不支持高价值转化通知
- ❌ 不支持通知频率控制
- ❌ 不支持多渠道通知
- ❌ 不支持通知开关

---

### 原始设计（配置表方式）

**使用方式：**
```python
# 通过配置表进行详细配置
product_config = ProductNotificationConfig(
    product_id=1,
    notification_enabled=True,
    notify_on_conversion=True,
    notify_on_high_value=True,
    high_value_threshold=100.0,
    notify_channels='["telegram", "email"]',
    telegram_chat_id="123456789",
    email_address="product@example.com",
    notification_frequency="realtime"
)
```

**优点：**
- ✅ 支持高级功能（高价值通知、频率控制）
- ✅ 支持多渠道通知
- ✅ 支持通知开关和条件判断

**缺点：**
- ❌ 配置复杂
- ❌ 需要额外的配置表
- ❌ 需要前端界面支持

---

## 🎯 建议

### 方案一：保持当前简化实现（推荐）

**适用场景：**
- 通知需求简单
- 只需要基本的通知功能
- 希望配置简单

**操作：**
- 继续使用 `products.notification_address` 字段
- 保留配置表但不使用（未来扩展）
- `postback_notifications` 表继续使用（记录历史）

---

### 方案二：启用配置表功能

**适用场景：**
- 需要高价值转化通知
- 需要通知频率控制
- 需要多渠道通知

**操作：**
- 修改 `PostbackNotifier` 使用配置表
- 实现高价值转化检测
- 实现通知频率控制
- 实现多渠道通知

---

## 📝 代码中的使用情况

### 当前代码中的引用

**`app/core/postback/notifier.py`：**
```python
# 导入但未使用
from app.models.models import (
    ClientNotificationConfig, 
    ProductNotificationConfig, 
    PostbackNotification  # ✅ 正在使用
)

# 未使用的方法（保留用于未来）
def _should_notify(...)  # 使用配置表判断
def _get_notification_channels(...)  # 从配置表获取渠道
```

**`app/models/models.py`：**
- 所有三个模型都已定义
- 但只有 `PostbackNotification` 在使用

---

## 🔮 未来扩展建议

如果需要启用配置表功能，可以：

1. **高价值转化通知**
   ```python
   if conversion.payout >= config.high_value_threshold:
       # 发送高价值转化通知
   ```

2. **通知频率控制**
   ```python
   if config.notification_frequency == 'hourly':
       # 每小时汇总发送
   elif config.notification_frequency == 'daily':
       # 每天汇总发送
   ```

3. **多渠道通知**
   ```python
   channels = json.loads(config.notify_channels)
   for channel in channels:
       if channel == 'telegram':
           send_telegram(...)
       elif channel == 'email':
           send_email(...)
   ```

---

## 📊 总结

| 表名 | 状态 | 用途 | 建议 |
|------|------|------|------|
| `client_notification_configs` | 未使用 | 客户级别通知配置 | 保留用于未来功能 |
| `product_notification_configs` | 未使用 | 产品级别通知配置 | 保留用于未来功能 |
| `postback_notifications` | **正在使用** | 通知发送历史记录 | **继续使用** |

**当前实现：**
- ✅ 使用 `products.notification_address` 字段（简单直接）
- ✅ 使用 `postback_notifications` 表（记录历史）
- ⚠️ 配置表已创建但未使用（保留用于未来）

**建议：**
- 如果只需要基本通知功能，保持当前实现
- 如果需要高级功能，可以启用配置表
- `postback_notifications` 表必须保留（用于历史记录）

