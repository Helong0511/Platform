# CPL系统扣量和扣金额原理与操作说明

## 目录

1. [系统概述](#系统概述)
2. [核心概念](#核心概念)
3. [扣量原理](#扣量原理)
4. [扣金额原理](#扣金额原理)
5. [配置层级与优先级](#配置层级与优先级)
6. [扣减策略详解](#扣减策略详解)
7. [系统架构](#系统架构)
8. [操作指南](#操作指南)
9. [数据模型](#数据模型)
10. [统计与监控](#统计与监控)
11. [常见问题](#常见问题)

---

## 1. 系统概述

### 1.1 系统简介

CPL（Cost Per Lead）扣减系统是一个智能化的转化扣减管理平台，用于在转化处理过程中自动执行扣量和扣金额操作。系统支持灵活的配置方式，可以针对不同的广告主、Offer或渠道设置独立的扣减规则。

### 1.2 核心功能

- **按比例扣量**：根据配置的比例，自动扣减转化数量
- **按比例扣金额**：根据配置的比例，自动扣减转化金额
- **多层级配置**：支持广告主、Offer、渠道三个层级的配置
- **多种扣减策略**：支持随机、按比例、轮询三种扣减策略
- **完整日志记录**：记录所有扣减操作的详细信息
- **统计分析**：提供扣减数据的统计和分析功能

### 1.3 应用场景

- 控制转化成本，降低无效转化带来的损失
- 优化渠道质量，对低质量渠道进行扣减
- 平衡广告主和渠道之间的利益分配
- 实现精细化的转化管理

---

## 2. 核心概念

### 2.1 扣量（Volume Deduction）

**定义**：扣量是指将部分转化记录标记为无效，不计算到最终的转化统计中。被扣量的转化不会保存到主转化表（postback_conversions），但会在扣减日志表中记录。

**特点**：
- 扣量是"全有或全无"的操作，即一个转化要么被扣量（数量变为0），要么不被扣量（数量保持为1）
- 扣量操作是隐藏的，被扣量的转化对渠道不可见
- 扣量比例是动态计算的，确保在统计时间窗口内（默认24小时）达到目标比例

### 2.2 扣金额（Amount Deduction）

**定义**：扣金额是指按照配置的比例，从转化金额中扣除一定比例，但转化记录仍然保留。

**特点**：
- 扣金额是比例操作，每个转化都会按比例扣减金额
- 扣金额后的转化仍然会保存到主转化表
- 扣金额比例是固定的，直接应用于每个转化

### 2.3 配置层级

系统支持三个层级的配置，优先级从高到低：

1. **Offer级别**：针对特定Offer的扣减配置（优先级最高）
2. **Advertiser级别**：针对特定广告主的扣减配置
3. **Publisher级别**：针对特定渠道的扣减配置（优先级最低）

### 2.4 扣减策略

系统支持三种扣减策略：

1. **random（随机）**：随机选择转化进行扣量，但确保总体比例正确
2. **proportional（按比例）**：按固定间隔扣量，如每10个扣1个
3. **round_robin（轮询）**：轮询方式扣量，按固定间隔循环

---

## 3. 扣量原理

### 3.1 扣量计算流程

扣量计算是一个动态过程，系统会实时统计最近的转化数据，并根据统计结果决定是否对当前转化进行扣量。

#### 3.1.1 统计时间窗口

系统默认使用**24小时**作为统计时间窗口，统计最近24小时内的转化数据。这个时间窗口可以通过代码中的`hours`参数调整。

#### 3.1.2 统计指标

系统会统计以下指标：

- **total（总转化数）**：统计时间窗口内所有转化记录的总数（包括被扣量的和未扣量的）
- **deducted（已扣量数）**：统计时间窗口内已经被扣量的转化数量
- **processed（已处理数）**：统计时间窗口内已经处理的转化数量（等于total）

#### 3.1.3 扣量判断逻辑

系统使用以下逻辑判断是否对当前转化进行扣量：

```python
# 1. 计算应该扣减的总数量
should_deduct_count = int(total * volume_deduction_ratio)

# 2. 如果已经扣减够了，不再扣减
if deducted >= should_deduct_count:
    return False  # 不扣量

# 3. 计算剩余需要扣减的数量
remaining_to_deduct = should_deduct_count - deducted

# 4. 计算剩余未处理的转化数
remaining_conversions = total - processed

# 5. 根据策略决定是否扣减当前转化
```

### 3.2 扣量策略详解

#### 3.2.1 随机策略（random）

**原理**：使用概率算法，确保在统计时间窗口内达到目标扣量比例。

**计算公式**：
```
probability = remaining_to_deduct / remaining_conversions
```

**示例**：
- 配置扣量比例：10%（0.1）
- 统计窗口内总转化：100个
- 应该扣量：10个
- 已扣量：5个
- 已处理：80个
- 剩余需扣量：5个
- 剩余未处理：20个
- 当前转化扣量概率：5/20 = 25%

**优点**：
- 扣量分布随机，难以预测
- 能确保总体比例准确

**缺点**：
- 可能出现短期波动

#### 3.2.2 按比例策略（proportional）

**原理**：按固定间隔扣量，如每N个扣1个。

**计算公式**：
```
interval = int(1 / volume_deduction_ratio)
should_deduct = (processed + 1) % interval == 0
```

**示例**：
- 配置扣量比例：10%（0.1）
- 间隔：1 / 0.1 = 10
- 第1、11、21、31...个转化会被扣量

**优点**：
- 扣量分布均匀
- 可预测性强

**缺点**：
- 容易被识别规律

#### 3.2.3 轮询策略（round_robin）

**原理**：轮询方式扣量，从第一个转化开始按间隔循环。

**计算公式**：
```
interval = int(1 / volume_deduction_ratio)
should_deduct = processed % interval == 0
```

**示例**：
- 配置扣量比例：10%（0.1）
- 间隔：1 / 0.1 = 10
- 第0、10、20、30...个转化会被扣量（从0开始）

**优点**：
- 扣量分布均匀
- 实现简单

**缺点**：
- 容易被识别规律

### 3.3 扣量执行流程

当系统判断需要扣量时，执行以下流程：

1. **标记扣量**：将`should_deduct_volume`设置为`True`
2. **更新数量**：
   - `original_volume = 1`
   - `deducted_volume = 1`
   - `final_volume = 0`
3. **不保存转化**：被扣量的转化不会保存到`postback_conversions`表
4. **记录日志**：在`conversion_deduction_logs`表中记录扣量信息

---

## 4. 扣金额原理

### 4.1 扣金额计算

扣金额计算相对简单，直接按照配置的比例从原始金额中扣除。

#### 4.1.1 计算公式

```python
deduction_amount = original_amount * amount_deduction_ratio
final_amount = original_amount - deduction_amount
```

#### 4.1.2 计算示例

**示例1**：
- 原始金额：100元
- 扣金额比例：10%（0.1）
- 扣减金额：100 × 0.1 = 10元
- 最终金额：100 - 10 = 90元

**示例2**：
- 原始金额：50元
- 扣金额比例：20%（0.2）
- 扣减金额：50 × 0.2 = 10元
- 最终金额：50 - 10 = 40元

### 4.2 扣金额执行流程

当系统启用扣金额时，执行以下流程：

1. **计算扣减金额**：根据配置的比例计算扣减金额
2. **更新金额**：
   - `original_amount`：保持原始金额
   - `deducted_amount`：记录扣减的金额
   - `final_amount`：计算最终金额
3. **保存转化**：扣金额后的转化仍然保存到`postback_conversions`表，但使用`final_amount`作为`payout`字段
4. **记录日志**：在`conversion_deduction_logs`表中记录扣金额信息

### 4.3 扣金额与扣量的区别

| 特性 | 扣量 | 扣金额 |
|------|------|--------|
| 操作对象 | 转化数量 | 转化金额 |
| 是否保存转化 | 否 | 是 |
| 计算方式 | 动态统计 | 固定比例 |
| 可见性 | 隐藏 | 可见 |
| 应用场景 | 完全拒绝低质量转化 | 降低转化成本但保留转化 |

---

## 5. 配置层级与优先级

### 5.1 配置层级

系统支持三个层级的配置，每个配置只能属于一个层级：

#### 5.1.1 Offer级别配置

**适用场景**：
- 针对特定Offer设置扣减规则
- 不同Offer有不同的扣减需求

**配置方式**：
- `offer_id`：指定Offer ID
- `advertiser_id`：NULL
- `publisher_id`：NULL

**优先级**：最高（1）

#### 5.1.2 Advertiser级别配置

**适用场景**：
- 针对特定广告主设置统一的扣减规则
- 适用于广告主下所有Offer

**配置方式**：
- `advertiser_id`：指定广告主ID
- `offer_id`：NULL
- `publisher_id`：NULL

**优先级**：中等（2）

#### 5.1.3 Publisher级别配置

**适用场景**：
- 针对特定渠道设置扣减规则
- 适用于该渠道的所有转化

**配置方式**：
- `publisher_id`：指定渠道ID
- `advertiser_id`：NULL
- `offer_id`：NULL

**优先级**：最低（3）

### 5.2 优先级查找逻辑

系统按以下顺序查找配置：

```
1. 查找Offer级别配置
   ├─ 如果找到，使用该配置
   └─ 如果未找到，继续查找

2. 查找Advertiser级别配置
   ├─ 如果找到，使用该配置
   └─ 如果未找到，继续查找

3. 查找Publisher级别配置
   ├─ 如果找到，使用该配置
   └─ 如果未找到，不应用扣减
```

### 5.3 优先级示例

**场景1**：
- Offer ID=100 有配置（扣量10%）
- Advertiser ID=10 有配置（扣量20%）
- Publisher ID=5 有配置（扣量30%）
- **结果**：使用Offer配置（扣量10%）

**场景2**：
- Offer ID=100 无配置
- Advertiser ID=10 有配置（扣量20%）
- Publisher ID=5 有配置（扣量30%）
- **结果**：使用Advertiser配置（扣量20%）

**场景3**：
- Offer ID=100 无配置
- Advertiser ID=10 无配置
- Publisher ID=5 有配置（扣量30%）
- **结果**：使用Publisher配置（扣量30%）

### 5.4 配置激活状态

每个配置都有一个`is_active`字段，只有激活的配置才会被使用：

- `is_active = True`：配置激活，会被使用
- `is_active = False`：配置未激活，不会被使用

---

## 6. 扣减策略详解

### 6.1 策略选择建议

#### 6.1.1 随机策略（random）

**适用场景**：
- 需要隐藏扣量规律
- 对扣量分布要求不严格
- 希望扣量难以被预测

**推荐使用**：
- 对渠道质量要求较高的场景
- 需要防止渠道识别扣量规律

#### 6.1.2 按比例策略（proportional）

**适用场景**：
- 需要均匀分布扣量
- 对扣量时间分布有要求
- 希望扣量可预测

**推荐使用**：
- 需要稳定扣量比例的场景
- 对扣量分布有明确要求

#### 6.1.3 轮询策略（round_robin）

**适用场景**：
- 需要简单的扣量逻辑
- 对扣量分布要求不高
- 希望实现简单

**推荐使用**：
- 简单的扣量需求
- 对扣量策略要求不高的场景

### 6.2 策略对比

| 策略 | 扣量分布 | 可预测性 | 实现复杂度 | 推荐度 |
|------|----------|----------|------------|--------|
| random | 随机 | 低 | 中等 | ⭐⭐⭐⭐⭐ |
| proportional | 均匀 | 高 | 低 | ⭐⭐⭐⭐ |
| round_robin | 均匀 | 高 | 低 | ⭐⭐⭐ |

---

## 7. 系统架构

### 7.1 核心模块

#### 7.1.1 扣减管理模块（deduction_manager.py）

**位置**：`app/core/deduction/deduction_manager.py`

**主要功能**：
- `find_deduction_config()`：查找扣减配置
- `get_recent_conversion_stats()`：获取转化统计
- `should_deduct_volume()`：判断是否扣量
- `calculate_amount_deduction()`：计算扣金额
- `apply_deduction()`：应用扣减
- `log_deduction()`：记录扣减日志

#### 7.1.2 服务层（conversion_deduction_service.py）

**位置**：`app/services/cpl/conversion_deduction_service.py`

**主要功能**：
- 扣减配置的CRUD操作
- 扣减日志查询
- 扣减统计计算

#### 7.1.3 API层（deductions.py）

**位置**：`app/api/api_v1/endpoints/cpl/conversions/deductions.py`

**主要功能**：
- 提供RESTful API接口
- 配置管理接口
- 日志查询接口
- 统计查询接口

### 7.2 数据流程

```
转化到达 (Postback)
    ↓
查找扣减配置 (find_deduction_config)
    ↓
获取转化统计 (get_recent_conversion_stats)
    ↓
判断是否扣量 (should_deduct_volume)
    ↓
计算扣金额 (calculate_amount_deduction)
    ↓
应用扣减 (apply_deduction)
    ↓
记录日志 (log_deduction)
    ↓
保存转化 (PostbackConversion)
```

### 7.3 数据库表结构

#### 7.3.1 扣减配置表（conversion_deduction_configs）

存储扣减配置信息。

#### 7.3.2 扣减日志表（conversion_deduction_logs）

记录所有扣减操作的详细信息。

---

## 8. 操作指南

### 8.1 创建扣减配置

#### 8.1.1 通过API创建

**接口**：`POST /api/v1/cpl/conversions/deductions/`

**请求示例**：

```json
{
  "level": "offer",
  "target_id": 100,
  "enable_volume_deduction": true,
  "volume_deduction_ratio": 0.1,
  "deduction_strategy": "random",
  "enable_amount_deduction": true,
  "amount_deduction_ratio": 0.05,
  "priority": 0,
  "is_active": true
}
```

**参数说明**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| level | string | 是 | 配置层级：advertiser/offer/publisher |
| target_id | int | 是 | 配置对象ID |
| enable_volume_deduction | bool | 否 | 是否启用扣量（默认false） |
| volume_deduction_ratio | float | 否 | 扣量比例（0-1，默认0.0） |
| deduction_strategy | string | 否 | 扣减策略：random/proportional/round_robin（默认random） |
| enable_amount_deduction | bool | 否 | 是否启用扣金额（默认false） |
| amount_deduction_ratio | float | 否 | 扣金额比例（0-1，默认0.0） |
| priority | int | 否 | 优先级（默认0） |
| is_active | bool | 否 | 是否激活（默认true） |

**注意事项**：
- 至少需要启用一种扣减方式（扣量或扣金额）
- 同一层级同一对象只能有一个激活的配置
- 扣量比例和扣金额比例必须在0-1之间

#### 8.1.2 配置示例

**示例1：仅扣量**

```json
{
  "level": "offer",
  "target_id": 100,
  "enable_volume_deduction": true,
  "volume_deduction_ratio": 0.15,
  "deduction_strategy": "random",
  "enable_amount_deduction": false,
  "is_active": true
}
```

**示例2：仅扣金额**

```json
{
  "level": "advertiser",
  "target_id": 10,
  "enable_volume_deduction": false,
  "enable_amount_deduction": true,
  "amount_deduction_ratio": 0.1,
  "is_active": true
}
```

**示例3：同时扣量和扣金额**

```json
{
  "level": "publisher",
  "target_id": 5,
  "enable_volume_deduction": true,
  "volume_deduction_ratio": 0.1,
  "deduction_strategy": "random",
  "enable_amount_deduction": true,
  "amount_deduction_ratio": 0.05,
  "is_active": true
}
```

### 8.2 查询扣减配置

#### 8.2.1 获取配置列表

**接口**：`GET /api/v1/cpl/conversions/deductions/`

**查询参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| page | int | 页码（默认1） |
| page_size | int | 每页条数（默认20） |
| level | string | 配置层级过滤 |
| is_active | bool | 状态过滤 |
| keyword | string | 搜索关键词（配置对象名称） |

**响应示例**：

```json
{
  "code": 200,
  "message": "success",
  "data": [
    {
      "id": 1,
      "level": "offer",
      "target_id": 100,
      "offer_name": "测试Offer",
      "enable_volume_deduction": true,
      "volume_deduction_ratio": 0.1,
      "deduction_strategy": "random",
      "enable_amount_deduction": true,
      "amount_deduction_ratio": 0.05,
      "priority": 0,
      "is_active": true,
      "created_at": "2024-01-01T00:00:00",
      "updated_at": "2024-01-01T00:00:00"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

### 8.3 更新扣减配置

#### 8.3.1 更新配置

**接口**：`PUT /api/v1/cpl/conversions/deductions/{config_id}`

**请求示例**：

```json
{
  "enable_volume_deduction": true,
  "volume_deduction_ratio": 0.2,
  "is_active": true
}
```

**注意事项**：
- 只能更新配置的字段值，不能修改`level`和`target_id`
- 如果要修改配置层级或对象，需要删除旧配置并创建新配置

#### 8.3.2 更新配置状态

**接口**：`PATCH /api/v1/cpl/conversions/deductions/{config_id}/status?is_active=true`

**功能**：快速启用或禁用配置

### 8.4 删除扣减配置

**接口**：`DELETE /api/v1/cpl/conversions/deductions/{config_id}`

**注意事项**：
- 删除配置不会影响已记录的扣减日志
- 删除后，相关的转化将不再应用扣减

### 8.5 查询扣减日志

#### 8.5.1 获取日志列表

**接口**：`GET /api/v1/cpl/conversions/deductions/logs`

**查询参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| page | int | 页码（默认1） |
| page_size | int | 每页条数（默认20） |
| start_date | string | 开始日期（YYYY-MM-DD） |
| end_date | string | 结束日期（YYYY-MM-DD） |
| advertiser_id | int | 广告主ID过滤 |
| offer_id | int | Offer ID过滤 |
| publisher_id | int | 渠道ID过滤 |

**响应示例**：

```json
{
  "code": 200,
  "message": "success",
  "data": [
    {
      "id": 1,
      "conversion_id": 12345,
      "click_id": "click_001",
      "advertiser_id": 10,
      "advertiser_name": "测试广告主",
      "offer_id": 100,
      "offer_name": "测试Offer",
      "publisher_id": 5,
      "publisher_name": "测试渠道",
      "original_volume": 1,
      "original_amount": 100.0,
      "deducted_volume": 1,
      "deducted_amount": 5.0,
      "final_volume": 0,
      "final_amount": 95.0,
      "deduction_config_id": 1,
      "volume_deduction_ratio": 0.1,
      "amount_deduction_ratio": 0.05,
      "deduction_strategy": "random",
      "deduction_reason": null,
      "created_at": "2024-01-01T00:00:00"
    }
  ],
  "total": 100,
  "page": 1,
  "page_size": 20
}
```

### 8.6 查询扣减统计

#### 8.6.1 获取统计数据

**接口**：`GET /api/v1/cpl/conversions/deductions/stats`

**查询参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| start_date | string | 开始日期（YYYY-MM-DD，默认30天前） |
| end_date | string | 结束日期（YYYY-MM-DD，默认今天） |
| group_by | string | 分组方式：time/advertiser/offer/publisher（默认time） |
| advertiser_id | int | 广告主ID过滤 |
| offer_id | int | Offer ID过滤 |
| publisher_id | int | 渠道ID过滤 |

**响应示例**：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "original_volume": 1000,
    "deducted_volume": 100,
    "final_volume": 900,
    "volume_deduction_ratio": 0.1,
    "original_amount": 100000.0,
    "deducted_amount": 5000.0,
    "final_amount": 95000.0,
    "amount_deduction_ratio": 0.05,
    "items": []
  }
}
```

---

## 9. 数据模型

### 9.1 扣减配置表（conversion_deduction_configs）

#### 9.1.1 表结构

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | int | 配置ID（主键） |
| advertiser_id | int | 广告主ID（可为NULL） |
| offer_id | int | Offer ID（可为NULL） |
| publisher_id | int | 渠道ID（可为NULL） |
| volume_deduction_ratio | float | 扣量比例（0-1） |
| amount_deduction_ratio | float | 扣金额比例（0-1） |
| deduction_strategy | string | 扣减策略 |
| enable_volume_deduction | bool | 是否启用扣量 |
| enable_amount_deduction | bool | 是否启用扣金额 |
| priority | int | 优先级 |
| is_active | bool | 是否激活 |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

#### 9.1.2 索引

- `idx_advertiser_id`：广告主ID索引
- `idx_offer_id`：Offer ID索引
- `idx_publisher_id`：渠道ID索引
- `idx_is_active`：激活状态索引
- `idx_priority`：优先级索引

### 9.2 扣减日志表（conversion_deduction_logs）

#### 9.2.1 表结构

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | int | 记录ID（主键） |
| conversion_id | int | 转化记录ID（可为NULL） |
| click_id | string | 点击ID |
| advertiser_id | int | 广告主ID |
| offer_id | int | Offer ID |
| publisher_id | int | 渠道ID |
| original_volume | int | 原始转化数量 |
| original_amount | float | 原始转化金额 |
| deducted_volume | int | 扣减的转化数量 |
| deducted_amount | float | 扣减的转化金额 |
| final_volume | int | 最终转化数量 |
| final_amount | float | 最终转化金额 |
| deduction_config_id | int | 使用的扣减配置ID |
| volume_deduction_ratio | float | 使用的扣量比例 |
| amount_deduction_ratio | float | 使用的扣金额比例 |
| deduction_strategy | string | 使用的扣减策略 |
| deduction_reason | text | 扣减原因说明 |
| created_at | datetime | 创建时间 |

#### 9.2.2 索引

- `idx_conversion_id`：转化记录ID索引
- `idx_click_id`：点击ID索引
- `idx_advertiser_id`：广告主ID索引
- `idx_offer_id`：Offer ID索引
- `idx_publisher_id`：渠道ID索引
- `idx_created_at`：创建时间索引
- `idx_deduction_config_id`：扣减配置ID索引

### 9.3 数据关系

```
ConversionDeductionConfig (扣减配置)
    ├─ advertiser_id → Advertiser (广告主)
    ├─ offer_id → Offer (Offer)
    └─ publisher_id → Publisher (渠道)

ConversionDeductionLog (扣减日志)
    ├─ conversion_id → PostbackConversion (转化记录)
    ├─ click_id → Click (点击记录)
    ├─ advertiser_id → Advertiser (广告主)
    ├─ offer_id → Offer (Offer)
    ├─ publisher_id → Publisher (渠道)
    └─ deduction_config_id → ConversionDeductionConfig (扣减配置)
```

---

## 10. 统计与监控

### 10.1 关键指标

#### 10.1.1 扣量指标

- **原始转化数（original_volume）**：统计时间窗口内所有转化数量
- **已扣量数（deducted_volume）**：统计时间窗口内被扣量的转化数量
- **最终转化数（final_volume）**：统计时间窗口内未被扣量的转化数量
- **扣量比例（volume_deduction_ratio）**：已扣量数 / 原始转化数

#### 10.1.2 扣金额指标

- **原始金额（original_amount）**：统计时间窗口内所有转化的原始金额总和
- **已扣金额（deducted_amount）**：统计时间窗口内被扣减的金额总和
- **最终金额（final_amount）**：统计时间窗口内扣减后的金额总和
- **扣金额比例（amount_deduction_ratio）**：已扣金额 / 原始金额

### 10.2 监控建议

#### 10.2.1 实时监控

- 监控扣量比例是否达到配置目标
- 监控扣金额是否正常计算
- 监控扣减日志是否正常记录

#### 10.2.2 定期检查

- 每周检查扣减统计，确保扣减比例符合预期
- 每月分析扣减日志，识别异常模式
- 定期审查配置，确保配置合理有效

### 10.3 告警设置

建议设置以下告警：

1. **扣量比例异常**：实际扣量比例与配置比例偏差超过5%
2. **扣减日志缺失**：连续1小时没有扣减日志记录
3. **配置异常**：发现无效或冲突的配置

---

## 11. 常见问题

### 11.1 扣量相关问题

#### Q1：为什么扣量比例和配置不一致？

**A**：扣量比例是动态计算的，基于统计时间窗口（默认24小时）内的数据。在时间窗口初期，扣量比例可能不稳定，随着数据积累会逐渐接近配置比例。

**解决方案**：
- 等待统计时间窗口积累足够数据
- 检查是否有多个配置冲突
- 检查配置的激活状态

#### Q2：扣量后转化去哪里了？

**A**：被扣量的转化不会保存到`postback_conversions`表，但会在`conversion_deduction_logs`表中记录。这是系统的设计，目的是隐藏扣量操作。

#### Q3：如何调整扣量比例？

**A**：通过更新扣减配置的`volume_deduction_ratio`字段。注意，调整后只影响新的转化，已处理的转化不会重新计算。

### 11.2 扣金额相关问题

#### Q1：扣金额是每个转化都扣吗？

**A**：是的，如果启用了扣金额，每个转化都会按照配置的比例扣减金额。

#### Q2：扣金额后的转化还能看到吗？

**A**：可以，扣金额后的转化仍然会保存到`postback_conversions`表，但`payout`字段会使用扣减后的金额。

#### Q3：如何计算扣金额？

**A**：扣金额 = 原始金额 × 扣金额比例。例如，原始金额100元，扣金额比例10%，则扣减10元，最终金额90元。

### 11.3 配置相关问题

#### Q1：多个配置会冲突吗？

**A**：不会，系统按优先级查找配置，只会使用优先级最高的配置。优先级：Offer > Advertiser > Publisher。

#### Q2：如何禁用配置？

**A**：有两种方式：
1. 更新配置的`is_active`字段为`false`
2. 删除配置

#### Q3：配置修改后何时生效？

**A**：配置修改后立即生效，只影响新的转化，已处理的转化不会重新计算。

### 11.4 性能相关问题

#### Q1：扣减操作会影响性能吗？

**A**：扣减操作会进行数据库查询和统计计算，但系统已优化，对性能影响较小。如果转化量非常大，建议定期清理旧的扣减日志。

#### Q2：统计时间窗口可以调整吗？

**A**：可以，在代码中修改`get_recent_conversion_stats()`函数的`hours`参数。但建议保持24小时，这是经过优化的默认值。

### 11.5 数据一致性问题

#### Q1：扣减日志和转化记录不一致怎么办？

**A**：这是正常现象。被扣量的转化不会保存到转化表，但会在扣减日志表中记录。可以通过扣减日志表查询所有转化（包括被扣量的）。

#### Q2：如何验证扣减是否正确？

**A**：可以通过以下方式验证：
1. 查询扣减统计，检查扣量比例和扣金额比例
2. 查询扣减日志，检查具体扣减记录
3. 对比原始金额和最终金额

---

## 附录

### A. 代码文件位置

- 扣减管理模块：`app/core/deduction/deduction_manager.py`
- 服务层：`app/services/cpl/conversion_deduction_service.py`
- API层：`app/api/api_v1/endpoints/cpl/conversions/deductions.py`
- 数据模型：`app/models/models.py`（ConversionDeductionConfig、ConversionDeductionLog）
- Schema定义：`app/schemas/cpl/deduction.py`

### B. API接口列表

| 接口 | 方法 | 说明 |
|------|------|------|
| /api/v1/cpl/conversions/deductions/ | POST | 创建扣减配置 |
| /api/v1/cpl/conversions/deductions/ | GET | 获取扣减配置列表 |
| /api/v1/cpl/conversions/deductions/{config_id} | PUT | 更新扣减配置 |
| /api/v1/cpl/conversions/deductions/{config_id} | DELETE | 删除扣减配置 |
| /api/v1/cpl/conversions/deductions/{config_id}/status | PATCH | 更新配置状态 |
| /api/v1/cpl/conversions/deductions/stats | GET | 获取扣减统计 |
| /api/v1/cpl/conversions/deductions/logs | GET | 获取扣减日志 |

### C. 术语表

| 术语 | 说明 |
|------|------|
| CPL | Cost Per Lead，按转化付费 |
| 扣量 | 将转化标记为无效，不计算到统计中 |
| 扣金额 | 按比例从转化金额中扣除 |
| 配置层级 | 配置的作用范围（Offer/Advertiser/Publisher） |
| 扣减策略 | 扣量的执行方式（random/proportional/round_robin） |
| 统计时间窗口 | 用于计算扣量比例的统计时间范围（默认24小时） |

---

## 版本历史

- **v1.0**（2024-01-01）：初始版本，包含基本扣量和扣金额功能

---

**文档结束**

