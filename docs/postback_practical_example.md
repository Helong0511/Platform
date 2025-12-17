# Postback 实战示例 - 手把手操作

## 🎯 实战场景

假设你是一个产品运营，需要追踪通过 Macan 广告平台带来的用户购买转化。

---

## 📝 第一步：在 Macan 平台配置 Postback URL

### 操作步骤（详细版）

**1.1 登录 Macan 平台**

```
1. 打开浏览器
2. 访问：https://macan-native.com/
3. 输入账号密码登录
4. 点击右上角头像 → 进入 Dashboard
```

**1.2 找到 Postback 配置**

```
导航路径：
Dashboard 
  → Campaigns（广告活动）
    → 选择你的 Campaign
      → Settings（设置）
        → Tracking（追踪设置）
          → Postback URL（回调URL）
```

**1.3 填写 Postback URL**

**你的服务器地址：** `https://client.btfrx.online`

**完整的 Postback URL（直接复制使用）：**
```
https://client.btfrx.online/api/v1/postback/macan?clk_id={click_id}&devad_id={gaid/idfa}&event_name={event_id}&event_value={event_value}&carrier={carrier}&os={platform}&payout={payout}
```

**实际操作：**

1. 在 Postback URL 输入框中，**直接复制粘贴**上面的完整 URL
2. **无需修改任何内容**，URL 已经配置好
3. 点击 **Save**（保存）按钮
4. 看到 **"Settings saved successfully"** 提示

**重要提示：**
- URL 中的 `{click_id}`、`{event_id}` 等是 Macan 平台的宏变量
- Macan 会自动将这些变量替换为实际值
- 不要手动修改这些宏变量

**配置截图说明：**
```
┌─────────────────────────────────────────────┐
│ Postback URL Configuration                  │
├─────────────────────────────────────────────┤
│                                             │
│ Postback URL:                               │
│ ┌─────────────────────────────────────────┐ │
│ │ https://client.btfrx.online/api/v1/   │ │
│ │ postback/macan?clk_id={click_id}...   │ │
│ └─────────────────────────────────────────┘ │
│                                             │
│ [Save] [Cancel]                             │
└─────────────────────────────────────────────┘
```

---

## 🧪 第二步：测试 Postback 接口

### 方法 1：使用浏览器测试（最简单）

**操作步骤：**

1. **打开浏览器**（Chrome、Firefox 等）

2. **在地址栏输入以下 URL**：
   ```
   https://client.btfrx.online/api/v1/postback/macan?clk_id=test_browser_001&event_name=purchase&payout=10.5
   ```

3. **按 Enter 键**

4. **查看页面显示的结果**：
   ```json
   {
     "success": true,
     "message": "PostBack 接收成功",
     "conversion_id": "test_browser_001",
     "platform": "macan"
   }
   ```

5. **如果看到上面的 JSON，说明接口正常！** ✅

### 方法 2：使用 curl 命令测试

**在终端（Terminal）中执行：**

```bash
# 测试 GET 请求
curl "https://client.btfrx.online/api/v1/postback/macan?clk_id=test_curl_001&event_name=purchase&event_value=99.99&payout=10.5&os=IOS&carrier=China%20Mobile"
```

**预期输出：**
```json
{
  "success": true,
  "message": "PostBack 接收成功",
  "conversion_id": "test_curl_001",
  "platform": "macan"
}
```

**如果看到错误，检查：**
- 域名是否正确
- 服务器是否运行
- 网络是否连通

### 方法 3：使用 Postman 测试

**操作步骤：**

**3.1 创建新请求**
```
1. 打开 Postman
2. 点击左上角 "New" 按钮
3. 选择 "HTTP Request"
```

**3.2 配置请求**
```
Method: GET
URL: https://client.btfrx.online/api/v1/postback/macan
```

**3.3 添加查询参数**

点击 **Params** 标签，添加以下参数：

| Key | Value |
|-----|-------|
| clk_id | test_postman_001 |
| event_name | purchase |
| event_value | 99.99 |
| payout | 10.5 |
| os | IOS |
| carrier | China Mobile |

**3.4 发送请求**

1. 点击右上角 **Send** 按钮
2. 查看下方 **Response** 区域
3. 应该看到 JSON 响应

**3.5 测试 POST 请求**

1. 将 Method 改为 **POST**
2. 点击 **Body** 标签
3. 选择 **raw** 和 **JSON**
4. 输入以下内容：
   ```json
   {
     "clk_id": "test_postman_002",
     "event_name": "purchase",
     "event_value": 199.99,
     "payout": 20.5,
     "os": "Android",
     "carrier": "China Unicom",
     "product_id": 1,
     "client_id": 1
   }
   ```
5. 点击 **Send**

---

## 📊 第三步：查看转化数据

### 方法 1：通过前端界面查看

