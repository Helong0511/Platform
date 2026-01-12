# Telegram 信息通知方案设计

## 一、方案概述

### 1.1 目标
设计一个完善的 Telegram 通知系统，支持：
- **客户通知**：客户可以接收与自己相关的转化、数据更新等通知
- **管理员通知**：管理员可以接收系统级通知、所有转化通知、异常告警等

### 1.2 设计原则
1. **权限隔离**：客户只能接收自己相关的通知，管理员可以接收所有通知
2. **灵活配置**：支持按客户、按产品、按通知类型进行配置
3. **消息格式统一**：使用统一的消息模板，便于阅读和理解
4. **性能优化**：异步发送，不阻塞主流程
5. **容错机制**：发送失败不影响业务逻辑，记录详细日志

---

## 二、通知场景分类

### 2.1 客户通知场景

#### 场景1：转化通知
- **触发条件**：客户的产品发生转化
- **通知对象**：该客户配置的 Telegram Chat ID
- **通知内容**：
  - 转化ID、平台、事件名称
  - 原始金额 (PO)、扣后金额 (PO(扣))
  - 产品名称、客户名称
  - 转化时间
- **配置控制**：
  - `ClientNotificationConfig.notify_on_conversion`
  - `ClientNotificationConfig.telegram_chat_id`
  - `ClientNotificationConfig.notification_enabled`

#### 场景2：高价值转化通知
- **触发条件**：转化金额超过客户配置的阈值
- **通知对象**：该客户配置的 Telegram Chat ID
- **通知内容**：同转化通知，但添加高价值标识
- **配置控制**：
  - `ClientNotificationConfig.notify_on_high_value`
  - `ClientNotificationConfig.high_value_threshold`

#### 场景3：数据更新通知
- **触发条件**：客户的数据（广告数据、转化数据等）有重要更新
- **通知对象**：该客户配置的 Telegram Chat ID
- **通知内容**：
  - 数据类型（广告数据、转化数据等）
  - 更新范围（日期范围、数据条数）
  - 更新时间

#### 场景4：API 调用通知
- **触发条件**：客户通过 API 获取数据
- **通知对象**：该客户配置的 Telegram Chat ID（可选）
- **通知内容**：
  - API 调用类型
  - 获取的数据条数
  - 调用时间

### 2.2 管理员通知场景

#### 场景1：所有转化通知
- **触发条件**：系统内任何转化发生
- **通知对象**：管理员配置的 Telegram Chat ID（`TELEGRAM_ADMIN`）
- **通知内容**：
  - 转化ID、平台、事件名称
  - 原始金额 (PO)、扣后金额 (PO(扣))
  - 产品名称、客户名称
  - 渠道信息（Publisher）
  - 转化时间
- **配置控制**：系统配置 `TELEGRAM_ADMIN`

#### 场景2：系统异常告警
- **触发条件**：系统发生异常（错误、警告等）
- **通知对象**：管理员配置的 Telegram Chat ID
- **通知内容**：
  - 异常类型（错误、警告）
  - 异常描述
  - 发生时间
  - 相关上下文信息

#### 场景3：转发失败告警
- **触发条件**：Postback 转发给渠道失败
- **通知对象**：管理员配置的 Telegram Chat ID
- **通知内容**：
  - 转化ID
  - 渠道信息
  - 失败原因
  - 错误详情（包含点击参数）
  - 失败时间

#### 场景4：转发成功通知（可选）
- **触发条件**：Postback 转发给渠道成功
- **通知对象**：管理员配置的 Telegram Chat ID（可选，可配置）
- **通知内容**：
  - 转化ID
  - 渠道信息
  - 转发URL
  - 响应状态
  - 成功时间

#### 场景5：系统统计通知
- **触发条件**：定时任务（每小时、每天）
- **通知对象**：管理员配置的 Telegram Chat ID
- **通知内容**：
  - 时间段内的转化统计
  - 转化总数、总金额
  - 失败转发次数
  - 异常次数

---

## 三、消息格式设计

### 3.1 客户转化通知格式

```
△ Postback 转化通知

产品: {产品名称}
平台: {平台名称}
转化ID: {conversion_id}
事件: {event_name}

💰 金额信息
• 原始收益 (PO): ${original_payout:.2f}
• 扣后收益 (PO(扣)): ${payout:.2f}

⏰ 时间: {转化时间}

---
客户: {客户名称}
```

