# 生产环境部署检查清单

## ✅ 已完成的检查和修复

### 1. 安全性检查 ✅

#### 1.1 认证和授权
- ✅ JWT 令牌生成和验证已实现
- ✅ 令牌黑名单机制已实现
- ✅ 密码使用 bcrypt 加密存储
- ✅ 所有 API 端点都有权限检查（70+ 个端点使用 `Depends(get_current_user)` 或 `Depends(require_admin)`）
- ✅ 用户状态检查（is_active, login_restricted）已实现

#### 1.2 CSRF 防护
- ✅ CSRF 中间件已启用
- ✅ 所有前端 POST/PUT/DELETE 请求都包含 CSRF 令牌
- ✅ 文件上传请求已修复（移除手动 Content-Type，确保包含 CSRF 令牌）
- ✅ 多进程环境下使用 Redis 同步 CSRF 令牌
- ✅ 所有 API 函数都使用 `ensureCsrfToken()` 确保令牌存在

#### 1.3 SQL 注入防护
- ✅ 使用 SQLAlchemy ORM（参数化查询）
- ✅ 输入验证和 SQL 注入检测已实现（`app/core/validation.py`）
- ✅ 未发现直接使用字符串拼接的 SQL 查询

#### 1.4 XSS 防护
- ✅ XSS 检测已实现（`app/core/validation.py`）
- ✅ 安全响应头已配置（X-Frame-Options, X-Content-Type-Options）

#### 1.5 其他安全措施
- ✅ HTTPS 强制重定向（生产环境）
- ✅ API 限流已实现
- ✅ 登录接口限流（防止暴力破解）
- ✅ CORS 配置严格（生产环境不允许 localhost）
- ✅ 安全响应头中间件已配置

### 2. 配置检查 ✅

#### 2.1 环境变量验证
- ✅ 生产环境必须设置：
  - `PRODUCTION_ENV=production` 或 `prod`
  - `SECRET_KEY`（至少32字符）
  - `DATABASE_URL`（不能使用默认密码）
  - `BACKEND_CORS_ORIGINS`（不能包含 localhost）
  - `FIRST_SUPERUSER_PASSWORD`（至少12字符，不能使用默认密码）

#### 2.2 数据库配置
- ✅ 连接池配置合理（pool_size=15, max_overflow=10）
- ✅ 连接回收时间设置（3600秒）
- ✅ 多进程环境优化（每个 worker 独立连接池）

#### 2.3 Redis 配置
- ✅ Redis 连接池配置
- ✅ CSRF 令牌使用 Redis 存储（多进程同步）
- ✅ 限流使用 Redis（回退到内存存储）

### 3. 错误处理 ✅

#### 3.1 全局异常处理
- ✅ 全局异常处理器已实现
- ✅ HTTP 500/503 错误记录到操作日志
- ✅ 连接断开异常正确处理（避免 EndOfStream 错误）
- ✅ 错误响应格式统一

#### 3.2 前端错误处理
- ✅ Axios 拦截器处理 401/403/429 错误
- ✅ CSRF 错误自动重试机制
- ✅ 错误消息用户友好显示

### 4. 日志记录 ✅

#### 4.1 后端日志
- ✅ 日志文件轮转（5MB，保留5个备份）
- ✅ 日志包含进程ID（多进程环境）
- ✅ 日志级别可配置（生产环境默认 WARNING）
- ✅ 请求日志中间件记录所有请求

#### 4.2 审计日志
- ✅ 所有关键操作记录到审计日志
- ✅ 前端错误记录到操作日志
- ✅ 后端错误记录到操作日志

### 5. 性能优化 ✅

#### 5.1 数据库优化
- ✅ 数据库索引已创建（ad_data 表有复合索引）
- ✅ 查询使用参数化（防止 SQL 注入）
- ✅ 连接池配置合理

#### 5.2 缓存
- ✅ Redis 用于 CSRF 令牌和限流
- ✅ 客户端详情缓存（5分钟 TTL）

#### 5.3 部署配置
- ✅ Gunicorn 配置优化（3 workers，120秒超时）
- ✅ Nginx 配置优化（gzip 压缩，静态资源缓存）
- ✅ 静态资源缓存（7天）

### 6. 代码质量 ✅

#### 6.1 代码检查
- ✅ 无硬编码密码或密钥
- ✅ 无 SQL 注入风险
- ✅ 无明显的安全漏洞
- ✅ 前端无 console.log（仅 logger.js 和 ApiDocumentation.vue 有，这是正常的）

#### 6.2 依赖项
- ✅ requirements.txt 版本固定
- ✅ 无已知安全漏洞的依赖项

### 7. 部署配置 ✅

#### 7.1 Gunicorn
- ✅ 配置文件已优化
- ✅ Worker 数量根据 CPU 自动计算
- ✅ 超时配置合理（120秒）
- ✅ 日志配置正确

#### 7.2 Nginx
- ✅ HTTPS 配置正确
- ✅ SSL 证书配置
- ✅ 安全头配置
- ✅ 反向代理配置正确
- ✅ 静态资源缓存配置

