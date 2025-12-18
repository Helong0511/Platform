# CPL 系统部署指南

## 📋 部署前准备

### 1. 备份数据库
```bash
# 备份整个数据库
mysqldump -u username -p platform > platform_backup_$(date +%Y%m%d_%H%M%S).sql

# 或者只备份特定表
mysqldump -u username -p platform postback_conversions > postback_conversions_backup.sql
```

### 2. 检查数据库版本
确保 MySQL 版本 >= 5.7 或 MariaDB >= 10.2

---

## 🚀 部署步骤

### 第一步：执行数据库迁移

#### 1.1 创建新表
```bash
mysql -u username -p platform < scripts/data/cpl_system_tables.sql
```

**验证**：
```sql
USE platform;
SHOW TABLES LIKE '%advertiser%';
SHOW TABLES LIKE '%publisher%';
SHOW TABLES LIKE '%offer%';
SHOW TABLES LIKE '%click%';
SHOW TABLES LIKE '%cap%';
SHOW TABLES LIKE '%discount%';
SHOW TABLES LIKE '%test%';
```

#### 1.2 修改现有表
```bash
mysql -u username -p platform < scripts/data/alter_postback_conversions_table.sql
```

**验证**：
```sql
USE platform;
DESCRIBE postback_conversions;
-- 检查是否有 click_id, click_time, conversion_status 字段
```

### 第二步：重启应用

```bash
# 如果使用 systemd
sudo systemctl restart your-app-service

# 或者如果使用 supervisor
supervisorctl restart your-app

# 或者直接重启
pkill -f "uvicorn"  # 或你的应用进程名
# 然后重新启动应用
```

### 第三步：验证功能

#### 3.1 检查前端页面
1. 登录系统
2. 检查侧边栏是否有 "CPL系统" 菜单
3. 访问各个管理页面，确认可以正常加载

#### 3.2 测试基础功能
1. **创建广告主**
   - 访问：广告主管理
   - 点击"添加广告主"
   - 填写信息并保存
   - 验证是否创建成功

2. **创建渠道**
   - 访问：渠道管理
   - 点击"添加渠道"
   - 填写信息并保存
   - 验证是否创建成功

3. **创建Offer**
   - 访问：Offer管理
   - 点击"添加Offer"
   - 选择广告主，填写信息
   - 分配渠道
   - 验证是否创建成功

#### 3.3 测试业务逻辑
1. **测试Cap功能**
   - 创建Cap配置
   - 验证Cap检查是否生效

2. **测试扣量功能**
   - 创建扣量配置
   - 验证扣量计算是否正确

3. **测试点击追踪**
   - 访问点击追踪URL
   - 验证Click记录是否创建

4. **测试Postback处理**
   - 发送测试Postback
   - 验证是否关联Click ID
   - 验证Cap和扣量是否生效

---

## ⚙️ 配置说明

### 1. 追踪基础URL配置

在 `app/core/config.py` 或环境变量中配置：
```python
TRACKING_BASE_URL = "https://client.btfrx.online"
```

### 2. 定时任务配置

#### 2.1 每日Cap重置任务

需要配置定时任务，每天 00:00 UTC 执行：
```python
# 在定时任务配置中添加
from app.scheduler.cpl_tasks import reset_daily_caps_task

# 每天 00:00 UTC 执行
schedule.add_job(
    reset_daily_caps_task,
    trigger='cron',
    hour=0,
    minute=0,
    timezone='UTC'
)
```

#### 2.2 Cap计数同步任务（可选）

用于修复计数不准确的情况：
```python
from app.scheduler.cpl_tasks import sync_cap_counts_task

# 每天 01:00 UTC 执行
schedule.add_job(
    sync_cap_counts_task,
    trigger='cron',
    hour=1,
    minute=0,
    timezone='UTC'
)
```

---

## 🔍 故障排查

### 问题1：前端页面无法访问

**检查**：
1. 路由是否正确注册
2. 菜单配置是否正确
3. 浏览器控制台是否有错误

**解决**：
```bash
# 检查路由文件
cat frontend/src/router/index.js | grep -i "cpl\|advertiser\|publisher\|offer"

# 检查菜单文件
cat frontend/src/components/Layout/Sidebar.vue | grep -i "cpl"
```

### 问题2：API 返回 404

**检查**：
1. API 路由是否正确注册
2. 后端服务是否正常运行

**解决**：
```bash
# 检查API路由
cat app/api/api_v1/api.py | grep -i "advertiser\|publisher\|offer"

# 检查后端日志
tail -f logs/app.log | grep -i "error\|exception"
```

### 问题3：数据库字段不存在

**检查**：
```sql
-- 检查新表是否存在
SHOW TABLES LIKE '%advertiser%';

-- 检查字段是否存在
DESCRIBE postback_conversions;
```

**解决**：
- 重新执行数据库迁移脚本
- 检查脚本是否有错误

### 问题4：Cap检查不生效

**检查**：
1. Cap配置是否正确创建
2. Cap检查逻辑是否被调用
3. 日志中是否有相关错误

**解决**：
```python
# 检查Cap配置
SELECT * FROM offer_caps WHERE is_active = 1;

# 检查日志
grep -i "cap" logs/app.log
```

### 问题5：扣量计算不正确

**检查**：
1. 扣量配置是否正确
2. 优先级是否正确应用
3. 计算逻辑是否有错误

**解决**：
```python
# 检查扣量配置
SELECT * FROM offer_discounts WHERE is_active = 1;

# 检查渠道默认扣量
SELECT id, publisher_name, price_discount FROM publishers;
```

---

## 📊 性能优化建议

### 1. 数据库索引

确保以下字段有索引：
- `clicks.click_id`
- `clicks.offer_id`
- `clicks.publisher_id`
- `postback_conversions.click_id`
- `postback_conversions.conversion_status`

### 2. 查询优化

- 使用分页查询，避免一次性加载大量数据
- 对常用查询字段建立复合索引
- 定期清理历史数据

### 3. 缓存策略

- 缓存广告主、渠道、Offer列表（如果数据不经常变化）
- 缓存Cap配置（需要及时更新）

---

## 🔐 安全建议

1. **API权限控制**
   - 确保所有管理API都需要管理员权限
   - 测试工具API也需要权限控制

2. **数据验证**
   - 所有输入数据都需要验证
   - 防止SQL注入和XSS攻击

3. **日志记录**
   - 记录所有重要操作
   - 定期审查日志

---

## 📝 维护建议

### 日常维护

1. **每日检查**
   - 检查Cap重置任务是否执行成功
   - 检查错误日志

2. **每周检查**
   - 检查数据统计是否正常
   - 检查Cap计数是否准确

3. **每月检查**
   - 清理历史测试数据
   - 优化数据库性能

### 数据清理

```sql
-- 清理旧的测试记录（保留最近30天）
DELETE FROM advertiser_tests 
WHERE created_at < DATE_SUB(NOW(), INTERVAL 30 DAY);

DELETE FROM affiliate_tests 
WHERE created_at < DATE_SUB(NOW(), INTERVAL 30 DAY);
```

---

## 📞 支持

如遇到问题，请检查：
1. 日志文件：`logs/app.log`
2. 数据库错误日志
3. 前端浏览器控制台

---

**最后更新**: 2025-12-17

