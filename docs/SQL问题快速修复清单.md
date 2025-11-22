# SQL 问题快速修复清单

## 🔴 必须立即修复的问题

### 1. ENUM 值不匹配
```sql
-- 执行顺序：先更新数据，再修改结构
UPDATE `users` SET `role` = 'admin' WHERE `role` = 'ADMIN';
UPDATE `users` SET `role` = 'client' WHERE `role` = 'CLIENT';
ALTER TABLE `users` MODIFY COLUMN `role` ENUM('admin','client') NOT NULL DEFAULT 'client';
```

**代码修改：** 无需修改，代码中已使用 `UserRole.ADMIN` 和 `UserRole.CLIENT`（枚举值是小写）

### 2. 添加唯一约束
```sql
-- 先检查是否有重复数据
SELECT `date`, `product_id`, COUNT(*) as cnt
FROM `ad_data`
GROUP BY `date`, `product_id`
HAVING cnt > 1;

-- 如果有重复，需要先清理，然后执行：
ALTER TABLE `ad_data` ADD UNIQUE KEY `uq_ad_data_date_product` (`date`, `product_id`);
```

### 3. 字段长度不匹配

**模型代码需要修改：**

1. `app/models/models.py` 第 28 行：
   ```python
   # 修改前
   hashed_password = Column('hashed_password', String(100), ...)
   # 修改后
   hashed_password = Column('hashed_password', String(191), ...)
   ```

2. `app/models/session.py` 第 20 和 44 行：
   ```python
   # 修改前
   token_jti = Column(String(32), ...)
   # 修改后
   token_jti = Column(String(64), ...)
   ```

---

## 🟡 建议修复的问题

### 4. 移除生成列（如果使用模型中的 @property）
```sql
ALTER TABLE `ad_data` DROP COLUMN `coverage_rate`;
ALTER TABLE `ad_data` DROP COLUMN `display_rate`;
ALTER TABLE `ad_data` DROP COLUMN `click_rate`;
```

**注意：** 确保应用代码使用模型中的 `@property` 计算这些值。

### 5. 优化日期查询索引
```sql
-- MySQL 8.0+ 支持函数索引
ALTER TABLE `ad_data` ADD INDEX `idx_ad_data_date_func` ((DATE(`date`)));
```

**代码优化：** 修改 `app/api/api_v1/endpoints/ad_data.py` 中的 `get_ad_data_summary()` 函数，将 `func.date()` 改为范围查询。

---

## 🟢 可选优化

### 6. 清理冗余索引
```sql
ALTER TABLE `users` DROP INDEX `idx_users_username`;
ALTER TABLE `users` DROP INDEX `idx_users_email`;
```

### 7. 优化审计日志索引
```sql
ALTER TABLE `user_audit_logs` ADD INDEX `idx_audit_log_created_at_user` (`created_at`, `user_id`);
ALTER TABLE `user_audit_logs` ADD INDEX `idx_audit_log_created_at_action` (`created_at`, `action_type`);
```

---

## 📋 执行顺序

1. **备份数据库** ⚠️
2. 修复 ENUM 值（问题 1）
3. 检查并修复唯一约束（问题 2）
4. 修改模型代码（问题 3）
5. 测试应用功能
6. 执行可选优化（问题 4-7）

---

## ⚠️ 注意事项

- 所有修改前请先备份数据库
- 在生产环境执行前，先在测试环境验证
- 修改 ENUM 值后，需要重启应用
- 修改模型代码后，需要重新部署应用