#### 7.3 部署脚本
- ✅ update_frontend.sh 脚本存在
- ⚠️ 注意：脚本中使用了 `sudo chmod -R 777`，建议改为更安全的权限设置

## ⚠️ 部署前必须检查的事项

### 1. 环境变量设置

确保在生产服务器上设置以下环境变量：

```bash
# 必需的环境变量
export PRODUCTION_ENV=production
export SECRET_KEY="<至少32字符的随机字符串>"
export DATABASE_URL="mysql+aiomysql://user:password@host:port/database"
export BACKEND_CORS_ORIGINS="https://your-domain.com"
export FIRST_SUPERUSER_PASSWORD="<至少12字符的强密码>"

# 可选但建议设置的环境变量
export REDIS_URL="redis://localhost:6379/0"
export REDIS_PASSWORD="<如果有密码>"
export LOG_LEVEL="WARNING"
export ACCESS_TOKEN_EXPIRE_MINUTES=240
```

### 2. 数据库准备

- [ ] 确保数据库已创建
- [ ] 确保数据库用户有足够权限
- [ ] 运行数据库迁移（如果需要）
- [ ] 检查数据库连接池配置是否适合服务器资源

### 3. Redis 准备

- [ ] 确保 Redis 服务运行
- [ ] 检查 Redis 内存配置
- [ ] 如果 Redis 有密码，设置 `REDIS_PASSWORD` 环境变量

### 4. SSL 证书

- [ ] 确保 SSL 证书文件存在且有效
- [ ] 检查证书路径是否正确（nginx 配置中）
- [ ] 确保证书未过期

### 5. 文件权限

- [ ] 检查日志目录权限（`/data/Platform/logs`）
- [ ] 检查前端构建目录权限（`/data/Platform/frontend/dist`）
- [ ] 检查 Gunicorn PID 文件目录权限

### 6. 系统服务

- [ ] 检查 systemd 服务文件配置
- [ ] 确保服务在系统启动时自动启动
- [ ] 测试服务重启命令

### 7. 防火墙

- [ ] 确保端口 80 和 443 开放
- [ ] 确保后端端口（8960）只允许本地访问
- [ ] 检查 IP 白名单配置（如果需要）

### 8. 监控和备份

- [ ] 设置日志监控
- [ ] 设置数据库备份
- [ ] 设置应用监控（可选）

## 📋 部署步骤

1. **备份现有数据**
   ```bash
   mysqldump -u user -p database_name > backup_$(date +%Y%m%d).sql
   ```

2. **更新代码**
   ```bash
   cd /data/Platform
   git pull
   ```

3. **更新依赖**
   ```bash
   source venv/bin/activate
   pip install -r requirements.txt
   ```

4. **构建前端**
   ```bash
   cd frontend
   npm install
   npm run build
   ```

5. **重启服务**
   ```bash
   sudo systemctl restart Platform-backend.service
   sudo systemctl restart nginx
   ```

6. **检查服务状态**
   ```bash
   sudo systemctl status Platform-backend.service
   sudo systemctl status nginx
   ```

7. **检查日志**
   ```bash
   tail -f /data/Platform/logs/app.log
   tail -f /var/log/nginx/error.log
   ```

## 🔍 部署后验证

1. **功能测试**
   - [ ] 登录功能
   - [ ] 创建/更新/删除操作
   - [ ] 文件上传
   - [ ] API 调用

2. **安全测试**
   - [ ] HTTPS 强制重定向
   - [ ] CSRF 防护
   - [ ] API 限流
   - [ ] 权限检查

3. **性能测试**
   - [ ] 响应时间
   - [ ] 并发请求
   - [ ] 数据库连接池

4. **日志检查**
   - [ ] 无错误日志
   - [ ] 请求日志正常
   - [ ] 审计日志正常

## ⚠️ 已知问题和建议

1. **部署脚本权限**
   - `update_frontend.sh` 中使用了 `chmod -R 777`，建议改为更安全的权限（如 755）

2. **日志轮转**
   - 当前日志文件大小限制为 5MB，如果日志量大，可能需要调整

3. **数据库连接**
   - 当前连接池配置适合 3 workers，如果增加 workers，需要相应调整数据库连接数限制

4. **Redis 可用性**
   - 如果 Redis 不可用，系统会回退到内存存储，但多进程环境下可能有问题

## 📝 注意事项

1. **首次部署**
   - 确保创建管理员账户（通过环境变量 `FIRST_SUPERUSER` 和 `FIRST_SUPERUSER_PASSWORD`）
   - 首次启动会自动创建数据库表

2. **更新部署**
   - 更新前备份数据库
   - 检查是否有数据库迁移需要运行
   - 更新后检查日志确认无错误

3. **监控**
   - 定期检查日志文件大小
   - 监控数据库连接数
   - 监控 Redis 内存使用

## ✅ 检查完成

所有关键检查已完成，代码已准备好部署到生产环境。

**最后更新**: 2025-01-XX

