# Postback 通知功能使用指南

## 📋 概述

Postback 通知功能允许系统在接收到转化事件时，自动按客户和产品发送通知。当前版本支持 Telegram 通知，未来将支持邮件、短信等多种通知渠道。

---

## 🎯 功能特性

### ✅ 已实现功能

1. **按客户和产品通知**
   - 当客户的产品有转化时，自动发送通知
   - 通知包含客户名称、产品名称、转化详情等信息

2. **Telegram 通知**
   - 支持发送到全局 Telegram 群组/频道
   - 异步发送，不阻塞主流程

3. **通知消息格式**
   - 包含完整的转化信息
   - 清晰的消息格式，易于阅读

### ⚠️ 待实现功能

1. **按客户配置通知**
   - 每个客户可以配置自己的通知渠道和接收人
   - 支持 Telegram Chat ID、邮箱、手机号等

2. **按产品配置通知**
   - 每个产品可以配置独立的通知规则
   - 支持高价值转化通知阈值

3. **通知频率控制**
   - 实时通知（默认）
   - 定时汇总通知（每小时/每天）

4. **多通知渠道**
   - 邮件通知
   - 短信通知
   - Webhook 通知

---

## 🔧 当前实现

### 通知触发时机

当系统接收到 postback 转化事件并成功保存后，会自动触发通知：

```
上游平台发送 Postback
    ↓
系统接收并验证
    ↓
保存转化记录到数据库
    ↓
触发通知（按客户和产品）
    ↓
发送 Telegram 通知
```

### 通知消息格式

**单条转化通知示例：**

```
🔔 Postback 转化通知

客户：张三
公司：ABC 公司
产品：产品A

平台：MACAN
转化ID：macan_click_abc123
事件：purchase
价值：$99.99
收益：$10.50
系统：IOS
运营商：China Mobile
时间：2024-01-15 10:35:00
```

**批量汇总通知示例：**

```
📊 Postback 转化汇总通知

客户：张三
产品：产品A

转化数量：10 条
总价值：$999.90
总收益：$105.00

平台统计：
  • MACAN: 8 条, $84.00
  • ADDERMOBI: 2 条, $21.00

时间范围：2024-01-15 10:00 至 2024-01-15 11:00
```

---

## 📝 代码实现

### 通知服务

通知功能由 `PostbackNotifier` 类实现，位于 `app/core/postback/notifier.py`。

**主要方法：**

1. `notify_conversion()` - 通知单条转化
2. `notify_batch_conversions()` - 批量通知转化
3. `_build_notification_message()` - 构建通知消息
4. `_send_notification_async()` - 异步发送通知

### 集成位置

通知功能已集成到 `PostbackProcessor` 中，在保存转化记录后自动触发：

```python
# app/core/postback/processor.py

# 保存转化记录
db.add(conversion)
await db.commit()

# 发送通知
await PostbackNotifier.notify_conversion(
    conversion=conversion,
    db=db
)
```

---

## 🔮 未来扩展

### 1. 客户通知配置

**数据库表设计：**

```sql
CREATE TABLE client_notification_configs (
    id INT PRIMARY KEY AUTO_INCREMENT,
    client_id INT NOT NULL,
    notification_enabled BOOLEAN DEFAULT TRUE,
    notify_on_conversion BOOLEAN DEFAULT TRUE,
    notify_on_high_value BOOLEAN DEFAULT FALSE,
    high_value_threshold DECIMAL(10,2),
    notify_channels TEXT,  -- JSON: ['telegram', 'email', 'sms']
    telegram_chat_id VARCHAR(100),
    email_address VARCHAR(255),
    phone_number VARCHAR(20),
    notification_frequency VARCHAR(20) DEFAULT 'realtime',
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (client_id) REFERENCES clients(id)
);
```

**功能：**
- 每个客户可以配置是否启用通知
- 配置通知渠道（Telegram、邮件、短信）
- 配置高价值转化通知阈值
- 配置通知频率（实时、每小时、每天）

### 2. 产品通知配置

**数据库表设计：**

```sql
CREATE TABLE product_notification_configs (
    id INT PRIMARY KEY AUTO_INCREMENT,
    product_id INT NOT NULL,
    notification_enabled BOOLEAN DEFAULT TRUE,
    notify_on_conversion BOOLEAN DEFAULT TRUE,
    notify_on_high_value BOOLEAN DEFAULT FALSE,
    high_value_threshold DECIMAL(10,2),
    notify_channels TEXT,
    telegram_chat_id VARCHAR(100),
    email_address VARCHAR(255),
    phone_number VARCHAR(20),
    notification_frequency VARCHAR(20) DEFAULT 'realtime',
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (product_id) REFERENCES products(id)
);
```

