# CPL 系统需求对比分析

## 📋 文档需求 vs 当前系统对比

根据提供的 CPL 系统界面和说明书，以下是需要改动的地方：

---

## 🔴 重大改动（需要新增核心概念）

### 1. **Advertiser (广告主) - 上游概念**

**文档需求：**
- Advertiser Name, Advertiser ID, Email
- 管理广告主（Admin Only）

**当前系统：**
- ❌ 没有 Advertiser 概念
- ✅ 有 `Client`（客户），但这是"下游"概念

**需要改动：**
- 新增 `Advertiser` 模型（上游广告主）
- 新增广告主管理界面（CRUD）
- 数据库表：`advertisers`

---

### 2. **Publisher/Affiliate (渠道) - 下游概念**

**文档需求：**
- Publisher Name, Publisher ID, Email
- 管理渠道（Admin Only）
- 渠道测试功能

**当前系统：**
- ✅ **已确认：渠道 = 下游 = 客户**
- ✅ **`Client`（客户） = Publisher/Affiliate（渠道） = 下游**
- ✅ 已有 `Client` 模型和管理界面

**需要改动：**
- ✅ **无需新增模型，直接使用现有的 `Client` 模型**
- ⚠️ 可能需要添加字段：`publisher_id`（如果文档要求独立的 Publisher ID，可以使用 `Client.id` 或 `Client.key`）
- ⚠️ 需要添加渠道测试功能（Affiliate Test）

---

### 3. **Offer (单子) - 核心业务概念**

**文档需求：**
- Offer Name
- ADV Offer ID（上游的 offer ID）
- Offer ID（系统生成的唯一ID）
- Advertiser（关联广告主）
- Preview Link
- PO (Price Out) - 上游价格
- PO (扣价后) - 扣价后的价格
- Country, Type, Status (Active/Inactive)
- Cap (上游), Cap (下游)
- ADV Tracklink（上游的，不显示给下游）
- 生成给下游的Tracklink
- Postback 配置（单子建立时把我们的参数配置进去）
- Publisher（可分配给下游渠道）

**当前系统：**
- ✅ 有 `Product`（产品），但功能不完整
- ❌ 缺少：ADV Offer ID、Preview Link、PO、Cap、Tracklink 等

**需要改动：**
- 扩展 `Product` 模型或新增 `Offer` 模型
- 添加字段：`advertiser_offer_id`, `preview_link`, `price_out`, `price_after_discount`, `country`, `offer_type`, `advertiser_tracklink`, `downstream_tracklink`
- 添加 Cap 管理功能
- 添加 Tracklink 生成功能

---

### 4. **Click (点击) - 新概念**

**文档需求：**
- 记录每次点击
- Click ID, Click Time
- 关联 Offer、Publisher

**当前系统：**
- ❌ 没有 Click 记录
- ✅ 只有 Conversion（转化）记录

**需要改动：**
- 新增 `Click` 模型
- 记录点击事件
- 数据库表：`clicks`

---

### 5. **Conversion Log 增强**

**文档需求：**
- Click ID（关联点击）
- Click Time
- Conversion Time
- Status (Approved/Pending)
- 可筛选 Offer ID/Publisher/Status

**当前系统：**
- ✅ 有 `PostbackConversion`，但缺少：
  - ❌ Click ID 关联
  - ❌ Click Time
  - ❌ Status (Approved/Pending)

**需要改动：**
- 扩展 `PostbackConversion` 模型
- 添加字段：`click_id`, `click_time`, `status` (approved/pending)

---

### 6. **Summary (转化总览) - 统计功能**

**文档需求：**
- Offer ID, Offer Name
- Advertiser（仅管理员可见）
- Publisher
- Click（点击数）
- Conversion（转化数）
- CR (Conversion Rate) = Conversion/Click
- PO (仅管理员可见)
- PO (扣价后)
- 可筛选 Offer ID/Advertiser/Publisher

**当前系统：**
- ✅ 有基础统计接口
- ❌ 缺少：Click 统计、CR 计算、PO 显示

**需要改动：**
- 新增统计接口，包含 Click、Conversion、CR
- 区分管理员和普通用户可见的数据

---

### 7. **Cap 管理 - 新功能**

**文档需求：**
- Advertiser Offer Cap：对特定广告主的 offer 设置 cap
- Offer Cap：对特定 offer 设置 cap
- Daily Cap 和 Total Cap
- 从转化数维度控制
- 达到 cap 后自动下线

**当前系统：**
- ❌ 没有 Cap 管理功能

**需要改动：**
- 新增 `Cap` 模型
- 数据库表：`caps`
- Cap 管理界面（CRUD）
- Cap 检查逻辑（处理转化时检查）

---

### 8. **扣量 Discount - 部分实现**

**文档需求：**
- Offer 级别的扣量
- Price Discount（价格扣量）- CPL PO 扣量
- 渠道级别的扣量
- 扣量优先级：Offer 扣量 > 渠道扣量

**当前系统：**
- ✅ 有 `ecpm_deduct_ratio` 和 `revenue_deduct_ratio`（产品级别）
- ✅ **已确认：有 `cplpo_deduct_ratio`（CPL PO减扣比例）在 `products` 表中**
- ❌ 没有渠道级别的扣量
- ❌ 没有扣量管理界面（需要在产品管理界面中添加扣量字段的编辑）

