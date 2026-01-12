# Telegram 自动通知客户实现说明

## 一、实现概述

系统已完整实现 Telegram 自动通知客户的功能。当转化发生时，系统会根据客户的配置自动发送 Telegram 通知。

## 二、实现流程

### 2.1 转化处理流程

```
转化发生 → PostbackProcessor.process() 
  → 保存转化记录 
  → PostbackNotifier.notify_conversion()
    → 查询客户通知配置
    → 检查是否需要通知
    → 根据通知频率处理
      → realtime: 立即发送
      → hourly: 加入 Redis 队列
      → daily: 加入 Redis 队列
```

### 2.2 通知频率控制

#### 实时通知（realtime）
- **触发时机**：转化发生时立即发送
- **实现方式**：使用 `asyncio.create_task()` 异步发送，不阻塞主流程
- **适用场景**：需要实时了解转化情况的客户

#### 每小时汇总（hourly）
- **触发时机**：每小时整点执行定时任务
- **实现方式**：
  1. 转化发生时，将通知信息加入 Redis 队列
  2. 定时任务每小时从队列中取出所有通知
  3. 按客户和产品分组汇总
  4. 发送汇总消息
- **适用场景**：转化量较大，希望减少通知频率的客户

#### 每天汇总（daily）
- **触发时机**：每天 00:00 执行定时任务
- **实现方式**：
  1. 转化发生时，将通知信息加入 Redis 队列
  2. 定时任务每天从队列中取出所有通知
  3. 按客户和产品分组汇总
  4. 发送汇总消息
- **适用场景**：转化量很大，只需要每天统计的客户

## 三、核心代码实现

### 3.1 通知触发（`app/core/postback/notifier.py`）

```python
async def notify_conversion(
    conversion: PostbackConversion,
    db: AsyncSession,
    product: Optional[Product] = None,
    client: Optional[Client] = None
) -> None:
    """
    通知转化事件（根据配置决定是否发送）
    """
    # 1. 获取客户和产品信息
    # 2. 获取客户和产品通知配置
    # 3. 检查是否需要发送通知
    # 4. 获取通知渠道和 Telegram Chat ID
    # 5. 构建通知消息
    # 6. 根据通知频率决定发送方式
    
    notification_frequency = config.notification_frequency if config else 'realtime'
    
    if notification_frequency == 'realtime':
        # 实时通知：立即发送
        asyncio.create_task(
            TelegramNotificationService.send_client_notification(...)
        )
    else:
        # 汇总通知：加入 Redis 队列
        redis_client = await get_redis_client()
        notification_item = {
            'conversion_id': conversion.id,
            'client_id': client.id,
            'product_id': product.id,
            'telegram_chat_id': telegram_chat_id,
            'message': message,
            'notification_type': notification_type,
            'frequency': notification_frequency,
            'created_at': conversion.created_at.isoformat(),
            'payout': float(conversion.payout),
            'original_payout': float(conversion.original_payout)
        }
        
        queue_key = f"notification_queue:{notification_frequency}:{client.id}"
        await redis_client.lpush(queue_key, json.dumps(notification_item))
```

### 3.2 汇总任务（`app/scheduler_module/tasks/notification_summary_task.py`）

```python
async def process_hourly_notifications(db: AsyncSession) -> Dict[str, Any]:
    """
    处理每小时汇总通知
    """
    # 1. 从 Redis 获取所有 hourly 队列
    # 2. 按客户和产品分组
    # 3. 构建汇总消息
    # 4. 发送汇总通知
```

### 3.3 定时任务配置（`app/scheduler_module/task_config.py`）

```python
"通知汇总任务（每小时）": {
    "task_name": "通知汇总任务（每小时）",
    "task_module": "app.scheduler_module.tasks.notification_summary_task",
    "task_function": "process_hourly_notification_task",
    "cron_expression": "0 * * * *",  # 每小时整点执行
    "description": "每小时执行一次，汇总并发送 hourly 频率的客户通知",
},

"通知汇总任务（每天）": {
    "task_name": "通知汇总任务（每天）",
    "task_module": "app.scheduler_module.tasks.notification_summary_task",
    "task_function": "process_daily_notification_task",
    "cron_expression": "0 0 * * *",  # 每天 00:00 执行
    "description": "每天执行一次，汇总并发送 daily 频率的客户通知",
},
```

## 四、通知消息格式

### 4.1 实时通知消息

```
△ Postback 转化通知

产品: {product_name}
平台: {platform}
转化ID: {conversion_id}
事件: {event_name}

💰 金额信息
• 原始收益 (PO): ${original_payout:.2f}
• 扣后收益 (PO(扣)): ${payout:.2f}

⏰ 时间: {created_at}

---
客户: {client_name} ({user_full_name})
```

