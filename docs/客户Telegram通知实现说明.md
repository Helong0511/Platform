# 客户 Telegram 通知实现说明

## 一、实现概述

客户 Telegram 通知系统已经完整实现，支持通过客户通知配置（`ClientNotificationConfig`）发送 Telegram 通知。

## 二、配置方式

### 2.1 前端配置

客户可以通过前端界面配置 Telegram 通知：

1. **访问路径**：在客户管理页面，点击客户名称，打开客户详情对话框
2. **配置项**：
   - **启用通知**：总开关，关闭后不发送任何通知
   - **通知转化事件**：是否在转化发生时发送通知
   - **高价值转化通知**：只通知超过阈值的转化
   - **高价值阈值**：设置高价值转化的金额阈值
   - **通知渠道**：选择通知渠道（Telegram、Email、SMS）
   - **Telegram Chat ID**：输入 Telegram Chat ID
   - **通知频率**：实时通知、每小时汇总、每天汇总

### 2.2 配置优先级

通知配置的优先级如下：

1. **客户通知配置**（`ClientNotificationConfig`）- **最高优先级**
   - 如果客户配置了 `telegram_chat_id`，使用客户配置
   - 如果客户配置了通知开关，按配置执行

2. **产品通知配置**（`ProductNotificationConfig`）
   - 如果客户没有配置，使用产品配置

3. **产品表中的通知地址**（`Product.notification_address`）- **向后兼容**
   - 如果既没有客户配置，也没有产品配置，使用产品表中的通知地址
   - 如果通知地址是纯数字，作为 Telegram Chat ID 处理

## 三、实现逻辑

### 3.1 通知触发流程

```
转化发生
  ↓
PostbackProcessor.process_postback()
  ↓
PostbackNotifier.notify_conversion()
  ↓
1. 获取客户和产品信息
2. 查询客户通知配置（ClientNotificationConfig）
3. 查询产品通知配置（ProductNotificationConfig）
4. 检查是否需要发送通知（_should_notify）
   - 检查 notification_enabled
   - 检查 notify_on_conversion
   - 检查高价值转化通知条件
5. 获取 Telegram Chat ID（优先使用客户配置）
6. 构建通知消息（使用 TelegramNotificationService）
7. 发送通知（异步，不阻塞主流程）
```

### 3.2 关键代码位置

**通知触发**：`app/core/postback/notifier.py` - `notify_conversion()` 方法

**消息构建**：`app/services/telegram_notification_service.py`
- `build_client_conversion_message()` - 普通转化通知
- `build_client_high_value_message()` - 高价值转化通知

**通知发送**：`app/services/telegram_notification_service.py`
- `send_client_notification()` - 发送客户通知

### 3.3 通知判断逻辑

```python
def _should_notify(conversion, product_config, client_config):
    # 优先使用产品配置，如果没有则使用客户配置
    config = product_config if product_config else client_config
    
    # 如果没有配置，默认发送通知（向后兼容）
    if not config:
        return True, 'conversion'
    
    # 检查是否启用通知
    if not config.notification_enabled:
        return False, 'conversion'
    
    # 检查是否通知转化事件
    if not config.notify_on_conversion:
        # 如果配置了高价值通知，检查是否满足条件
        if config.notify_on_high_value and conversion.payout:
            threshold = config.high_value_threshold or 0
            if conversion.payout >= threshold:
                return True, 'high_value'
        return False, 'conversion'
    
    # 检查高价值转化通知
    if config.notify_on_high_value and conversion.payout:
        threshold = config.high_value_threshold or 0
        if conversion.payout >= threshold:
            return True, 'high_value'
    
    # 普通转化通知
    return True, 'conversion'
```

## 四、消息格式

### 4.1 普通转化通知

```
△ Postback 转化通知

产品: {产品名称}
平台: {平台名称}
转化ID: {转化ID}
事件: {事件名称}

💰 金额信息
• 原始收益 (PO): ${原始金额}
• 扣后收益 (PO(扣)): ${扣后金额}

⏰ 时间: {转化时间}

---
客户: {客户名称} ({用户全名})
```

### 4.2 高价值转化通知

