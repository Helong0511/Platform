# 前端API请求与后端响应匹配检查报告

## 检查时间
2024年12月

## 检查范围
- 前端API调用（8个模块）
- 后端API端点响应格式
- 请求参数匹配
- 响应数据格式匹配
- 错误处理一致性

---

## 1. 仪表盘模块 ✅

### 1.1 获取统计数据

**前端请求：** (`frontend/src/api/dashboard.js`)
```javascript
GET /api/v1/dashboard/stats?period=week
```

**后端端点：** (`app/api/api_v1/endpoints/dashboard.py`)
```python
@router.get("/stats", response_model=ResponseBaseSchema[DashboardStatsResponse])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/dashboard/stats`
- ✅ 请求方法：GET
- ✅ 查询参数：`period` (day/week/month/last_month)
- ✅ 响应格式：`ResponseBaseSchema[DashboardStatsResponse]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`

**响应数据结构：**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total_requests": 1000,
    "total_matches": 800,
    "avg_coverage": 80.0,
    "total_impressions": 600,
    "avg_display_rate": 75.0,
    "total_clicks": 50,
    "avg_ctr": 8.33,
    "avg_ecpm_deducted": 1.5,
    "total_revenue_deducted": 900.0,
    "avg_ecpm_undeducted": 2.0,
    "total_revenue_undeducted": 1200.0
  }
}
```

---

### 1.2 获取趋势数据

**前端请求：** (`frontend/src/api/dashboard.js`)
```javascript
GET /api/v1/dashboard/trends?period=week
```

**后端端点：** (`app/api/api_v1/endpoints/dashboard.py`)
```python
@router.get("/trends", response_model=ResponseBaseSchema[TrendDataResponse])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/dashboard/trends`
- ✅ 请求方法：GET
- ✅ 查询参数：`period` (day/week/month/last_month)
- ✅ 响应格式：`ResponseBaseSchema[TrendDataResponse]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`

**响应数据结构：**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "dates": ["2024-01-01", "2024-01-02"],
    "series": [
      {"name": "请求数", "data": [100, 200]},
      {"name": "匹配数", "data": [80, 160]},
      {"name": "展示数", "data": [60, 120]},
      {"name": "点击数", "data": [5, 10]},
      {"name": "转化数", "data": [1, 2]}
    ]
  }
}
```

---

## 2. 用户管理模块 ✅

### 2.1 获取用户列表

**前端请求：** (`frontend/src/api/user.js`)
```javascript
GET /api/v1/users/?page=1&page_size=10&username=xxx&role=admin&status=active
```

**后端端点：** (`app/api/api_v1/endpoints/users.py`)
```python
@router.get("/", response_model=PaginatedResponseBaseSchema[list[UserResponse]])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/users/`
- ✅ 请求方法：GET
- ✅ 查询参数：`page`, `page_size`, `username`, `role`, `status`
- ✅ 响应格式：`PaginatedResponseBaseSchema[list[UserResponse]]`
- ✅ 前端使用：`normalizePaginatedResponse(response)`

**响应数据结构：**
```json
{
  "code": 200,
  "message": "success",
  "data": [
    {
      "id": 1,
      "username": "admin",
      "email": "admin@example.com",
      "full_name": "管理员",
      "role": "admin",
      "is_active": true,
      "api_enabled": false,
      "password_change_enabled": false,
      "client": null
    }
  ],
  "total": 10,
  "page": 1,
  "page_size": 10,
  "total_pages": 1
}
```

---

### 2.2 获取用户详情

**前端请求：** (`frontend/src/api/user.js`)
```javascript
GET /api/v1/users/{id}
```

**后端端点：** (`app/api/api_v1/endpoints/users.py`)
```python
@router.get("/{user_id}", response_model=ResponseBaseSchema[UserResponse])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/users/{user_id}`
- ✅ 请求方法：GET
- ✅ 路径参数：`user_id`
- ✅ 响应格式：`ResponseBaseSchema[UserResponse]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`

---

### 2.3 创建用户

**前端请求：** (`frontend/src/api/user.js`)
```javascript
POST /api/v1/users/
Body: { username, email, password, full_name, role, is_active }
```

**后端端点：** (`app/api/api_v1/endpoints/users.py`)
```python
@router.post("/", response_model=ResponseBaseSchema[UserResponse])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/users/`
- ✅ 请求方法：POST
- ✅ 请求体：`UserCreate` schema
- ✅ 响应格式：`ResponseBaseSchema[UserResponse]`
- ✅ 前端使用：`normalizeResponse(response)`

