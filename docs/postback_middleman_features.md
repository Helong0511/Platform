# Postback 中间商功能需求文档

## 📋 概述

作为 Postback 管理 S2S（Server-to-Server）的中间商，您需要同时管理**上游（广告平台）**和**下游（广告主/产品方）**的数据流转。本文档详细说明作为中间商所需的核心功能和扩展功能。

---

## 🎯 核心架构

```
┌─────────────┐
│  上游平台   │  (Macan, Addermobi, Skymobi 等)
│ (广告平台)  │
└──────┬──────┘
       │ 发送 Postback
       ▼
┌─────────────────────────────────────┐
│      中间商平台 (您)                │
│  ┌───────────────────────────────┐ │
│  │  1. 接收上游 Postback          │ │
│  │  2. 数据验证和标准化           │ │
│  │  3. 数据存储和统计             │ │
│  │  4. 收益计算（抽成）           │ │
│  │  5. 转发给下游                 │ │
│  └───────────────────────────────┘ │
└──────┬──────────────────────────────┘
       │ 转发 Postback
       ▼
┌─────────────┐
│  下游系统   │  (广告主服务器、其他追踪平台)
│ (广告主)    │
└─────────────┘
```

---

## 🔝 针对上游（广告平台）的功能

### 1. ✅ 多平台支持（已有）

**功能描述：**
- 支持多个上游广告平台的 postback 回调
- 每个平台有独立的处理器（Handler）

**当前支持：**
- ✅ Macan
- ⚠️ Addermobi（可扩展）
- ⚠️ Skymobi（可扩展）
- ⚠️ 其他平台（可扩展）

**需要扩展：**
- 添加更多平台支持
- 统一的平台管理界面

---

### 2. ✅ 数据接收和验证（已有）

**功能描述：**
- 接收上游平台的 postback 回调
- 验证必填参数
- 数据格式验证

**当前实现：**
- ✅ GET/POST 方式接收
- ✅ 平台特定验证逻辑
- ✅ 错误处理和日志记录

**需要增强：**
- ⚠️ IP 白名单验证（可选）
- ⚠️ 签名验证（如果上游支持）
- ⚠️ 请求频率限制（防攻击）

---

### 3. ✅ 数据标准化（已有）

**功能描述：**
- 将不同平台的数据格式统一为标准格式
- 字段映射和转换

**当前实现：**
- ✅ 各平台 Handler 的 normalize 方法
- ✅ 统一的数据模型（PostbackConversion）

**需要增强：**
- ⚠️ 自定义字段映射配置
- ⚠️ 数据转换规则配置

---

### 4. ✅ 防重复处理（已有）

**功能描述：**
- 防止同一转化事件被重复处理
- 数据库唯一性约束

**当前实现：**
- ✅ 唯一性约束：`(platform, conversion_id, event_name)`
- ✅ 处理前检查是否已存在

**需要增强：**
- ⚠️ 重复检测告警
- ⚠️ 重复数据统计

---

### 5. ⚠️ 上游配置管理（待实现）

**功能描述：**
- 管理不同上游平台的配置信息
- 配置每个平台的 postback URL、参数格式等

**需要实现：**
- 上游平台配置表
- 配置管理界面
- 配置验证和测试功能

**数据库设计建议：**
```sql
CREATE TABLE upstream_platforms (
    id INT PRIMARY KEY AUTO_INCREMENT,
    platform_name VARCHAR(50) UNIQUE NOT NULL,
    display_name VARCHAR(100),
    postback_url_template TEXT,
    request_method VARCHAR(10) DEFAULT 'GET',
    required_params TEXT,  -- JSON格式，必填参数列表
    optional_params TEXT,  -- JSON格式，可选参数列表
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME,
    updated_at DATETIME
);
```

---

### 6. ⚠️ 上游数据统计和监控（部分实现）

**功能描述：**
- 统计各上游平台的转化数据
- 监控上游平台的回调情况
- 异常告警