```
⭐ 高价值转化通知

产品: {产品名称}
平台: {平台名称}
转化ID: {转化ID}
事件: {事件名称}

💰 金额信息
• 原始收益 (PO): ${原始金额}
• 扣后收益 (PO(扣)): ${扣后金额}
• 阈值: ${阈值} ✅

⏰ 时间: {转化时间}

---
客户: {客户名称} ({用户全名})
```

## 五、配置示例

### 5.1 通过前端配置

1. 登录系统（管理员或客户用户）
2. 进入客户管理页面
3. 点击客户名称，打开客户详情对话框
4. 点击"通知配置"按钮
5. 填写配置：
   - 启用通知：✅
   - 通知转化事件：✅
   - 高价值转化通知：✅（可选）
   - 高价值阈值：$10.00（可选）
   - 通知渠道：选择 Telegram
   - Telegram Chat ID：输入您的 Chat ID（例如：-1001234567890）
   - 通知频率：实时通知
6. 点击"保存"

### 5.2 通过 API 配置

```bash
# 创建或更新客户通知配置
POST /api/v1/notification-configs/clients/{client_id}/config

{
  "notification_enabled": true,
  "notify_on_conversion": true,
  "notify_on_high_value": true,
  "high_value_threshold": 10.0,
  "notify_channels": "[\"telegram\"]",
  "telegram_chat_id": "-1001234567890",
  "notification_frequency": "realtime"
}
```

## 六、获取 Telegram Chat ID

### 6.1 个人用户

1. 在 Telegram 中搜索 `@userinfobot`
2. 发送 `/start` 命令
3. 机器人会返回您的 Chat ID（通常是数字，例如：123456789）

### 6.2 群组/频道

1. 将机器人添加到群组或频道
2. 在群组中发送任意消息
3. 访问 `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates`
4. 查找 `chat.id` 字段（通常是负数，例如：-1001234567890）

## 七、测试通知

### 7.1 测试配置

1. 配置完成后，等待下一个转化发生
2. 如果配置了实时通知，转化发生后立即收到通知
3. 检查 Telegram 是否收到消息

### 7.2 常见问题

**问题1：没有收到通知**
- 检查 `notification_enabled` 是否为 `true`
- 检查 `notify_on_conversion` 是否为 `true`
- 检查 `telegram_chat_id` 是否正确
- 检查转化是否真的发生了
- 查看后端日志，确认是否有错误

**问题2：收到重复通知**
- 检查是否同时配置了客户通知和产品通知
- 检查是否同时配置了客户通知配置和产品表中的通知地址

**问题3：通知格式不正确**
- 检查消息构建逻辑是否正确
- 检查转化数据是否完整

## 八、技术细节

### 8.1 异步发送

所有通知都是异步发送的，不会阻塞主流程：

```python
asyncio.create_task(
    TelegramNotificationService.send_client_notification(
        message=message,
        telegram_chat_id=telegram_chat_id,
        conversion=conversion,
        db=db
    )
)
```

### 8.2 错误处理

通知发送失败不会影响转化处理流程，只会记录日志：

```python
except Exception as e:
    logger.warning(
        f"发送转化通知失败: conversion_id={conversion.id}, "
        f"error={str(e)}",
        exc_info=True
    )
```

### 8.3 通知记录

通知发送后会记录到 `postback_notifications` 表：

- `conversion_id`：转化记录ID
- `client_id`：客户ID
- `product_id`：产品ID
- `notification_type`：通知类型（conversion, high_value）
- `notification_channel`：通知渠道（telegram）
- `notification_status`：通知状态（sent, failed, pending）
- `notification_message`：通知消息内容
- `error_message`：错误信息（如果有）

## 九、总结

客户 Telegram 通知系统已经完整实现，支持：

✅ 通过客户通知配置发送 Telegram 通知  
✅ 支持普通转化通知和高价值转化通知  
✅ 支持通知开关和条件判断  
✅ 异步发送，不阻塞主流程  
✅ 完善的错误处理和日志记录  
✅ 通知记录保存到数据库  

**配置方式**：通过前端界面或 API 配置客户通知配置，填写 Telegram Chat ID 即可。
