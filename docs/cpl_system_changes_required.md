# CPL 系统改动需求清单

## 📋 概述

根据 CPL 系统需求文档，当前系统需要进行重大改动以支持完整的 CPL（Cost Per Lead）功能。本文档详细列出所有需要改动的地方，**请仔细审查并确认后再进行代码更改**。

---

## 🔴 重大改动（需要确认）

### 1. 数据模型重构

#### 1.1 新增表结构

**需要新增以下表：**

1. **advertisers（广告主表）**
   ```sql
   CREATE TABLE advertisers (
       id INT PRIMARY KEY AUTO_INCREMENT,
       advertiser_id VARCHAR(50) UNIQUE NOT NULL COMMENT '广告主ID（系统生成）',
       advertiser_name VARCHAR(100) NOT NULL COMMENT '广告主名称',
       email VARCHAR(255) COMMENT '邮箱（可选）',
       mobile VARCHAR(20) COMMENT '手机号',
       is_active BOOLEAN DEFAULT TRUE,
       created_at DATETIME,
       updated_at DATETIME
   );
   ```

2. **publishers（渠道表）**
   ```sql
   CREATE TABLE publishers (
       id INT PRIMARY KEY AUTO_INCREMENT,
       publisher_id VARCHAR(50) UNIQUE NOT NULL COMMENT '渠道ID（系统生成）',
       publisher_name VARCHAR(100) NOT NULL COMMENT '渠道名称',
       email VARCHAR(255) COMMENT '邮箱（可选）',
       price_discount DECIMAL(5,2) DEFAULT 0.00 COMMENT '渠道级别的价格扣量比例',
       active_advertiser_count INT DEFAULT 0 COMMENT '活跃的广告主数量',
       is_active BOOLEAN DEFAULT TRUE,
       created_at DATETIME,
       updated_at DATETIME
   );
   ```

3. **clicks（点击记录表）**
   ```sql
   CREATE TABLE clicks (
       id INT PRIMARY KEY AUTO_INCREMENT,
       click_id VARCHAR(255) UNIQUE NOT NULL COMMENT '点击ID（系统生成）',
       offer_id INT COMMENT '关联的Offer ID',
       publisher_id INT COMMENT '关联的渠道ID',
       advertiser_id INT COMMENT '关联的广告主ID',
       click_time DATETIME NOT NULL COMMENT '点击时间',
       ip VARCHAR(50) COMMENT '点击IP地址',
       device VARCHAR(100) COMMENT '设备信息',
       country VARCHAR(50) COMMENT '国家',
       user_agent TEXT COMMENT 'User Agent',
       referer TEXT COMMENT '来源页面',
       conversion_id INT COMMENT '关联的转化ID（如果已转化）',
       created_at DATETIME,
       INDEX idx_click_id (click_id),
       INDEX idx_offer_id (offer_id),
       INDEX idx_publisher_id (publisher_id),
       INDEX idx_click_time (click_time)
   );
   ```

4. **offers（单子表）** - 可能需要重构 products 表
   ```sql
   CREATE TABLE offers (
       id INT PRIMARY KEY AUTO_INCREMENT,
       offer_id VARCHAR(50) UNIQUE NOT NULL COMMENT 'Offer ID（系统生成）',
       offer_name VARCHAR(200) NOT NULL COMMENT 'Offer名称',
       advertiser_offer_id VARCHAR(100) COMMENT '上游系统中的Offer ID',
       advertiser_id INT NOT NULL COMMENT '关联的广告主ID',
       preview_link TEXT COMMENT '预览链接',
       payout DECIMAL(10,2) COMMENT '上游支付金额（PO）',
       affiliate_payout DECIMAL(10,2) COMMENT '扣价后给渠道的金额',
       country VARCHAR(50) COMMENT '国家',
       category VARCHAR(50) COMMENT '分类',
       type VARCHAR(50) COMMENT '类型',
       status VARCHAR(20) DEFAULT 'Active' COMMENT '状态：Active/Inactive',
       upstream_cap INT COMMENT '上游转化上限',
       downstream_cap INT COMMENT '下游转化上限',
       advertiser_tracklink TEXT COMMENT '上游的Tracklink（不显示给下游）',
       downstream_tracklink TEXT COMMENT '生成给下游的Tracklink',
       postback_url TEXT COMMENT 'Postback URL（配置我们的参数）',
       is_active BOOLEAN DEFAULT TRUE,
       created_at DATETIME,
       updated_at DATETIME,
       FOREIGN KEY (advertiser_id) REFERENCES advertisers(id)
   );
   ```