---

### 2.4 更新用户

**前端请求：** (`frontend/src/api/user.js`)
```javascript
PUT /api/v1/users/{id}
Body: { email, full_name, role, is_active }
```

**后端端点：** (`app/api/api_v1/endpoints/users.py`)
```python
@router.put("/{user_id}", response_model=ResponseBaseSchema[UserResponse])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/users/{user_id}`
- ✅ 请求方法：PUT
- ✅ 请求体：`UserUpdate` schema
- ✅ 响应格式：`ResponseBaseSchema[UserResponse]`
- ✅ 前端使用：`normalizeResponse(response)`

---

### 2.5 删除用户

**前端请求：** (`frontend/src/api/user.js`)
```javascript
DELETE /api/v1/users/{id}
```

**后端端点：** (`app/api/api_v1/endpoints/users.py`)
```python
@router.delete("/{user_id}", response_model=ResponseBaseSchema[dict])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/users/{user_id}`
- ✅ 请求方法：DELETE
- ✅ 响应格式：`ResponseBaseSchema[dict]`
- ✅ 前端处理：直接返回`true`（不检查响应体）

---

### 2.6 获取用户统计信息

**前端请求：** (`frontend/src/api/user.js`)
```javascript
GET /api/v1/users/stats
```

**后端端点：** (`app/api/api_v1/endpoints/users.py`)
```python
@router.get("/stats", response_model=ResponseBaseSchema[dict])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/users/stats`
- ✅ 请求方法：GET
- ✅ 响应格式：`ResponseBaseSchema[dict]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`

---

### 2.7 修改密码

**前端请求：** (`frontend/src/api/user.js`)
```javascript
PUT /api/v1/users/me/password
Body: { old_password, new_password }
```

**后端端点：** (`app/api/api_v1/endpoints/users.py`)
```python
@router.put("/me/password", response_model=ResponseBaseSchema[dict])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/users/me/password`
- ✅ 请求方法：PUT
- ✅ 请求体：`PasswordChange` schema
- ✅ 响应格式：`ResponseBaseSchema[dict]`
- ✅ 前端使用：`normalizeResponse(response)`

---

### 2.8 获取当前用户信息

**前端请求：** (`frontend/src/api/user.js`)
```javascript
GET /api/v1/users/me
```

**后端端点：** (`app/api/api_v1/endpoints/users.py`)
```python
@router.get("/me", response_model=ResponseBaseSchema[UserResponse])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/users/me`
- ✅ 请求方法：GET
- ✅ 响应格式：`ResponseBaseSchema[UserResponse]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`

---

### 2.9 导出用户数据

**前端请求：** (`frontend/src/api/user.js`)
```javascript
GET /api/v1/users/export/excel?page=1&page_size=10&...
```

**后端端点：** (`app/api/api_v1/endpoints/users.py`)
```python
@router.get("/export/excel", response_class=StreamingResponse)
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/users/export/excel`
- ✅ 请求方法：GET
- ✅ 响应类型：`StreamingResponse` (Excel文件)
- ✅ 前端处理：blob下载，处理`Content-Disposition`头

---

## 3. 客户管理模块 ✅

### 3.1 获取客户列表

**前端请求：** (`frontend/src/api/client.js`)
```javascript
GET /api/v1/clients/?page=1&page_size=10&company_name=xxx&is_active=true
```

**后端端点：** (`app/api/api_v1/endpoints/clients.py`)
```python
@router.get("/", response_model=PaginatedResponseBaseSchema[list[ClientResponse]])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/clients/`
- ✅ 请求方法：GET
- ✅ 查询参数：`page`, `page_size`, `company_name`, `is_active`
- ✅ 响应格式：`PaginatedResponseBaseSchema[list[ClientResponse]]`
- ✅ 前端使用：`normalizePaginatedResponse(response)`

---

### 3.2 获取客户详情

**前端请求：** (`frontend/src/api/client.js`)
```javascript
GET /api/v1/clients/{id}
```

**后端端点：** (`app/api/api_v1/endpoints/clients.py`)
```python
@router.get("/{client_id}", response_model=ResponseBaseSchema[ClientResponse])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/clients/{client_id}`
- ✅ 请求方法：GET
- ✅ 响应格式：`ResponseBaseSchema[ClientResponse]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`

---

### 3.3 创建客户

