# CPL 系统参数详细列表

## 一、核心实体参数

### 1. Click（点击记录）参数

**表名**: `clicks`

| 参数名 | 类型 | 必填 | 说明 | 备注 |
|--------|------|------|------|------|
| `id` | Integer | 自动 | 点击记录ID（主键） | 自增 |
| `click_id` | String(255) | ✅ | 点击ID（系统生成，唯一标识） | 唯一索引 |
| `offer_id` | Integer | ❌ | 关联的Offer ID | 外键，可为空 |
| `publisher_id` | Integer | ❌ | 关联的渠道ID | 外键，可为空 |
| `advertiser_id` | Integer | ❌ | 关联的广告主ID | 外键，可为空 |
| `short_link_id` | Integer | ❌ | 关联的短链接ID | 外键，可为空 |
| `click_time` | DateTime | ✅ | 点击时间 | 索引 |
| `ip` | String(50) | ❌ | 点击IP地址 | |
| `device` | String(100) | ❌ | 设备信息 | |
| `country` | String(50) | ❌ | 国家 | |
| `user_agent` | Text | ❌ | User Agent | |
| `referer` | Text | ❌ | 来源页面 | |
| `conversion_id` | Integer | ❌ | 关联的转化ID（如果已转化） | 索引 |
| `created_at` | DateTime | 自动 | 创建时间 | |

**Tracklink 中的参数**:
- `click_id`: 点击ID（必填）
- `offer_id`: Offer ID（必填）
- `publisher_id`: 渠道ID（可选）

---

### 2. Conversion（转化记录）参数

**表名**: `conversions`（传统转化表）

| 参数名 | 类型 | 必填 | 说明 | 备注 |
|--------|------|------|------|------|
| `id` | Integer | 自动 | 转化记录ID（主键） | 自增 |
| `click_id` | String(255) | ✅ | 关联的Click ID | 唯一索引 |
| `offer_id` | Integer | ✅ | 关联的Offer ID | 外键 |
| `publisher_id` | Integer | ✅ | 关联的渠道ID | 外键 |
| `advertiser_id` | Integer | ✅ | 关联的广告主ID | 外键 |
| `conversion_time` | DateTime | ✅ | 转化时间 | 索引 |
| `payout` | Float | ❌ | 支付金额 | |
| `status` | String(20) | ✅ | 转化状态 | 默认 'Pending' |
| `created_at` | DateTime | 自动 | 创建时间 | |

---

### 3. PostbackConversion（Postback转化记录）参数

**表名**: `postback_conversions`

| 参数名 | 类型 | 必填 | 说明 | 备注 |
|--------|------|------|------|------|
| `id` | Integer | 自动 | 转化记录ID（主键） | 自增 |
| `platform` | String(50) | ✅ | 平台名称 | 如：macan, bft, addermobi |
| `conversion_id` | String(255) | ✅ | 转化ID（各平台唯一标识） | 如：clk_id |
| `event_name` | String(100) | ❌ | 事件名称 | 索引 |
| `event_value` | Float | ❌ | 事件价值（购买价格等） | |
| `payout` | Float | ❌ | 支付金额 | |
| `devad_id` | String(255) | ❌ | 设备广告ID（IDFA或GAID） | |
| `os` | String(20) | ❌ | 操作系统（IOS或Android） | |
| `carrier` | String(50) | ❌ | 用户运营商 | |
| `ip` | String(50) | ❌ | 点击IP地址 | |
| `gid` | String(100) | ❌ | 渠道ID（Channel ID） | |
| `product_id` | Integer | ❌ | 关联的产品ID | 外键 |
| `client_id` | Integer | ❌ | 关联的客户ID | 外键 |
| `click_id` | String(255) | ❌ | 关联的Click ID | 索引 |
| `click_time` | DateTime | ❌ | 点击时间 | |
| `conversion_status` | String(20) | ✅ | 转化状态 | 默认 'Pending' |
| `raw_data` | Text | ❌ | 原始回调数据（JSON格式） | |
| `created_at` | DateTime | 自动 | 创建时间 | 索引 |

---

### 4. Offer（单子）参数

**表名**: `offers`

