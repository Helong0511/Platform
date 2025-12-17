# Postback 操作指南 - 超级详细版

## 📋 目录

1. [准备工作](#一准备工作)
2. [在 Macan 平台配置 Postback](#二在-macan-平台配置-postback)
3. [测试 Postback 接口](#三测试-postback-接口)
4. [查看转化数据](#四查看转化数据)
5. [完整流程示例](#五完整流程示例)
6. [常见问题排查](#六常见问题排查)

---

## 一、准备工作

### 1.1 确认服务器信息

**步骤：**

1. **获取服务器地址**
   ```bash
   # 实际服务器地址
   https://client.btfrx.online
   ```

2. **确认 API 路径**
   ```
   统一接口：/api/v1/postback/macan
   兼容接口：/api/v1/macan/postback
   
   完整地址：https://client.btfrx.online/api/v1/postback/macan
   ```

3. **测试服务器连通性**
   ```bash
   # 测试服务器是否可访问
   curl "https://client.btfrx.online/api/v1/postback/macan?clk_id=test&event_name=test"
   ```

### 1.2 准备测试工具

**推荐工具：**
- **Postman**：图形化 API 测试工具
- **curl**：命令行工具
- **浏览器**：用于 GET 请求测试

---

## 二、在 Macan 平台配置 Postback

### 2.1 登录 Macan 平台

**操作步骤：**

1. 打开浏览器，访问：`https://macan-native.com/`
2. 使用你的账号登录
3. 进入 **广告管理** 或 **Campaign 管理** 页面

### 2.2 找到 Postback 配置位置

**导航路径：**
```
Macan 平台
  → Campaign（广告活动）
    → Settings（设置）
      → Postback URL（回调URL配置）
```

### 2.3 配置 Postback URL

**URL 模板：**
```
https://client.btfrx.online/api/v1/postback/macan?clk_id={click_id}&devad_id={gaid/idfa}&event_name={event_id}&event_value={event_value}&carrier={carrier}&os={platform}&payout={payout}
```

**详细说明：**

| 参数 | 宏变量 | 说明 | 示例值 |
|------|--------|------|--------|
| `clk_id` | `{click_id}` | Macan 点击ID（必填） | abc123xyz |
| `devad_id` | `{gaid/idfa}` | 设备广告ID | 12345678-1234-1234-1234-123456789012 |
| `event_name` | `{event_id}` | 事件ID（必填） | purchase |
| `event_value` | `{event_value}` | 购买价格 | 99.99 |
| `carrier` | `{carrier}` | 运营商 | China Mobile |
| `os` | `{platform}` | 操作系统 | IOS |
| `payout` | `{payout}` | 支付金额 | 10.5 |

**实际操作：**

1. **复制完整的 Postback URL**
   ```
   https://client.btfrx.online/api/v1/postback/macan?clk_id={click_id}&devad_id={gaid/idfa}&event_name={event_id}&event_value={event_value}&carrier={carrier}&os={platform}&payout={payout}
   ```

2. **粘贴到 Macan 平台**
   - 在 Postback URL 输入框中直接粘贴上面的完整 URL
   - 无需修改，直接使用
   - 点击 **保存** 或 **Apply**

**注意：** URL 中的 `{click_id}`、`{event_id}` 等是 Macan 平台的宏变量，Macan 会自动替换为实际值，不要手动修改。

### 2.4 配置 Click Tracker（点击追踪）

**目的：** 在广告链接中添加追踪参数

**操作步骤：**

1. **找到广告链接配置**
   ```
   Campaign → Ad Creative → Landing Page URL
   ```

2. **原始链接示例**
   ```
   https://your-product.com/app
   ```

3. **添加追踪参数**
   ```
   https://your-product.com/app?click_id=[sid]&ios_idfa=[devad_id]&source=[gid]
   ```

4. **参数说明**
   - `[sid]`：Macan 自动替换为 click_id
   - `[devad_id]`：Macan 自动替换为设备ID
   - `[gid]`：Macan 自动替换为渠道ID

5. **保存配置**

---

## 三、测试 Postback 接口

### 3.1 使用 curl 测试（GET 方式）

**步骤 1：准备测试命令**

```bash
curl -X GET "https://client.btfrx.online/api/v1/postback/macan?clk_id=test123&event_name=purchase&devad_id=test-device-id&event_value=99.99&payout=10.5&os=IOS&carrier=China%20Mobile"
```

**步骤 2：执行命令**

```bash
# 在终端执行
curl -X GET "https://client.btfrx.online/api/v1/postback/macan?clk_id=test123&event_name=purchase&devad_id=test-device-id&event_value=99.99&payout=10.5&os=IOS&carrier=China%20Mobile"

# 预期响应
{
  "success": true,
  "message": "PostBack 接收成功",
  "conversion_id": "test123",
  "platform": "macan"
}
```

**步骤 3：检查日志**

```bash
# 查看服务器日志
tail -f logs/app.log

# 应该看到类似日志
# INFO: 平台 macan postback 转化记录已保存: conversion_id=test123, event_name=purchase, ...
```

### 3.2 使用 curl 测试（POST 方式）

**步骤 1：准备 JSON 数据**

创建文件 `test_postback.json`：
```json
{
  "clk_id": "test456",
  "event_name": "purchase",
  "devad_id": "test-device-id-456",
  "event_value": 199.99,
  "payout": 20.5,
  "os": "Android",
  "carrier": "China Unicom",
  "gid": "channel1",
  "product_id": 1,
  "client_id": 1
}
```

**步骤 2：发送 POST 请求**

```bash
curl -X POST "https://client.btfrx.online/api/v1/postback/macan" \
  -H "Content-Type: application/json" \
  -d @test_postback.json

# 或者直接写 JSON
curl -X POST "https://client.btfrx.online/api/v1/postback/macan" \
  -H "Content-Type: application/json" \
  -d '{
    "clk_id": "test456",
    "event_name": "purchase",
    "devad_id": "test-device-id-456",
    "event_value": 199.99,
    "payout": 20.5,
    "os": "Android",
    "carrier": "China Unicom"
  }'
```

**步骤 3：验证响应**

```json
{
  "success": true,
  "message": "PostBack 接收成功",
  "conversion_id": "test456",
  "platform": "macan"
}
```

### 3.3 使用 Postman 测试

**步骤 1：创建新请求**

1. 打开 Postman
2. 点击 **New** → **HTTP Request**
3. 选择请求方法：**GET** 或 **POST**

**步骤 2：配置 GET 请求**

```
Method: GET
URL: https://client.btfrx.online/api/v1/postback/macan
```

**Params（查询参数）：**
| Key | Value |
|-----|-------|
| clk_id | test789 |
| event_name | purchase |
| devad_id | test-device-789 |
| event_value | 299.99 |
| payout | 30.5 |
| os | IOS |
| carrier | China Mobile |

**步骤 3：配置 POST 请求**

```
Method: POST
URL: https://client.btfrx.online/api/v1/postback/macan
Headers:
  Content-Type: application/json
Body (raw JSON):
{
  "clk_id": "test789",
  "event_name": "purchase",
  "devad_id": "test-device-789",
  "event_value": 299.99,
  "payout": 30.5,
  "os": "IOS",
  "carrier": "China Mobile",
  "product_id": 1,
  "client_id": 1
}
```

**步骤 4：发送请求**

1. 点击 **Send** 按钮
2. 查看响应结果
3. 检查状态码（应该是 200）

### 3.4 使用浏览器测试（GET 方式）

**步骤 1：构建 URL**

```
https://client.btfrx.online/api/v1/postback/macan?clk_id=browser-test&event_name=purchase&payout=5.5
```

**步骤 2：在浏览器中打开**

1. 复制完整 URL
2. 粘贴到浏览器地址栏
3. 按 Enter

**步骤 3：查看响应**

浏览器会显示 JSON 响应：
```json
{
  "success": true,
  "message": "PostBack 接收成功",
  "conversion_id": "browser-test",
  "platform": "macan"
}
```

---

## 四、查看转化数据

### 4.1 通过前端界面查看

**步骤 1：登录系统**

1. 打开前端地址：`https://client.btfrx.online`
2. 使用管理员账号登录

**步骤 2：进入 Postback 管理页面**

1. 在左侧菜单找到 **Postback管理**
2. 点击进入

**步骤 3：查看转化记录**

页面会显示：
- **统计卡片**：各平台的总转化数、总支付金额等
- **转化记录表格**：详细的转化记录列表

**步骤 4：筛选数据**

可以使用以下筛选条件：
- **平台**：选择 macan 或其他平台
- **事件名称**：如 purchase
- **产品ID**：筛选特定产品
- **客户ID**：筛选特定客户
- **时间范围**：选择日期范围

**步骤 5：查看详情**

1. 点击表格中的 **详情** 按钮
2. 查看完整的转化信息，包括：
   - 转化ID
   - 事件信息
   - 设备信息
   - 原始JSON数据

### 4.2 通过 API 查询

**步骤 1：获取管理员 Token**

```bash
# 登录获取 token
curl -X POST "https://client.btfrx.online/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=your-password"

# 响应中包含 token
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**步骤 2：查询转化记录**

```bash
# 查询所有转化记录
curl -X GET "https://client.btfrx.online/api/v1/postback/conversions?page=1&page_size=20" \
  -H "Authorization: Bearer YOUR_TOKEN"

# 按平台筛选
curl -X GET "https://client.btfrx.online/api/v1/postback/conversions?platform=macan&page=1&page_size=20" \
  -H "Authorization: Bearer YOUR_TOKEN"

# 按时间范围筛选
curl -X GET "https://client.btfrx.online/api/v1/postback/conversions?start_date=2024-01-01&end_date=2024-01-31" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**步骤 3：查询统计信息**

```bash
# 获取所有平台统计
curl -X GET "https://client.btfrx.online/api/v1/postback/stats" \
  -H "Authorization: Bearer YOUR_TOKEN"

# 按平台和时间范围统计
curl -X GET "https://client.btfrx.online/api/v1/postback/stats?platform=macan&start_date=2024-01-01&end_date=2024-01-31" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 4.3 直接查询数据库

**步骤 1：连接数据库**

```bash
mysql -u your_username -p your_database
```

**步骤 2：查询转化记录**

```sql
-- 查看所有转化记录
SELECT * FROM postback_conversions ORDER BY created_at DESC LIMIT 10;

-- 按平台查询
SELECT * FROM postback_conversions WHERE platform = 'macan' ORDER BY created_at DESC;

-- 统计各平台转化数
SELECT 
    platform,
    COUNT(*) as total_conversions,
    SUM(payout) as total_payout,
    SUM(event_value) as total_event_value
FROM postback_conversions
GROUP BY platform;

-- 查询特定时间范围
SELECT * FROM postback_conversions 
WHERE DATE(created_at) BETWEEN '2024-01-01' AND '2024-01-31'
ORDER BY created_at DESC;
```

**步骤 3：查看原始数据**

```sql
-- 查看原始JSON数据
SELECT id, platform, conversion_id, event_name, raw_data 
FROM postback_conversions 
WHERE id = 1;

-- 格式化查看（MySQL 5.7+）
SELECT 
    id,
    platform,
    conversion_id,
    JSON_PRETTY(raw_data) as formatted_data
FROM postback_conversions 
WHERE id = 1;
```

---

## 五、完整流程示例

### 场景：用户通过 Macan 广告购买产品

#### 步骤 1：用户在 Macan 平台看到广告

**实际情况：**
- 用户在 Macan 平台的 App 中看到你的产品广告
- 广告显示：**"限时优惠，立即购买！"**

**技术细节：**
```
Macan 平台记录：
- 用户ID: user_12345
- 设备ID: iPhone_xyz789
- 点击时间: 2024-01-15 10:30:00
- 生成 click_id: macan_click_abc123def456
```

#### 步骤 2：用户点击广告

**用户操作：**
- 用户点击广告按钮

**技术流程：**
```
1. Macan 平台捕获点击事件
2. 生成追踪链接：
   https://your-product.com/app?click_id=macan_click_abc123def456&ios_idfa=xyz789&source=channel1
3. 跳转到你的产品页面
```

**实际跳转链接示例：**
```
原始链接：https://your-product.com/app
实际跳转：https://your-product.com/app?click_id=macan_click_abc123def456&ios_idfa=12345678-1234-1234-1234-123456789012&source=macan_channel_001
```

#### 步骤 3：用户在你的产品中完成购买

**用户操作：**
- 浏览产品
- 选择商品：**"高级会员套餐"**
- 点击购买
- 完成支付：**$99.99**

**产品服务器记录：**
```json
{
  "order_id": "order_20240115_001",
  "user_id": "user_12345",
  "product_id": 1,
  "amount": 99.99,
  "payment_method": "credit_card",
  "device_id": "12345678-1234-1234-1234-123456789012",
  "click_id": "macan_click_abc123def456",
  "timestamp": "2024-01-15 10:35:00"
}
```

#### 步骤 4：Macan 平台检测到转化

**Macan 平台操作：**
- Macan 通过以下方式之一检测到转化：
  1. **你的产品服务器主动通知 Macan**（如果配置了）
  2. **Macan 定期检查用户行为**（自动检测）

**Macan 平台记录：**
```
转化事件：
- click_id: macan_click_abc123def456
- event_name: purchase
- event_value: 99.99
- payout: 10.5 (Macan 的收益)
- devad_id: 12345678-1234-1234-1234-123456789012
- os: IOS
- carrier: China Mobile
- timestamp: 2024-01-15 10:35:00
```

#### 步骤 5：Macan 发送 Postback

**Macan 平台自动执行：**

**方式 A：GET 请求**
```
GET https://client.btfrx.online/api/v1/postback/macan?
  clk_id=macan_click_abc123def456&
  event_name=purchase&
  event_value=99.99&
  payout=10.5&
  devad_id=12345678-1234-1234-1234-123456789012&
  os=IOS&
  carrier=China%20Mobile&
  gid=channel1
```

**方式 B：POST 请求**
```
POST https://client.btfrx.online/api/v1/postback/macan
Content-Type: application/json

{
  "clk_id": "macan_click_abc123def456",
  "event_name": "purchase",
  "event_value": 99.99,
  "payout": 10.5,
  "devad_id": "12345678-1234-1234-1234-123456789012",
  "os": "IOS",
  "carrier": "China Mobile",
  "gid": "channel1"
}
```

#### 步骤 6：我们的服务器接收并处理

**处理流程：**

**6.1 接收请求**
```python
# 服务器接收到请求
Request received:
  Method: GET
  Path: /api/v1/postback/macan
  Params: {
    "clk_id": "macan_click_abc123def456",
    "event_name": "purchase",
    ...
  }
```

**6.2 路由到处理器**
```python
# FastAPI 路由匹配
router.get("/postback/{platform}")  # platform = "macan"
  → receive_postback_get()
```

**6.3 获取平台处理器**
```python
# 从注册表获取 Macan 处理器
handler = get_handler("macan")  # 返回 MacanPostbackHandler
```

**6.4 验证数据**
```python
# Macan Handler 验证
handler.validate({
  "clk_id": "macan_click_abc123def456",
  "event_name": "purchase",
  ...
})
# 检查：clk_id 存在 ✓, event_name 存在 ✓
# 返回：(True, None)
```

**6.5 标准化数据**
```python
# Macan Handler 标准化
normalized = handler.normalize({
  "clk_id": "macan_click_abc123def456",
  "event_name": "purchase",
  ...
})
# 返回：
{
  "conversion_id": "macan_click_abc123def456",  # clk_id → conversion_id
  "event_name": "purchase",
  "event_value": 99.99,
  "payout": 10.5,
  "devad_id": "12345678-1234-1234-1234-123456789012",
  "os": "IOS",
  "carrier": "China Mobile",
  "gid": "channel1"
}
```

**6.6 检查是否重复**
```python
# 查询数据库
existing = db.query(PostbackConversion).filter(
    PostbackConversion.platform == "macan",
    PostbackConversion.conversion_id == "macan_click_abc123def456",
    PostbackConversion.event_name == "purchase"
).first()

# 结果：None（不存在，继续处理）
```

**6.7 保存到数据库**
```python
# 创建转化记录
conversion = PostbackConversion(
    platform="macan",
    conversion_id="macan_click_abc123def456",
    event_name="purchase",
    event_value=99.99,
    payout=10.5,
    devad_id="12345678-1234-1234-1234-123456789012",
    os="IOS",
    carrier="China Mobile",
    gid="channel1",
    raw_data='{"clk_id":"macan_click_abc123def456",...}',  # 原始JSON
    created_at=datetime.now()
)

# 保存
db.add(conversion)
db.commit()
```

**6.8 返回成功响应**
```python
# 返回给 Macan
return {
    "success": True,
    "message": "PostBack 接收成功",
    "conversion_id": "macan_click_abc123def456",
    "platform": "macan"
}
```

**6.9 记录日志**
```python
# 写入日志文件
logger.info(
    "平台 macan postback 转化记录已保存: "
    "conversion_id=macan_click_abc123def456, "
    "event_name=purchase, "
    "payout=10.5, "
    "product_id=None, client_id=None"
)
```

#### 步骤 7：查看转化数据

**7.1 在前端查看**

1. 登录系统
2. 进入 **Postback管理**
3. 在表格中可以看到：
   ```
   ID: 1
   平台: MACAN
   转化ID: macan_click_abc123def456
   事件名称: purchase
   事件价值: $99.99
   支付金额: $10.50
   设备ID: 12345678-1234-1234-1234-123456789012
   操作系统: IOS
   运营商: China Mobile
   创建时间: 2024-01-15 10:35:00
   ```

**7.2 在数据库中查看**

```sql
SELECT * FROM postback_conversions WHERE conversion_id = 'macan_click_abc123def456';

-- 结果：
+----+---------+------------------------------+-------------+-------------+--------+--------------------------------------+------+--------------+------+---------------------+
| id | platform| conversion_id                | event_name  | event_value | payout | devad_id                             | os   | carrier      | gid  | created_at          |
+----+---------+------------------------------+-------------+-------------+--------+--------------------------------------+------+--------------+------+---------------------+
| 1  | macan   | macan_click_abc123def456     | purchase    | 99.99       | 10.5   | 12345678-1234-1234-1234-123456789012 | IOS  | China Mobile  | ch1  | 2024-01-15 10:35:00 |
+----+---------+------------------------------+-------------+-------------+--------+--------------------------------------+------+--------------+------+---------------------+
```

---

## 六、常见问题排查

### 问题 1：Postback 没有收到

**排查步骤：**

1. **检查 Macan 配置**
   ```
   ✓ Postback URL 是否正确
   ✓ URL 中的域名是否可以访问
   ✓ 宏变量是否正确（{click_id} 等）
   ```

2. **检查服务器日志**
   ```bash
   # 查看最近的日志
   tail -n 100 logs/app.log | grep postback
   
   # 查看错误日志
   tail -n 100 logs/app.log | grep ERROR
   ```

3. **测试接口是否正常**
   ```bash
   # 手动测试
   curl "https://client.btfrx.online/api/v1/postback/macan?clk_id=test&event_name=test"
   ```

4. **检查防火墙/安全组**
   ```
   ✓ 确保 Macan 的 IP 可以访问你的服务器
   ✓ 检查防火墙规则
   ✓ 检查 Nginx/Apache 配置
   ```

### 问题 2：收到 Postback 但数据没有保存

**排查步骤：**

1. **检查数据库连接**
   ```python
   # 测试数据库连接
   python -c "from app.core.database import get_db; print('DB OK')"
   ```

2. **检查数据验证**
   ```bash
   # 查看日志中的验证错误
   tail -n 100 logs/app.log | grep "验证失败"
   ```

3. **检查唯一性约束**
   ```sql
   -- 检查是否已存在相同记录
   SELECT * FROM postback_conversions 
   WHERE platform = 'macan' 
   AND conversion_id = 'your_conversion_id'
   AND event_name = 'your_event_name';
   ```

### 问题 3：数据格式不正确

**排查步骤：**

1. **查看原始数据**
   ```sql
   SELECT raw_data FROM postback_conversions WHERE id = 1;
   ```

2. **检查 Handler 逻辑**
   ```python
   # 查看 Macan Handler 的 normalize 方法
   # 确认字段映射是否正确
   ```

3. **测试不同格式的数据**
   ```bash
   # 测试各种参数组合
   curl "https://client.btfrx.online/api/v1/postback/macan?clk_id=test1&event_name=purchase"
   curl "https://client.btfrx.online/api/v1/postback/macan?click_id=test2&event_id=purchase"
   ```

### 问题 4：重复处理

**现象：**
- 同一条转化记录被处理多次

**原因：**
- Macan 可能重复发送 Postback
- 网络重试导致重复请求

**解决方案：**
- ✅ 已实现：数据库唯一性约束防止重复
- ✅ 已实现：检查逻辑会跳过已存在的记录

**验证：**
```sql
-- 检查是否有重复记录
SELECT platform, conversion_id, event_name, COUNT(*) as count
FROM postback_conversions
GROUP BY platform, conversion_id, event_name
HAVING count > 1;
```

### 问题 5：权限错误

**现象：**
- 查询接口返回 403 Forbidden

**原因：**
- 不是管理员账号
- Token 已过期

**解决方案：**
```bash
# 1. 确认是管理员账号
# 2. 重新登录获取新 Token
curl -X POST "https://client.btfrx.online/api/v1/auth/login" \
  -d "username=admin&password=your-password"

# 3. 使用新 Token 访问
curl -X GET "https://client.btfrx.online/api/v1/postback/conversions" \
  -H "Authorization: Bearer NEW_TOKEN"
```

---

## 七、最佳实践

### 7.1 配置建议

1. **使用 HTTPS**
   ```
   ✓ 生产环境必须使用 HTTPS
   ✓ 保护数据传输安全
   ```

2. **配置 IP 白名单**（可选）
   ```
   ✓ 如果 Macan 提供 IP 列表，可以配置白名单
   ✓ 提高安全性
   ```

3. **监控和告警**
   ```
   ✓ 设置日志监控
   ✓ 配置异常告警
   ✓ 定期检查数据一致性
   ```

### 7.2 数据管理

1. **定期备份**
   ```sql
   -- 定期备份 postback_conversions 表
   mysqldump -u user -p database postback_conversions > backup.sql
   ```

2. **数据归档**
   ```
   ✓ 定期归档旧数据
   ✓ 保留重要数据用于分析
   ```

3. **数据清理**
   ```sql
   -- 清理测试数据（谨慎操作）
   DELETE FROM postback_conversions 
   WHERE conversion_id LIKE 'test%';
   ```

---

## 八、完整测试流程

### 端到端测试步骤

**1. 准备测试环境**
```bash
# 确保服务运行
systemctl status Platform-backend.service

# 检查数据库
mysql -u user -p -e "USE database; SELECT COUNT(*) FROM postback_conversions;"
```

**2. 发送测试 Postback**
```bash
# 测试 GET 请求
curl "https://client.btfrx.online/api/v1/postback/macan?clk_id=test001&event_name=purchase&payout=10.5"

# 测试 POST 请求
curl -X POST "https://client.btfrx.online/api/v1/postback/macan" \
  -H "Content-Type: application/json" \
  -d '{"clk_id":"test002","event_name":"purchase","payout":20.5}'
```

**3. 验证数据保存**
```sql
-- 查询测试数据
SELECT * FROM postback_conversions 
WHERE conversion_id IN ('test001', 'test002');
```

**4. 通过 API 查询**
```bash
# 查询转化记录
curl -X GET "https://client.btfrx.online/api/v1/postback/conversions?platform=macan" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**5. 通过前端查看**
- 登录系统
- 进入 Postback 管理
- 查看转化记录

**6. 清理测试数据**
```sql
-- 删除测试数据
DELETE FROM postback_conversions 
WHERE conversion_id LIKE 'test%';
```

---

## 九、总结

### 关键操作步骤

1. ✅ **配置 Macan Postback URL**
2. ✅ **测试接口是否正常**
3. ✅ **监控 Postback 接收情况**
4. ✅ **查看和验证转化数据**
5. ✅ **定期检查数据一致性**

### 重要提醒

- 🔒 **安全性**：生产环境使用 HTTPS
- 📊 **监控**：定期检查日志和数据
- 🔄 **测试**：上线前充分测试
- 📝 **文档**：记录配置信息便于维护

按照以上步骤操作，你就可以完整地使用 Postback 服务了！

