# Postback 下游转发功能说明

## 📋 功能概述

Postback 下游转发功能允许您将接收到的 postback 转化数据自动转发给下游系统（如广告主的服务器、其他追踪平台等）。当产品配置了下游 URL 后，系统会在接收到 postback 回调并成功保存后，自动将转化数据转发到配置的下游地址。

## 🎯 使用场景

1. **多平台数据同步**：将转化数据同步到多个追踪平台
2. **广告主回调**：将转化数据转发给广告主的服务器
3. **数据分析平台**：将数据发送到数据分析系统
4. **实时通知**：实时通知下游系统转化事件

## 🔧 配置步骤

### 1. 在产品管理中配置下游 URL

1. 登录系统，进入 **用户管理** 页面
2. 选择对应的客户，点击 **产品管理**
3. 添加或编辑产品时，在表单底部找到 **下游 Postback 配置** 部分
4. 填写以下信息：
   - **下游 Postback URL**：下游系统的接收地址（例如：`https://example.com/api/postback`）
   - **请求方式**：选择 GET 或 POST
     - **GET**：数据作为 URL 参数传递
     - **POST**：数据作为 JSON body 传递（推荐）

### 2. 配置示例

**GET 方式配置：**
```
下游 Postback URL: https://example.com/api/postback
请求方式: GET
```

**POST 方式配置：**
```
下游 Postback URL: https://example.com/api/postback
请求方式: POST
```

## 📤 转发数据格式

### GET 请求格式

转发时，数据会作为 URL 参数附加到下游 URL 后面：

```
GET https://example.com/api/postback?
  conversion_id=abc123&
  platform=macan&
  event_name=purchase&
  event_value=99.99&
  payout=10.5&
  devad_id=xyz789&
  os=IOS&
  carrier=China Mobile&
  ip=192.168.1.1&
  gid=channel001&
  product_id=1&
  client_id=2&
  timestamp=2024-01-01T12:00:00Z
```

### POST 请求格式

转发时，数据会作为 JSON body 发送：

```json
{
  "conversion_id": "abc123",
  "platform": "macan",
  "event_name": "purchase",
  "event_value": 99.99,
  "payout": 10.5,
  "devad_id": "xyz789",
  "os": "IOS",
  "carrier": "China Mobile",
  "ip": "192.168.1.1",
  "gid": "channel001",
  "product_id": 1,
  "client_id": 2,
  "timestamp": "2024-01-01T12:00:00Z"
}
```

### 数据字段说明

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `conversion_id` | string | 转化ID（各平台唯一标识） | `abc123` |
| `platform` | string | 平台名称 | `macan` |
| `event_name` | string | 事件名称 | `purchase` |
| `event_value` | float | 事件价值（购买价格等） | `99.99` |
| `payout` | float | 支付金额（确认的广告单元价格） | `10.5` |
| `devad_id` | string | 设备广告ID（IDFA或GAID） | `xyz789` |
| `os` | string | 操作系统 | `IOS` |
| `carrier` | string | 用户运营商 | `China Mobile` |
| `ip` | string | 点击IP地址 | `192.168.1.1` |
| `gid` | string | 渠道ID | `channel001` |
| `product_id` | integer | 产品ID | `1` |
| `client_id` | integer | 客户ID | `2` |
| `timestamp` | string | 转化时间（ISO 8601格式） | `2024-01-01T12:00:00Z` |

**注意**：只有非空的字段才会被包含在转发数据中。

## 🔍 查看转发日志

### 通过 API 查询

管理员可以通过以下接口查询转发日志：

```
GET /api/v1/postback/forward-logs
```

**查询参数：**
- `conversion_id` (可选)：转化记录ID
- `product_id` (可选)：产品ID
- `success` (可选)：是否成功（true/false）
- `start_date` (可选)：起始日期（YYYY-MM-DD）
- `end_date` (可选)：结束日期（YYYY-MM-DD）
- `page` (可选)：页码（默认：1）
- `page_size` (可选)：每页数量（默认：20，最大：100）

