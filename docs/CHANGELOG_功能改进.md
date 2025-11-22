# 功能改进变更日志

## 2024年12月 - 安全性和性能优化

### 新增功能

#### 🔒 安全增强

1. **CSRF防护**
   - 添加CSRF中间件，防止跨站请求伪造攻击
   - 支持Redis存储CSRF令牌（生产环境多进程）
   - 前端自动处理CSRF令牌
   - 配置项：`ENABLE_CSRF`、`CSRF_TOKEN_EXPIRE_SECONDS`

2. **Token黑名单机制**
   - 实现JWT令牌黑名单功能
   - 支持主动撤销token
   - 退出登录时自动加入黑名单
   - Token验证时检查黑名单

3. **会话管理**
   - 添加用户会话跟踪功能
   - 支持查看活跃会话
   - 支持撤销指定会话或所有其他会话
   - 管理员可以管理任意用户的会话

#### ⚡ 性能优化

4. **Redis限流支持**
   - 限流中间件支持Redis存储（多进程环境）
   - 自动回退到内存存储（Redis不可用时）
   - 配置项：`REDIS_HOST`、`REDIS_PORT`、`REDIS_DB`、`REDIS_PASSWORD`

5. **全文搜索索引**
   - 为users、clients、products、scheduled_tasks表添加全文索引
   - 支持中文搜索（ngram解析器）
   - 自动回退到LIKE查询（索引不可用时）
   - 显著提升搜索性能

6. **虚拟滚动组件**
   - 添加VirtualTable组件（基于Element Plus）
   - 添加VirtualList组件（简单列表）
   - 优化大数据量列表的渲染性能
   - 支持移动端优化

### 修改的文件

#### 后端

- `app/core/csrf.py` - 新增CSRF防护模块
- `app/core/redis_client.py` - 新增Redis客户端模块
- `app/core/middleware.py` - 更新限流中间件支持Redis
- `app/core/security.py` - 更新token验证支持黑名单检查
- `app/core/fulltext_search.py` - 新增全文搜索工具模块
- `app/core/config.py` - 添加Redis和CSRF配置项
- `app/models/session.py` - 新增会话和黑名单模型
- `app/models/__init__.py` - 新增模型导出文件
- `app/api/api_v1/endpoints/auth.py` - 更新登录逻辑记录会话
- `app/api/api_v1/endpoints/sessions.py` - 新增会话管理API
- `app/api/api_v1/endpoints/users.py` - 更新搜索使用全文索引
- `app/api/api_v1/endpoints/clients.py` - 更新搜索使用全文索引
- `app/api/api_v1/endpoints/products.py` - 更新搜索使用全文索引
- `app/api/api_v1/endpoints/scheduled_tasks.py` - 更新搜索使用全文索引
- `app/api/api_v1/api.py` - 注册会话管理路由
- `app/main.py` - 添加Redis生命周期管理和模型导入
- `requirements.txt` - 添加redis>=5.0.0依赖

#### 前端

- `frontend/src/main.js` - 添加CSRF令牌处理
- `frontend/src/components/VirtualTable.vue` - 新增虚拟滚动表格组件
- `frontend/src/components/VirtualList.vue` - 新增虚拟滚动列表组件

#### 数据库

- `scripts/add_fulltext_indexes.sql` - 新增全文索引创建脚本

#### 文档

- `docs/数据库迁移说明.md` - 新增数据库迁移说明
- `README_虚拟滚动使用说明.md` - 新增虚拟滚动使用说明
- `功能改进完成总结.md` - 新增功能改进总结
- `env.example` - 更新环境变量示例

### 数据库迁移

#### 必须执行

1. **添加全文搜索索引**：
   ```bash
   mysql -u root -p platform < scripts/add_fulltext_indexes.sql
   ```

2. **会话管理表**：
   - 会在应用启动时自动创建
   - 或参考`docs/数据库迁移说明.md`手动创建

### 配置更新

#### 环境变量（.env文件）

```env
# Redis配置（可选但推荐，生产环境强烈建议配置）
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your-redis-password

# CSRF配置
ENABLE_CSRF=true
CSRF_TOKEN_EXPIRE_SECONDS=3600
```

### 依赖更新

- `redis>=5.0.0` - Redis客户端（支持异步）

### 破坏性变更

无

### 向后兼容性

- ✅ 所有新功能都是可选的
- ✅ Redis未配置时自动回退到内存存储
- ✅ CSRF可通过配置禁用
- ✅ 全文搜索自动回退到LIKE查询
- ✅ 会话管理不影响现有登录流程

### 已知问题

1. **全文索引**：
   - 需要MySQL 5.7.6+支持ngram解析器
   - 如果MySQL版本不支持，可以移除`WITH PARSER ngram`部分

2. **Redis**：
   - 如果未配置Redis，多进程环境下限流可能不一致
   - 生产环境强烈建议配置Redis

### 升级指南

1. **更新依赖**：
   ```bash
   pip install -r requirements.txt
   ```

2. **配置Redis**（推荐）：
   - 设置环境变量：`REDIS_HOST`、`REDIS_PORT`等
   - 或使用Docker Compose启动Redis服务

3. **执行数据库迁移**：
   ```bash
   mysql -u root -p platform < scripts/add_fulltext_indexes.sql
   ```

4. **重启应用**：
   - 应用启动时会自动创建会话管理表
   - 检查日志确认所有功能正常

### 测试建议

1. 测试CSRF防护是否正常工作
2. 测试Redis限流是否正常工作
3. 测试会话管理功能
4. 测试全文搜索性能
5. 测试虚拟滚动组件（大数据量场景）

### 相关文档

- `docs/数据库迁移说明.md` - 数据库迁移详细说明
- `README_虚拟滚动使用说明.md` - 虚拟滚动组件使用说明
- `功能改进完成总结.md` - 功能改进详细总结

