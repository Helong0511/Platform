# Postback 转发成功检查配置 - 超级详细示例

本文档提供各种场景下的详细配置示例，帮助您正确配置转发成功检查规则。

## 目录
1. [HTTP 状态码检查](#http-状态码检查)
2. [关键词检查](#关键词检查)
3. [JSON 检查](#json-检查)
4. [实际场景示例](#实际场景示例)
5. [常见错误配置](#常见错误配置)

---

## HTTP 状态码检查

### 场景 1：使用默认状态码（200-299 为成功）

**配置方式 1：不填写任何配置**
```
（留空）
```

**配置方式 2：明确指定使用状态码检查**
```json
{
  "type": "status_code"
}
```

**说明：**
- 默认行为：HTTP 状态码在 200-299 范围内认为成功
- 适用场景：大多数标准 HTTP API

**实际效果：**
- ✅ 200 OK → 成功
- ✅ 201 Created → 成功
- ✅ 204 No Content → 成功
- ❌ 400 Bad Request → 失败
- ❌ 500 Internal Server Error → 失败

---

### 场景 2：只接受 200 状态码

**配置：**
```json
{
  "type": "status_code",
  "success_status_codes": [200]
}
```

**说明：**
- 只有状态码为 200 时才认为成功
- 其他所有状态码（包括 201、202 等）都认为失败

**实际效果：**
- ✅ 200 OK → 成功
- ❌ 201 Created → 失败
- ❌ 202 Accepted → 失败
- ❌ 204 No Content → 失败
- ❌ 400 Bad Request → 失败

---

### 场景 3：接受多个特定状态码

**配置：**
```json
{
  "type": "status_code",
  "success_status_codes": [200, 201, 202, 204]
}
```

**说明：**
- 状态码为 200、201、202 或 204 时都认为成功
- 其他状态码认为失败

**实际效果：**
- ✅ 200 OK → 成功
- ✅ 201 Created → 成功
- ✅ 202 Accepted → 成功
- ✅ 204 No Content → 成功
- ❌ 400 Bad Request → 失败
- ❌ 500 Internal Server Error → 失败

---

### 场景 4：接受 200 和 201，但拒绝其他 2xx

**配置：**
```json
{
  "type": "status_code",
  "success_status_codes": [200, 201]
}
```

**实际效果：**
- ✅ 200 OK → 成功
- ✅ 201 Created → 成功
- ❌ 202 Accepted → 失败（不在列表中）
- ❌ 204 No Content → 失败（不在列表中）

---

## 关键词检查

### 场景 1：下游只返回 "OK"（精确匹配）

**下游响应：**
```
OK
```

**配置：**
```json
{
  "type": "keyword",
  "success_keywords": ["OK"],
  "exact_match": true
}
```

**说明：**
- `exact_match: true` 表示精确匹配
- 响应文本去除首尾空白后必须完全等于 "OK"（不区分大小写）

**实际效果：**
- ✅ "OK" → 成功
- ✅ "ok" → 成功（不区分大小写）
- ✅ "Ok" → 成功
- ✅ "  OK  " → 成功（去除首尾空白）
- ✅ "OK\n" → 成功（去除首尾空白）
- ❌ "OK success" → 失败（包含其他内容）
- ❌ "Response: OK" → 失败（包含其他内容）
- ❌ "OK\nError" → 失败（包含其他内容）

---

### 场景 2：下游返回包含 "OK" 的文本（包含匹配）

**下游响应示例：**
```
Response: OK
Success: OK
OK received
```

**配置：**
```json
{
  "type": "keyword",
  "success_keywords": ["OK"]
}
```

**说明：**
- 默认 `exact_match: false`，表示包含匹配
- 不区分大小写
- 只要响应文本中包含 "OK" 就认为成功

**实际效果：**
- ✅ "OK" → 成功
- ✅ "ok" → 成功
- ✅ "Response: OK" → 成功（包含 OK）
- ✅ "OK received" → 成功（包含 OK）
- ✅ "Success: ok" → 成功（包含 ok，不区分大小写）
- ❌ "Error occurred" → 失败（不包含 OK）

---

### 场景 3：下游返回多种成功关键词

**下游响应示例：**
```
success
OK
200
```

**配置：**
```json
{
  "type": "keyword",
  "success_keywords": ["success", "OK", "200"]
}
```

**说明：**
- 只要响应中包含任意一个成功关键词就认为成功
- 不区分大小写

**实际效果：**
- ✅ "success" → 成功（匹配 "success"）
- ✅ "OK" → 成功（匹配 "OK"）
- ✅ "200" → 成功（匹配 "200"）
- ✅ "Response: success" → 成功（包含 "success"）
- ✅ "Status: OK" → 成功（包含 "OK"）
- ❌ "Error occurred" → 失败（不包含任何成功关键词）

---

### 场景 4：同时检查成功和失败关键词

**下游响应示例：**
```
success
error
```

**配置：**
```json
{
  "type": "keyword",
  "success_keywords": ["success", "OK"],
  "failure_keywords": ["error", "fail", "failed"]
}
```

**说明：**
- 失败关键词优先级更高
- 如果响应中包含失败关键词，即使也包含成功关键词，仍然认为失败

**实际效果：**
- ✅ "success" → 成功
- ✅ "OK" → 成功
- ❌ "error" → 失败（包含失败关键词）
- ❌ "failed" → 失败（包含失败关键词）
- ❌ "success but error occurred" → 失败（虽然包含 success，但也包含 error）
- ✅ "success without error" → 成功（包含 success，不包含失败关键词）

---

### 场景 5：精确匹配多个关键词（或关系）

**下游响应示例：**
```
OK
SUCCESS
```

**配置：**
```json
{
  "type": "keyword",
  "success_keywords": ["OK", "SUCCESS"],
  "exact_match": true
}
```

**说明：**
- 精确匹配，响应文本必须完全等于列表中的任意一个关键词

**实际效果：**
- ✅ "OK" → 成功（精确匹配 "OK"）
- ✅ "ok" → 成功（不区分大小写）
- ✅ "SUCCESS" → 成功（精确匹配 "SUCCESS"）
- ✅ "success" → 成功（不区分大小写）
- ❌ "OK received" → 失败（不是精确匹配）
- ❌ "Response: OK" → 失败（不是精确匹配）

---

## JSON 检查

### 场景 1：检查 JSON 字段值

**下游响应：**
```json
{
  "status": "ok",
  "message": "success"
}
```

**配置：**
```json
{
  "type": "json",
  "json_path": "status",
  "json_value": "ok"
}
```

**说明：**
- 检查 JSON 响应中 `status` 字段的值
- 如果值等于 "ok"，认为成功

**实际效果：**
- ✅ `{"status": "ok"}` → 成功
- ✅ `{"status": "OK"}` → 失败（区分大小写，但可以配置多个值）
- ❌ `{"status": "error"}` → 失败
- ❌ `{"status": "failed"}` → 失败

---

### 场景 2：检查嵌套 JSON 字段

**下游响应：**
```json
{
  "data": {
    "result": {
      "status": "success"
    }
  }
}
```

**配置：**
```json
{
  "type": "json",
  "json_path": "data.result.status",
  "json_value": "success"
}
```

**说明：**
- 使用点号分隔的路径访问嵌套字段
- 检查 `data.result.status` 的值

**实际效果：**
- ✅ `{"data": {"result": {"status": "success"}}}` → 成功
- ❌ `{"data": {"result": {"status": "error"}}}` → 失败
- ❌ `{"data": {"result": {"status": "failed"}}}` → 失败

---

### 场景 3：只检查字段是否存在（不检查值）

**下游响应：**
```json
{
  "status": "ok"
}
```

**配置：**
```json
{
  "type": "json",
  "json_path": "status"
}
```

**说明：**
- 只配置 `json_path`，不配置 `json_value`
- 只要字段存在且不为空/False/None，就认为成功

**实际效果：**
- ✅ `{"status": "ok"}` → 成功（字段存在且不为空）
- ✅ `{"status": "success"}` → 成功（字段存在且不为空）
- ✅ `{"status": true}` → 成功（字段存在且不为 False）
- ❌ `{"status": false}` → 失败（字段值为 False）
- ❌ `{"status": null}` → 失败（字段值为 null）
- ❌ `{"status": ""}` → 失败（字段值为空字符串）
- ❌ `{"error": "message"}` → 失败（字段不存在）

---

### 场景 4：检查数字类型的值

**下游响应：**
```json
{
  "code": 200,
  "message": "success"
}
```

**配置：**
```json
{
  "type": "json",
  "json_path": "code",
  "json_value": "200"
}
```

**说明：**
- JSON 中的数字会被转换为字符串进行比较
- `"200"` 会匹配数字 `200`

**实际效果：**
- ✅ `{"code": 200}` → 成功（200 转换为 "200" 匹配）
- ✅ `{"code": "200"}` → 成功（字符串 "200" 匹配）
- ❌ `{"code": 201}` → 失败（201 不等于 200）

---

## 实际场景示例

### 场景 1：标准 REST API（返回 JSON）

**下游响应：**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "conversion_id": "12345"
  }
}
```

**配置方案 1：检查 status 字段**
```json
{
  "type": "json",
  "json_path": "status",
  "json_value": "success"
}
```

**配置方案 2：检查 code 字段**
```json
{
  "type": "json",
  "json_path": "code",
  "json_value": "200"
}
```

**配置方案 3：使用 HTTP 状态码（默认）**
```json
{
  "type": "status_code"
}
```

---

### 场景 2：简单文本响应

**下游响应：**
```
OK
```

**配置：**
```json
{
  "type": "keyword",
  "success_keywords": ["OK"],
  "exact_match": true
}
```

---

### 场景 3：包含状态信息的文本响应

**下游响应：**
```
Status: success
Conversion ID: 12345
```

**配置：**
```json
{
  "type": "keyword",
  "success_keywords": ["success"]
}
```

---

### 场景 4：XML 响应（使用关键词检查）

**下游响应：**
```xml
<?xml version="1.0"?>
<response>
  <status>success</status>
  <message>Conversion received</message>
</response>
```

**配置：**
```json
{
  "type": "keyword",
  "success_keywords": ["<status>success</status>", "success"]
}
```

---

### 场景 5：只接受特定 HTTP 状态码的 JSON API

**下游响应：**
```json
{
  "status": "ok"
}
```

**要求：只接受 200 状态码**

**配置：**
```json
{
  "type": "status_code",
  "success_status_codes": [200]
}
```

---

### 场景 6：复杂嵌套 JSON

**下游响应：**
```json
{
  "result": {
    "status": {
      "code": 0,
      "message": "success"
    }
  }
}
```

**配置方案 1：检查 code 字段**
```json
{
  "type": "json",
  "json_path": "result.status.code",
  "json_value": "0"
}
```

**配置方案 2：检查 message 字段**
```json
{
  "type": "json",
  "json_path": "result.status.message",
  "json_value": "success"
}
```

---

## 常见错误配置

### ❌ 错误 1：JSON 格式错误

**错误配置：**
```
type: keyword
success_keywords: [OK]
```

**问题：** 不是有效的 JSON 格式

**正确配置：**
```json
{
  "type": "keyword",
  "success_keywords": ["OK"]
}
```

---

### ❌ 错误 2：缺少必需字段

**错误配置：**
```json
{
  "type": "json"
}
```

**问题：** JSON 检查缺少 `json_path` 字段

**正确配置：**
```json
{
  "type": "json",
  "json_path": "status",
  "json_value": "ok"
}
```

---

### ❌ 错误 3：关键词列表为空

**错误配置：**
```json
{
  "type": "keyword",
  "success_keywords": []
}
```

**问题：** 成功关键词列表为空，无法判断

**正确配置：**
```json
{
  "type": "keyword",
  "success_keywords": ["OK"]
}
```

---

### ❌ 错误 4：状态码列表为空

**错误配置：**
```json
{
  "type": "status_code",
  "success_status_codes": []
}
```

**问题：** 状态码列表为空，会回退到默认行为（200-299）

**正确配置：**
```json
{
  "type": "status_code",
  "success_status_codes": [200, 201]
}
```

---

### ❌ 错误 5：类型拼写错误

**错误配置：**
```json
{
  "type": "keywrod",
  "success_keywords": ["OK"]
}
```

**问题：** `type` 值拼写错误（应该是 "keyword"）

**正确配置：**
```json
{
  "type": "keyword",
  "success_keywords": ["OK"]
}
```

---

## 配置位置

### 渠道（Publisher）转发配置

1. 进入渠道管理页面
2. 编辑渠道
3. 在 `postback_success_check` 字段中填写 JSON 配置

### 产品（Product）转发配置

1. 进入产品管理页面
2. 编辑产品
3. 在 `downstream_postback_success_check` 字段中填写 JSON 配置

---

## 测试建议

1. **先测试简单配置**：从最简单的 HTTP 状态码检查开始
2. **逐步增加复杂度**：确认基本功能正常后，再添加关键词或 JSON 检查
3. **查看日志**：转发失败时，查看日志中的详细错误信息
4. **检查响应内容**：在 `PostbackForwardLog` 表中查看实际的响应内容

---

## 总结

- **HTTP 状态码检查**：适用于标准 HTTP API
- **关键词检查**：适用于文本响应或需要检查响应内容的场景
- **JSON 检查**：适用于 JSON API，需要检查特定字段值
- **组合使用**：可以结合 HTTP 状态码和内容检查，提高准确性

选择合适的检查方式，确保转发成功判断的准确性！

---

## 快速参考表

### HTTP 状态码检查

| 场景 | 配置 | 说明 |
|------|------|------|
| 默认（200-299） | 留空或 `{"type": "status_code"}` | 所有 2xx 状态码为成功 |
| 只接受 200 | `{"type": "status_code", "success_status_codes": [200]}` | 只有 200 为成功 |
| 接受 200 和 201 | `{"type": "status_code", "success_status_codes": [200, 201]}` | 200 或 201 为成功 |

### 关键词检查

| 场景 | 配置 | 说明 |
|------|------|------|
| 精确匹配 "OK" | `{"type": "keyword", "success_keywords": ["OK"], "exact_match": true}` | 响应必须完全等于 "OK" |
| 包含 "OK" | `{"type": "keyword", "success_keywords": ["OK"]}` | 响应包含 "OK" 即可 |
| 多个关键词 | `{"type": "keyword", "success_keywords": ["OK", "success"]}` | 包含任意一个即可 |
| 检查失败关键词 | `{"type": "keyword", "success_keywords": ["OK"], "failure_keywords": ["error"]}` | 包含 "error" 则失败 |

### JSON 检查

| 场景 | 配置 | 说明 |
|------|------|------|
| 检查 status 字段 | `{"type": "json", "json_path": "status", "json_value": "ok"}` | status 字段值必须为 "ok" |
| 检查嵌套字段 | `{"type": "json", "json_path": "data.status", "json_value": "success"}` | 检查 data.status 字段 |
| 只检查存在 | `{"type": "json", "json_path": "status"}` | 只要 status 字段存在且不为空即可 |

---

## 实际业务场景完整示例

### 场景 A：Facebook Postback API

**实际响应：**
```json
{
  "success": true,
  "event_id": "12345"
}
```

**推荐配置：**
```json
{
  "type": "json",
  "json_path": "success",
  "json_value": "true"
}
```

**或者：**
```json
{
  "type": "json",
  "json_path": "success"
}
```
（只检查字段存在，因为 true 不为空）

---

### 场景 B：Google Ads Postback

**实际响应：**
```
200 OK
```

**推荐配置：**
```json
{
  "type": "status_code",
  "success_status_codes": [200]
}
```

**或者（如果响应体是 "OK"）：**
```json
{
  "type": "keyword",
  "success_keywords": ["OK"],
  "exact_match": true
}
```

---

### 场景 C：TikTok Postback

**实际响应：**
```json
{
  "code": 0,
  "message": "success"
}
```

**推荐配置：**
```json
{
  "type": "json",
  "json_path": "code",
  "json_value": "0"
}
```

**说明：** TikTok 通常使用 code=0 表示成功

---

### 场景 D：Snapchat Postback

**实际响应：**
```json
{
  "status": "SUCCESS",
  "data": {
    "conversion_id": "abc123"
  }
}
```

**推荐配置：**
```json
{
  "type": "json",
  "json_path": "status",
  "json_value": "SUCCESS"
}
```

---

### 场景 E：自定义 Postback（简单文本）

**实际响应：**
```
OK
```

**推荐配置：**
```json
{
  "type": "keyword",
  "success_keywords": ["OK"],
  "exact_match": true
}
```

---

### 场景 F：自定义 Postback（包含信息）

**实际响应：**
```
Conversion received: 12345
Status: success
```

**推荐配置：**
```json
{
  "type": "keyword",
  "success_keywords": ["success", "received"]
}
```

---

### 场景 G：复杂 JSON 响应

**实际响应：**
```json
{
  "result": {
    "code": 200,
    "status": "ok",
    "data": {
      "conversion": {
        "id": "12345",
        "status": "processed"
      }
    }
  }
}
```

**配置方案 1：检查 code**
```json
{
  "type": "json",
  "json_path": "result.code",
  "json_value": "200"
}
```

**配置方案 2：检查 status**
```json
{
  "type": "json",
  "json_path": "result.status",
  "json_value": "ok"
}
```

**配置方案 3：检查嵌套 status**
```json
{
  "type": "json",
  "json_path": "result.data.conversion.status",
  "json_value": "processed"
}
```

---

## 调试技巧

### 1. 查看实际响应内容

转发后，在 `PostbackForwardLog` 表中查看：
- `response_status`: HTTP 状态码
- `response_body`: 响应内容（前 2000 字符）
- `success`: 是否成功
- `error_message`: 错误信息（如果失败）

### 2. 测试配置

1. **先使用默认配置**（不填写任何配置）
2. **查看日志**，了解实际响应内容
3. **根据响应内容**，选择合适的检查方式
4. **逐步调整配置**，直到匹配成功

### 3. 常见问题排查

**问题：配置了但总是失败**
- 检查 JSON 格式是否正确
- 检查字段路径是否正确（区分大小写）
- 检查关键词是否匹配（注意大小写，虽然代码不区分，但配置要正确）

**问题：响应是 JSON 但检查失败**
- 检查 `json_path` 是否正确
- 检查 `json_value` 是否匹配（区分大小写）
- 查看日志中的实际响应内容

**问题：关键词检查不匹配**
- 检查 `exact_match` 设置是否正确
- 检查响应文本中是否真的包含关键词
- 查看日志中的实际响应内容

---

## 最佳实践

1. **优先使用 HTTP 状态码检查**：如果下游 API 遵循标准 HTTP 规范，使用状态码检查最简单
2. **JSON 检查更精确**：如果响应是 JSON，使用 JSON 检查比关键词检查更可靠
3. **关键词检查作为备选**：如果响应是文本或 XML，使用关键词检查
4. **配置失败关键词**：如果可能，同时配置失败关键词，提高准确性
5. **测试后再上线**：配置后先测试，确认无误后再应用到生产环境

---

## 配置验证清单

在配置前，请确认：

- [ ] JSON 格式正确（可以使用在线 JSON 验证工具）
- [ ] `type` 字段值正确（"status_code"、"json" 或 "keyword"）
- [ ] 如果使用 JSON 检查，`json_path` 字段已填写
- [ ] 如果使用关键词检查，`success_keywords` 不为空
- [ ] 如果使用状态码检查，`success_status_codes` 不为空（或使用默认）
- [ ] 已查看实际响应内容，确认配置匹配

---

## 联系支持

如果遇到配置问题，请提供：
1. 实际响应内容（从 `PostbackForwardLog` 表获取）
2. 当前配置
3. 错误信息（从日志或 `error_message` 字段获取）

这样可以帮助快速定位问题！