**示例请求：**
```bash
curl -X GET "https://client.btfrx.online/api/v1/postback/forward-logs?product_id=1&success=true&page=1&page_size=20" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**响应示例：**
```json
{
  "code": 200,
  "message": "查询成功",
  "data": [
    {
      "id": 1,
      "conversion_id": 123,
      "product_id": 1,
      "downstream_url": "https://example.com/api/postback",
      "request_method": "POST",
      "request_data": "{\"conversion_id\":\"abc123\",\"platform\":\"macan\"}",
      "response_status": 200,
      "response_body": "OK",
      "success": true,
      "error_message": null,
      "retry_count": 0,
      "created_at": "2024-01-01T12:00:00Z",
      "completed_at": "2024-01-01T12:00:01Z"
    }
  ],
  "total": 100,
  "page": 1,
  "page_size": 20
}
```

## ⚙️ 技术特性

### 1. 异步转发

- 转发操作在后台异步执行，不会阻塞 postback 接收流程
- 即使转发失败，也不会影响 postback 的正常接收和存储

### 2. 错误处理

- 转发失败时会记录详细的错误信息
- 支持超时控制（默认 10 秒）
- 所有转发尝试都会记录到日志中

### 3. 数据完整性

- 转发数据基于已保存的转化记录
- 确保数据的一致性和完整性

### 4. 日志记录

- 每次转发都会创建日志记录
- 记录请求数据、响应状态、错误信息等
- 方便排查问题和审计

## 🚨 注意事项

1. **URL 格式**：确保下游 URL 格式正确，包含协议（http:// 或 https://）
2. **网络连通性**：确保服务器能够访问下游 URL
3. **超时设置**：转发请求默认超时时间为 10 秒
4. **数据格式**：下游系统需要能够处理 GET 参数或 JSON body
5. **安全性**：建议使用 HTTPS 协议，确保数据传输安全
6. **性能影响**：转发是异步执行的，不会影响主流程性能

## 🔄 工作流程

```
1. 广告平台发送 Postback 回调
   ↓
2. 系统接收并验证数据
   ↓
3. 保存转化记录到数据库
   ↓
4. 检查产品是否配置了下游 URL
   ↓
5. 如果配置了，异步转发数据到下游
   ↓
6. 记录转发日志（成功或失败）
```

## 📝 示例场景

### 场景 1：转发给广告主服务器

**配置：**
- 下游 URL：`https://advertiser.com/api/conversions`
- 请求方式：POST

**转发数据：**
```json
{
  "conversion_id": "abc123",
  "platform": "macan",
  "event_name": "purchase",
  "event_value": 99.99,
  "payout": 10.5,
  "product_id": 1,
  "timestamp": "2024-01-01T12:00:00Z"
}
```

### 场景 2：转发给数据分析平台

**配置：**
- 下游 URL：`https://analytics.example.com/webhook`
- 请求方式：GET

**转发 URL：**
```
https://analytics.example.com/webhook?conversion_id=abc123&platform=macan&event_name=purchase&payout=10.5
```

## 🛠️ 故障排查

### 问题 1：转发失败

**可能原因：**
- 下游 URL 不可访问
- 网络连接问题
- 下游服务器返回错误状态码

**解决方法：**
1. 检查转发日志中的错误信息
2. 验证下游 URL 是否正确
3. 测试下游 URL 是否可访问
4. 检查下游服务器的日志

### 问题 2：转发超时

**可能原因：**
- 下游服务器响应慢
- 网络延迟高

**解决方法：**
1. 检查下游服务器的性能
2. 优化下游服务器的响应时间
3. 考虑使用消息队列进行异步处理

### 问题 3：数据格式不匹配

**可能原因：**
- 下游系统期望的数据格式不同

**解决方法：**
1. 查看转发日志中的请求数据
2. 与下游系统开发者确认数据格式要求
3. 考虑开发自定义转发处理器（需要代码修改）

## 📚 相关文档

- [Postback 服务说明](./postback_service.md)
- [Postback 原理说明](./postback_principle.md)
- [Postback 操作指南](./postback_operation_guide.md)