5. **offer_publisher_assignments（Offer-渠道分配表）**
   ```sql
   CREATE TABLE offer_publisher_assignments (
       id INT PRIMARY KEY AUTO_INCREMENT,
       offer_id INT NOT NULL,
       publisher_id INT NOT NULL,
       is_active BOOLEAN DEFAULT TRUE,
       created_at DATETIME,
       UNIQUE KEY uk_offer_publisher (offer_id, publisher_id),
       FOREIGN KEY (offer_id) REFERENCES offers(id),
       FOREIGN KEY (publisher_id) REFERENCES publishers(id)
   );
   ```

6. **offer_caps（Cap配置表）**
   ```sql
   CREATE TABLE offer_caps (
       id INT PRIMARY KEY AUTO_INCREMENT,
       cap_type VARCHAR(50) NOT NULL COMMENT 'Cap类型：advertiser_offer/offer',
       advertiser_id INT COMMENT '广告主ID（如果是advertiser_offer类型）',
       offer_id INT NOT NULL COMMENT 'Offer ID',
       publisher_id INT COMMENT '渠道ID（如果为空，表示所有渠道）',
       daily_cap INT COMMENT '每日Cap',
       total_cap INT COMMENT '总Cap',
       current_daily_count INT DEFAULT 0 COMMENT '当前每日计数',
       current_total_count INT DEFAULT 0 COMMENT '当前总计数',
       cap_start_date DATETIME COMMENT 'Cap开始日期（用于Total Cap）',
       is_active BOOLEAN DEFAULT TRUE,
       created_at DATETIME,
       updated_at DATETIME,
       FOREIGN KEY (offer_id) REFERENCES offers(id),
       FOREIGN KEY (advertiser_id) REFERENCES advertisers(id),
       FOREIGN KEY (publisher_id) REFERENCES publishers(id)
   );
   ```

7. **offer_discounts（扣量配置表）**
   ```sql
   CREATE TABLE offer_discounts (
       id INT PRIMARY KEY AUTO_INCREMENT,
       discount_type VARCHAR(50) NOT NULL COMMENT '扣量类型：offer/channel',
       offer_id INT COMMENT 'Offer ID（如果是offer类型）',
       publisher_id INT NOT NULL COMMENT '渠道ID',
       discount_ratio DECIMAL(5,2) NOT NULL COMMENT '扣量比例（0-100）',
       is_active BOOLEAN DEFAULT TRUE,
       created_at DATETIME,
       updated_at DATETIME,
       FOREIGN KEY (offer_id) REFERENCES offers(id),
       FOREIGN KEY (publisher_id) REFERENCES publishers(id)
   );
   ```

8. **advertiser_tests（上游测试记录表）**
   ```sql
   CREATE TABLE advertiser_tests (
       id INT PRIMARY KEY AUTO_INCREMENT,
       advertiser_id INT NOT NULL,
       advertiser_name VARCHAR(100),
       advertiser_offer_id VARCHAR(100),
       offer_id INT NOT NULL COMMENT '平台内的Offer ID',
       offer_name VARCHAR(200),
       price DECIMAL(10,2),
       country VARCHAR(50),
       click_id VARCHAR(255) COMMENT '测试生成的Click ID',
       click_url TEXT COMMENT '测试生成的Click Url',
       test_time DATETIME,
       created_at DATETIME,
       FOREIGN KEY (advertiser_id) REFERENCES advertisers(id),
       FOREIGN KEY (offer_id) REFERENCES offers(id)
   );
   ```

