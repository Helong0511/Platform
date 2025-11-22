# CSRF令牌服务器重启处理说明

## 问题背景

当用户登录后，如果服务器后端关闭然后又重新打开，可能会导致CSRF令牌验证失败：

1. **前端状态**：用户已登录，CSRF token存储在 `sessionStorage` 中
2. **后端状态**：
   - 如果使用Redis存储：token可能仍然存在（Redis未重启）
   - 如果使用内存存储：token会丢失（进程重启）
3. **问题**：前端使用旧的CSRF token发送请求，后端可能找不到该token，导致403错误

## 解决方案

### 1. 后端自动生成新token

当后端检测到CSRF token不存在时（可能是服务器重启导致）：

1. **生成新的CSRF token**并存储
2. **在403错误响应头中添加新的CSRF token**（`X-CSRF-Token`）
3. 前端可以从错误响应中获取新token

**代码位置**：`app/core/csrf.py` 第381-410行

### 2. 前端自动重试机制

当前端收到403 CSRF错误时：

1. **清除旧的CSRF token**
2. **自动发送GET请求获取新的CSRF token**
3. **使用新token自动重试原始请求**
4. 如果自动重试失败，显示友好的错误提示

**代码位置**：`frontend/src/main.js` 第146-172行

### 3. 响应拦截器自动更新

前端响应拦截器会自动从所有响应头中提取CSRF token并更新：

- 成功响应：更新token
- 错误响应：也尝试提取token（即使请求失败，响应头中也可能包含新token）

**代码位置**：`frontend/src/main.js` 第88-104行

## 工作流程

### 场景1：服务器重启，使用Redis存储（Redis未重启）

```
1. 用户登录 → 获取CSRF token → 存储到Redis和sessionStorage
2. 服务器重启 → Redis中的token仍然存在
3. 用户发送请求 → 使用旧token → 后端从Redis找到token → ✅ 验证通过
```

### 场景2：服务器重启，使用内存存储

```
1. 用户登录 → 获取CSRF token → 存储到内存和sessionStorage
2. 服务器重启 → 内存中的token丢失
3. 用户发送POST请求 → 使用旧token → 后端找不到token → ❌ 403错误
4. 后端自动生成新token → 在403响应头中添加新token
5. 前端收到403错误 → 检测到CSRF错误 → 自动获取新token → 自动重试请求 → ✅ 成功
```

### 场景3：服务器重启，使用Redis存储（Redis也重启）

```
1. 用户登录 → 获取CSRF token → 存储到Redis和sessionStorage
2. 服务器和Redis都重启 → Redis中的token丢失
3. 用户发送POST请求 → 使用旧token → 后端找不到token → ❌ 403错误
4. 后端自动生成新token → 在403响应头中添加新token
5. 前端收到403错误 → 检测到CSRF错误 → 自动获取新token → 自动重试请求 → ✅ 成功
```

## 配置说明

### CSRF Token过期时间

在 `.env` 文件中配置：

```bash
# CSRF令牌过期时间（秒）
# 默认值：3600（1小时）
CSRF_TOKEN_EXPIRE_SECONDS=3600
```

### Redis配置（推荐）

使用Redis存储CSRF token可以避免服务器重启后token丢失：

```bash
# Redis连接URL
REDIS_URL=redis://localhost:6379/0
```

**优势**：
- 服务器重启后，如果Redis未重启，token仍然有效
- 多进程环境下，所有进程共享同一个token存储

**注意**：
- 如果Redis也重启，token会丢失，但系统会自动处理（生成新token）

## 用户体验

### 自动处理（无需用户操作）

1. **服务器重启后第一次请求**：
   - 如果token丢失，后端自动生成新token
   - 前端自动获取新token并重试
   - 用户无感知，请求自动成功

2. **自动重试失败**：
   - 显示友好提示："CSRF令牌已过期，请刷新页面后重试"
   - 用户刷新页面即可（页面加载时会自动获取新token）

### 手动处理（如果自动处理失败）

如果自动重试失败，用户可以：
1. 刷新页面（F5或Ctrl+R）
2. 页面加载时会自动获取新的CSRF token
3. 重新执行操作

## 技术细节

### 后端处理逻辑

```python
# 1. 验证CSRF token
if not stored_token:
    # 2. 生成新的CSRF token
    new_csrf_token = generate_csrf_token()
    # 3. 存储新token
    await redis_client.setex(csrf_key, expire_time, new_csrf_token)
    # 4. 在HTTPException中添加新token
    http_exc._csrf_token = new_csrf_token
    raise http_exc

# 5. 异常处理器在响应头中添加新token
response.headers["X-CSRF-Token"] = exc._csrf_token
```

### 前端处理逻辑

```javascript
// 1. 检测到403 CSRF错误
if (error.response.status === 403 && errorDetail.includes('CSRF')) {
    // 2. 清除旧token
    sessionStorage.removeItem('csrf_token');
    
    // 3. 自动获取新token
    const response = await axios.get('/api/v1/users/stats');
    const newToken = response.headers['x-csrf-token'];
    sessionStorage.setItem('csrf_token', newToken);
    
    // 4. 使用新token重试原始请求
    originalRequest.headers['X-CSRF-Token'] = newToken;
    return axios(originalRequest);
}
```

## 最佳实践

1. **使用Redis存储**：避免服务器重启后token丢失
2. **配置合理的过期时间**：默认1小时，可根据需要调整
3. **监控CSRF错误**：如果频繁出现CSRF错误，检查Redis连接状态
4. **前端自动重试**：已实现，用户无需手动处理

## 相关文档

- [CSRF防护说明](./CSRF防护说明.md)（如果存在）
- [定时任务队列管理说明](./定时任务队列管理说明.md)