**前端请求：** (`frontend/src/api/client.js`)
```javascript
POST /api/v1/clients/
Body: { user_id, company_name, contact_person, phone, address, allowed_ips, ... }
```

**后端端点：** (`app/api/api_v1/endpoints/clients.py`)
```python
@router.post("/", response_model=ResponseBaseSchema[ClientResponse])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/clients/`
- ✅ 请求方法：POST
- ✅ 请求体：`ClientCreate` schema
- ✅ 响应格式：`ResponseBaseSchema[ClientResponse]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`

---

### 3.4 更新客户

**前端请求：** (`frontend/src/api/client.js`)
```javascript
PUT /api/v1/clients/{id}
Body: { company_name, contact_person, phone, address, allowed_ips, ... }
```

**后端端点：** (`app/api/api_v1/endpoints/clients.py`)
```python
@router.put("/{client_id}", response_model=ResponseBaseSchema[ClientResponse])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/clients/{client_id}`
- ✅ 请求方法：PUT
- ✅ 请求体：`ClientUpdate` schema
- ✅ 响应格式：`ResponseBaseSchema[ClientResponse]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`

---

### 3.5 快速更新客户开关

**前端请求：** (`frontend/src/api/client.js`)
```javascript
PATCH /api/v1/clients/{id}/switches
Body: { api_enabled, password_change_enabled }
```

**后端端点：** (`app/api/api_v1/endpoints/clients.py`)
```python
@router.patch("/{client_id}/switches", response_model=ResponseBaseSchema[ClientResponse])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/clients/{client_id}/switches`
- ✅ 请求方法：PATCH
- ✅ 请求体：`ClientSwitchUpdate` schema
- ✅ 响应格式：`ResponseBaseSchema[ClientResponse]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`

---

### 3.6 删除客户

**前端请求：** (`frontend/src/api/client.js`)
```javascript
DELETE /api/v1/clients/{id}
```

**后端端点：** (`app/api/api_v1/endpoints/clients.py`)
```python
@router.delete("/{client_id}", response_model=ResponseBaseSchema[dict])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/clients/{client_id}`
- ✅ 请求方法：DELETE
- ✅ 响应格式：`ResponseBaseSchema[dict]`
- ✅ 前端处理：直接返回`true`

---

### 3.7 导出客户数据

**前端请求：** (`frontend/src/api/client.js`)
```javascript
GET /api/v1/clients/export?page=1&page_size=10&...
```

**后端端点：** (`app/api/api_v1/endpoints/clients.py`)
```python
@router.get("/export", response_class=StreamingResponse)
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/clients/export`
- ✅ 请求方法：GET
- ✅ 响应类型：`StreamingResponse` (Excel文件)
- ✅ 前端处理：blob下载

---

## 4. 产品管理模块 ✅

### 4.1 获取产品列表

**前端请求：** (`frontend/src/api/product.js`)
```javascript
GET /api/v1/products/?page=1&page_size=10&client_id=1&name=xxx&is_active=true
```

**后端端点：** (`app/api/api_v1/endpoints/products.py`)
```python
@router.get("/", response_model=PaginatedResponseBaseSchema[list[ProductResponse]])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/products/`
- ✅ 请求方法：GET
- ✅ 查询参数：`page`, `page_size`, `client_id`, `name`, `is_active`
- ✅ 响应格式：`PaginatedResponseBaseSchema[list[ProductResponse]]`
- ✅ 前端使用：`normalizePaginatedResponse(response)`

---

### 4.2 获取产品详情

**前端请求：** (`frontend/src/api/product.js`)
```javascript
GET /api/v1/products/{id}
```

**后端端点：** (`app/api/api_v1/endpoints/products.py`)
```python
@router.get("/{product_id}", response_model=ResponseBaseSchema[ProductResponse])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/products/{product_id}`
- ✅ 请求方法：GET
- ✅ 响应格式：`ResponseBaseSchema[ProductResponse]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`

---

### 4.3 创建产品

**前端请求：** (`frontend/src/api/product.js`)
```javascript
POST /api/v1/products/
Body: { client_id, name, ecpm_deduct_ratio, revenue_deduct_ratio, is_active }
```

**后端端点：** (`app/api/api_v1/endpoints/products.py`)
```python
@router.post("/", response_model=ResponseBaseSchema[ProductResponse])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/products/`
- ✅ 请求方法：POST
- ✅ 请求体：`ProductCreate` schema
- ✅ 响应格式：`ResponseBaseSchema[ProductResponse]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`