**当前实现：**
- ✅ 基础统计接口（`/api/v1/postback/stats`）
- ✅ 转化记录查询

**需要增强：**
- ⚠️ 实时监控面板
- ⚠️ 异常告警（如：上游回调中断、数据异常等）
- ⚠️ 数据对比分析（与上游平台数据对比）

---

### 7. ⚠️ 上游重试机制（待实现）

**功能描述：**
- 如果接收上游 postback 失败，记录并重试
- 支持手动重试失败的记录

**需要实现：**
- 失败记录表
- 自动重试队列
- 重试策略配置（重试次数、间隔等）

---

## 🔽 针对下游（广告主/产品方）的功能

### 1. ✅ 下游转发（已有）

**功能描述：**
- 将接收到的转化数据转发给下游系统
- 支持 GET/POST 方式

**当前实现：**
- ✅ 产品级别的下游 URL 配置
- ✅ 自动转发功能
- ✅ 转发日志记录

**需要增强：**
- ⚠️ 多个下游 URL 支持（一个产品转发到多个下游）
- ⚠️ 下游转发重试机制
- ⚠️ 下游转发失败告警

---

### 2. ⚠️ 下游配置管理（部分实现）

**功能描述：**
- 管理下游系统的配置
- 支持多个下游 URL
- 下游数据格式配置

**当前实现：**
- ✅ 产品级别的下游 URL 配置（单个）

**需要增强：**
- ⚠️ 多个下游 URL 配置（一个产品可以转发到多个下游）
- ⚠️ 下游数据格式转换/映射
- ⚠️ 下游转发条件（只转发符合条件的转化）
- ⚠️ 下游转发延迟（批量转发）

**数据库设计建议：**
```sql
CREATE TABLE downstream_configs (
    id INT PRIMARY KEY AUTO_INCREMENT,
    product_id INT,
    downstream_name VARCHAR(100),  -- 下游名称
    downstream_url VARCHAR(500) NOT NULL,
    request_method VARCHAR(10) DEFAULT 'GET',
    data_mapping TEXT,  -- JSON格式，数据字段映射规则
    forward_conditions TEXT,  -- JSON格式，转发条件（如：只转发payout>10的）
    is_active BOOLEAN DEFAULT TRUE,
    retry_count INT DEFAULT 3,
    retry_interval INT DEFAULT 60,  -- 重试间隔（秒）
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (product_id) REFERENCES products(id)
);
```

---

### 3. ⚠️ 下游数据格式转换（待实现）

**功能描述：**
- 不同下游可能需要不同的数据格式
- 字段映射和转换
- 自定义数据格式

**需要实现：**
- 数据格式转换引擎
- 字段映射配置
- 模板系统（支持宏变量）

**示例：**
```json
{
  "conversion_id": "{conversion_id}",
  "transaction_id": "{conversion_id}",
  "amount": "{payout}",
  "currency": "USD",
  "timestamp": "{timestamp}",
  "custom_field": "custom_value"
}
```

---

### 4. ✅ 下游转发日志（已有）

**功能描述：**
- 记录所有下游转发请求
- 记录成功/失败状态
- 记录错误信息

**当前实现：**
- ✅ PostbackForwardLog 表
- ✅ 转发日志查询接口

**需要增强：**
- ⚠️ 转发日志统计和分析
- ⚠️ 失败率监控
- ⚠️ 转发延迟统计

---

### 5. ⚠️ 下游转发重试机制（待实现）

**功能描述：**
- 下游转发失败时自动重试
- 支持配置重试次数和间隔
- 支持手动重试

**需要实现：**
- 重试队列系统
- 重试策略配置
- 重试日志记录

---

### 6. ⚠️ 下游转发过滤（待实现）

**功能描述：**
- 只转发符合条件的转化
- 支持多种过滤条件

**过滤条件示例：**
- 只转发 payout > 10 的转化
- 只转发特定事件类型
- 只转发特定平台的转化
- 只转发特定产品的转化

---