### 3.2 客户高价值转化通知格式

```
⭐ 高价值转化通知

产品: {产品名称}
平台: {平台名称}
转化ID: {conversion_id}
事件: {event_name}

💰 金额信息
• 原始收益 (PO): ${original_payout:.2f}
• 扣后收益 (PO(扣)): ${payout:.2f}
• 阈值: ${threshold:.2f} ✅

⏰ 时间: {转化时间}

---
客户: {客户名称}
```

### 3.3 管理员转化通知格式

```
📊 Postback 转化通知（管理员）

转化ID: {conversion_id}
平台: {平台名称}
事件: {event_name}

💰 金额信息
• 原始金额 (PO): ${original_payout:.2f}
• 扣后金额 (PO(扣)): ${payout:.2f}

👤 客户信息
• 客户: {客户名称}
• 产品: {产品名称}

📤 渠道信息
• 渠道ID: {publisher_id}
• 渠道名称: {publisher_name}

⏰ 时间: {转化时间}
```

### 3.4 管理员转发失败告警格式

```
❌ Postback 转发失败告警

转化ID: {conversion_id}
平台: {平台名称}

📤 渠道信息
• 渠道ID: {publisher_id}
• 渠道名称: {publisher_name}
• Postback URL: {postback_url}

❌ 错误信息
• 状态码: {status_code}
• 错误: {error_message}

📋 点击参数
{点击参数JSON}

⏰ 时间: {失败时间}
```

### 3.5 管理员转发成功通知格式

```
✅ Postback 转发成功

转化ID: {conversion_id}
平台: {平台名称}

📤 渠道信息
• 渠道ID: {publisher_id}
• 渠道名称: {publisher_name}
• Postback URL: {postback_url[:100]}

✅ 响应信息
• 状态码: {status_code}
• 响应: {response_body[:200]}

⏰ 时间: {成功时间}
```

### 3.6 系统异常告警格式

```
⚠️ 系统异常告警

类型: {异常类型}
描述: {异常描述}

📍 位置
• 模块: {模块名称}
• 函数: {函数名称}
• 行号: {行号}

📋 上下文
{相关上下文信息}

⏰ 时间: {发生时间}
```

---

## 四、配置管理设计

### 4.1 客户通知配置

**数据表**：`client_notification_configs`

**配置字段**：
- `notification_enabled`: 是否启用通知（默认：true）
- `notify_on_conversion`: 转化时通知（默认：true）
- `notify_on_high_value`: 高价值转化通知（默认：false）
- `high_value_threshold`: 高价值阈值（可选）
- `telegram_chat_id`: Telegram Chat ID（必需，用于客户通知）
- `notification_frequency`: 通知频率（realtime/hourly/daily，默认：realtime）
- `notify_channels`: 通知渠道（JSON格式，如：["telegram"]）

**配置优先级**：
1. 客户通知配置（`ClientNotificationConfig`）
2. 产品通知配置（`ProductNotificationConfig`）
3. 产品表中的通知地址（`Product.notification_address`）

### 4.2 管理员通知配置

**系统配置**（环境变量或配置表）：
- `TELEGRAM_ADMIN`: 管理员 Telegram Chat ID（必需）
- `TELEGRAM_ENABLE`: 是否启用 Telegram（默认：true）
- `ADMIN_NOTIFY_ALL_CONVERSIONS`: 是否通知所有转化（默认：true）
- `ADMIN_NOTIFY_FORWARD_SUCCESS`: 是否通知转发成功（默认：false）
- `ADMIN_NOTIFY_FORWARD_FAILURE`: 是否通知转发失败（默认：true）
- `ADMIN_NOTIFY_SYSTEM_ERRORS`: 是否通知系统错误（默认：true）

### 4.3 通知频率控制

**实时通知（realtime）**：
- 每次事件发生时立即发送
- 适用于：转化通知、高价值转化通知、转发失败告警

**每小时汇总（hourly）**：
- 每小时汇总一次，发送汇总消息
- 适用于：大量转化的场景，减少通知频率

**每天汇总（daily）**：
- 每天汇总一次，发送汇总消息
- 适用于：统计通知、系统状态报告