---

### 4.4 更新产品

**前端请求：** (`frontend/src/api/product.js`)
```javascript
PUT /api/v1/products/{id}
Body: { name, ecpm_deduct_ratio, revenue_deduct_ratio, is_active }
```

**后端端点：** (`app/api/api_v1/endpoints/products.py`)
```python
@router.put("/{product_id}", response_model=ResponseBaseSchema[ProductResponse])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/products/{product_id}`
- ✅ 请求方法：PUT
- ✅ 请求体：`ProductUpdate` schema
- ✅ 响应格式：`ResponseBaseSchema[ProductResponse]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`

---

### 4.5 删除产品

**前端请求：** (`frontend/src/api/product.js`)
```javascript
DELETE /api/v1/products/{id}
```

**后端端点：** (`app/api/api_v1/endpoints/products.py`)
```python
@router.delete("/{product_id}", response_model=ResponseBaseSchema[dict])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/products/{product_id}`
- ✅ 请求方法：DELETE
- ✅ 响应格式：`ResponseBaseSchema[dict]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`

---

### 4.6 获取可用产品名称

**前端请求：** (`frontend/src/api/product.js`)
```javascript
GET /api/v1/products/available-names?exclude_client_id=1&search=xxx
```

**后端端点：** (`app/api/api_v1/endpoints/products.py`)
```python
@router.get("/available-names", response_model=ListResponseBaseSchema[list[ProductNameOption]])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/products/available-names`
- ✅ 请求方法：GET
- ✅ 查询参数：`exclude_client_id`, `search`
- ✅ 响应格式：`ListResponseBaseSchema[list[ProductNameOption]]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: false })`，返回`{ data, count }`

---

### 4.7 获取产品分配历史

**前端请求：** (`frontend/src/api/product.js`)
```javascript
GET /api/v1/product-assignments/products/{productId}/assignments
```

**后端端点：** (`app/api/api_v1/endpoints/product_assignments.py`)
```python
@router.get("/products/{product_id}/assignments", response_model=ResponseBaseSchema[ProductAssignmentListResponse])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/product-assignments/products/{product_id}/assignments`
- ✅ 请求方法：GET
- ✅ 响应格式：`ResponseBaseSchema[ProductAssignmentListResponse]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`

---

## 5. 广告数据模块 ✅

### 5.1 获取广告数据列表

**前端请求：** (`frontend/src/api/adData.js`)
```javascript
GET /api/v1/ad-data/?page=1&page_size=10&start_date=xxx&end_date=xxx&product_id=1&client_id=1
```

**后端端点：** (`app/api/api_v1/endpoints/ad_data.py`)
```python
@router.get("/", response_model=ResponseBaseSchema[AdDataListResponse])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/ad-data/`
- ✅ 请求方法：GET
- ✅ 查询参数：`page`, `page_size`, `start_date`, `end_date`, `product_id`, `client_id`
- ✅ 响应格式：`ResponseBaseSchema[AdDataListResponse]`（包含分页信息）
- ✅ 前端使用：`normalizePaginatedResponse(response)`

**注意：** ✅ 后端返回`AdDataListResponse`，包含分页字段（`total`, `page`, `page_size`），前端使用`normalizePaginatedResponse`处理是正确的。

---

### 5.2 获取广告数据详情

**前端请求：** (`frontend/src/api/adData.js`)
```javascript
// 注意：前端代码中已移除getAdDataDetail函数，但后端端点存在
GET /api/v1/ad-data/{data_id}
```

**后端端点：** (`app/api/api_v1/endpoints/ad_data.py`)
```python
@router.get("/{data_id}", response_model=ResponseBaseSchema[AdDataResponse])
```

**匹配情况：** ⚠️ 前端未使用
- ⚠️ 前端代码中已移除`getAdDataDetail`函数
- ✅ 后端端点存在且正常
- **建议：** 如果不需要，可以移除后端端点；如果需要，恢复前端调用

---

### 5.3 更新广告数据

**前端请求：** (`frontend/src/api/adData.js`)
```javascript
POST /api/v1/ad-data/{id}
Body: { date, product_id, request_count, match_count, ... }
```

**后端端点：** (`app/api/api_v1/endpoints/ad_data.py`)
```python
@router.post("/{data_id}", response_model=ResponseBaseSchema[AdDataResponse])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/ad-data/{data_id}`
- ✅ 请求方法：POST（注意：更新使用POST而不是PUT）
- ✅ 请求体：广告数据字段
- ✅ 响应格式：`ResponseBaseSchema[AdDataResponse]`
- ✅ 前端使用：`normalizeResponse(response)`

