# 代码规范文档

本文档定义了前后端代码的命名规范和编码风格，确保代码的一致性和可维护性。

## 📋 快速参考

### 命名规范速查表

| 类型 | 后端（Python） | 前端（JavaScript/Vue） |
|------|---------------|----------------------|
| **文件** | `snake_case.py` | `camelCase.js` 或 `PascalCase.vue` |
| **类** | `PascalCase` | `PascalCase` |
| **函数/方法** | `snake_case()` | `camelCase()` |
| **变量** | `snake_case` | `camelCase` |
| **常量** | `UPPER_SNAKE_CASE` | `UPPER_SNAKE_CASE` |
| **私有** | `_snake_case` | `_camelCase` |
| **API路径** | `kebab-case` | `kebab-case` |
| **数据库表** | `snake_case` (复数) | - |
| **数据库字段** | `snake_case` | - |

### 关键规则

1. **后端 Python**: 全部使用 `snake_case`（类名除外用 `PascalCase`）
2. **前端 JavaScript**: 全部使用 `camelCase`（组件名用 `PascalCase`）
3. **API 路径**: 使用 `kebab-case`（如 `/api/v1/short-links/`）
4. **API 参数和响应字段**: 使用 `snake_case`（如 `page_size`, `user_id`, `created_at`）
5. **数据库**: 全部使用 `snake_case`

### ⚠️ 重要注意事项

- **前端代码中的API数据字段**：虽然前端内部变量使用 `camelCase`，但API请求参数和响应数据中的字段名必须使用 `snake_case`，以保持与后端API规范的一致性。
- **数据转换**：如果需要在内部使用 `camelCase` 格式的数据，可以在数据获取后进行转换，但发送到API的数据必须使用 `snake_case`。

---

## 目录