---

## 五、权限控制设计

### 5.1 客户权限
- **只能接收**：与自己客户ID相关的转化通知
- **不能接收**：其他客户的通知、系统级通知
- **配置权限**：只能查看和修改自己的通知配置

### 5.2 管理员权限
- **可以接收**：所有转化通知、系统异常告警、转发失败告警
- **配置权限**：可以查看和修改所有客户的通知配置
- **系统配置**：可以修改系统级通知配置

### 5.3 权限检查逻辑

```python
# 客户通知权限检查
if current_user.role == UserRole.CLIENT:
    # 只能接收自己客户的通知
    if conversion.client_id != current_user.client_id:
        return  # 跳过通知
    
# 管理员通知权限检查
if current_user.role == UserRole.ADMIN:
    # 可以接收所有通知
    # 使用系统配置的 TELEGRAM_ADMIN
```

---

## 六、实现架构设计

### 6.1 通知服务层

```
app/services/
  └── telegram_notification_service.py
      ├── TelegramNotificationService
      │   ├── send_client_notification()      # 发送客户通知
      │   ├── send_admin_notification()        # 发送管理员通知
      │   ├── send_conversion_notification()   # 发送转化通知
      │   ├── send_forward_failure_alert()    # 发送转发失败告警
      │   └── send_system_alert()             # 发送系统告警
      └── 消息构建器
          ├── build_client_conversion_message()
          ├── build_admin_conversion_message()
          ├── build_forward_failure_message()
          └── build_system_alert_message()
```

### 6.2 通知配置管理

```
app/services/
  └── notification_config_service.py (已存在)
      ├── get_client_notification_config()
      ├── create_or_update_client_notification_config()
      └── get_admin_notification_config()  # 新增
```

### 6.3 通知触发点

**客户通知触发点**：
1. `PostbackNotifier.notify_conversion()` - 转化通知
2. `PostbackProcessor.process()` - 转化处理时
3. API 数据获取时（可选）

**管理员通知触发点**：
1. `PostbackForwarder.forward_to_publisher()` - 转发成功/失败
2. `PostbackProcessor.process()` - 所有转化
3. 系统异常处理中间件
4. 定时任务（统计通知）

---

## 七、消息模板设计

### 7.1 模板变量

**通用变量**：
- `{conversion_id}`: 转化ID
- `{platform}`: 平台名称
- `{event_name}`: 事件名称
- `{original_payout}`: 原始金额
- `{payout}`: 扣后金额
- `{timestamp}`: 时间戳

**客户相关变量**：
- `{client_name}`: 客户名称
- `{product_name}`: 产品名称
- `{user_full_name}`: 用户全名

**渠道相关变量**：
- `{publisher_id}`: 渠道ID
- `{publisher_name}`: 渠道名称
- `{postback_url}`: Postback URL

### 7.2 模板管理

**方案1：代码中硬编码**（简单，但不够灵活）
- 在消息构建函数中直接编写模板

**方案2：数据库模板表**（推荐，灵活）
- 创建 `notification_templates` 表
- 支持按通知类型、用户角色配置模板
- 支持模板变量替换

**方案3：配置文件**（中等灵活）
- 在配置文件中定义模板
- 支持环境变量覆盖

---

## 八、通知频率控制实现

### 8.1 实时通知（realtime）
- 每次事件发生时立即发送
- 使用 `asyncio.create_task()` 异步发送
- 不阻塞主流程

### 8.2 每小时汇总（hourly）
- 使用 Redis 或数据库缓存待发送的通知
- 定时任务每小时执行一次，汇总并发送
- 汇总消息格式：
  ```
  📊 转化汇总（{开始时间} - {结束时间}）
  
  • 转化总数: {count}
  • 总金额: ${total_payout:.2f}
  • 高价值转化: {high_value_count}
  ```

### 8.3 每天汇总（daily）
- 类似每小时汇总，但每天执行一次
- 包含更详细的统计信息

---

## 九、错误处理和日志

### 9.1 错误处理
- **发送失败不影响业务**：使用 `try-except` 捕获异常
- **重试机制**：失败后最多重试 3 次，间隔 1 秒
- **失败记录**：记录到 `postback_notifications` 表

