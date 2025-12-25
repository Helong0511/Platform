# Clicks 表优化方案

## 一、当前表结构分析

### 1.1 现有索引

```sql
PRIMARY KEY (id)
UNIQUE INDEX idx_click_id (click_id)
INDEX idx_offer_id (offer_id)
INDEX idx_publisher_id (publisher_id)
INDEX idx_advertiser_id (advertiser_id)
INDEX idx_short_link_id (short_link_id)
INDEX idx_click_time (click_time)
INDEX idx_conversion_id (conversion_id)
```

### 1.2 查询模式分析

根据代码分析，主要查询模式：

1. **统计查询**（最常见）：
   ```sql
   -- 按时间范围 + offer_id + publisher_id 统计
   SELECT offer_id, publisher_id, COUNT(*) 
   FROM clicks 
   WHERE click_time >= ? AND click_time < ?
     AND offer_id = ? 
     AND publisher_id = ?
   GROUP BY offer_id, publisher_id
   ```

2. **时间范围查询**：
   ```sql
   -- 按时间范围查询
   SELECT * FROM clicks 
   WHERE click_time >= ? AND click_time < ?
   ```

3. **多条件过滤**：
   ```sql
   -- 按多个条件过滤
   SELECT * FROM clicks 
   WHERE offer_id = ? 
     AND publisher_id = ? 
     AND advertiser_id = ?
     AND click_time >= ?
   ```

---

## 二、优化建议

### 2.1 添加复合索引（高优先级）

#### 索引1：时间范围 + Offer + Publisher（最常用）

```sql
-- 用于统计查询（按时间范围 + offer_id + publisher_id 分组）
CREATE INDEX idx_clicks_time_offer_publisher 
ON clicks(click_time, offer_id, publisher_id);
```

**优势**：
- ✅ 覆盖最常见的统计查询
- ✅ 支持时间范围 + offer_id + publisher_id 的过滤
- ✅ 支持 GROUP BY offer_id, publisher_id

#### 索引2：时间范围 + Offer

```sql
-- 用于按Offer统计
CREATE INDEX idx_clicks_time_offer 
ON clicks(click_time, offer_id);
```

**优势**：
- ✅ 支持按时间范围 + offer_id 的查询
- ✅ 用于按Offer统计的接口

#### 索引3：Offer + Publisher + 时间（可选）

```sql
-- 用于按Offer和Publisher过滤
CREATE INDEX idx_clicks_offer_publisher_time 
ON clicks(offer_id, publisher_id, click_time);
```

**优势**：
- ✅ 如果查询先按 offer_id 和 publisher_id 过滤，再按时间排序
- ✅ 支持按 offer_id + publisher_id 的统计

---

### 2.2 分区表（如果数据量很大）

如果 `clicks` 表数据量超过 **1000万条**，考虑按时间分区：

```sql
-- 按月分区（示例）
ALTER TABLE clicks 
PARTITION BY RANGE (YEAR(click_time) * 100 + MONTH(click_time)) (
    PARTITION p202501 VALUES LESS THAN (202502),
    PARTITION p202502 VALUES LESS THAN (202503),
    PARTITION p202503 VALUES LESS THAN (202504),
    -- ... 更多分区
    PARTITION p_future VALUES LESS THAN MAXVALUE
);
```

**优势**：
- ✅ 提高查询性能（只扫描相关分区）
- ✅ 便于数据归档（删除整个分区）
- ✅ 减少索引大小

**注意**：
- ⚠️ 需要 MySQL 5.7+ 或 8.0+
- ⚠️ 分区键必须是主键的一部分
- ⚠️ 需要定期维护分区

---

### 2.3 数据归档策略

#### 方案1：归档到历史表

```sql
-- 创建历史表（结构与 clicks 相同）
CREATE TABLE clicks_history LIKE clicks;

-- 定期归档（例如：归档3个月前的数据）
INSERT INTO clicks_history 
SELECT * FROM clicks 
WHERE click_time < DATE_SUB(NOW(), INTERVAL 3 MONTH);

-- 删除已归档的数据
DELETE FROM clicks 
WHERE click_time < DATE_SUB(NOW(), INTERVAL 3 MONTH);
```