### 4.2 高价值转化通知

```
⭐ 高价值转化通知

产品: {product_name}
平台: {platform}
转化ID: {conversion_id}

💰 金额信息
• 原始收益 (PO): ${original_payout:.2f}
• 扣后收益 (PO(扣)): ${payout:.2f}
• 阈值: ${threshold:.2f}

⏰ 时间: {created_at}

---
客户: {client_name} ({user_full_name})
```

### 4.3 每小时汇总通知

```
📊 Postback 转化汇总通知（每小时）

产品: {product_name}
时间范围: {start_time} - {end_time}

💰 汇总信息
• 转化总数: {count}
• 原始总收益: ${total_original_payout:.2f}
• 扣后总收益: ${total_payout:.2f}

---
客户: {client_name} ({user_full_name})
```

### 4.4 每天汇总通知

```
📊 Postback 转化汇总通知（每天）

产品: {product_name}
日期: {date}

💰 汇总信息
• 转化总数: {count}
• 原始总收益: ${total_original_payout:.2f}
• 扣后总收益: ${total_payout:.2f}

---
客户: {client_name} ({user_full_name})
```

## 五、配置要求

### 5.1 客户通知配置

客户需要在系统中配置以下信息：

1. **启用通知**：打开通知开关
2. **通知转化事件**：选择是否通知所有转化
3. **高价值转化通知**（可选）：设置阈值，只通知超过阈值的转化
4. **通知渠道**：选择 Telegram
5. **Telegram Chat ID**：填写客户的 Telegram Chat ID
6. **通知频率**：选择 realtime/hourly/daily

### 5.2 系统要求

1. **Redis**：用于存储汇总通知队列（hourly/daily 需要）
2. **Telegram Bot**：已配置 Telegram Bot Token
3. **定时任务系统**：已启用定时任务调度器

## 六、降级策略

### 6.1 Redis 不可用

如果 Redis 不可用，系统会自动降级为实时发送：

```python
if not redis_client:
    # Redis 不可用时，降级为实时发送
    logger.warning("Redis 不可用，降级为实时发送通知")
    asyncio.create_task(
        TelegramNotificationService.send_client_notification(...)
    )
```

### 6.2 通知发送失败

通知发送失败不会影响主流程，只记录日志：

```python
try:
    # 发送通知
    await TelegramNotificationService.send_client_notification(...)
except Exception as e:
    # 通知失败不影响主流程，只记录日志
    logger.warning(f"发送转化通知失败: {str(e)}")
```

## 七、监控和日志

### 7.1 日志记录

系统会记录以下日志：

- 通知加入队列：`通知已加入汇总队列: conversion_id={id}, frequency={freq}`
- 通知发送成功：`客户通知已发送: conversion_id={id}`
- 通知发送失败：`发送转化通知失败: conversion_id={id}, error={error}`
- 汇总任务执行：`通知汇总任务（每小时）执行完成: {result}`

### 7.2 通知记录

所有通知都会记录到 `postback_notifications` 表：

- `auto_notify=True`：自动通知
- `notification_status`：sent/failed/pending
- `notification_message`：通知消息内容
- `error_message`：错误信息（如果失败）

## 八、使用示例

### 8.1 配置客户通知

1. 登录系统（管理员）
2. 进入 **用户管理** 页面
3. 找到客户用户，点击 **"通知"** 按钮
4. 配置通知设置：
   - 启用通知：✅
   - 通知转化事件：✅
   - 通知渠道：Telegram ✅
   - Telegram Chat ID：`-1001234567890`
   - 通知频率：实时通知
5. 点击 **"保存"**

### 8.2 测试通知

1. 触发一次转化（通过 Postback API）
2. 系统会自动：
   - 处理转化
   - 检查客户配置
   - 发送 Telegram 通知
3. 客户会在 Telegram 中收到通知消息

## 九、总结

✅ **已实现的功能**：
- 实时通知（realtime）
- 每小时汇总通知（hourly）
- 每天汇总通知（daily）
- 高价值转化通知
- 通知记录和历史
- 降级策略
- 错误处理和日志

✅ **自动化流程**：
- 转化发生时自动触发通知
- 定时任务自动汇总和发送
- 无需人工干预

✅ **可靠性**：
- Redis 不可用时自动降级
- 通知失败不影响主流程
- 完整的错误处理和日志记录

现在系统已经完全实现了 Telegram 自动通知客户的功能！
