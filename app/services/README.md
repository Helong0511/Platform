# 服务层使用指南

## 概述

服务层（Service Layer）将业务逻辑从API端点（endpoints）中抽离，提供更好的代码组织、复用性和可测试性。

## 架构设计

```
app/
├── services/              # 服务层
│   ├── base_service.py   # 服务基类
│   ├── user_service.py   # 用户服务
│   └── product_service.py # 产品服务
├── api/
│   └── api_v1/
│       └── endpoints/    # API端点（薄层，只负责HTTP处理）
└── core/
    └── dependencies.py    # 依赖注入配置
```

## 使用方式

### 1. 在Endpoint中使用服务层

**重构前（业务逻辑在endpoint中）：**
```python
@router.get("/users/{user_id}")
async def get_user(user_id: int, db: AsyncSession = Depends(get_db), ...):
    # 业务逻辑直接写在endpoint中
    query = select(User).where(User.id == user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if not user:
        raise_api_exception(...)
    return ResponseBaseSchema.success(data=user)
```

**重构后（使用服务层）：**
```python
from app.core.dependencies import get_user_service
from app.services.user_service import UserService

@router.get("/users/{user_id}")
async def get_user(
    user_id: int,
    user_service: UserService = Depends(get_user_service),
    current_user: User = Depends(get_current_user)
):
    # 业务逻辑在服务层
    user = await user_service.get_user_by_id(user_id, current_user)
    return ResponseBaseSchema.success(data=UserResponse.model_validate(user))
```

### 2. 服务层方法示例

```python
# services/user_service.py
class UserService(BaseService[User]):
    async def get_user_by_id(self, user_id: int, current_user: User) -> User:
        """获取用户详情（带权限检查）"""
        # 权限检查
        if current_user.role != UserRole.ADMIN and current_user.id != user_id:
            raise_api_exception(ErrorCode.FORBIDDEN, ...)
        
        # 查询逻辑
        user = await self.get_by_id(user_id)
        if not user:
            raise_api_exception(ErrorCode.USER_NOT_FOUND, ...)
        
        return user
```

### 3. 使用缓存装饰器

```python
from app.core.infrastructure.cache import cached

class UserService(BaseService[User]):
    @cached("user_stats", ttl=300)
    async def get_user_stats(self) -> Dict[str, Any]:
        """获取用户统计信息（自动缓存5分钟）"""
        # 统计逻辑
        return stats_data
```

### 4. 缓存失效

```python
from app.core.infrastructure.cache import CacheInvalidator

class UserService(BaseService[User]):
    async def update_user(self, user_id: int, user_data: Dict) -> User:
        # 更新用户
        user = await self._update_user_internal(user_id, user_data)
        
        # 失效相关缓存
        await CacheInvalidator.invalidate_user_cache(user_id)
        
        return user
```

## 服务层设计原则

### 1. 单一职责
每个服务类只负责一个领域（如UserService只处理用户相关业务）

### 2. 权限检查
服务层方法应该包含权限检查逻辑，而不是在endpoint中检查

### 3. 数据验证
业务规则验证应该在服务层完成

### 4. 审计日志
服务层方法应该记录审计日志

### 5. 异常处理
使用统一的异常处理机制（raise_api_exception）

## 优势

1. **代码复用**：业务逻辑可以在多个endpoint中复用
2. **易于测试**：服务层方法可以直接测试，不需要模拟HTTP请求
3. **职责分离**：endpoint只负责HTTP处理，业务逻辑在服务层
4. **易于维护**：业务逻辑集中管理，修改更方便

## 迁移步骤

1. 创建服务类（继承BaseService）
2. 将业务逻辑从endpoint移到服务方法
3. 在endpoint中使用服务层
4. 测试验证
5. 删除endpoint中的旧代码

## 注意事项

1. 服务层方法应该是异步的（async）
2. 服务层方法应该包含完整的错误处理
3. 服务层方法应该记录审计日志
4. 服务层方法应该进行权限检查
5. 使用缓存装饰器时，注意缓存键的唯一性