| 参数名 | 类型 | 必填 | 说明 | 备注 |
|--------|------|------|------|------|
| `id` | Integer | 自动 | Offer ID（主键） | 自增 |
| `offer_name` | String(200) | ✅ | Offer名称 | |
| `advertiser_offer_id` | String(100) | ❌ | 上游系统中的Offer ID | ADV Offer ID |
| `advertiser_id` | Integer | ✅ | 关联的广告主ID | 外键，索引 |
| `preview_link` | Text | ❌ | 预览链接 | |
| `payout` | Float | ❌ | 上游支付金额（PO） | |
| `affiliate_payout` | Float | ❌ | 扣价后给渠道的金额 | PO扣价后 |
| `country` | String(50) | ❌ | 国家 | 索引 |
| `category` | String(50) | ❌ | 分类 | |
| `type` | String(50) | ❌ | 类型 | |
| `status` | String(20) | ✅ | 状态 | 默认 'Active'，索引 |
| `upstream_cap` | Integer | ❌ | 上游转化上限 | |
| `downstream_cap` | Integer | ❌ | 下游转化上限 | |
| `advertiser_tracklink` | Text | ❌ | 上游的Tracklink | 配置我们的参数 |
| `downstream_tracklink` | Text | ❌ | 生成给下游的Tracklink | |
| `postback_url` | Text | ❌ | Postback URL | 配置我们的参数 |
| `postback_method` | String(10) | ✅ | Postback请求方式 | 默认 'GET' |
| `click_validity_hours` | Integer | ✅ | 点击有效期（小时） | 默认 720（30天） |
| `is_active` | Boolean | ✅ | 是否激活 | 默认 True，索引 |
| `created_at` | DateTime | 自动 | 创建时间 | |
| `updated_at` | DateTime | 自动 | 更新时间 | |

**Tracklink 参数**:
- `{click_id}`: 点击ID占位符
- `{publisher_id}`: 渠道ID占位符

---

### 5. Publisher（渠道）参数

**表名**: `publishers`

| 参数名 | 类型 | 必填 | 说明 | 备注 |
|--------|------|------|------|------|
| `id` | Integer | 自动 | 渠道ID（主键） | 自增 |
| `publisher_name` | String(100) | ✅ | 渠道名称 | 索引 |
| `email` | String(255) | ❌ | 邮箱 | |
| `price_discount` | Float | ✅ | 渠道级别的价格扣量比例 | 默认 0.0（0-100） |
| `postback_url` | Text | ❌ | Postback URL | 渠道的Postback配置 |
| `postback_method` | String(10) | ✅ | Postback请求方式 | 默认 'GET' |
| `active_advertiser_count` | Integer | ✅ | 活跃的广告主数量 | 默认 0 |
| `is_active` | Boolean | ✅ | 是否激活 | 默认 True，索引 |
| `created_at` | DateTime | 自动 | 创建时间 | |
| `updated_at` | DateTime | 自动 | 更新时间 | |

**别名**: `channel_id`（在某些接口中，`publisher_id` 也被称为 `channel_id`）

---

### 6. Advertiser（广告主）参数

**表名**: `advertisers`

| 参数名 | 类型 | 必填 | 说明 | 备注 |
|--------|------|------|------|------|
| `id` | Integer | 自动 | 广告主ID（主键） | 自增 |
| `advertiser_name` | String(100) | ✅ | 广告主名称 | 索引 |
| `email` | String(255) | ❌ | 邮箱 | |
| `mobile` | String(20) | ❌ | 手机号 | |
| `is_active` | Boolean | ✅ | 是否激活 | 默认 True，索引 |
| `created_at` | DateTime | 自动 | 创建时间 | |
| `updated_at` | DateTime | 自动 | 更新时间 | |

---

## 二、Postback 回调参数

### BFT Postback 参数

**接口**: `/api/v1/bft/postback`

#### 必填参数
| 参数名 | 类型 | 说明 | 别名 |
|--------|------|------|------|
| `click_id` | String | 转化ID（必须是系统中存在的 click_id） | `clk_id`, `cid`, `clickid`, `clickId`, `ClickId`, `conversion_id`, `conversionId` |

#### 可选参数
| 参数名 | 类型 | 说明 | 别名 |
|--------|------|------|------|
| `event_name` | String | 事件名称 | `event_id`, `eventId`, `event`, `eventName`, `EventName` |
| `event_value` | Float | 事件价值（购买价格等） | |
| `payout` | Float | 支付金额 | |
| `os` | String | 操作系统 | Windows, Linux, Darwin, IOS, Android |
| `devad_id` | String | 设备广告ID（IDFA或GAID） | |
| `carrier` | String | 运营商 | |
| `ip` | String | IP地址 | 如果不提供会自动获取 |
| `gid` | String | 渠道ID | |
| `offer_id` | Integer/String | Offer ID | |
| `channel_id` | Integer/String | 渠道ID | 也支持 `publisher_id` |
| `product_id` | Integer | 产品ID | |
| `client_id` | Integer | 客户ID | |