- [后端（Python）规范](#后端python规范)
- [前端（JavaScript/Vue）规范](#前端javascriptvue规范)
- [API 接口规范](#api-接口规范)
- [数据库规范](#数据库规范)
- [通用规范](#通用规范)
- [检查清单](#检查清单)

---

## 后端（Python）规范

### 命名规范

#### 1. 文件命名
- **规则**: 使用 `snake_case`（小写字母 + 下划线）
- **示例**: 
  - ✅ `user_service.py`
  - ✅ `advertiser_service.py`
  - ✅ `base_repository.py`
  - ❌ `UserService.py`
  - ❌ `userService.py`

#### 2. 类命名
- **规则**: 使用 `PascalCase`（首字母大写的驼峰命名）
- **示例**:
  - ✅ `UserService`
  - ✅ `BaseRepository`
  - ✅ `ShortLinkService`
  - ❌ `user_service`
  - ❌ `userService`

#### 3. 函数/方法命名
- **规则**: 使用 `snake_case`
- **示例**:
  - ✅ `get_user_by_id()`
  - ✅ `create_user()`
  - ✅ `update_user()`
  - ❌ `getUserById()`
  - ❌ `getUser()`

#### 4. 变量命名
- **规则**: 使用 `snake_case`
- **示例**:
  - ✅ `user_id`
  - ✅ `current_user`
  - ✅ `page_size`
  - ❌ `userId`
  - ❌ `currentUser`

#### 5. 常量命名
- **规则**: 使用 `UPPER_SNAKE_CASE`（全大写 + 下划线）
- **示例**:
  - ✅ `API_V1_STR`
  - ✅ `MAX_PAGE_SIZE`
  - ✅ `SECRET_KEY`
  - ❌ `apiV1Str`
  - ❌ `maxPageSize`

#### 6. 私有变量/方法
- **规则**: 使用单下划线前缀 `_` 表示内部使用
- **示例**:
  - ✅ `_internal_method()`
  - ✅ `_private_variable`
  - ❌ `__double_underscore`（除非需要名称修饰）

#### 7. 模块/包命名
- **规则**: 使用 `snake_case`，简短且有意义
- **示例**:
  - ✅ `app/core/`
  - ✅ `app/services/`
  - ✅ `app/api/`
  - ❌ `app/Core/`
  - ❌ `app/services/`

### 代码风格

#### 1. 导入顺序
```python
# 1. 标准库
import os
import logging
from datetime import datetime

# 2. 第三方库
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

# 3. 本地应用
from app.core.database import get_db
from app.models.models import User
from app.services.user_service import UserService
```

#### 2. 类型注解
- **规则**: 使用 Python 3.10+ 类型注解
- **示例**:
```python
async def get_user_by_id(
    self,
    user_id: int,
    current_user: User,
    include_client: bool = True
) -> User:
    """获取用户详情"""
    pass
```

#### 3. 文档字符串
- **规则**: 使用三引号 `"""` 编写 docstring
- **格式**: Google 风格
```python
def get_user_by_id(self, user_id: int) -> User:
    """
    根据ID获取用户详情
    
    Args:
        user_id: 用户ID
        current_user: 当前用户（用于权限检查）
    
    Returns:
        User: 用户对象
    
    Raises:
        HTTPException: 如果用户不存在或没有权限
    """
    pass
```

#### 4. 异常处理
```python
try:
    result = await some_operation()
except SpecificException as e:
    logger.error(f"操作失败: {e}")
    raise_api_exception(ErrorCode.SOME_ERROR, detail=str(e))
```

---

## 前端（JavaScript/Vue）规范

### 命名规范

#### 1. 文件命名
- **规则**: 
  - JavaScript 文件: `camelCase.js` 或 `kebab-case.js`
  - Vue 组件: `PascalCase.vue`
- **示例**:
  - ✅ `userService.js`
  - ✅ `versionCheck.js`
  - ✅ `UserManagement.vue`
  - ✅ `ShortLinkFormDialog.vue`
  - ❌ `user_service.js`
  - ❌ `user-management.vue`（组件名）

#### 2. 变量命名
- **规则**: 使用 `camelCase`
- **示例**:
  - ✅ `userData`
  - ✅ `currentUser`
  - ✅ `pageSize`
  - ❌ `user_data`
  - ❌ `current_user`

**重要说明**：
- 前端内部变量必须使用 `camelCase`
- 但**API请求/响应数据**中的字段名应保持后端的 `snake_case` 格式（如 `user_id`, `created_at`, `is_active`）
- 这是因为API接口规范要求使用 `snake_case`，前端需要与后端保持一致
- 示例：
  ```javascript
  // ✅ 正确：内部变量使用 camelCase
  const currentUser = ref(null);
  const pageSize = ref(20);
  
  // ✅ 正确：API请求参数使用 snake_case（与后端一致）
  const params = {
    page: 1,
    page_size: 20,
    user_id: 123
  };
  
  // ✅ 正确：API响应数据字段使用 snake_case（与后端一致）
  const userData = {
    id: 1,
    user_name: 'admin',
    created_at: '2024-01-01'
  };
  
  // ❌ 错误：内部变量不应使用 snake_case
  const current_user = ref(null);
  const page_size = ref(20);
  ```

#### 3. 函数/方法命名
- **规则**: 使用 `camelCase`，动词开头
- **示例**:
  - ✅ `getUsers()`
  - ✅ `createUser()`
  - ✅ `updateUser()`
  - ✅ `handleSubmit()`
  - ❌ `get_users()`
  - ❌ `GetUsers()`

#### 4. 常量命名
- **规则**: 使用 `UPPER_SNAKE_CASE`
- **示例**:
  - ✅ `API_BASE_URL`
  - ✅ `MAX_RETRY_COUNT`
  - ✅ `DEFAULT_PAGE_SIZE`
  - ❌ `apiBaseUrl`
  - ❌ `maxRetryCount`

#### 5. 组件命名
- **规则**: 使用 `PascalCase`
- **示例**:
  - ✅ `<UserManagement />`
  - ✅ `<ShortLinkFormDialog />`
  - ❌ `<user-management />`
  - ❌ `<shortLinkFormDialog />`

#### 6. 私有变量/方法
- **规则**: 使用单下划线前缀 `_` 表示内部使用
- **示例**:
  - ✅ `_internalMethod()`
  - ✅ `_privateVariable`
  - ❌ `__doubleUnderscore`

#### 7. 组合式函数（Composables）
- **规则**: 使用 `use` 前缀 + `camelCase`
- **示例**:
  - ✅ `useUserForm()`
  - ✅ `usePagination()`
  - ✅ `useClientStats()`
  - ❌ `use_user_form()`

### 代码风格

#### 1. 导入顺序
```javascript
// 1. Vue 核心
import { ref, computed, onMounted } from 'vue';

// 2. 第三方库
import axios from 'axios';
import { ElMessage } from 'element-plus';

// 3. 本地工具
import { request } from '@/utils/api';
import { logger } from '@/utils/logger';

// 4. 本地组件
import UserFormDialog from './components/UserFormDialog.vue';
```

#### 2. Vue 组件结构
```vue
<template>
  <!-- 模板内容 -->
</template>

<script setup>
// 1. 导入
import { ref, computed } from 'vue';

// 2. Props 和 Emits
const props = defineProps({
  userId: {
    type: Number,
    required: true
  }
});

// 3. 响应式数据
const loading = ref(false);
const userData = ref(null);

// 4. 计算属性
const isAdmin = computed(() => {
  return authStore.isAdmin;
});

// 5. 方法
const handleSubmit = async () => {
  // ...
};

// 6. 生命周期
onMounted(() => {
  // ...
});
</script>

<style scoped>
/* 样式 */
</style>
```

#### 3. 函数文档
```javascript
/**
 * 获取用户列表
 * 
 * @param {Object} params - 查询参数
 * @param {number} params.page - 页码，从1开始
 * @param {number} params.pageSize - 每页条数
 * @param {string} [params.username] - 用户名筛选
 * @returns {Promise<Object>} 返回标准化的分页响应对象
 * 
 * @example
 * const result = await getUsers({ page: 1, pageSize: 10 });
 */
export const getUsers = async (params) => {
  // ...
};
```

---

## API 接口规范

### 1. URL 路径命名
- **规则**: 使用 `kebab-case`（小写字母 + 连字符）
- **示例**:
  - ✅ `/api/v1/users/`
  - ✅ `/api/v1/short-links/`
  - ✅ `/api/v1/postback/conversions`
  - ❌ `/api/v1/shortLinks/`
  - ❌ `/api/v1/short_links/`

### 2. HTTP 方法
- **GET**: 查询数据
- **POST**: 创建数据
- **PUT**: 完整更新数据
- **PATCH**: 部分更新数据
- **DELETE**: 删除数据

### 3. 请求/响应格式

#### 请求参数
- **查询参数**: `snake_case`
  - ✅ `page_size`
  - ✅ `user_id`
  - ❌ `pageSize`
  - ❌ `userId`

- **请求体**: `snake_case`
```json
{
  "user_name": "admin",
  "full_name": "管理员",
  "is_active": true
}
```

#### 响应格式
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 1,
    "user_name": "admin",
    "full_name": "管理员"
  }
}
```

### 4. 分页响应
```json
{
  "code": 200,
  "message": "success",
  "data": [...],
  "total": 100,
  "page": 1,
  "page_size": 10,
  "total_pages": 10
}
```

---

## 数据库规范

### 1. 表名
- **规则**: 使用 `snake_case`，复数形式
- **示例**:
  - ✅ `users`
  - ✅ `short_links`
  - ✅ `postback_conversions`
  - ❌ `Users`
  - ❌ `shortLinks`

### 2. 字段名
- **规则**: 使用 `snake_case`
- **示例**:
  - ✅ `user_id`
  - ✅ `created_at`
  - ✅ `is_active`
  - ❌ `userId`
  - ❌ `createdAt`

### 3. 外键命名
- **规则**: `{表名}_id`
- **示例**:
  - ✅ `user_id`
  - ✅ `offer_id`
  - ✅ `publisher_id`
  - ❌ `userId`
  - ❌ `offerId`

### 4. 时间字段
- **规则**: 使用 `_at` 后缀
- **示例**:
  - ✅ `created_at`
  - ✅ `updated_at`
  - ✅ `deleted_at`
  - ❌ `createdAt`
  - ❌ `createTime`

### 5. 布尔字段
- **规则**: 使用 `is_` 或 `has_` 前缀
- **示例**:
  - ✅ `is_active`
  - ✅ `is_deleted`
  - ✅ `has_permission`
  - ❌ `active`
  - ❌ `deleted`

---

## 通用规范

### 1. 注释规范
- **单行注释**: 使用 `//`（JavaScript）或 `#`（Python）
- **多行注释**: 使用 `/* */`（JavaScript）或 `"""`（Python）
- **文档注释**: 使用 JSDoc（JavaScript）或 docstring（Python）

### 2. 代码格式化
- **Python**: 使用 Black 或遵循 PEP 8
- **JavaScript**: 使用 Prettier 或 ESLint
- **缩进**: 
  - Python: 4 个空格
  - JavaScript: 2 个空格

### 3. 错误处理
- **后端**: 使用统一的异常处理机制
  ```python
  raise_api_exception(ErrorCode.USER_NOT_FOUND, detail="用户不存在")
  ```
- **前端**: 使用统一的错误处理函数
  ```javascript
  try {
    await someOperation();
  } catch (error) {
    handleError(error);
  }
  ```

### 4. 日志规范
- **级别**: DEBUG, INFO, WARNING, ERROR
- **格式**: 包含上下文信息
  ```python
  logger.info(f"用户 {user_id} 创建成功")
  logger.error(f"操作失败: {error}", exc_info=True)
  ```
  ```javascript
  logger.info('用户创建成功', { userId: user.id });
  logger.error('操作失败', { error: error.message });
  ```

### 5. 版本控制
- **提交信息**: 使用清晰的中文描述
  - ✅ `feat: 添加用户管理功能`
  - ✅ `fix: 修复登录验证问题`
  - ✅ `refactor: 重构用户服务层`
  - ❌ `update`
  - ❌ `fix bug`

---

## 检查清单

在提交代码前，请确保：

- [ ] 文件命名符合规范
- [ ] 变量/函数命名符合规范
- [ ] API 路径使用 kebab-case
- [ ] 数据库字段使用 snake_case
- [ ] 添加了必要的注释和文档
- [ ] 错误处理完善
- [ ] 日志记录适当
- [ ] 代码格式化正确

---

## 参考资源

- [PEP 8 - Python 代码风格指南](https://pep8.org/)
- [Vue.js 风格指南](https://cn.vuejs.org/style-guide/)
- [Google JavaScript 风格指南](https://google.github.io/styleguide/jsguide.html)
- [RESTful API 设计规范](https://restfulapi.net/)