### 9.2 日志记录
- **成功日志**：记录发送成功的信息（客户ID、通知类型等）
- **失败日志**：记录发送失败的详细信息（错误信息、堆栈等）
- **性能日志**：记录发送耗时，便于性能优化

---

## 十、性能优化

### 10.1 异步发送
- 所有通知使用异步发送，不阻塞主流程
- 使用 `asyncio.create_task()` 创建后台任务

### 10.2 批量发送
- 对于汇总通知，批量发送多条消息
- 使用 Telegram Bot API 的批量发送功能（如果支持）

### 10.3 消息队列（可选）
- 对于高并发场景，可以使用消息队列（Redis Queue、RabbitMQ）
- 后台工作进程处理通知发送

---

## 十一、安全考虑

### 11.1 敏感信息保护
- **不发送敏感信息**：不在通知中发送密码、Token 等敏感信息
- **数据脱敏**：对于敏感数据，进行脱敏处理

### 11.2 权限验证
- **Chat ID 验证**：验证 Telegram Chat ID 的有效性
- **权限检查**：确保客户只能接收自己相关的通知

### 11.3 频率限制
- **防止滥用**：限制单个 Chat ID 的通知频率
- **防刷机制**：检测异常的通知频率，自动暂停

---

## 十二、测试方案

### 12.1 单元测试
- 测试消息构建函数
- 测试权限检查逻辑
- 测试配置读取逻辑

### 12.2 集成测试
- 测试完整的通知流程
- 测试不同配置下的通知行为
- 测试错误处理机制

### 12.3 性能测试
- 测试高并发场景下的通知发送
- 测试异步发送的性能影响
- 测试批量发送的性能

---

## 十三、实施计划

### 阶段1：基础功能
1. 实现客户通知配置管理
2. 实现管理员通知配置管理
3. 实现消息构建函数
4. 实现基础的通知发送功能

### 阶段2：通知场景
1. 实现客户转化通知
2. 实现管理员转化通知
3. 实现转发失败告警
4. 实现系统异常告警

### 阶段3：高级功能
1. 实现通知频率控制
2. 实现汇总通知
3. 实现消息模板管理
4. 实现性能优化

### 阶段4：测试和优化
1. 完善单元测试
2. 完善集成测试
3. 性能优化
4. 文档完善

---

## 十四、数据库设计

### 14.1 通知模板表（可选）