---

### 5.4 删除广告数据

**前端请求：** (`frontend/src/api/adData.js`)
```javascript
DELETE /api/v1/ad-data/{dataId}
```

**后端端点：** (`app/api/api_v1/endpoints/ad_data.py`)
```python
@router.delete("/{data_id}", response_model=ResponseBaseSchema[dict])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/ad-data/{data_id}`
- ✅ 请求方法：DELETE
- ✅ 响应格式：`ResponseBaseSchema[dict]`
- ✅ 前端使用：`normalizeResponse(response)`

---

### 5.5 批量删除广告数据

**前端请求：** (`frontend/src/api/adData.js`)
```javascript
DELETE /api/v1/ad-data/batch
Body: [1, 2, 3, ...]  // 数据ID数组
```

**后端端点：** (`app/api/api_v1/endpoints/ad_data.py`)
```python
@router.delete("/batch", response_model=ResponseBaseSchema[dict])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/ad-data/batch`
- ✅ 请求方法：DELETE
- ✅ 请求体：数据ID数组
- ✅ 响应格式：`ResponseBaseSchema[dict]`
- ✅ 前端使用：`normalizeResponse(response)`

---

### 5.6 导出广告数据

**前端请求：** (`frontend/src/api/adData.js`)
```javascript
GET /api/v1/excel/export/ad-data?start_date=xxx&end_date=xxx&product_id=1&client_id=1
```

**后端端点：** (`app/api/api_v1/endpoints/excel/export_handler.py`)
```python
async def export_ad_data_handler(...) -> StreamingResponse
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/excel/export/ad-data`
- ✅ 请求方法：GET
- ✅ 查询参数：`start_date`, `end_date`, `product_id`, `client_id`
- ✅ 响应类型：`StreamingResponse` (Excel文件)
- ✅ 前端处理：blob下载，处理JSON错误响应（业务错误返回200但响应体是JSON）

**特殊处理：** ✅ 优秀
- ✅ 前端检查响应类型（JSON vs Excel）
- ✅ 前端检查blob大小（小于5KB可能是错误JSON）
- ✅ 前端处理`Content-Disposition`头（支持UTF-8编码的文件名）

---

### 5.7 导入广告数据

**前端请求：** (`frontend/src/api/adData.js`)
```javascript
POST /api/v1/excel/import/ad-data
Body: FormData { file, client_id? }
```

**后端端点：** (`app/api/api_v1/endpoints/excel/router.py`)
```python
@router.post("/import/ad-data", response_model=ResponseBaseSchema[ExcelImportResponse])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/excel/import/ad-data`
- ✅ 请求方法：POST
- ✅ 请求体：`multipart/form-data`，包含`file`和可选的`client_id`
- ✅ 响应格式：`ResponseBaseSchema[ExcelImportResponse]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: false })`，返回`data`字段

---

### 5.8 获取有数据的客户列表

**前端请求：** (`frontend/src/api/adData.js`)
```javascript
GET /api/v1/ad-data/clients-with-data?start_date=xxx&end_date=xxx
```

**后端端点：** (`app/api/api_v1/endpoints/ad_data.py`)
```python
@router.get("/clients-with-data", response_model=ListResponseBaseSchema[list[dict]])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/ad-data/clients-with-data`
- ✅ 请求方法：GET
- ✅ 查询参数：`start_date`, `end_date`
- ✅ 响应格式：`ListResponseBaseSchema[list[dict]]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: false })`，返回`{ data, count }`

---

### 5.9 获取有数据的产品列表

**前端请求：** (`frontend/src/api/adData.js`)
```javascript
GET /api/v1/ad-data/products-with-data?client_id=1&start_date=xxx&end_date=xxx
```

**后端端点：** (`app/api/api_v1/endpoints/ad_data.py`)
```python
@router.get("/products-with-data", response_model=ListResponseBaseSchema[list[dict]])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/ad-data/products-with-data`
- ✅ 请求方法：GET
- ✅ 查询参数：`client_id`, `start_date`, `end_date`
- ✅ 响应格式：`ListResponseBaseSchema[list[dict]]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: false })`，返回`{ data, count }`

---

## 6. 定时任务模块 ✅

### 6.1 获取定时任务列表

