# 前端 API 调用统一指南

## 概述

本文档说明前端 API 调用的统一规范和最佳实践，帮助开发者选择合适的 API 调用方式。

## API 调用方式

### 1. 使用 `request` 工具函数（推荐）

**适用场景：**
- 简单的 CRUD 操作（GET、POST、PUT、DELETE）
- 标准 JSON 响应
- 不需要特殊处理的请求

**优点：**
- 自动处理错误和响应格式化
- 统一的错误提示
- 代码简洁

**示例：**
```javascript
import { request } from '@/utils/api'

// GET 请求（分页响应）
export function getUsers(params) {
  return request({
    url: '/api/v1/users/',
    method: 'get',
    params
  }, { paginated: true })
}

// GET 请求（普通响应）
export function getUser(id) {
  return request({
    url: `/api/v1/users/${id}`,
    method: 'get'
  }, { returnDataOnly: true })
}

// POST 请求
export function createUser(data) {
  return request({
    url: '/api/v1/users/',
    method: 'post',
    data
  })
}

// PUT 请求
export function updateUser(id, data) {
  return request({
    url: `/api/v1/users/${id}`,
    method: 'put',
    data
  })
}

// DELETE 请求
export function deleteUser(id) {
  return request({
    url: `/api/v1/users/${id}`,
    method: 'delete'
  })
}
```

### 2. 使用 `axios` 直接调用

**适用场景：**
- 文件下载（`responseType: 'blob'`）
- 文件上传（`FormData`）
- 需要特殊错误处理的请求
- 需要自定义响应处理的请求

**优点：**
- 完全控制请求和响应
- 支持特殊场景（文件下载/上传）

**示例：**
```javascript
import axios from 'axios'
import { normalizeResponse, extractErrorMessage, isErrorHandled } from '../utils/api'
import { ElMessage } from 'element-plus'

// 文件下载
export const exportUsers = async (params = {}) => {
  try {
    const response = await axios.get('/api/v1/users/export/excel', {
      params,
      responseType: 'blob'
    })
    
    // 处理文件下载
    const blob = new Blob([response.data])
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = '用户数据.xlsx'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    
    ElMessage.success('导出成功')
  } catch (error) {
    if (isErrorHandled(error)) {
      throw error
    }
    const errorMsg = extractErrorMessage(error)
    ElMessage.error(errorMsg)
    throw error
  }
}

// 文件上传
export const importAdData = async (formData) => {
  try {
    const response = await axios.post('/api/v1/excel/import/ad-data', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      },
      timeout: 60000
    })
    return normalizeResponse(response)
  } catch (error) {
    const errorMsg = extractErrorMessage(error)
    ElMessage.error(errorMsg)
    throw error
  }
}
```

## `request` 函数选项

`request` 函数支持以下选项：

```javascript
request(config, {
  returnDataOnly: false,  // 是否只返回 data 字段
  paginated: false,      // 是否为分页响应
  silent: false          // 是否静默处理错误（不显示错误消息）
})
```

### 选项说明

#### `returnDataOnly`
- `true`: 只返回响应中的 `data` 字段
- `false`: 返回完整的响应对象（包含 `code`, `message`, `data`）

**示例：**
```javascript
// 返回完整响应
const response = await request({
  url: '/api/v1/users/1',
  method: 'get'
})
// response = { code: 200, message: 'success', data: {...} }

// 只返回 data
const user = await request({
  url: '/api/v1/users/1',
  method: 'get'
}, { returnDataOnly: true })
// user = {...}
```

#### `paginated`
- `true`: 使用 `normalizePaginatedResponse` 处理分页响应
- `false`: 使用 `normalizeResponse` 处理普通响应

**示例：**
```javascript
// 分页响应
const users = await request({
  url: '/api/v1/users/',
  method: 'get',
  params: { page: 1, page_size: 10 }
}, { paginated: true })
// users = { data: [...], total: 100, page: 1, page_size: 10 }

// 普通响应
const user = await request({
  url: '/api/v1/users/1',
  method: 'get'
})
// user = { code: 200, message: 'success', data: {...} }
```

#### `silent`
- `true`: 不显示错误消息（静默处理）
- `false`: 自动显示错误消息

**示例：**
```javascript
// 静默处理错误
try {
  await request({
    url: '/api/v1/users/1',
    method: 'get'
  }, { silent: true })
} catch (error) {
  // 错误不会自动显示消息，需要手动处理
  console.error(error)
}
```

## CSRF Token 处理

### 使用 `request` 函数
CSRF token 由 axios 拦截器自动处理，无需手动添加。

### 使用 `axios` 直接调用
需要在请求前确保 CSRF token 存在：

```javascript
import { ensureCsrfToken } from '../utils/api'

export const createUser = async (userData) => {
  // 确保 CSRF token 存在
  await ensureCsrfToken()
  
  const csrfToken = sessionStorage.getItem('csrf_token')
  const response = await axios.post('/api/v1/users/', userData, {
    headers: {
      'X-CSRF-Token': csrfToken
    }
  })
  return normalizeResponse(response)
}
```

## 错误处理

### 使用 `request` 函数
错误会自动处理并显示消息，无需手动处理。

### 使用 `axios` 直接调用
需要手动处理错误：

```javascript
import { extractErrorMessage, isErrorHandled } from '../utils/api'
import { ElMessage } from 'element-plus'

try {
  const response = await axios.get('/api/v1/users/')
  return normalizeResponse(response)
} catch (error) {
  // 检查错误是否已被处理（如429限流）
  if (isErrorHandled(error)) {
    throw error
  }
  
  // 提取并显示错误消息
  const errorMsg = extractErrorMessage(error)
  ElMessage.error(errorMsg)
  throw error
}
```

## 最佳实践

### 1. 优先使用 `request` 函数
对于简单的 CRUD 操作，优先使用 `request` 函数，代码更简洁。

### 2. 特殊场景使用 `axios`
对于文件下载、文件上传等特殊场景，使用 `axios` 直接调用。

### 3. 统一错误处理
使用 `request` 函数时，错误会自动处理。使用 `axios` 时，遵循统一的错误处理模式。

### 4. 响应格式化
- 分页响应：使用 `normalizePaginatedResponse`
- 普通响应：使用 `normalizeResponse`
- 文件响应：直接使用原始响应

### 5. 代码风格
- 使用 `request` 的函数：使用 `export function` 声明
- 使用 `axios` 的函数：使用 `export const` 声明

## 迁移指南

### 从 `axios` 迁移到 `request`

**迁移前：**
```javascript
export const getUsers = async (params) => {
  try {
    const response = await axios.get('/api/v1/users/', { params })
    return normalizePaginatedResponse(response)
  } catch (error) {
    if (isErrorHandled(error)) {
      throw error
    }
    const errorMsg = extractErrorMessage(error)
    ElMessage.error(errorMsg)
    throw error
  }
}
```

**迁移后：**
```javascript
export function getUsers(params) {
  return request({
    url: '/api/v1/users/',
    method: 'get',
    params
  }, { paginated: true })
}
```

## 总结

- **简单操作**：使用 `request` 函数
- **特殊场景**：使用 `axios` 直接调用
- **统一风格**：遵循本文档的规范和示例

通过遵循本指南，可以保持代码的一致性和可维护性。

