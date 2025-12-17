# Postback 快速开始指南

## 🚀 5分钟快速配置

### 第一步：在 Macan 平台配置 Postback URL

**完整 URL（直接复制使用）：**
```
https://client.btfrx.online/api/v1/postback/macan?clk_id={click_id}&devad_id={gaid/idfa}&event_name={event_id}&event_value={event_value}&carrier={carrier}&os={platform}&payout={payout}
```

**操作步骤：**
1. 登录 Macan 平台：https://macan-native.com/
2. 进入 Campaign → Settings → Postback URL
3. **直接复制粘贴**上面的完整 URL
4. 点击保存

**重要提示：**
- URL 中的 `{click_id}`、`{event_id}` 等是 Macan 的宏变量，会自动替换
- **不要修改**这些宏变量
- **不要修改**域名部分

---

### 第二步：测试接口（可选但推荐）

**方法 1：浏览器测试（最简单）**

在浏览器地址栏输入：
```
https://client.btfrx.online/api/v1/postback/macan?clk_id=test001&event_name=purchase&payout=10.5
```

**应该看到：**
```json
{
  "success": true,
  "message": "PostBack 接收成功",
  "conversion_id": "test001",
  "platform": "macan"
}
```

**方法 2：curl 命令测试**

```bash
curl "https://client.btfrx.online/api/v1/postback/macan?clk_id=test002&event_name=purchase&payout=20.5"
```

---

### 第三步：查看转化数据

**通过前端查看：**
1. 访问：https://client.btfrx.online
2. 使用管理员账号登录
3. 点击左侧菜单 **"Postback管理"**
4. 查看转化记录和统计信息

**通过 API 查看：**
```bash
# 1. 登录获取 Token
curl -X POST "https://client.btfrx.online/api/v1/auth/login" \
  -d "username=admin&password=your_password"

# 2. 查询转化记录（使用获取的 Token）
curl -X GET "https://client.btfrx.online/api/v1/postback/conversions?platform=macan" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 📋 完整配置清单

### Macan 平台配置

- [ ] 登录 Macan 平台
- [ ] 找到 Postback URL 配置位置
- [ ] 填写 Postback URL：
  ```
  https://client.btfrx.online/api/v1/postback/macan?clk_id={click_id}&devad_id={gaid/idfa}&event_name={event_id}&event_value={event_value}&carrier={carrier}&os={platform}&payout={payout}
  ```
- [ ] 保存配置
- [ ] 测试接口是否正常

### 验证配置

- [ ] 使用浏览器测试 GET 请求
- [ ] 使用 curl 测试 POST 请求
- [ ] 检查服务器日志
- [ ] 验证数据是否保存到数据库
- [ ] 通过前端查看转化记录

---

## 🎯 实际使用示例

### 真实场景：用户购买流程

**1. 用户在 Macan 看到广告并点击**
```
Macan 生成：click_id = macan_abc123
```

**2. 用户在你的产品中完成购买**
```
订单金额：$99.99
```

**3. Macan 自动发送 Postback**
```
GET https://client.btfrx.online/api/v1/postback/macan?
  clk_id=macan_abc123&
  event_name=purchase&
  event_value=99.99&
  payout=10.5
```

**4. 系统自动保存数据**
```
✅ 数据已保存到数据库
✅ 可以在 Postback管理 页面查看
```

---

## 🔍 快速测试命令

### 测试 GET 请求
```bash
curl "https://client.btfrx.online/api/v1/postback/macan?clk_id=quick_test&event_name=purchase&payout=5.5"
```

### 测试 POST 请求
```bash
curl -X POST "https://client.btfrx.online/api/v1/postback/macan" \
  -H "Content-Type: application/json" \
  -d '{"clk_id":"quick_test_post","event_name":"purchase","payout":15.5}'
```

### 查询转化记录（需要 Token）
```bash
# 先登录获取 Token
TOKEN=$(curl -s -X POST "https://client.btfrx.online/api/v1/auth/login" \
  -d "username=admin&password=your_password" | jq -r '.access_token')

# 查询记录
curl -X GET "https://client.btfrx.online/api/v1/postback/conversions?platform=macan" \
  -H "Authorization: Bearer $TOKEN"
```

---

## ❓ 常见问题

### Q1: 如何确认 Postback 是否配置成功？

**A:** 在 Macan 平台配置后，等待真实的转化事件，或者手动发送测试请求。

### Q2: 如何查看是否收到了 Postback？

**A:** 
1. 查看服务器日志：`tail -f logs/app.log | grep postback`
2. 登录系统查看 Postback管理页面
3. 直接查询数据库：`SELECT * FROM postback_conversions ORDER BY created_at DESC LIMIT 10;`

### Q3: Postback 没有收到怎么办？

**A:** 
1. 检查 Macan 平台的 URL 配置是否正确
2. 测试接口是否可访问：`curl "https://client.btfrx.online/api/v1/postback/macan?clk_id=test&event_name=test"`
3. 查看服务器日志排查错误

---

## 📚 更多文档

- **详细操作指南**：`docs/postback_operation_guide.md`
- **实战示例**：`docs/postback_practical_example.md`
- **原理说明**：`docs/postback_principle.md`
- **服务文档**：`docs/postback_service.md`

---

## ✅ 配置完成检查

配置完成后，你应该能够：

- ✅ 在 Macan 平台看到 Postback URL 已保存
- ✅ 使用浏览器测试接口返回成功
- ✅ 在系统中看到测试转化记录
- ✅ 真实转化事件能正常接收和存储

**如果以上都正常，说明配置成功！** 🎉

