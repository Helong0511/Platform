# Macan S2S 对接分析文档

## 一、Macan S2S 概述

Macan S2S (Server-to-Server) 是一种服务器到服务器的转化追踪方案，用于追踪广告转化事件。

参考文档：https://macan-native.com/docs/advertiser/S2S/

## 二、对接流程

### 1. Click Tracker（点击追踪）

在广告链接中添加追踪参数，Macan 支持的宏（Macro）包括：

| 参数 | 宏 | 说明 |
|------|-----|------|
| Click ID* | `[sid]` | Macan click ID（必填） |
| Apple IDFA | `[devad_id]` | Apple iOS IDFA |
| Google Advertising ID | `[devad_id]` | Android Google AID |
| Channel ID | `[gid]` | Channel ID |

**示例追踪链接：**
```
http://yourtrackerdomain.com/?click_id=[sid]&ios_idfa=[devad_id]&source=[gid]
```

### 2. PostBack URL（回调URL）

当转化事件发生时，Macan 会向我们的服务器发送回调请求。

**回调参数说明：**

| 参数 | 说明 | 是否必填 |
|------|------|---------|
| clk_id | Macan click ID | ✅ 必填 |
| devad_id | Apple IDFA 或 Google Advertising ID | ❌ 可选 |
| event_name | Event ID（事件ID） | ✅ 必填 |
| event_value | purchase price（购买价格） | ❌ 可选 |
| payout | payout confirmed ad unit price（确认的广告单元价格） | ❌ 可选 |
| carrier | User carrier（用户运营商） | ❌ 可选 |
| os | IOS 或 Android | ❌ 可选 |
| ip | Click IP（点击IP） | ❌ 可选 |
| gid | Channel ID（渠道ID） | ❌ 可选 |

**示例 PostBack URL：**
```
http://mcanlabs.com/conv/?clk_id={click_id}&devad_id={gaid/idfa}&event_name={event_id}&event_value={event_value}&carrier={carrier}&os={platform}&payout={payout}
```

## 三、对接方案

### 1. 创建 PostBack 接收接口

需要创建一个接口来接收 Macan 的回调请求，接口路径建议：
- `/api/v1/macan/postback` 或
- `/api/v1/notify/macan`

### 2. 数据处理逻辑

1. **接收回调数据**：接收 Macan 发送的 GET 或 POST 请求
2. **数据验证**：验证必填参数（clk_id, event_name）
3. **数据存储**：将转化事件数据存储到数据库
4. **响应处理**：返回 200 状态码确认接收成功

### 3. 数据库设计

可以考虑创建新表存储 Macan 转化事件数据，或者与现有的 AdData 表关联。

**建议表结构：**
- macan_conversions（Macan 转化事件表）
  - id: 主键
  - clk_id: Macan click ID
  - devad_id: 设备广告ID
  - event_name: 事件名称
  - event_value: 事件价值
  - payout: 支付金额
  - carrier: 运营商
  - os: 操作系统
  - ip: IP地址
  - gid: 渠道ID
  - product_id: 关联的产品ID（可选）
  - client_id: 关联的客户ID（可选）
  - created_at: 创建时间

### 4. 与现有系统集成

- 可以通过 `clk_id` 或其他参数关联到具体的产品和客户
- 可以将转化数据汇总到 AdData 表中
- 可以用于生成转化报告

## 四、实现步骤

1. ✅ 创建 PostBack 接收接口
2. ✅ 实现数据验证逻辑
3. ✅ 实现数据存储逻辑
4. ✅ 添加日志记录
5. ✅ 测试接口功能

## 五、注意事项

1. **安全性**：
   - 验证请求来源（IP白名单或签名验证）
   - 防止重复回调（通过 clk_id + event_name 去重）

2. **性能**：
   - 异步处理回调数据
   - 批量插入数据库

3. **监控**：
   - 记录所有回调请求
   - 监控回调失败情况
   - 设置告警机制

4. **兼容性**：
   - 支持 GET 和 POST 请求
   - 处理参数缺失的情况
   - 返回标准的 HTTP 响应