```sql
CREATE TABLE `notification_templates` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `template_type` VARCHAR(50) NOT NULL COMMENT '模板类型：client_conversion, admin_conversion, forward_failure等',
  `user_role` VARCHAR(20) NOT NULL COMMENT '用户角色：client, admin',
  `template_content` TEXT NOT NULL COMMENT '模板内容（支持变量替换）',
  `is_active` TINYINT(1) DEFAULT 1 COMMENT '是否启用',
  `created_at` DATETIME NOT NULL,
  `updated_at` DATETIME NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_template_type_role` (`template_type`, `user_role`)
) COMMENT='通知模板表';
```

### 14.2 通知发送记录表（扩展）

在现有的 `postback_notifications` 表中添加字段：
- `telegram_chat_id`: Telegram Chat ID
- `telegram_message_id`: Telegram 消息ID（用于后续编辑/删除）
- `notification_role`: 通知角色（client/admin）

---

## 十五、配置示例

### 15.1 客户通知配置示例

```json
{
  "notification_enabled": true,
  "notify_on_conversion": true,
  "notify_on_high_value": true,
  "high_value_threshold": 100.0,
  "telegram_chat_id": "123456789",
  "notification_frequency": "realtime",
  "notify_channels": ["telegram"]
}
```

### 15.2 管理员通知配置示例

```env
TELEGRAM_ENABLE=true
TELEGRAM_ADMIN=-1001234567890
ADMIN_NOTIFY_ALL_CONVERSIONS=true
ADMIN_NOTIFY_FORWARD_SUCCESS=false
ADMIN_NOTIFY_FORWARD_FAILURE=true
ADMIN_NOTIFY_SYSTEM_ERRORS=true
```

---

## 十六、前端管理界面设计（仅管理员）

### 16.1 管理员通知配置页面

#### 页面路径
- **路由路径**：`/app/admin/telegram-notification-config`
- **路由名称**：`TelegramNotificationConfig`
- **权限要求**：仅管理员可访问（`requiresAdmin: true`）

#### 页面布局

```
┌─────────────────────────────────────────────────────────┐
│  Telegram 通知配置（管理员）                              │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  【基础配置】                                            │
│  ┌──────────────────────────────────────────────────┐  │
│  │ ☑ 启用 Telegram 通知                              │  │
│  │                                                    │  │
│  │ Telegram Chat ID: [________________]            │  │
│  │ ℹ️ 获取 Chat ID：与 @BotFather 创建的机器人对话， │  │
│  │    发送 /start，然后发送任意消息，机器人会返回    │  │
│  │    Chat ID                                         │  │
│  │                                                    │  │
│  │ [测试连接] 按钮                                    │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  【通知场景配置】                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │ ☑ 通知所有转化                                     │  │
│  │    ℹ️ 当系统内任何转化发生时，发送通知给管理员     │  │
│  │                                                    │  │
│  │ ☑ 通知转发失败                                     │  │
│  │    ℹ️ 当 Postback 转发给渠道失败时，发送告警      │  │
│  │                                                    │  │
│  │ ☐ 通知转发成功                                     │  │
│  │    ℹ️ 当 Postback 转发给渠道成功时，发送通知      │  │
│  │    （可选，默认关闭）                              │  │
│  │                                                    │  │
│  │ ☑ 通知系统异常                                     │  │
│  │    ℹ️ 当系统发生异常时，发送告警                   │  │
│  │                                                    │  │
│  │ ☐ 定时统计通知                                     │  │
│  │    ℹ️ 定时发送系统统计信息                          │  │
│  │    频率: [每小时 ▼]                                │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  【通知消息预览】                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │ 📊 Postback 转化通知（管理员）                    │  │
│  │                                                  │  │
│  │ 转化ID: bpt7KMtEX497DrdtKWMPMweTXEYA4wKkpmbhFjHE│  │
│  │ 平台: KEPLERADS                                  │  │
│  │ 事件: purchase                                   │  │
│  │                                                  │  │
│  │ 💰 金额信息                                       │  │
│  │ • 原始金额 (PO): $2.80                           │  │
│  │ • 扣后金额 (PO(扣)): $2.42                       │  │
│  │                                                  │  │
│  │ 👤 客户信息                                       │  │
│  │ • 客户: 客户A                                    │  │
│  │ • 产品: 产品B                                    │  │
│  │                                                  │  │
│  │ 📤 渠道信息                                       │  │
│  │ • 渠道ID: 4                                      │  │
│  │ • 渠道名称: HappyOffer                          │  │
│  │                                                  │  │
│  │ ⏰ 时间: 2026-01-12 14:57:19                     │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  [保存配置] [重置] [测试发送]                            │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

#### 功能模块

**1. 基础配置模块**
- **启用开关**：启用/禁用 Telegram 通知功能
- **Chat ID 输入**：输入管理员的 Telegram Chat ID
- **Chat ID 获取说明**：显示如何获取 Chat ID 的提示
- **测试连接按钮**：测试 Telegram 连接是否正常

**2. 通知场景配置模块**
- **通知所有转化**：开关，是否通知所有转化
- **通知转发失败**：开关，是否通知转发失败
- **通知转发成功**：开关，是否通知转发成功（可选）
- **通知系统异常**：开关，是否通知系统异常
- **定时统计通知**：开关 + 频率选择（每小时/每天）

**3. 消息预览模块**
- **实时预览**：根据当前配置，实时预览通知消息格式
- **示例数据**：使用示例数据展示消息效果

**4. 操作按钮**
- **保存配置**：保存当前配置
- **重置**：重置为默认配置
- **测试发送**：发送一条测试消息到配置的 Chat ID

### 16.2 通知记录查看页面

#### 页面位置
- 在现有的 **Postback管理** 页面中，已有"通知记录"按钮
- 可以扩展为独立的管理页面：`/app/admin/notification-records`

#### 功能增强

**筛选功能**：
- 按通知类型筛选（转化通知、转发失败、系统异常等）
- 按通知角色筛选（客户通知、管理员通知）
- 按状态筛选（已发送、失败、待发送）
- 按时间范围筛选