9. **affiliate_tests（下游测试记录表）**
   ```sql
   CREATE TABLE affiliate_tests (
       id INT PRIMARY KEY AUTO_INCREMENT,
       publisher_id INT NOT NULL,
       click_id VARCHAR(255) NOT NULL COMMENT '下游提供的Click ID',
       offer_id INT NOT NULL,
       offer_name VARCHAR(200),
       price DECIMAL(10,2),
       country VARCHAR(50),
       platform VARCHAR(50),
       postback_time DATETIME COMMENT 'Postback发送时间',
       status VARCHAR(50) COMMENT '发送状态：Send Success/Failed',
       affiliate_return_content TEXT COMMENT '渠道返回内容',
       created_at DATETIME,
       FOREIGN KEY (publisher_id) REFERENCES publishers(id),
       FOREIGN KEY (offer_id) REFERENCES offers(id)
   );
   ```

#### 1.2 修改现有表

**postback_conversions 表需要添加字段：**
```sql
ALTER TABLE postback_conversions 
ADD COLUMN click_id VARCHAR(255) COMMENT '关联的Click ID',
ADD COLUMN click_time DATETIME COMMENT '点击时间',
ADD COLUMN conversion_status VARCHAR(20) DEFAULT 'Pending' COMMENT '转化状态：Approved/Pending',
ADD INDEX idx_click_id (click_id);
```

**products 表可能需要重命名或添加映射：**
- 选项1：重命名 `products` 为 `offers`
- 选项2：保持 `products` 表，添加 `offers` 表，建立映射关系
- 选项3：在 `products` 表中添加 `offer_id` 字段，建立一对一关系

---

### 2. 核心功能实现

#### 2.1 点击追踪系统 ⚠️ **需要实现**

**功能描述：**
- 生成唯一的 Click ID
- 记录点击信息（IP、Device、Country、User Agent等）
- 生成 Tracklink（包含系统参数）
- 关联点击和转化

**需要实现：**
1. Click ID 生成器（类似短链接生成器）
2. 点击追踪接口：`GET /track/click/{offer_id}?publisher_id=xxx`
3. 点击记录存储
4. Tracklink 生成逻辑

**影响范围：**
- 新增 `app/core/tracking/click_tracker.py`
- 新增 `app/api/api_v1/endpoints/tracking.py`
- 修改 `app/models/models.py`（添加 Click 模型）

---

#### 2.2 Tracklink 生成 ⚠️ **需要实现**

**功能描述：**
- 为每个 Offer 生成上游 Tracklink（包含我们的参数）
- 为每个 Offer-Publisher 组合生成下游 Tracklink
- Tracklink 需要包含 Click ID 参数

**需要实现：**
1. Tracklink 模板系统
2. 参数替换逻辑
3. 上游 Tracklink：`{advertiser_tracklink}?our_param={click_id}`
4. 下游 Tracklink：`{our_tracklink}?offer_id={offer_id}&publisher_id={publisher_id}&click_id={click_id}`

**影响范围：**
- 新增 `app/core/tracking/tracklink_generator.py`
- 修改 Offer 创建/编辑逻辑

---

#### 2.3 Cap 管理系统 ⚠️ **需要实现**

**功能描述：**
- 支持 Daily Cap 和 Total Cap
- 支持 Advertiser Offer Cap 和 Offer Cap
- 达到上限时自动下线 Offer

**需要实现：**
1. Cap 配置管理（CRUD）
2. Cap 检查逻辑（每次转化时检查）
3. 自动下线逻辑
4. Cap 重置逻辑（每日重置 Daily Cap）

**影响范围：**
- 新增 `app/core/cap/cap_manager.py`
- 新增 `app/api/api_v1/endpoints/caps.py`
- 修改转化处理逻辑（添加 Cap 检查）

---

#### 2.4 扣量系统 ⚠️ **需要实现**

**功能描述：**
- 支持 Offer 级别和 Channel 级别的扣量
- 价格扣量（Price Discount）
- 扣量优先级：Offer > Channel

**需要实现：**
1. Discount 配置管理（CRUD）
2. 扣量计算逻辑（计算 Affiliate Price）
3. 扣量优先级处理