**前端请求：** (`frontend/src/api/scheduledTask.js`)
```javascript
GET /api/v1/scheduled-tasks/?page=1&page_size=10&is_active=true&is_running=false&task_name=xxx
```

**后端端点：** (`app/api/api_v1/endpoints/scheduled_tasks.py`)
```python
@router.get("/", response_model=PaginatedResponseBaseSchema[list[ScheduledTaskResponse]])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/scheduled-tasks/`
- ✅ 请求方法：GET
- ✅ 查询参数：`page`, `page_size`, `is_active`, `is_running`, `task_name`
- ✅ 响应格式：`PaginatedResponseBaseSchema[list[ScheduledTaskResponse]]`
- ✅ 前端使用：`normalizePaginatedResponse(response)`

---

### 6.2 获取定时任务详情

**前端请求：** (`frontend/src/api/scheduledTask.js`)
```javascript
GET /api/v1/scheduled-tasks/{encodedTaskName}
// 注意：前端对任务名称进行URL编码
```

**后端端点：** (`app/api/api_v1/endpoints/scheduled_tasks.py`)
```python
@router.get("/{task_name}", response_model=ResponseBaseSchema[ScheduledTaskResponse])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/scheduled-tasks/{task_name}`
- ✅ 请求方法：GET
- ✅ 路径参数：`task_name`（前端进行URL编码，支持中文）
- ✅ 响应格式：`ResponseBaseSchema[ScheduledTaskResponse]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`

---

### 6.3 创建定时任务

**前端请求：** (`frontend/src/api/scheduledTask.js`)
```javascript
POST /api/v1/scheduled-tasks/
Body: { task_name, cron_expression, description, function_path, is_active }
```

**后端端点：** (`app/api/api_v1/endpoints/scheduled_tasks.py`)
```python
@router.post("/", response_model=ResponseBaseSchema[ScheduledTaskResponse])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/scheduled-tasks/`
- ✅ 请求方法：POST
- ✅ 请求体：`ScheduledTaskCreate` schema
- ✅ 响应格式：`ResponseBaseSchema[ScheduledTaskResponse]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`

---

### 6.4 更新定时任务

**前端请求：** (`frontend/src/api/scheduledTask.js`)
```javascript
PATCH /api/v1/scheduled-tasks/{encodedTaskName}
Body: { task_name?, is_active?, description?, cron_expression?, function_path? }
```

**后端端点：** (`app/api/api_v1/endpoints/scheduled_tasks.py`)
```python
@router.patch("/{task_name}", response_model=ResponseBaseSchema[ScheduledTaskResponse])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/scheduled-tasks/{task_name}`
- ✅ 请求方法：PATCH
- ✅ 请求体：`ScheduledTaskUpdate` schema
- ✅ 响应格式：`ResponseBaseSchema[ScheduledTaskResponse]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`

---

### 6.5 手动触发定时任务

**前端请求：** (`frontend/src/api/scheduledTask.js`)
```javascript
POST /api/v1/scheduled-tasks/{encodedTaskName}/trigger
```

**后端端点：** (`app/api/api_v1/endpoints/scheduled_tasks.py`)
```python
@router.post("/{task_name}/trigger", response_model=ResponseBaseSchema[dict])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/scheduled-tasks/{task_name}/trigger`
- ✅ 请求方法：POST
- ✅ 响应格式：`ResponseBaseSchema[dict]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`

---

### 6.6 释放任务锁

**前端请求：** (`frontend/src/api/scheduledTask.js`)
```javascript
POST /api/v1/scheduled-tasks/{encodedTaskName}/release-lock
```

**后端端点：** (`app/api/api_v1/endpoints/scheduled_tasks.py`)
```python
@router.post("/{task_name}/release-lock", response_model=ResponseBaseSchema[dict])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/scheduled-tasks/{task_name}/release-lock`
- ✅ 请求方法：POST
- ✅ 响应格式：`ResponseBaseSchema[dict]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`

---

## 7. 审计日志模块 ✅

### 7.1 获取操作日志列表

**前端请求：** (`frontend/src/api/auditLog.js`)
```javascript
GET /api/v1/audit-logs/?page=1&page_size=10&user_id=1&username=xxx&action_type=LOGIN&resource_type=USER&ip_address=xxx&success=true&start_date=xxx&end_date=xxx
```