**需要改动：**
- ✅ **无需新增 `Discount` 模型，扣量已在 `products` 表中实现**
- ⚠️ 需要在产品管理界面中添加 `cplpo_deduct_ratio` 字段的编辑功能
- ⚠️ 需要实现扣量计算逻辑（在转发给下游时应用扣量）
- ⚠️ 如果需要渠道级别的扣量，可以考虑在 `clients` 表中添加字段，或使用独立的扣量配置表

---

### 9. **Tracklink 生成 - 新功能**

**文档需求：**
- ADV Tracklink（上游的，建立单子时配置我们的参数）
- 生成给下游的Tracklink（包含我们的参数）

**当前系统：**
- ❌ 没有 Tracklink 生成功能

**需要改动：**
- 新增 Tracklink 生成逻辑
- 在 Offer 创建时自动生成
- 支持参数配置

---

### 10. **测试功能 - 新功能**

**文档需求：**

**上游测试 (Advertiser Test)：**
- 模拟点击，生成 Click ID 和 Click URL
- 手动将 Click ID 回传给上游
- 测试上游对接情况

**下游测试 (Affiliate Test)：**
- 手动发送 Postback 给下游
- 显示 Status 和 Affiliate Return Content
- 测试下游对接情况

**当前系统：**
- ❌ 没有测试功能

**需要改动：**
- 新增测试接口
- 模拟点击功能
- 手动发送 Postback 功能
- 测试记录表

---

## 🟡 中等改动（功能增强）

### 11. **Postback 参数配置**

**文档需求：**
- 单子建立时把我们的参数配置到上游的 postback URL
- 生成给下游的 postback URL 包含我们的参数

**当前系统：**
- ✅ 有下游转发功能
- ❌ 没有参数配置功能

**需要改动：**
- 新增参数配置表
- 参数模板功能

---

### 12. **Offer 分配**

**文档需求：**
- Offer 可以分配给多个 Publisher
- 每个 Publisher 看到分配给自己的 Offer

**当前系统：**
- ✅ 有 `ProductAssignment`（产品分配）
- ⚠️ 需要确认是否支持多对多分配

**需要改动：**
- 确认并完善分配功能

---

## 🟢 小改动（界面优化）

### 13. **界面字段调整**

**需要调整的字段显示：**
- Conversion Log 中显示 Click ID、Click Time
- Summary 中显示 Click、Conversion、CR
- 区分管理员和普通用户可见的数据

---

## 📊 数据库改动总结

### 需要新增的表：

1. **advertisers** - 广告主表（上游）
2. ~~**publishers** 或 **affiliates** - 渠道表~~ ✅ **无需新增，使用现有的 `clients` 表**
3. **clicks** - 点击记录表
4. **caps** - Cap 配置表
5. ~~**discounts** - 扣量表~~ ✅ **无需新增，扣量已在 `products` 表中实现（`cplpo_deduct_ratio` 字段）**
6. **offer_tests** 或 **advertiser_tests** - 上游测试记录表
7. **affiliate_tests** - 下游测试记录表（使用 `client_id` 关联到 `clients` 表）
8. **tracklinks** - Tracklink 配置表（可选）

### 需要修改的表：

1. **products** - 扩展为 Offer 概念，添加多个字段
2. **postback_conversions** - 添加 click_id, click_time, status 字段

---

## ⚠️ 重要提醒

这些改动涉及：
1. **数据模型重构**：新增多个核心概念（Advertiser、Offer、Click），Publisher 使用现有的 Client 模型
2. **业务逻辑重构**：从简单的 Postback 转发扩展为完整的 CPL 系统
3. **界面重构**：需要重新设计多个管理界面
4. **数据迁移**：可能需要将现有的 Product 数据迁移到新的 Offer 结构

**建议：**
- 分阶段实施
- ✅ 已确认核心概念映射关系：**渠道 = 下游 = Client**，**上游 = Advertiser**
- 评估现有数据的影响

---

## ✅ 已确认的概念映射

1. **渠道 = 下游 = 客户：**
   - ✅ 文档中的 **Publisher/Affiliate（渠道）** = **下游** = 当前系统的 **`Client`（客户）**
   - ✅ **无需新增 Publisher 模型，直接使用现有的 `Client` 模型**
   - ✅ 所有涉及 Publisher/Affiliate 的地方，都使用 `Client` 模型

2. **上游 = 广告主（新概念）：**
   - ⚠️ 文档中的 **Advertiser（广告主）** = **上游** = 需要新增的概念
   - ⚠️ 需要新增 `Advertiser` 模型和管理界面

3. **单子 = 产品：**
   - ⚠️ 文档中的 **Offer（单子）** ≈ 当前系统的 **`Product`（产品）**
   - ⚠️ 需要扩展 `Product` 模型，添加 Offer 相关字段
   - ⚠️ 或者新增独立的 `Offer` 模型（需要确认）

---

## ❓ 仍需确认的问题

1. **Product vs Offer：**
   - 当前系统的 `Product` 是否可以直接扩展为 `Offer`？
   - 还是需要新增独立的 `Offer` 模型？

2. **优先级：**
   - 哪些功能是必须的？
   - 哪些功能可以后续实现？

3. **兼容性：**
   - 是否需要保持现有 API 的兼容性？
   - 现有数据如何迁移？

---

请确认以上改动是否符合您的需求，我将根据您的确认进行代码实现。