**3.1 登录系统**

```
1. 打开浏览器
2. 访问：https://client.btfrx.online
3. 输入管理员账号密码
4. 点击"登录"
```

**3.2 进入 Postback 管理**

```
左侧菜单栏：
  📊 数据仪表
  📄 广告数据
  ...
  🔗 Postback管理  ← 点击这里
```

**3.3 查看数据**

页面会显示：

**顶部统计卡片：**
```
┌─────────────┬─────────────┬─────────────┐
│ MACAN       │             │             │
│ 总转化数: 5 │ 总支付: $50 │ 总价值: $500│
└─────────────┴─────────────┴─────────────┘
```

**转化记录表格：**
```
┌────┬────────┬──────────────────────┬───────────┬─────────┬──────────┐
│ ID │ 平台   │ 转化ID              │ 事件名称  │ 支付金额│ 创建时间│
├────┼────────┼──────────────────────┼───────────┼─────────┼──────────┤
│ 1  │ MACAN  │ test_browser_001    │ purchase  │ $10.50  │ 10:35:00 │
│ 2  │ MACAN  │ test_curl_001       │ purchase  │ $10.50  │ 10:40:00 │
│ 3  │ MACAN  │ test_postman_001    │ purchase  │ $10.50  │ 10:45:00 │
└────┴────────┴──────────────────────┴───────────┴─────────┴──────────┘
```

**3.4 查看详情**

1. 点击表格中任意一行的 **详情** 按钮
2. 弹出对话框显示完整信息：
   ```
   记录ID: 1
   平台: MACAN
   转化ID: test_browser_001
   事件名称: purchase
   事件价值: $99.99
   支付金额: $10.50
   设备ID: ...
   操作系统: IOS
   运营商: China Mobile
   原始数据: {...}
   ```

**3.5 筛选数据**

在页面顶部的筛选表单中：

1. **选择平台**：下拉选择 "Macan"
2. **输入事件名称**：输入 "purchase"
3. **选择时间范围**：选择日期
4. 点击 **查询** 按钮

### 方法 2：通过 API 查询

**3.1 获取管理员 Token**

```bash
# 登录获取 token
curl -X POST "https://client.btfrx.online/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=your_password"

# 响应：
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**3.2 保存 Token**

```bash
# 将 token 保存到变量（Linux/Mac）
export TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

# Windows PowerShell
$TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

**3.3 查询转化记录**

```bash
# 查询所有记录（第一页，每页20条）
curl -X GET "https://client.btfrx.online/api/v1/postback/conversions?page=1&page_size=20" \
  -H "Authorization: Bearer $TOKEN"

# 只查询 Macan 平台的记录
curl -X GET "https://client.btfrx.online/api/v1/postback/conversions?platform=macan&page=1&page_size=20" \
  -H "Authorization: Bearer $TOKEN"

# 查询特定时间范围
curl -X GET "https://client.btfrx.online/api/v1/postback/conversions?start_date=2024-01-01&end_date=2024-01-31" \
  -H "Authorization: Bearer $TOKEN"
```

**3.4 查询统计信息**

```bash
# 获取所有平台统计
curl -X GET "https://client.btfrx.online/api/v1/postback/stats" \
  -H "Authorization: Bearer $TOKEN"

# 响应示例：
{
  "code": 200,
  "message": "成功获取 1 个平台的统计信息",
  "data": [
    {
      "platform": "macan",
      "total_conversions": 5,
      "total_payout": 50.0,
      "total_event_value": 500.0,
      "unique_events": 1
    }
  ]
}
```

### 方法 3：直接查询数据库

**3.1 连接数据库**

```bash
# 使用 MySQL 客户端连接
mysql -u your_username -p your_database_name

# 输入密码后进入 MySQL 命令行
```

**3.2 查询转化记录**

```sql
-- 查看最近的10条记录
SELECT * FROM postback_conversions 
ORDER BY created_at DESC 
LIMIT 10;

-- 查看特定平台的记录
SELECT * FROM postback_conversions 
WHERE platform = 'macan' 
ORDER BY created_at DESC;

-- 统计各平台数据
SELECT 
    platform,
    COUNT(*) as 转化数,
    SUM(payout) as 总支付金额,
    SUM(event_value) as 总事件价值,
    MIN(created_at) as 最早时间,
    MAX(created_at) as 最晚时间
FROM postback_conversions
GROUP BY platform;
```

**3.3 查看原始数据**

```sql
-- 查看某条记录的原始JSON数据
SELECT 
    id,
    platform,
    conversion_id,
    event_name,
    raw_data
FROM postback_conversions 
WHERE id = 1;

-- 格式化查看JSON（MySQL 5.7+）
SELECT 
    id,
    platform,
    conversion_id,
    JSON_PRETTY(raw_data) as formatted_json
FROM postback_conversions 
WHERE id = 1;
```