**列表显示**：
- 通知ID
- 通知类型（带标签）
- 通知角色（客户/管理员）
- 通知渠道（Telegram/Email/SMS/Webhook）
- 通知状态（已发送/失败/待发送）
- 通知消息（可展开查看完整内容）
- 错误信息（如果有）
- 创建时间

**操作功能**：
- **查看详情**：查看完整的通知消息内容
- **重新发送**：对于失败的通知，可以重新发送
- **导出**：导出通知记录（CSV/Excel）

### 16.3 通知统计页面（可选）

#### 页面路径
- **路由路径**：`/app/admin/notification-stats`
- **路由名称**：`NotificationStats`
- **权限要求**：仅管理员可访问

#### 页面内容

**统计卡片**：
- 今日通知总数
- 今日成功通知数
- 今日失败通知数
- 今日转化通知数
- 今日转发失败告警数

**图表展示**：
- 通知趋势图（按时间）
- 通知类型分布（饼图）
- 通知成功率（折线图）
- 失败原因分析（柱状图）

**列表展示**：
- 最近的通知记录
- 失败通知列表
- 高频通知客户/产品

### 16.4 前端组件设计

#### 组件1：AdminTelegramConfigDialog.vue

**功能**：管理员 Telegram 通知配置对话框

**Props**：
- `visible`: Boolean - 是否显示对话框

**数据模型**：
```javascript
{
  telegram_enabled: true,
  telegram_chat_id: '',
  notify_all_conversions: true,
  notify_forward_failure: true,
  notify_forward_success: false,
  notify_system_errors: true,
  notify_statistics: false,
  statistics_frequency: 'hourly' // hourly, daily
}
```

**方法**：
- `loadConfig()`: 加载当前配置
- `saveConfig()`: 保存配置
- `testConnection()`: 测试 Telegram 连接
- `testSend()`: 发送测试消息
- `previewMessage()`: 预览消息格式

#### 组件2：NotificationRecordsTable.vue

**功能**：通知记录表格组件（增强版）

**Props**：
- `filters`: Object - 筛选条件
- `showRoleFilter`: Boolean - 是否显示角色筛选（默认true）

**增强功能**：
- 添加"通知角色"列（客户/管理员）
- 添加"通知类型"筛选（转化通知、转发失败、系统异常等）
- 添加"批量操作"功能（批量重新发送失败的通知）

#### 组件3：NotificationStats.vue

**功能**：通知统计页面组件

**数据获取**：
- 调用 API 获取统计数据
- 使用图表库（如 ECharts）展示数据

### 16.5 API 接口设计

#### 接口1：获取管理员通知配置

```javascript
GET /api/v1/notification-configs/admin/config

Response:
{
  "code": 200,
  "data": {
    "telegram_enabled": true,
    "telegram_chat_id": "-1001234567890",
    "notify_all_conversions": true,
    "notify_forward_failure": true,
    "notify_forward_success": false,
    "notify_system_errors": true,
    "notify_statistics": false,
    "statistics_frequency": "hourly"
  }
}
```

#### 接口2：保存管理员通知配置

```javascript
POST /api/v1/notification-configs/admin/config

Request Body:
{
  "telegram_enabled": true,
  "telegram_chat_id": "-1001234567890",
  "notify_all_conversions": true,
  "notify_forward_failure": true,
  "notify_forward_success": false,
  "notify_system_errors": true,
  "notify_statistics": false,
  "statistics_frequency": "hourly"
}

Response:
{
  "code": 200,
  "data": {
    "message": "配置已保存"
  }
}
```

#### 接口3：测试 Telegram 连接

```javascript
POST /api/v1/notification-configs/admin/test-connection

Request Body:
{
  "telegram_chat_id": "-1001234567890"
}

Response:
{
  "code": 200,
  "data": {
    "success": true,
    "message": "连接成功"
  }
}
```

#### 接口4：发送测试消息

```javascript
POST /api/v1/notification-configs/admin/test-message

Request Body:
{
  "telegram_chat_id": "-1001234567890",
  "message_type": "conversion" // conversion, forward_failure, system_error
}

Response:
{
  "code": 200,
  "data": {
    "success": true,
    "message": "测试消息已发送"
  }
}
```

#### 接口5：获取通知统计

