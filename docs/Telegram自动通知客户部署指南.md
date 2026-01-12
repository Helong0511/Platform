# Telegram 自动通知客户部署指南

## 一、部署前准备

### 1.1 环境要求

- ✅ Python 3.10+
- ✅ MySQL 5.7+ 或 8.0+
- ✅ Redis 5.0+（可选，但推荐）
- ✅ Telegram Bot Token（必需）

### 1.2 依赖检查

确保已安装以下 Python 包：
- `pyTelegramBotAPI` - Telegram Bot 库
- `redis` - Redis 客户端（可选）
- `sqlalchemy` - 数据库 ORM
- `fastapi` - Web 框架

### 1.3 配置检查

确保以下环境变量或配置已设置：
- `TELEGRAM_TOKEN` - Telegram Bot Token
- `TELEGRAM_ENABLE` - 是否启用 Telegram（默认：true）
- `REDIS_HOST` - Redis 主机（可选）
- `REDIS_PORT` - Redis 端口（可选）
- `REDIS_PASSWORD` - Redis 密码（可选）

## 二、数据库迁移

### 2.1 备份数据库

**重要**：执行迁移前必须备份数据库！

```bash
# 备份数据库
mysqldump -u username -p database_name > backup_$(date +%Y%m%d_%H%M%S).sql
```

### 2.2 执行迁移脚本

```bash
# 执行迁移脚本
mysql -u username -p database_name < scripts/data/migration_fix_postback_notification_conversion_id_nullable.sql
```

### 2.3 验证迁移

```sql
-- 检查字段修改
DESCRIBE postback_notifications;
-- 确认 conversion_id 字段的 Null 为 YES

-- 检查现有数据
SELECT COUNT(*) FROM postback_notifications WHERE conversion_id IS NULL;
```

## 三、代码部署

### 3.1 后端部署

1. **更新代码**
   ```bash
   git pull origin main
   # 或手动复制更新的文件
   ```

2. **重启服务**
   ```bash
   # 如果使用 systemd
   sudo systemctl restart platform-backend
   
   # 如果使用其他方式
   # 重启您的应用服务器
   ```

3. **检查日志**
   ```bash
   # 检查服务是否正常启动
   tail -f /var/log/platform-backend.log
   # 或
   journalctl -u platform-backend -f
   ```

### 3.2 前端部署

1. **更新代码**
   ```bash
   cd frontend
   git pull origin main
   # 或手动复制更新的文件
   ```

2. **构建（如果需要）**
   ```bash
   npm run build
   ```

3. **重启服务**
   ```bash
   # 如果使用 Nginx
   sudo systemctl reload nginx
   
   # 如果使用其他方式
   # 重启您的前端服务器
   ```

## 四、功能验证

### 4.1 实时通知测试

1. **配置客户通知**
   - 登录系统（管理员）
   - 进入用户管理页面
   - 找到客户用户，点击"通知"按钮
   - 配置：
     - 启用通知：✅
     - 通知转化事件：✅
     - 通知渠道：Telegram ✅
     - Telegram Chat ID：填写客户的 Chat ID
     - 通知频率：实时通知

2. **触发转化**
   - 通过 Postback API 触发一次转化
   - 或使用测试工具发送 Postback 请求

3. **验证通知**
   - 检查客户是否收到 Telegram 通知
   - 检查通知消息格式是否正确
   - 检查通知记录是否保存到数据库

### 4.2 每小时汇总通知测试

1. **配置客户通知**
   - 将通知频率改为"每小时汇总"

2. **触发多个转化**
   - 触发 3-5 个转化

3. **等待定时任务执行**
   - 等待到下一个整点（例如：15:00）
   - 或手动触发定时任务（如果支持）

4. **验证汇总通知**
   - 检查客户是否收到汇总通知
   - 检查汇总消息格式是否正确
   - 检查通知记录（`conversion_id` 应为 `NULL`）

### 4.3 每天汇总通知测试

1. **配置客户通知**
   - 将通知频率改为"每天汇总"

2. **触发多个转化**
   - 触发 3-5 个转化

3. **等待定时任务执行**
   - 等待到第二天 00:00
   - 或手动触发定时任务（如果支持）

4. **验证汇总通知**
   - 检查客户是否收到汇总通知
   - 检查汇总消息格式是否正确
   - 检查通知记录（`conversion_id` 应为 `NULL`）

### 4.4 高价值转化通知测试

1. **配置客户通知**
   - 启用"高价值转化通知"
   - 设置阈值（例如：$10.00）

2. **触发转化**
   - 触发一个超过阈值的转化
   - 触发一个低于阈值的转化

3. **验证通知**
   - 检查是否只收到超过阈值的转化通知
   - 检查高价值通知消息格式

### 4.5 通知记录查询测试

1. **查询实时通知记录**
   - 进入 Postback 管理页面
   - 查看转化记录的通知数量
   - 点击查看通知记录
   - 验证通知记录显示正确

