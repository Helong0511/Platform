# 数据库迁移脚本

## 移除字符串ID字段迁移

### 文件说明

1. **remove_string_ids.sql** - 兼容版本（适用于所有MySQL版本）
   - 使用动态SQL检查字段和索引是否存在
   - 适用于 MySQL 5.7 及以下版本

2. **remove_string_ids_simple.sql** - 简化版本（适用于 MySQL 8.0+）
   - 使用 `IF EXISTS` 语法
   - 更简洁，但需要 MySQL 8.0+

### 迁移内容

此迁移脚本会：

1. **删除 `advertisers` 表中的字段：**
   - 删除 `advertiser_id` 字段（varchar(50)）
   - 删除 `advertiser_id` 唯一索引
   - 删除 `idx_advertiser_id` 索引

2. **删除 `publishers` 表中的字段：**
   - 删除 `publisher_id` 字段（varchar(50)）
   - 删除 `publisher_id` 唯一索引
   - 删除 `idx_publisher_id` 索引

3. **删除 `offers` 表中的字段：**
   - 删除 `offer_id` 字段（varchar(50)）
   - 删除 `offer_id` 唯一索引
   - 删除 `idx_offer_id` 索引

### 执行步骤

1. **备份数据库**
   ```bash
   mysqldump -u username -p platform > backup_$(date +%Y%m%d_%H%M%S).sql
   ```

2. **停止应用服务**
   - 确保没有正在运行的应用程序连接数据库

3. **执行迁移脚本**
   ```bash
   # MySQL 8.0+ 使用简化版
   mysql -u username -p platform < scripts/migrations/remove_string_ids_simple.sql
   
   # MySQL 5.7 及以下使用兼容版
   mysql -u username -p platform < scripts/migrations/remove_string_ids.sql
   ```

4. **验证迁移结果**
   ```sql
   -- 检查 advertisers 表结构
   DESCRIBE advertisers;
   
   -- 检查 publishers 表结构
   DESCRIBE publishers;
   
   -- 检查 offers 表结构
   DESCRIBE offers;
   
   -- 确认字段已删除
   SELECT COLUMN_NAME 
   FROM information_schema.COLUMNS 
   WHERE TABLE_SCHEMA = 'platform' 
   AND TABLE_NAME IN ('advertisers', 'publishers', 'offers')
   AND COLUMN_NAME IN ('advertiser_id', 'publisher_id', 'offer_id');
   -- 应该返回空结果
   ```

5. **重启应用服务**

### 重要说明

- ⚠️ **此迁移不可逆**：删除的字段和索引无法恢复，请务必先备份
- ✅ **外键字段保留**：其他表中的 `advertiser_id`、`publisher_id` 和 `offer_id` 字段（作为外键）会保留
- ✅ **数据完整性**：所有关联数据保持不变，只是移除了字符串ID字段
- ✅ **向后兼容**：如果字段不存在，脚本会安全跳过，不会报错

### 回滚方案

如果需要回滚，需要手动重新创建字段：

```sql
-- 回滚 advertisers 表（示例，需要根据实际数据调整）
ALTER TABLE `advertisers` 
ADD COLUMN `advertiser_id` varchar(50) NOT NULL COMMENT '广告主ID（系统生成，唯一标识）' AFTER `id`;

ALTER TABLE `advertisers` 
ADD UNIQUE INDEX `advertiser_id`(`advertiser_id`),
ADD INDEX `idx_advertiser_id`(`advertiser_id`);

-- 回滚 publishers 表（示例，需要根据实际数据调整）
ALTER TABLE `publishers` 
ADD COLUMN `publisher_id` varchar(50) NOT NULL COMMENT '渠道ID（系统生成，唯一标识）' AFTER `id`;

ALTER TABLE `publishers` 
ADD UNIQUE INDEX `publisher_id`(`publisher_id`),
ADD INDEX `idx_publisher_id`(`publisher_id`);

-- 回滚 offers 表（示例，需要根据实际数据调整）
ALTER TABLE `offers` 
ADD COLUMN `offer_id` varchar(50) NOT NULL COMMENT 'Offer ID（系统生成，唯一标识）' AFTER `id`;

ALTER TABLE `offers` 
ADD UNIQUE INDEX `offer_id`(`offer_id`),
ADD INDEX `idx_offer_id`(`offer_id`);
```

注意：回滚时需要为现有记录生成新的字符串ID，这需要额外的数据迁移脚本。