**功能：**
- 每个产品可以配置独立的通知规则
- 产品级别的通知优先级高于客户级别
- 支持产品特定的通知接收人

### 3. 通知记录表

**数据库表设计：**

```sql
CREATE TABLE postback_notifications (
    id INT PRIMARY KEY AUTO_INCREMENT,
    conversion_id INT NOT NULL,
    client_id INT,
    product_id INT,
    notification_type VARCHAR(50),  -- 'conversion', 'high_value', 'error'
    notification_channel VARCHAR(50),  -- 'telegram', 'email', 'sms'
    notification_status VARCHAR(20),  -- 'sent', 'failed', 'pending'
    notification_message TEXT,
    error_message TEXT,
    created_at DATETIME,
    FOREIGN KEY (conversion_id) REFERENCES postback_conversions(id),
    FOREIGN KEY (client_id) REFERENCES clients(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
);
```

**功能：**
- 记录所有通知发送历史
- 支持通知状态查询
- 支持通知失败重试

---

## 🛠️ 配置说明

### 当前配置

当前版本使用全局 Telegram 通知，配置在 `app/core/config.py` 中：

```python
# Telegram 配置
TELEGRAM_ENABLE = True  # 是否启用 Telegram
TELEGRAM_TOKEN = "your_bot_token"  # Bot Token
```

### 未来配置

当实现客户和产品级别的通知配置后，可以通过管理界面配置：

1. **客户通知配置**
   - 进入客户管理页面
   - 选择客户，点击"通知配置"
   - 配置通知渠道、接收人、规则等

2. **产品通知配置**
   - 进入产品管理页面
   - 选择产品，点击"通知配置"
   - 配置产品特定的通知规则

---

## 📊 使用示例

### 场景 1：实时通知

当客户的产品有转化时，立即发送通知：

```
转化事件发生
    ↓
系统保存转化记录
    ↓
查询客户和产品信息
    ↓
构建通知消息
    ↓
发送 Telegram 通知（异步）
```

### 场景 2：批量汇总通知

定时任务每小时/每天汇总转化数据，发送汇总通知：

```python
# 查询过去1小时的转化
conversions = await db.execute(
    select(PostbackConversion).where(
        PostbackConversion.created_at >= one_hour_ago
    )
)

# 批量通知
await PostbackNotifier.notify_batch_conversions(
    conversions=conversions,
    db=db
)
```

### 场景 3：高价值转化通知

当转化价值超过阈值时，发送特殊通知：

```python
if conversion.payout and conversion.payout >= high_value_threshold:
    # 发送高价值转化通知
    await PostbackNotifier.notify_high_value_conversion(
        conversion=conversion,
        db=db
    )
```

---

## 🔍 故障排查

### 问题 1：没有收到通知

**可能原因：**
- Telegram Bot 未配置或未启用
- 客户/产品未配置通知
- 通知发送失败（查看日志）

**解决方法：**
1. 检查 `TELEGRAM_ENABLE` 和 `TELEGRAM_TOKEN` 配置
2. 查看日志文件 `logs/app.log`
3. 检查 Telegram Bot 是否正常运行

### 问题 2：通知消息格式不正确

**可能原因：**
- 客户或产品信息缺失
- 转化数据不完整

**解决方法：**
1. 确保转化记录包含 `product_id` 或 `client_id`
2. 检查客户和产品数据是否完整
3. 查看通知消息构建逻辑

### 问题 3：通知发送延迟

**可能原因：**
- 异步任务队列阻塞
- Telegram API 响应慢

**解决方法：**
1. 检查系统负载
2. 查看异步任务执行情况
3. 考虑使用消息队列（如 Redis、RabbitMQ）

---

## 📚 相关文档

- [Postback 中间商功能需求](./postback_middleman_features.md)
- [Postback 服务说明](./postback_service.md)
- [Postback 原理说明](./postback_principle.md)

---

## 🎯 总结

Postback 通知功能为中间商提供了及时了解转化情况的能力。当前版本已实现基础的按客户和产品通知功能，未来将支持更灵活的通知配置和多渠道通知。

**关键特性：**
- ✅ 自动通知转化事件
- ✅ 按客户和产品组织通知
- ✅ 异步发送，不阻塞主流程
- ✅ 清晰的通知消息格式
- ⚠️ 未来支持多通知渠道和灵活配置

通过通知功能，您可以：
- 及时了解转化情况
- 监控业务运行状态
- 快速响应异常情况
- 提升客户服务质量