---

## 🔄 完整实战流程示例

### 场景：真实用户购买流程

#### 时间线：2024-01-15 10:30:00 - 10:35:00

**10:30:00 - 用户看到广告**

```
用户操作：
- 用户在 Macan 平台的 App 中浏览
- 看到你的产品广告："限时优惠，立即购买！"
- 广告显示价格：$99.99

Macan 平台记录：
- 生成 click_id: macan_real_20240115_103000_abc123
- 记录设备信息：iPhone 14 Pro, iOS 17.0
- 记录运营商：China Mobile
- 记录渠道：macan_channel_001
```

**10:30:05 - 用户点击广告**

```
用户操作：
- 用户点击"立即购买"按钮

技术流程：
1. Macan 捕获点击事件
2. 生成追踪链接：
   https://your-product.com/app?
     click_id=macan_real_20240115_103000_abc123&
     ios_idfa=12345678-ABCD-EFGH-IJKL-123456789012&
     source=macan_channel_001

3. 浏览器跳转到你的产品页面
```

**10:30:10 - 用户浏览产品**

```
用户操作：
- 在产品页面浏览商品详情
- 查看价格、功能说明
- 决定购买

产品服务器记录：
- 记录访问日志
- 保存 click_id: macan_real_20240115_103000_abc123
- 记录用户行为
```

**10:35:00 - 用户完成购买**

```
用户操作：
1. 点击"立即购买"
2. 选择支付方式：信用卡
3. 输入支付信息
4. 确认支付
5. 支付成功！

产品服务器记录订单：
{
  "order_id": "ORD202401151035001",
  "user_id": "user_12345",
  "product_id": 1,
  "amount": 99.99,
  "currency": "USD",
  "payment_status": "paid",
  "click_id": "macan_real_20240115_103000_abc123",
  "device_id": "12345678-ABCD-EFGH-IJKL-123456789012",
  "timestamp": "2024-01-15 10:35:00"
}
```

**10:35:05 - Macan 检测到转化**

```
Macan 平台操作：
1. 检测到用户完成了购买
2. 匹配 click_id: macan_real_20240115_103000_abc123
3. 计算收益：$10.50（Macan 的佣金）
4. 准备发送 Postback
```

**10:35:10 - Macan 发送 Postback**

```
Macan 平台自动执行：

GET 请求：
GET https://client.btfrx.online/api/v1/postback/macan?
  clk_id=macan_real_20240115_103000_abc123&
  event_name=purchase&
  event_value=99.99&
  payout=10.5&
  devad_id=12345678-ABCD-EFGH-IJKL-123456789012&
  os=IOS&
  carrier=China%20Mobile&
  gid=macan_channel_001

HTTP 请求头：
Host: client.btfrx.online
User-Agent: Macan-Server/1.0
X-Forwarded-For: 123.456.789.0
```

**10:35:11 - 我们的服务器接收**

```
服务器日志记录：
[2024-01-15 10:35:11] INFO: 接收到 Postback 请求
  Method: GET
  Path: /api/v1/postback/macan
  Platform: macan
  Conversion ID: macan_real_20240115_103000_abc123
```

**10:35:12 - 数据验证**

```
处理流程：
1. 路由匹配：/postback/{platform} → platform = "macan"
2. 获取处理器：MacanPostbackHandler
3. 验证数据：
   - clk_id 存在？✓
   - event_name 存在？✓
   - 数据格式正确？✓
```

**10:35:13 - 数据标准化**

```
标准化过程：
原始数据：
{
  "clk_id": "macan_real_20240115_103000_abc123",
  "event_name": "purchase",
  ...
}

标准化后：
{
  "conversion_id": "macan_real_20240115_103000_abc123",
  "event_name": "purchase",
  "event_value": 99.99,
  "payout": 10.5,
  ...
}
```

**10:35:14 - 检查重复**

```
数据库查询：
SELECT * FROM postback_conversions 
WHERE platform = 'macan' 
  AND conversion_id = 'macan_real_20240115_103000_abc123'
  AND event_name = 'purchase';

结果：0 条记录（不存在，继续处理）
```

**10:35:15 - 保存数据库**

```
SQL 执行：
INSERT INTO postback_conversions (
  platform, conversion_id, event_name, event_value, 
  payout, devad_id, os, carrier, gid, raw_data, created_at
) VALUES (
  'macan', 
  'macan_real_20240115_103000_abc123',
  'purchase',
  99.99,
  10.5,
  '12345678-ABCD-EFGH-IJKL-123456789012',
  'IOS',
  'China Mobile',
  'macan_channel_001',
  '{"clk_id":"macan_real_20240115_103000_abc123",...}',
  '2024-01-15 10:35:15'
);

结果：成功插入，ID = 123
```