```javascript
GET /api/v1/notification-configs/admin/stats

Query Parameters:
- start_date: 开始日期（可选）
- end_date: 结束日期（可选）

Response:
{
  "code": 200,
  "data": {
    "total_count": 1000,
    "success_count": 950,
    "failure_count": 50,
    "conversion_count": 800,
    "forward_failure_count": 30,
    "system_error_count": 20,
    "trend_data": [
      {"date": "2026-01-12", "count": 100},
      ...
    ],
    "type_distribution": {
      "conversion": 800,
      "forward_failure": 30,
      "system_error": 20
    }
  }
}
```

### 16.6 前端路由配置

```javascript
// frontend/src/router/index.js

{
  path: 'admin/telegram-notification-config',
  name: 'TelegramNotificationConfig',
  component: () => import('../views/admin/TelegramNotificationConfig.vue'),
  meta: { requiresAdmin: true }
},
{
  path: 'admin/notification-records',
  name: 'NotificationRecords',
  component: () => import('../views/admin/NotificationRecords.vue'),
  meta: { requiresAdmin: true }
},
{
  path: 'admin/notification-stats',
  name: 'NotificationStats',
  component: () => import('../views/admin/NotificationStats.vue'),
  meta: { requiresAdmin: true }
}
```

### 16.7 前端 API 客户端

```javascript
// frontend/src/api/notification.js

/**
 * 获取管理员通知配置
 */
export const getAdminNotificationConfig = async () => {
  try {
    const response = await axios.get('/api/v1/notification-configs/admin/config');
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    handleError(error);
  }
};

/**
 * 保存管理员通知配置
 */
export const saveAdminNotificationConfig = async (configData) => {
  try {
    await refreshCsrfTokenBeforeRequest('/api/v1/dashboard/stats');
    const response = await axios.post(
      '/api/v1/notification-configs/admin/config',
      configData
    );
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    handleError(error);
  }
};

/**
 * 测试 Telegram 连接
 */
export const testTelegramConnection = async (chatId) => {
  try {
    await refreshCsrfTokenBeforeRequest('/api/v1/dashboard/stats');
    const response = await axios.post(
      '/api/v1/notification-configs/admin/test-connection',
      { telegram_chat_id: chatId }
    );
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    handleError(error);
  }
};

/**
 * 发送测试消息
 */
export const sendTestMessage = async (chatId, messageType) => {
  try {
    await refreshCsrfTokenBeforeRequest('/api/v1/dashboard/stats');
    const response = await axios.post(
      '/api/v1/notification-configs/admin/test-message',
      {
        telegram_chat_id: chatId,
        message_type: messageType
      }
    );
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    handleError(error);
  }
};

/**
 * 获取通知统计
 */
export const getNotificationStats = async (params = {}) => {
  try {
    const response = await axios.get('/api/v1/notification-configs/admin/stats', { params });
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    handleError(error);
  }
};
```

### 16.8 菜单配置

在管理员菜单中添加"Telegram 通知配置"菜单项：

```javascript
// 菜单配置位置（根据实际项目结构）
{
  title: 'Telegram 通知配置',
  icon: 'Bell',
  path: '/app/admin/telegram-notification-config',
  requiresAdmin: true
}
```

### 16.9 用户体验优化

**1. 实时验证**
- Chat ID 输入时，实时验证格式（数字或负数）
- 保存前验证必填项
- 输入错误时显示红色提示

**2. 操作反馈**
- 保存成功/失败提示（使用 ElMessage）
- 测试连接时显示加载状态
- 测试消息发送成功/失败提示
- 操作按钮禁用状态（防止重复提交）

**3. 帮助提示**
- Chat ID 获取方法提示（带链接或详细说明）
- 各配置项的说明提示（使用 InfoFilled 图标）
- 消息格式预览（实时更新）

**4. 响应式设计**
- 支持移动端访问
- 自适应布局
- 使用 `useDevice` composable 检测设备类型

**5. 数据持久化**
- 配置自动保存到后端
- 页面刷新后自动加载配置
- 支持配置导入/导出（可选）

### 16.10 前端页面结构

#### 页面1：TelegramNotificationConfig.vue

**文件路径**：`frontend/src/views/admin/TelegramNotificationConfig.vue`