---

### Macan Postback 参数

**接口**: `/api/v1/postback/macan`

#### 必填参数
| 参数名 | 类型 | 说明 | 别名 |
|--------|------|------|------|
| `clk_id` | String | Macan click ID | `click_id`, `cid`, `clickid`, `conversion_id` |

#### 可选参数
| 参数名 | 类型 | 说明 |
|--------|------|------|
| `event_name` | String | 事件名称 |
| `event_value` | Float | 事件价值 |
| `payout` | Float | 支付金额 |
| `devad_id` | String | 设备广告ID |
| `os` | String | 操作系统 |
| `carrier` | String | 运营商 |
| `ip` | String | IP地址 |
| `gid` | String | 渠道ID |
| `product_id` | Integer | 产品ID |
| `client_id` | Integer | 客户ID |

---

## 三、Tracklink 参数

### 上游 Tracklink（发送给广告主）

**生成函数**: `generate_upstream_tracklink()`

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `advertiser_tracklink` | String | ✅ | 上游的原始 Tracklink |
| `click_id` | String | ✅ | 我们生成的 Click ID |
| `offer_id` | String/Integer | ✅ | Offer ID |
| `publisher_id` | String/Integer | ❌ | 渠道ID |

**添加的参数**:
- `our_click_id`: 我们的 Click ID
- `our_offer_id`: 我们的 Offer ID
- `our_publisher_id`: 我们的渠道ID（如果提供）

---

### 下游 Tracklink（发送给渠道）

**生成函数**: `generate_downstream_tracklink()`

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `base_url` | String | ✅ | 基础URL（我们的追踪域名） |
| `offer_id` | String/Integer | ✅ | Offer ID |
| `publisher_id` | String/Integer | ✅ | 渠道ID |
| `click_id` | String | ✅ | Click ID |
| `additional_params` | Dict | ❌ | 额外参数 |

**URL 格式**:
```
{base_url}/track/click?offer_id={offer_id}&publisher_id={publisher_id}&click_id={click_id}
```

---

### Postback URL（配置给上游）

**生成函数**: `generate_postback_url()`

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `base_url` | String | ✅ | 基础URL（我们的Postback接收地址） |
| `click_id` | String | ✅ | Click ID |
| `offer_id` | String/Integer | ✅ | Offer ID |
| `publisher_id` | String/Integer | ❌ | 渠道ID |
| `additional_params` | Dict | ❌ | 额外参数 |

**URL 格式**:
```
{base_url}?click_id={click_id}&offer_id={offer_id}&publisher_id={publisher_id}
```

---

## 四、点击追踪接口参数

**接口**: `/api/v1/track/click/{offer_id}`

### Query 参数
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `offer_id` | Integer | ✅ | Offer ID（路径参数） |
| `publisher_id` | Integer | ❌ | 渠道ID（Query参数） |

### 自动获取的参数
| 参数名 | 类型 | 说明 |
|--------|------|------|
| `ip` | String | 从请求头获取客户端IP |
| `user_agent` | String | 从请求头获取 User-Agent |
| `referer` | String | 从请求头获取 Referer |
| `device` | String | 从 User-Agent 解析设备信息 |
| `country` | String | 从 IP 解析国家信息 |

---

## 五、配置相关参数

### OfferCap（Cap配置）参数

**表名**: `offer_caps`

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `id` | Integer | 自动 | Cap配置ID |
| `cap_type` | String(50) | ✅ | Cap类型 | `advertiser_offer` 或 `offer` |
| `advertiser_id` | Integer | ❌ | 广告主ID | 如果是 advertiser_offer 类型 |
| `offer_id` | Integer | ✅ | Offer ID | 外键 |
| `publisher_id` | Integer | ❌ | 渠道ID | 如果为空，表示所有渠道 |
| `daily_cap` | Integer | ❌ | 每日Cap | |
| `total_cap` | Integer | ❌ | 总Cap | |
| `current_daily_count` | Integer | ✅ | 当前每日计数 | 默认 0 |
| `current_total_count` | Integer | ✅ | 当前总计数 | 默认 0 |
| `cap_start_date` | DateTime | ❌ | Cap开始日期 | 用于 Total Cap |
| `is_active` | Boolean | ✅ | 是否激活 | 默认 True |

---