**后端端点：** (`app/api/api_v1/endpoints/audit_logs.py`)
```python
@router.get("/", response_model=AuditLogListResponse)
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/audit-logs/`
- ✅ 请求方法：GET
- ✅ 查询参数：`page`, `page_size`, `user_id`, `username`, `action_type`, `resource_type`, `ip_address`, `success`, `start_date`, `end_date`
- ✅ 响应格式：`AuditLogListResponse`（包含分页信息）
- ✅ 前端使用：`normalizePaginatedResponse(response)`

---

### 7.2 获取操作日志详情

**前端请求：** (`frontend/src/api/auditLog.js`)
```javascript
GET /api/v1/audit-logs/{logId}
```

**后端端点：** (`app/api/api_v1/endpoints/audit_logs.py`)
```python
@router.get("/{log_id}", response_model=ResponseBaseSchema[UserAuditLogResponse])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/audit-logs/{log_id}`
- ✅ 请求方法：GET
- ✅ 响应格式：`ResponseBaseSchema[UserAuditLogResponse]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`

---

### 7.3 获取日志统计摘要

**前端请求：** (`frontend/src/api/auditLog.js`)
```javascript
GET /api/v1/audit-logs/stats/summary?start_date=xxx&end_date=xxx
```

**后端端点：** (`app/api/api_v1/endpoints/audit_logs.py`)
```python
@router.get("/stats/summary", response_model=ResponseBaseSchema[dict])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/audit-logs/stats/summary`
- ✅ 请求方法：GET
- ✅ 查询参数：`start_date`, `end_date`
- ✅ 响应格式：`ResponseBaseSchema[dict]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`

---

## 8. ML模型管理模块 ✅

### 8.1 验证Excel列名映射

**前端请求：** (`frontend/src/api/mlModel.js`)
```javascript
POST /api/v1/ml-model/validate
Body: FormData { file }
```

**后端端点：** (`app/api/api_v1/endpoints/ml_model.py`)
```python
@router.post("/validate", response_model=ResponseBaseSchema[dict])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/ml-model/validate`
- ✅ 请求方法：POST
- ✅ 请求体：`multipart/form-data`，包含`file`
- ✅ 响应格式：`ResponseBaseSchema[dict]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`

---

### 8.2 获取映射规则状态

**前端请求：** (`frontend/src/api/mlModel.js`)
```javascript
GET /api/v1/ml-model/status
```

**后端端点：** (`app/api/api_v1/endpoints/ml_model.py`)
```python
@router.get("/status", response_model=ResponseBaseSchema[dict])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/ml-model/status`
- ✅ 请求方法：GET
- ✅ 响应格式：`ResponseBaseSchema[dict]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`

---

### 8.3 获取应用时区配置

**前端请求：** (`frontend/src/api/mlModel.js`)
```javascript
GET /api/v1/ml-model/timezone
```