**页面结构**：
```vue
<template>
  <div class="telegram-notification-config">
    <!-- 页面标题 -->
    <div class="page-header">
      <h2>Telegram 通知配置</h2>
      <p class="page-description">配置管理员的 Telegram 通知设置</p>
    </div>

    <!-- 配置表单 -->
    <el-card class="config-card">
      <!-- 基础配置 -->
      <el-divider content-position="left">基础配置</el-divider>
      <!-- 表单内容 -->
      
      <!-- 通知场景配置 -->
      <el-divider content-position="left">通知场景配置</el-divider>
      <!-- 表单内容 -->
      
      <!-- 消息预览 -->
      <el-divider content-position="left">消息预览</el-divider>
      <!-- 预览内容 -->
      
      <!-- 操作按钮 -->
      <div class="action-buttons">
        <el-button type="primary" @click="handleSave" :loading="saving">
          保存配置
        </el-button>
        <el-button @click="handleReset">重置</el-button>
        <el-button @click="handleTestSend" :loading="testing">
          测试发送
        </el-button>
      </div>
    </el-card>
  </div>
</template>
```

**主要功能**：
- 加载配置：页面加载时从后端获取配置
- 保存配置：保存到后端
- 测试连接：测试 Telegram Chat ID 是否有效
- 测试发送：发送测试消息
- 消息预览：实时预览消息格式

#### 页面2：NotificationRecords.vue（增强版）

**文件路径**：`frontend/src/views/admin/NotificationRecords.vue`

**增强功能**：
- 添加"通知角色"筛选（客户/管理员）
- 添加"通知类型"筛选（转化通知、转发失败、系统异常等）
- 添加批量操作功能
- 添加导出功能

#### 页面3：NotificationStats.vue（可选）

**文件路径**：`frontend/src/views/admin/NotificationStats.vue`

**功能**：
- 统计卡片展示
- 图表展示（使用 ECharts 或 Chart.js）
- 数据表格展示

### 16.11 前端组件复用

**复用现有组件**：
- `NotificationRecordsDialog.vue`：可以扩展用于通知记录查看
- `ClientNotificationConfigDialog.vue`：可以参考其设计风格

**新建组件**：
- `AdminTelegramConfigForm.vue`：管理员配置表单组件
- `NotificationMessagePreview.vue`：消息预览组件
- `NotificationStatsCards.vue`：统计卡片组件
- `NotificationStatsCharts.vue`：统计图表组件

### 16.12 前端状态管理

**使用 Pinia Store**（如果项目使用 Pinia）：

```javascript
// frontend/src/store/notification.js

export const useNotificationStore = defineStore('notification', {
  state: () => ({
    adminConfig: null,
    loading: false,
    lastUpdateTime: null
  }),
  
  actions: {
    async loadAdminConfig() {
      // 加载管理员配置
    },
    
    async saveAdminConfig(config) {
      // 保存管理员配置
    },
    
    async testConnection(chatId) {
      // 测试连接
    }
  }
});
```

### 16.13 前端验证规则

```javascript
// 表单验证规则
const formRules = {
  telegram_chat_id: [
    { required: true, message: '请输入 Telegram Chat ID', trigger: 'blur' },
    { 
      pattern: /^-?\d+$/, 
      message: 'Chat ID 必须是数字（可以是负数）', 
      trigger: 'blur' 
    }
  ]
};
```

### 16.14 前端错误处理

- **网络错误**：显示友好的错误提示
- **验证错误**：在表单字段下方显示错误信息
- **权限错误**：提示权限不足，引导到登录页
- **服务器错误**：显示服务器返回的错误信息

---

## 十七、总结

### 16.1 核心特性
1. **权限隔离**：客户和管理员的通知完全隔离
2. **灵活配置**：支持按客户、按产品、按通知类型配置
3. **统一格式**：使用统一的消息格式，便于阅读
4. **性能优化**：异步发送，不阻塞主流程
5. **容错机制**：完善的错误处理和日志记录

### 16.2 扩展性
- 支持添加新的通知场景
- 支持自定义消息模板
- 支持多种通知渠道（Telegram、Email、SMS）
- 支持通知频率控制

### 16.3 可维护性
- 清晰的代码结构
- 完善的日志记录
- 详细的文档说明
- 完整的测试覆盖