### OfferDiscount（扣量配置）参数

**表名**: `offer_discounts`

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `id` | Integer | 自动 | 扣量配置ID |
| `discount_type` | String(50) | ✅ | 扣量类型 | `offer` 或 `channel` |
| `offer_id` | Integer | ❌ | Offer ID | 如果是 offer 类型 |
| `publisher_id` | Integer | ✅ | 渠道ID | 外键 |
| `discount_ratio` | Float | ✅ | 扣量比例 | 0-100 |
| `is_active` | Boolean | ✅ | 是否激活 | 默认 True |

---

### OfferPublisherAssignment（Offer-渠道分配）参数

**表名**: `offer_publisher_assignments`

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `id` | Integer | 自动 | 分配ID |
| `offer_id` | Integer | ✅ | Offer ID | 外键，唯一约束 |
| `publisher_id` | Integer | ✅ | 渠道ID | 外键，唯一约束 |
| `downstream_cap` | Integer | ❌ | 该渠道的下游转化上限 | |
| `affiliate_payout` | Float | ❌ | 该渠道的扣价后金额 | PO扣价后 |
| `is_active` | Boolean | ✅ | 是否激活 | 默认 True |

---

## 六、系统内部参数映射

### Click ID 相关参数映射
以下参数名都可以表示 Click ID（按优先级）:
1. `click_id`
2. `clk_id`
3. `cid`
4. `clickid`
5. `clickId`
6. `ClickId`
7. `conversion_id`
8. `conversionId`

### Event Name 相关参数映射
以下参数名都可以表示事件名称（按优先级）:
1. `event_name`
2. `event_id`
3. `eventId`
4. `event`
5. `eventName`
6. `EventName`

### Channel/Publisher ID 相关参数映射
以下参数名都可以表示渠道ID:
- `publisher_id`
- `channel_id`
- `gid`（在某些平台中）

---

## 七、参数使用场景

### 1. 点击追踪流程
```
用户点击 → /track/click/{offer_id}?publisher_id={publisher_id}
         → 生成 click_id
         → 记录 Click 记录（包含 offer_id, publisher_id, advertiser_id, click_time, ip 等）
         → 重定向到上游 Tracklink（添加 our_click_id, our_offer_id 参数）
```

### 2. 转化回调流程
```
上游发送 Postback → /api/v1/bft/postback?click_id={click_id}&event_name={event_name}
                  → 通过 click_id 查找 Click 记录
                  → 获取 offer_id, publisher_id, advertiser_id, click_time
                  → 创建 PostbackConversion 记录
                  → 转发给下游 Postback URL（包含所有参数）
```

### 3. 参数传递链路
```
上游广告主 ← our_click_id, our_offer_id, our_publisher_id
         ↓
    CPL系统
         ↓
下游渠道 ← offer_id, publisher_id, click_id
```

---

## 八、注意事项

1. **Click ID 唯一性**: `click_id` 在整个系统中必须唯一，用于关联点击和转化记录。

2. **参数类型转换**: 
   - Postback 接口接收的参数可能是字符串，需要转换为相应的类型（整数、浮点数等）
   - 系统会自动处理类型转换

3. **参数别名支持**: 系统支持多种参数名变体，提高兼容性

4. **必填 vs 可选**: 
   - 必填参数：`click_id`（或别名）是 Postback 回调的必填参数
   - 其他参数都是可选的，但建议提供完整信息以便追踪和分析

5. **参数长度限制**: 
   - 字符串参数有长度限制（如 `click_id` 最大 255 字符）
   - 超长参数会被截断

6. **时间参数**: 
   - `click_time`: 点击时间，从 Click 记录中获取
   - `conversion_time`: 转化时间，Postback 回调时的时间
   - `click_validity_hours`: 点击有效期，默认 720 小时（30天）

---

## 九、常用参数组合

### 最小必填参数组合（Postback）
```json
{
  "click_id": "abc123..."
}
```

### 完整参数组合（Postback）
```json
{
  "click_id": "abc123...",
  "event_name": "purchase",
  "event_value": 99.99,
  "payout": 10.00,
  "offer_id": 1,
  "channel_id": 3,
  "os": "Android",
  "ip": "192.168.1.1",
  "devad_id": "12345678-1234-1234-1234-123456789012",
  "carrier": "China Mobile",
  "product_id": 1,
  "client_id": 1
}
```

---

**文档版本**: v1.0  
**最后更新**: 2025-01-XX  
**维护者**: CPL 系统开发团队