**影响范围：**
- 新增 `app/core/discount/discount_manager.py`
- 新增 `app/api/api_v1/endpoints/discounts.py`
- 修改转化处理逻辑（添加扣量计算）

---

#### 2.5 上游测试工具 ⚠️ **需要实现**

**功能描述：**
- 模拟点击测试
- 生成 Click ID 和 Click Url
- 测试记录管理

**需要实现：**
1. 测试记录管理（Add/Delete）
2. 模拟点击功能（生成 Click ID 和 Click Url）
3. 测试结果展示

**影响范围：**
- 新增 `app/api/api_v1/endpoints/advertiser_tests.py`
- 新增前端页面：`AdvertiserTestManagement.vue`

---

#### 2.6 下游测试工具 ⚠️ **需要实现**

**功能描述：**
- 手动发送 Postback 给下游
- 查看下游返回内容
- 测试记录管理

**需要实现：**
1. 测试记录管理（Send Postback/Delete）
2. 手动 Postback 发送功能
3. 返回内容记录和展示

**影响范围：**
- 新增 `app/api/api_v1/endpoints/affiliate_tests.py`
- 新增前端页面：`AffiliateTestManagement.vue`

---

### 3. 数据统计和报表

#### 3.1 转化总览（Summary）⚠️ **需要实现**

**需要统计的字段：**
- Offer ID
- Offer Name
- Advertiser（仅管理员可见）
- Publisher
- Click（点击数）
- Conversion（转化数）
- CR（Conversion Rate）
- PO（仅管理员可见）
- PO (扣价后)

**需要实现：**
1. 统计查询接口
2. 筛选功能（Offer ID/Advertiser/Publisher）
3. 前端展示页面

**影响范围：**
- 新增 `app/api/api_v1/endpoints/conversion_summary.py`
- 新增前端页面：`ConversionSummary.vue`

---

#### 3.2 Conversion Log 增强 ⚠️ **需要修改**

**当前系统：**
- 已有 `postback_conversions` 表
- 已有查询接口

**需要增强：**
1. 添加 Click ID、Click Time 字段
2. 添加 Status（Approved/Pending）字段
3. 添加筛选功能（Offer ID/Publisher/Status）
4. 前端展示优化

**影响范围：**
- 修改 `app/models/models.py`（PostbackConversion 模型）
- 修改 `app/api/api_v1/endpoints/postback.py`（查询接口）
- 修改前端页面

---

### 4. 前端界面

#### 4.1 需要新增的页面

1. **广告主管理页面**（仅管理员）
   - 列表展示
   - Add/Edit 功能

2. **渠道管理页面**（仅管理员）
   - 列表展示
   - Add/Edit 功能

3. **Offer 管理页面**（重构现有产品管理）
   - 列表展示
   - Add/Edit 功能
   - 字段包括：Offer Name、ADV Offer ID、Advertiser、Preview Link、PO、PO(扣价后)、Country、Type、Status、Cap、Tracklink、Postback 等

4. **Cap 管理页面**
   - 列表展示
   - MaxCap/Add/Edit/Delete 功能

5. **扣量管理页面**
   - 列表展示
   - Add/Edit/Delete 功能

6. **转化总览页面**
   - 统计表格
   - 筛选功能

7. **Conversion Log 页面**（增强现有）
   - 添加更多字段展示
   - 添加筛选功能

8. **上游测试页面**
   - 测试记录列表
   - Add/Delete/Test 功能

9. **下游测试页面**
   - 测试记录列表
   - Send Postback/Delete 功能

---

## 🟡 中等改动（需要确认）

### 1. 术语映射

**当前系统 → CPL 系统：**
- `Client` → `Publisher/Affiliate`（渠道）
- `Product` → `Offer`（单子）
- 需要新增：`Advertiser`（广告主）

**建议方案：**
- 保持 `Client` 和 `Product` 表，添加映射关系
- 或者创建新的 `Advertiser`、`Publisher`、`Offer` 表，建立映射

---