#### 方案2：只保留统计摘要

```sql
-- 创建统计摘要表
CREATE TABLE clicks_summary (
    id INT PRIMARY KEY AUTO_INCREMENT,
    date DATE NOT NULL,
    offer_id INT,
    publisher_id INT,
    advertiser_id INT,
    click_count INT,
    INDEX idx_date_offer_publisher (date, offer_id, publisher_id)
);

-- 定期汇总并归档
INSERT INTO clicks_summary (date, offer_id, publisher_id, advertiser_id, click_count)
SELECT 
    DATE(click_time) as date,
    offer_id,
    publisher_id,
    advertiser_id,
    COUNT(*) as click_count
FROM clicks
WHERE click_time < DATE_SUB(NOW(), INTERVAL 3 MONTH)
GROUP BY DATE(click_time), offer_id, publisher_id, advertiser_id;

-- 删除已汇总的原始数据
DELETE FROM clicks 
WHERE click_time < DATE_SUB(NOW(), INTERVAL 3 MONTH);
```

---

### 2.4 查询优化

#### 优化1：使用覆盖索引

如果只需要统计数量，不需要返回完整记录：

```sql
-- 优化前（需要回表）
SELECT * FROM clicks 
WHERE click_time >= ? AND offer_id = ?

-- 优化后（使用覆盖索引）
SELECT COUNT(*) FROM clicks 
WHERE click_time >= ? AND offer_id = ?
-- 如果索引包含所有需要的字段，可以只扫描索引
```

#### 优化2：限制查询范围

```sql
-- 添加 LIMIT 或分页
SELECT * FROM clicks 
WHERE click_time >= ? 
ORDER BY click_time DESC 
LIMIT 100;
```

---

## 三、实施步骤

### 步骤1：添加复合索引（立即执行）

```sql
-- 1. 添加时间范围 + Offer + Publisher 索引
CREATE INDEX idx_clicks_time_offer_publisher 
ON clicks(click_time, offer_id, publisher_id);

-- 2. 添加时间范围 + Offer 索引
CREATE INDEX idx_clicks_time_offer 
ON clicks(click_time, offer_id);

-- 3. 验证索引
SHOW INDEX FROM clicks;
```

**执行时间**：取决于数据量，通常几分钟到几十分钟

**影响**：
- ✅ 查询性能提升 10-100 倍
- ⚠️ 插入性能略微下降（约 5-10%）
- ⚠️ 索引占用额外存储空间（约 10-20%）

---

### 步骤2：监控查询性能

```sql
-- 启用慢查询日志
SET GLOBAL slow_query_log = 'ON';
SET GLOBAL long_query_time = 1;  -- 记录超过1秒的查询

-- 查看慢查询
SELECT * FROM mysql.slow_log 
WHERE sql_text LIKE '%clicks%' 
ORDER BY start_time DESC 
LIMIT 10;
```

---

### 步骤3：数据归档（如果数据量很大）

如果表数据量 > 1000万条，考虑实施数据归档：

1. 创建归档脚本
2. 设置定时任务（每月执行一次）
3. 归档3个月前的数据

---

## 四、性能预期

### 4.1 索引优化效果

| 查询类型 | 优化前 | 优化后 | 提升 |
|---------|--------|--------|------|
| 时间范围 + Offer + Publisher 统计 | 5-10秒 | 0.1-0.5秒 | **10-50倍** |
| 时间范围 + Offer 查询 | 3-5秒 | 0.1-0.3秒 | **10-30倍** |
| 单条记录查询（click_id） | 0.01秒 | 0.01秒 | 无变化 |

### 4.2 存储空间

- **索引空间**：约 10-20% 的表大小
- **示例**：如果表 10GB，索引约 1-2GB

---

## 五、迁移脚本

创建迁移脚本：`scripts/migrations/optimize_clicks_table.sql`