### 7. ⚠️ 下游批量转发（待实现）

**功能描述：**
- 支持批量转发（延迟转发）
- 减少下游系统压力
- 提高转发效率

**实现方式：**
- 定时任务批量转发
- 配置批量大小和间隔
- 批量转发日志

---

## 💰 中间商特有功能

### 1. ⚠️ 收益计算（抽成）（待实现）

**功能描述：**
- 计算中间商收益（从上游 payout 中抽成）
- 支持不同的抽成规则
- 收益统计和报表

**需要实现：**
- 抽成规则配置（按产品、按客户、按平台等）
- 收益计算逻辑
- 收益记录表
- 收益统计和报表

**数据库设计建议：**
```sql
CREATE TABLE revenue_rules (
    id INT PRIMARY KEY AUTO_INCREMENT,
    product_id INT,
    client_id INT,
    platform VARCHAR(50),
    rule_type VARCHAR(20),  -- 'percentage' 或 'fixed'
    value DECIMAL(10,2),  -- 百分比或固定金额
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME,
    updated_at DATETIME
);

CREATE TABLE revenue_records (
    id INT PRIMARY KEY AUTO_INCREMENT,
    conversion_id INT,
    upstream_payout DECIMAL(10,2),  -- 上游支付金额
    commission DECIMAL(10,2),  -- 抽成金额
    downstream_payout DECIMAL(10,2),  -- 转发给下游的金额
    rule_id INT,  -- 使用的抽成规则
    created_at DATETIME,
    FOREIGN KEY (conversion_id) REFERENCES postback_conversions(id),
    FOREIGN KEY (rule_id) REFERENCES revenue_rules(id)
);
```

---

### 2. ⚠️ 对账功能（待实现）

**功能描述：**
- 与上游平台对账
- 与下游系统对账
- 数据一致性检查

**需要实现：**
- 对账报表生成
- 差异检测和告警
- 对账历史记录

---

### 3. ⚠️ 数据聚合和统计（部分实现）

**功能描述：**
- 聚合各平台数据
- 生成统计报表
- 数据分析和可视化

**当前实现：**
- ✅ 基础统计接口

**需要增强：**
- ⚠️ 多维度统计（按平台、产品、客户、时间等）
- ⚠️ 数据可视化（图表、仪表盘）
- ⚠️ 自定义报表
- ⚠️ 数据导出（Excel、CSV）

---

### 4. ⚠️ 数据查询和导出（部分实现）

**功能描述：**
- 灵活的查询条件
- 数据导出功能
- 批量操作

**当前实现：**
- ✅ 转化记录查询接口
- ✅ 分页查询

**需要增强：**
- ⚠️ 高级查询（多条件组合）
- ⚠️ 数据导出（Excel、CSV、JSON）
- ⚠️ 批量导出
- ⚠️ 定时导出任务

---

### 5. ⚠️ 安全功能（待实现）

**功能描述：**
- 数据加密传输
- 签名验证
- IP 白名单
- 访问控制

**需要实现：**
- HTTPS 强制使用
- 下游转发签名（HMAC、JWT 等）
- IP 白名单管理
- API 访问控制（Token、API Key）

---

### 6. ✅ 通知功能（已完善）

**功能描述：**
- 按客户和产品进行转化通知
- 支持多种通知渠道（Telegram、邮件、短信等）
- 可配置的通知规则

**当前实现：**
- ✅ **按客户通知**：当客户的产品有转化时，通知该客户
- ✅ **按产品通知**：当特定产品有转化时，通知相关人员（优先级高于客户配置）
- ✅ **通知规则配置**：支持配置哪些事件需要通知
- ✅ **通知频率控制**：支持实时、每小时、每天汇总通知
- ✅ **高价值转化通知**：支持配置阈值，高价值转化使用特殊通知
- ✅ **多通知渠道**：支持 Telegram（已实现）、邮件、短信（框架已实现）
- ✅ **通知模板**：符合文档模板格式的通知消息
- ✅ **通知历史记录**：完整记录所有通知发送历史