**10:35:16 - 返回成功响应**

```
HTTP 响应：
Status: 200 OK
Content-Type: application/json

{
  "success": true,
  "message": "PostBack 接收成功",
  "conversion_id": "macan_real_20240115_103000_abc123",
  "platform": "macan"
}
```

**10:35:17 - 记录日志**

```
日志文件记录：
[2024-01-15 10:35:17] INFO: 平台 macan postback 转化记录已保存: 
  conversion_id=macan_real_20240115_103000_abc123, 
  event_name=purchase, 
  payout=10.5, 
  product_id=None, 
  client_id=None
```

**10:36:00 - 查看转化数据**

```
操作步骤：
1. 登录系统
2. 进入 Postback 管理
3. 在表格中看到新记录：

┌────┬────────┬──────────────────────────────────┬───────────┬─────────┬──────────────────┐
│ ID │ 平台   │ 转化ID                          │ 事件名称  │ 支付金额│ 创建时间         │
├────┼────────┼──────────────────────────────────┼───────────┼─────────┼──────────────────┤
│123 │ MACAN  │ macan_real_20240115_103000_abc123│ purchase  │ $10.50  │ 2024-01-15 10:35 │
└────┴────────┴──────────────────────────────────┴───────────┴─────────┴──────────────────┘

4. 点击"详情"查看完整信息
```

---

## 🛠️ 实际操作检查清单

### 配置阶段

- [ ] 1. 确认服务器地址和域名
- [ ] 2. 测试服务器连通性
- [ ] 3. 在 Macan 平台配置 Postback URL
- [ ] 4. 配置 Click Tracker（点击追踪）
- [ ] 5. 保存配置并确认

### 测试阶段

- [ ] 1. 使用浏览器测试 GET 请求
- [ ] 2. 使用 curl 测试 GET 请求
- [ ] 3. 使用 Postman 测试 POST 请求
- [ ] 4. 检查服务器日志
- [ ] 5. 验证数据是否保存到数据库

### 验证阶段

- [ ] 1. 通过前端界面查看转化记录
- [ ] 2. 通过 API 查询转化记录
- [ ] 3. 直接查询数据库验证
- [ ] 4. 检查数据完整性
- [ ] 5. 验证统计信息

### 上线阶段

- [ ] 1. 确认生产环境配置正确
- [ ] 2. 设置监控和告警
- [ ] 3. 准备应急处理方案
- [ ] 4. 文档化配置信息
- [ ] 5. 通知相关人员

---

## 💡 实用技巧

### 技巧 1：快速测试命令

创建一个测试脚本 `test_postback.sh`：

```bash
#!/bin/bash

DOMAIN="https://client.btfrx.online"
CLICK_ID="test_$(date +%s)"

echo "测试 Postback GET 请求..."
curl -X GET "${DOMAIN}/api/v1/postback/macan?clk_id=${CLICK_ID}&event_name=purchase&payout=10.5"

echo -e "\n\n测试 Postback POST 请求..."
curl -X POST "${DOMAIN}/api/v1/postback/macan" \
  -H "Content-Type: application/json" \
  -d "{
    \"clk_id\": \"${CLICK_ID}_post\",
    \"event_name\": \"purchase\",
    \"payout\": 20.5
  }"

echo -e "\n\n测试完成！"
```

使用方法：
```bash
chmod +x test_postback.sh
./test_postback.sh
```

### 技巧 2：监控 Postback 接收

创建一个监控脚本 `monitor_postback.sh`：

```bash
#!/bin/bash

# 监控最近的 Postback 日志
tail -f logs/app.log | grep --line-buffered "postback"

# 或者监控数据库
watch -n 5 'mysql -u user -p -e "SELECT COUNT(*) FROM postback_conversions WHERE created_at > DATE_SUB(NOW(), INTERVAL 1 HOUR);"'
```

### 技巧 3：快速查询转化数据

创建查询脚本 `query_conversions.sh`：

```bash
#!/bin/bash

TOKEN="your_token_here"
DOMAIN="https://client.btfrx.online"

# 查询最近的转化记录
curl -X GET "${DOMAIN}/api/v1/postback/conversions?page=1&page_size=10" \
  -H "Authorization: Bearer ${TOKEN}" | jq '.'

# 查询统计信息
curl -X GET "${DOMAIN}/api/v1/postback/stats" \
  -H "Authorization: Bearer ${TOKEN}" | jq '.'
```

---

## 📞 需要帮助？

如果遇到问题：

1. **查看日志**：`tail -f logs/app.log`
2. **检查数据库**：确认数据是否保存
3. **测试接口**：使用 curl 或 Postman 测试
4. **查看文档**：参考 `docs/postback_service.md`

按照以上步骤操作，你就能完整地使用 Postback 服务了！🎉