### 2. Postback 处理逻辑修改

**当前系统：**
- 接收上游 Postback → 保存 Conversion → 转发给下游

**需要修改：**
- 接收上游 Postback → 关联 Click ID → 保存 Conversion → 检查 Cap → 计算扣量 → 转发给下游

**影响范围：**
- 修改 `app/core/postback/processor.py`
- 添加 Cap 检查逻辑
- 添加扣量计算逻辑

---

### 3. 转化状态管理

**需要添加：**
- Conversion Status：Approved/Pending
- 状态审批流程（可选）

**影响范围：**
- 修改 `PostbackConversion` 模型
- 添加状态管理接口

---

## 🟢 小改动（建议）

### 1. 报表功能

**需要实现：**
- 日报表（Daily Data）
- 渠道报表（Affiliate Report）
- 广告主报表（Advertiser Report）
- Offer 报表（Offer Report）

---

### 2. 数据导出

**需要实现：**
- Excel 导出
- CSV 导出
- 筛选后导出

---

## ⚠️ 重要决策点

### 1. 数据模型选择

**选项 A：完全重构**
- 创建新的 `advertisers`、`publishers`、`offers` 表
- 迁移现有数据
- 优点：结构清晰，符合 CPL 系统设计
- 缺点：需要数据迁移，可能影响现有功能

**选项 B：映射关系**
- 保持现有 `clients`、`products` 表
- 创建 `advertisers`、`publishers`、`offers` 表
- 建立映射关系
- 优点：不影响现有功能
- 缺点：数据结构复杂，需要维护两套数据

**选项 C：扩展现有表**
- 在现有表中添加字段
- `clients` 表添加 `client_type` 字段（advertiser/publisher）
- `products` 表添加 Offer 相关字段
- 优点：改动最小
- 缺点：表结构可能不够清晰

**建议：选项 A（完全重构），但需要充分的数据迁移计划**

---

### 2. Click 追踪实现方式

**选项 A：独立点击追踪系统**
- 创建独立的点击追踪接口
- 每次点击都记录到数据库
- 优点：数据完整，可追溯
- 缺点：性能开销大

**选项 B：按需生成 Click ID**
- 只在需要时生成 Click ID
- 转化时再关联
- 优点：性能好
- 缺点：可能丢失点击数据

**建议：选项 A（独立点击追踪系统）**

---

## 📝 实施计划建议

### 阶段一：数据模型（1-2周）
1. 创建新的数据表
2. 数据迁移脚本
3. 模型定义

### 阶段二：核心功能（2-3周）
1. 点击追踪系统
2. Tracklink 生成
3. Cap 管理
4. 扣量系统

### 阶段三：测试工具（1周）
1. 上游测试工具
2. 下游测试工具

### 阶段四：统计和报表（1-2周）
1. 转化总览
2. Conversion Log 增强
3. 报表功能

### 阶段五：前端界面（2-3周）
1. 所有管理页面
2. 测试工具页面
3. 统计页面

---

## ✅ 确认清单

在开始实施前，请确认以下事项：

- [ ] 数据模型选择（选项 A/B/C）
- [ ] Click 追踪实现方式（选项 A/B）
- [ ] 是否保留现有 `clients` 和 `products` 表
- [ ] 数据迁移计划
- [ ] 功能优先级（哪些功能先实现）
- [ ] 测试计划

---

## 🚨 风险提示

1. **数据迁移风险**：如果选择完全重构，需要确保数据迁移的完整性和准确性
2. **性能影响**：点击追踪系统会增加数据库写入压力，需要考虑性能优化
3. **兼容性风险**：新系统可能与现有功能不兼容，需要充分测试
4. **开发周期**：完整实现所有功能需要较长时间，建议分阶段实施

---

## 📞 下一步

**请确认：**
1. 是否同意以上改动方案？
2. 选择哪个数据模型方案（A/B/C）？
3. 选择哪个 Click 追踪实现方式（A/B）？
4. 功能实现的优先级顺序？
5. 是否有其他特殊要求？

**确认后，我将开始实施代码更改。**

