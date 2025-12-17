# Postback 按产品通知地址通知功能说明

## 📋 概述

系统现在支持按照【客户】的【产品】的【通知地址】进行通知。每个产品可以配置独立的通知地址（Telegram Chat ID、邮箱、手机号等），通知会发送到产品配置的地址，而不是全局地址。

---

## 🎯 功能特性

### 通知地址优先级

```
产品通知配置 > 客户通知配置 > 默认配置
```

### 通知流程

```
1. 接收到 Postback 转化事件
   ↓
2. 获取产品通知配置
   ↓
3. 如果没有产品配置，获取客户通知配置
   ↓
4. 根据配置判断是否需要通知
   ↓
5. 获取产品配置的通知地址（telegram_chat_id、email_address、phone_number）
   ↓
6. 如果没有产品配置，使用客户配置的通知地址
   ↓
7. 发送通知到配置的地址
   ↓
8. 记录通知历史
```

---

## 🔧 配置方式

### 1. 产品通知配置（推荐）

为每个产品配置独立的通知地址：

```sql
-- 为产品配置 Telegram 通知地址
INSERT INTO product_notification_configs (
    product_id,
    notification_enabled,
    notify_channels,
    telegram_chat_id
) VALUES (
    1,  -- 产品ID
    TRUE,
    '["telegram"]',
    '123456789'  -- 产品的 Telegram Chat ID
);

-- 为产品配置邮箱通知地址
UPDATE product_notification_configs
SET notify_channels = '["email"]',
    email_address = 'product1@example.com'
WHERE product_id = 1;

-- 为产品配置多个通知渠道
UPDATE product_notification_configs
SET notify_channels = '["telegram", "email"]',
    telegram_chat_id = '123456789',
    email_address = 'product1@example.com'
WHERE product_id = 1;
```

### 2. 客户通知配置（备用）

如果产品没有配置，使用客户配置：

```sql
-- 为客户配置通知地址
INSERT INTO client_notification_configs (
    client_id,
    notification_enabled,
    notify_channels,
    telegram_chat_id
) VALUES (
    1,  -- 客户ID
    TRUE,
    '["telegram"]',
    '987654321'  -- 客户的 Telegram Chat ID
);
```

---

## 📝 使用示例

### 场景 1：产品配置了 Telegram Chat ID

**配置：**
```sql
-- 产品1配置了独立的 Telegram Chat ID
INSERT INTO product_notification_configs (
    product_id, notify_channels, telegram_chat_id
) VALUES (1, '["telegram"]', '123456789');
```

**结果：**
- 当产品1有转化时，通知发送到 Chat ID `123456789`
- 不会发送到全局 Telegram 地址

### 场景 2：产品没有配置，使用客户配置

**配置：**
```sql
-- 产品2没有配置
-- 客户配置了 Telegram Chat ID
INSERT INTO client_notification_configs (
    client_id, notify_channels, telegram_chat_id
) VALUES (1, '["telegram"]', '987654321');
```

**结果：**
- 当产品2有转化时，通知发送到客户的 Chat ID `987654321`
- 使用客户配置作为备用

### 场景 3：都没有配置，使用默认配置

**配置：**
- 产品没有配置
- 客户没有配置

**结果：**
- 通知发送到全局 Telegram 地址（`TELEGRAM_ADMIN` 配置）
- 保持向后兼容

---

## 🔍 通知地址获取逻辑

### Telegram 通知

```python
# 优先级：产品配置 > 客户配置 > 默认配置
telegram_chat_id = (
    product_config.telegram_chat_id if product_config 
    else client_config.telegram_chat_id if client_config 
    else None  # 使用默认配置
)
```

### 邮件通知

```python
# 优先级：产品配置 > 客户配置
email_address = (
    product_config.email_address if product_config 
    else client_config.email_address if client_config 
    else None
)
```

### 短信通知

```python
# 优先级：产品配置 > 客户配置
phone_number = (
    product_config.phone_number if product_config 
    else client_config.phone_number if client_config 
    else None
)
```

---

## 📊 配置示例

### 完整的产品通知配置

```sql
INSERT INTO product_notification_configs (
    product_id,
    notification_enabled,
    notify_on_conversion,
    notify_on_high_value,
    high_value_threshold,
    notify_channels,
    telegram_chat_id,
    email_address,
    phone_number,
    notification_frequency
) VALUES (
    1,                          -- 产品ID
    TRUE,                       -- 启用通知
    TRUE,                       -- 通知转化事件
    TRUE,                       -- 通知高价值转化
    100.00,                     -- 高价值阈值 $100
    '["telegram", "email"]',    -- 通知渠道
    '123456789',                -- Telegram Chat ID
    'product1@example.com',    -- 邮箱地址
    '+1234567890',              -- 手机号
    'realtime'                  -- 实时通知
);
```

---

## 🎯 关键改进

### 之前的行为
- ❌ 所有通知都发送到全局 Telegram 地址
- ❌ 无法为不同产品配置不同的通知地址
- ❌ 无法区分不同产品的通知

### 现在的行为
- ✅ 通知发送到产品配置的地址
- ✅ 每个产品可以配置独立的通知地址
- ✅ 支持产品级别的通知管理
- ✅ 如果没有产品配置，使用客户配置（备用）
- ✅ 如果都没有配置，使用默认配置（向后兼容）

---

## 🔧 代码实现

### 通知地址获取

```python
# app/core/postback/notifier.py

@staticmethod
def _get_channel_recipient(
    channel: str,
    product_config: Optional[ProductNotificationConfig],
    client_config: Optional[ClientNotificationConfig]
) -> Optional[str]:
    """获取渠道特定的接收人信息（优先使用产品配置）"""
    # 优先使用产品配置，如果没有则使用客户配置
    config = product_config if product_config else client_config
    
    if not config:
        return None
    
    if channel == 'telegram':
        return config.telegram_chat_id
    elif channel == 'email':
        return config.email_address
    elif channel == 'sms':
        return config.phone_number
    
    return None
```

### 通知发送

```python
# app/core/postback/notifier.py

@staticmethod
async def _send_to_channel(
    channel: str,
    message: str,
    recipient: Optional[str] = None
) -> bool:
    """发送通知到指定渠道（使用产品配置的通知地址）"""
    if channel == 'telegram':
        # 使用产品配置的 Telegram Chat ID
        chat_id = recipient if recipient else None
        await send_telegram_message(message, chat_id=chat_id)
        return True
    # ... 其他渠道
```

---

## 📝 注意事项

1. **优先级明确**：产品配置优先于客户配置
2. **向后兼容**：如果没有配置，使用默认行为
3. **配置验证**：确保通知地址格式正确
4. **错误处理**：如果通知地址无效，会记录错误但不影响主流程

---

## 🎉 总结

现在系统完全支持按照【客户】的【产品】的【通知地址】进行通知：

- ✅ 产品配置优先
- ✅ 客户配置备用
- ✅ 默认配置兜底
- ✅ 支持多渠道通知
- ✅ 完整的通知历史记录

通过为每个产品配置独立的通知地址，可以实现：
- 不同产品发送到不同的通知群组
- 产品级别的通知管理
- 更精细的通知控制