**数据库设计建议：**
```sql
-- 客户通知配置表
CREATE TABLE client_notification_configs (
    id INT PRIMARY KEY AUTO_INCREMENT,
    client_id INT NOT NULL,
    notification_enabled BOOLEAN DEFAULT TRUE,
    notify_on_conversion BOOLEAN DEFAULT TRUE,  -- 转化时通知
    notify_on_high_value BOOLEAN DEFAULT FALSE,  -- 高价值转化通知
    high_value_threshold DECIMAL(10,2),  -- 高价值阈值
    notify_channels TEXT,  -- JSON格式，通知渠道：['telegram', 'email', 'sms']
    telegram_chat_id VARCHAR(100),  -- Telegram Chat ID
    email_address VARCHAR(255),  -- 邮箱地址
    phone_number VARCHAR(20),  -- 手机号
    notification_frequency VARCHAR(20) DEFAULT 'realtime',  -- 'realtime', 'hourly', 'daily'
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (client_id) REFERENCES clients(id)
);

-- 产品通知配置表
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

-- 通知记录表（用于去重和统计）
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

**通知消息模板示例：**
```
🔔 Postback 转化通知

客户：{client_name}
产品：{product_name}
平台：{platform}
转化ID：{conversion_id}
事件：{event_name}
价值：${event_value}
收益：${payout}
时间：{timestamp}
```

---

### 7. ⚠️ 数据备份和恢复（待实现）

**功能描述：**
- 定期备份数据
- 数据恢复功能
- 数据归档

**需要实现：**
- 自动备份任务
- 备份文件管理
- 数据恢复功能
- 数据归档策略

---

## 📊 功能优先级建议

### 🔴 高优先级（核心功能）

1. **按客户和产品通知** - 及时通知相关人员 ⭐
2. **下游转发重试机制** - 确保数据不丢失
3. **多个下游 URL 支持** - 满足业务需求
4. **下游转发过滤** - 灵活控制转发
5. **收益计算** - 核心业务功能
6. **上游配置管理** - 便于管理多个上游平台

### 🟡 中优先级（重要功能）

1. **下游数据格式转换** - 适配不同下游
2. **对账功能** - 确保数据准确性
3. **监控和告警** - 及时发现问题
4. **数据导出** - 便于分析和报表
5. **安全功能** - 保护数据安全

### 🟢 低优先级（增强功能）

1. **批量转发** - 性能优化
2. **数据可视化** - 更好的用户体验
3. **数据备份和恢复** - 数据安全
4. **高级统计** - 深度分析

---

## 🛠️ 实现建议

### 阶段一：核心功能增强（1-2周）

1. 实现下游转发重试机制
2. 支持多个下游 URL 配置
3. 实现下游转发过滤
4. 完善上游配置管理

### 阶段二：业务功能（2-3周）

1. 实现收益计算功能
2. 实现对账功能
3. 增强数据统计和报表
4. 实现数据导出功能

### 阶段三：高级功能（3-4周）

1. 实现下游数据格式转换
2. 实现监控和告警
3. 实现安全功能
4. 实现数据可视化

---

## 📝 总结

作为 Postback 中间商，您需要：

**针对上游：**
- ✅ 多平台支持（已有）
- ✅ 数据接收和验证（已有）
- ⚠️ 上游配置管理（待实现）
- ⚠️ 上游监控和告警（待增强）

**针对下游：**
- ✅ 基础转发功能（已有）
- ⚠️ 多个下游支持（待实现）
- ⚠️ 转发重试机制（待实现）
- ⚠️ 数据格式转换（待实现）

**中间商特有：**
- ⚠️ 收益计算（待实现）
- ⚠️ 对账功能（待实现）
- ⚠️ 数据统计和报表（待增强）
- ⚠️ 监控和告警（待实现）

根据业务优先级，逐步实现这些功能，构建完整的中间商 Postback 管理系统。