2. **查询汇总通知记录**
   - 使用通知记录查询 API
   - 过滤条件：`notification_type=summary_hourly` 或 `summary_daily`
   - 验证汇总通知记录显示正确（`conversion_id` 显示为"汇总通知"）

### 4.6 降级测试

1. **Redis 不可用测试**
   - 停止 Redis 服务
   - 触发转化
   - 验证降级为实时发送
   - 检查日志

2. **队列满测试**
   - 模拟队列满的情况（需要大量转化）
   - 验证降级为实时发送
   - 检查日志

## 五、监控设置

### 5.1 通知发送成功率监控

建议监控指标：
- 实时通知发送成功率
- 汇总通知发送成功率
- 按客户统计发送成功率

监控方式：
- 查询 `postback_notifications` 表
- 统计 `notification_status='sent'` 的比例

### 5.2 定时任务监控

建议监控指标：
- 每小时汇总任务执行时间
- 每天汇总任务执行时间
- 任务执行成功率

监控方式：
- 查询定时任务执行记录
- 检查任务执行结果

### 5.3 Redis 队列监控

建议监控指标：
- 队列长度
- 队列处理速度
- Redis 连接状态

监控方式：
- 使用 Redis 命令：`LLEN notification_queue:hourly:*`
- 使用 Redis 命令：`LLEN notification_queue:daily:*`

## 六、常见问题

### 6.1 客户没有收到通知

**可能原因**：
1. Telegram Chat ID 配置错误
2. 通知未启用
3. 通知频率配置错误
4. Telegram Bot 未启动

**解决方法**：
1. 检查客户通知配置
2. 测试 Telegram 连接
3. 检查日志
4. 验证 Telegram Bot 状态

### 6.2 汇总通知没有发送

**可能原因**：
1. Redis 不可用
2. 定时任务未执行
3. 队列为空

**解决方法**：
1. 检查 Redis 连接
2. 检查定时任务执行记录
3. 检查队列内容
4. 检查日志

### 6.3 通知记录查询不到汇总通知

**可能原因**：
1. 数据库迁移未执行
2. `conversion_id` 字段仍为 `NOT NULL`

**解决方法**：
1. 执行数据库迁移脚本
2. 验证字段修改

## 七、回滚方案

### 7.1 代码回滚

如果部署后出现问题，可以回滚代码：

```bash
# 回滚到上一个版本
git checkout <previous-commit-hash>

# 重启服务
sudo systemctl restart platform-backend
```

### 7.2 数据库回滚

如果需要回滚数据库迁移：

```sql
-- 恢复 conversion_id 字段为 NOT NULL（不推荐，会丢失汇总通知记录）
ALTER TABLE `postback_notifications` 
MODIFY COLUMN `conversion_id` int NOT NULL COMMENT '转化记录ID';
```

**注意**：回滚数据库迁移会丢失汇总通知记录，不推荐。

## 八、性能优化建议

### 8.1 Redis 优化

- 确保 Redis 有足够的内存
- 监控 Redis 内存使用
- 定期清理过期队列

### 8.2 数据库优化

- 确保 `postback_notifications` 表有合适的索引
- 定期清理旧的通知记录（可选）

### 8.3 定时任务优化

- 监控任务执行时间
- 如果任务执行时间过长，考虑优化查询逻辑

## 九、安全检查

### 9.1 权限检查

- ✅ 确保只有管理员可以配置客户通知
- ✅ 确保客户只能查看自己的通知记录

### 9.2 输入验证

- ✅ Telegram Chat ID 格式验证
- ✅ 通知频率验证
- ✅ 消息长度限制

## 十、部署检查清单

### 10.1 部署前

- [ ] 备份数据库
- [ ] 检查代码更新
- [ ] 检查配置文件
- [ ] 检查依赖包

### 10.2 部署中

- [ ] 执行数据库迁移
- [ ] 更新后端代码
- [ ] 更新前端代码
- [ ] 重启服务

### 10.3 部署后

- [ ] 测试实时通知
- [ ] 测试汇总通知
- [ ] 测试通知记录查询
- [ ] 检查日志
- [ ] 设置监控

## 十一、总结

### 11.1 部署步骤总结

1. **备份数据库** ⚠️ 必须
2. **执行数据库迁移** ⚠️ 必须
3. **更新代码** ⚠️ 必须
4. **重启服务** ⚠️ 必须
5. **功能测试** ✅ 推荐
6. **设置监控** ✅ 推荐

### 11.2 重要提醒

1. ⚠️ **数据库迁移**：部署前必须执行
2. ⚠️ **功能测试**：部署后必须测试
3. ⚠️ **监控设置**：建议设置监控和告警

### 11.3 支持

如果遇到问题：
1. 检查日志文件
2. 检查数据库状态
3. 检查 Redis 状态
4. 检查 Telegram Bot 状态
5. 参考文档和常见问题

---

**部署完成时间**：________  
**部署人员**：________  
**测试结果**：________  
**备注**：________