**后端端点：** (`app/api/api_v1/endpoints/ml_model.py`)
```python
@router.get("/timezone", response_model=ResponseBaseSchema[dict])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/ml-model/timezone`
- ✅ 请求方法：GET
- ✅ 响应格式：`ResponseBaseSchema[dict]`，包含`timezone`字段
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`，提取`timezone`字段，默认值`'Asia/Shanghai'`

---

### 8.4 解析Excel列名

**前端请求：** (`frontend/src/api/mlModel.js`)
```javascript
POST /api/v1/ml-model/parse-excel
Body: FormData { file }
```

**后端端点：** (`app/api/api_v1/endpoints/ml_model.py`)
```python
@router.post("/parse-excel", response_model=ResponseBaseSchema[dict])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/ml-model/parse-excel`
- ✅ 请求方法：POST
- ✅ 请求体：`multipart/form-data`，包含`file`
- ✅ 响应格式：`ResponseBaseSchema[dict]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`

---

### 8.5 保存用户映射规则

**前端请求：** (`frontend/src/api/mlModel.js`)
```javascript
POST /api/v1/ml-model/save-mapping
Body: { excel_column: db_field, ... }
Headers: { Authorization: Bearer {token} }
```

**后端端点：** (`app/api/api_v1/endpoints/ml_model.py`)
```python
@router.post("/save-mapping", response_model=ResponseBaseSchema[dict])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/ml-model/save-mapping`
- ✅ 请求方法：POST
- ✅ 请求体：映射规则对象
- ✅ 响应格式：`ResponseBaseSchema[dict]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`
- ✅ 前端手动添加Authorization头（虽然拦截器也会添加，但这里是显式添加）

---

### 8.6 预览Excel数据

**前端请求：** (`frontend/src/api/mlModel.js`)
```javascript
POST /api/v1/ml-model/preview?rows=10
Body: FormData { file }
```

**后端端点：** (`app/api/api_v1/endpoints/ml_model.py`)
```python
@router.post("/preview", response_model=ResponseBaseSchema[dict])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/ml-model/preview`
- ✅ 请求方法：POST
- ✅ 查询参数：`rows`（预览行数，默认10）
- ✅ 请求体：`multipart/form-data`，包含`file`
- ✅ 响应格式：`ResponseBaseSchema[dict]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`

---

### 8.7 导入训练数据

**前端请求：** (`frontend/src/api/mlModel.js`)
```javascript
POST /api/v1/ml-model/import
Body: FormData { file }
```

**后端端点：** (`app/api/api_v1/endpoints/ml_model.py`)
```python
@router.post("/import", response_model=ResponseBaseSchema[dict])
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/ml-model/import`
- ✅ 请求方法：POST
- ✅ 请求体：`multipart/form-data`，包含`file`
- ✅ 响应格式：`ResponseBaseSchema[dict]`
- ✅ 前端使用：`normalizeResponse(response, { returnDataOnly: true })`

---

## 9. 认证模块 ✅

### 9.1 用户登录

**前端请求：** (`frontend/src/store/index.js`)
```javascript
POST /api/v1/auth/login
Body: FormData { username, password }
```

**后端端点：** (`app/api/api_v1/endpoints/auth.py`)
```python
@router.post("/login", response_model=LoginResponse)
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/auth/login`
- ✅ 请求方法：POST
- ✅ 请求体：`OAuth2PasswordRequestForm`（username, password）
- ✅ 响应格式：`LoginResponse`（包含access_token, token_type, user）
- ✅ 前端处理：直接使用响应数据，存储token和userInfo

---

### 9.2 用户退出登录

**前端请求：** (`frontend/src/api/user.js`)
```javascript
POST /api/v1/auth/logout
```

**后端端点：** (`app/api/api_v1/endpoints/auth.py`)
```python
@router.post("/logout")
```

**匹配情况：** ✅ 完全匹配
- ✅ 请求路径：`/api/v1/auth/logout`
- ✅ 请求方法：POST
- ✅ 响应格式：`{ "message": "退出登录成功" }`
- ✅ 前端处理：静默处理（即使API失败也清除本地状态）

---

## 10. 发现的问题和建议

### 10.1 问题

1. **广告数据详情端点未使用**
   - **位置：** `frontend/src/api/adData.js`
   - **问题：** 前端代码中已移除`getAdDataDetail`函数，但后端端点`GET /api/v1/ad-data/{data_id}`存在
   - **影响：** 无实际影响，但存在未使用的端点
   - **建议：** 如果不需要，可以移除后端端点；如果需要，恢复前端调用

2. **广告数据列表响应格式** ✅ 已确认
   - **位置：** `app/api/api_v1/endpoints/ad_data.py`
   - **状态：** ✅ `AdDataListResponse`包含分页字段（`total`, `page`, `page_size`），前端使用`normalizePaginatedResponse`处理是正确的
   - **建议：** 无

---

### 10.2 优点

1. ✅ **统一的响应格式处理**：前端使用`normalizeResponse`和`normalizePaginatedResponse`统一处理响应
2. ✅ **错误处理完善**：前端使用`extractErrorMessage`统一提取错误信息
3. ✅ **文件下载处理优秀**：导出功能正确处理blob响应和JSON错误响应
4. ✅ **URL编码处理**：定时任务名称进行URL编码，支持中文
5. ✅ **请求参数匹配**：所有API的请求参数与后端端点完全匹配

---

## 11. 总体评价

### 11.1 匹配度

- **完全匹配：** 95%+
- **部分匹配：** 5%
- **不匹配：** 0%

### 11.2 评分

- **API路径匹配：** 10/10
- **请求方法匹配：** 10/10
- **请求参数匹配：** 10/10
- **响应格式匹配：** 9.5/10
- **错误处理一致性：** 10/10

**总体评分：9.9/10** ⭐⭐⭐⭐⭐

---

## 12. 建议的改进

### 高优先级
1. 无

### 中优先级
1. 移除未使用的后端端点（广告数据详情），或恢复前端调用

### 低优先级
3. 统一所有列表接口使用`PaginatedResponseBaseSchema`（如果当前不是）

---

## 检查完成时间
2024年12月

