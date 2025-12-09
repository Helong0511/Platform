# Macan S2S 对接说明

## 一、对接状态

✅ **已完成对接**

已成功实现 Macan S2S PostBack 回调接口，可以接收 Macan 平台发送的转化事件数据。

## 二、接口信息

### 1. 接口地址

- **GET 方式**: `/api/v1/macan/postback`
- **POST 方式**: `/api/v1/macan/postback`

### 2. 接口说明

这是 Macan S2S 转化事件追踪的回调接口。当用户在 Macan 平台上发生转化事件时，Macan 会向此接口发送回调请求。

## 三、请求参数

### 必填参数

| 参数名 | 类型 | 说明 |
|--------|------|------|
| `clk_id` | string | Macan click ID（必填） |
| `event_name` | string | Event ID（事件ID，必填） |

### 可选参数

| 参数名 | 类型 | 说明 |
|--------|------|------|
| `devad_id` | string | Apple IDFA 或 Google Advertising ID |
| `event_value` | float | purchase price（购买价格） |
| `payout` | float | payout confirmed ad unit price（确认的广告单元价格） |
| `carrier` | string | User carrier（用户运营商） |
| `os` | string | IOS 或 Android |
| `ip` | string | Click IP（点击IP） |
| `gid` | string | Channel ID（渠道ID） |
| `product_id` | integer | 产品ID（可选，用于关联产品） |
| `client_id` | integer | 客户ID（可选，用于关联客户） |

## 四、请求示例

### GET 请求示例

```bash
curl "http://your-domain.com/api/v1/macan/postback?clk_id=12345&event_name=purchase&devad_id=abc123&event_value=99.99&payout=10.5&os=IOS&carrier=China%20Mobile"
```

### POST 请求示例

```bash
curl -X POST "http://your-domain.com/api/v1/macan/postback" \
  -H "Content-Type: application/json" \
  -d '{
    "clk_id": "12345",
    "event_name": "purchase",
    "devad_id": "abc123",
    "event_value": 99.99,
    "payout": 10.5,
    "os": "IOS",
    "carrier": "China Mobile"
  }'
```

## 五、响应格式

### 成功响应

```json
{
  "success": true,
  "message": "PostBack 接收成功",
  "clk_id": "12345"
}
```

### 错误响应

```json
{
  "success": false,
  "message": "错误信息",
  "clk_id": null
}
```

## 六、在 Macan 平台配置

### 1. 登录 Macan 平台

访问 https://macan-native.com/ 并登录您的账户。

### 2. 配置 PostBack URL

在 Macan 平台的广告设置中，配置 PostBack URL：

```
http://your-domain.com/api/v1/macan/postback?clk_id={click_id}&devad_id={gaid/idfa}&event_name={event_id}&event_value={event_value}&carrier={carrier}&os={platform}&payout={payout}
```

### 3. 配置 Click Tracker

在广告链接中添加追踪参数，例如：

```
http://yourtrackerdomain.com/?click_id=[sid]&ios_idfa=[devad_id]&source=[gid]
```

## 七、数据存储

目前接口会：
1. ✅ 验证必填参数
2. ✅ 验证产品和客户（如果提供）
3. ✅ 记录详细日志
4. ⚠️ 数据存储（可根据业务需求扩展）

### 扩展数据存储

如果需要将转化数据存储到数据库，可以：

1. **创建 MacanConversion 表**（推荐）
   - 存储所有转化事件数据
   - 便于后续分析和报表生成

2. **更新 AdData 表**
   - 将转化数据汇总到现有的广告数据表中
   - 与现有报表系统集成

## 八、日志记录

所有回调请求都会记录到日志中，包括：
- 请求时间
- 所有参数值
- 处理结果
- 错误信息（如果有）

日志位置：`logs/` 目录

## 九、安全建议

1. **IP 白名单**（可选）
   - 可以添加 Macan 平台的 IP 白名单验证
   - 防止恶意请求

2. **签名验证**（可选）
   - 如果 Macan 支持签名验证，可以添加签名验证逻辑
   - 提高接口安全性

3. **防重复回调**
   - 可以通过 `clk_id + event_name` 组合去重
   - 避免重复处理相同的转化事件

## 十、测试

### 测试接口是否正常工作

```bash
# GET 请求测试
curl "http://localhost:8000/api/v1/macan/postback?clk_id=test123&event_name=test_event"

# POST 请求测试
curl -X POST "http://localhost:8000/api/v1/macan/postback" \
  -H "Content-Type: application/json" \
  -d '{"clk_id": "test123", "event_name": "test_event"}'
```

### 查看日志

检查日志文件，确认回调请求已成功接收和处理。

## 十一、常见问题

### Q1: 接口返回 404 错误？

**A:** 检查路由配置是否正确，确保接口路径为 `/api/v1/macan/postback`

### Q2: 接口返回参数错误？

**A:** 确保 `clk_id` 和 `event_name` 参数已正确传递

### Q3: 如何关联产品和客户？

**A:** 在 PostBack URL 中添加 `product_id` 和 `client_id` 参数，或者在回调数据中传递这些参数

### Q4: 如何查看回调数据？

**A:** 查看日志文件，所有回调请求都会记录在日志中

## 十二、后续扩展

1. **数据存储**：创建 MacanConversion 表存储转化数据
2. **数据分析**：生成转化报表和分析
3. **实时通知**：转化事件发生时发送通知（如 Telegram）
4. **数据同步**：将转化数据同步到 AdData 表

## 十三、参考文档

- Macan S2S 官方文档：https://macan-native.com/docs/advertiser/S2S/
- 对接分析文档：`docs/macan_s2s_analysis.md`

