# CPL 系统 Postback URL 占位符参数映射表

本文档详细列出了 CPL 系统中所有可用于 Postback URL 占位符的参数，包括对应的数据库表、字段名、数据类型和详细说明。

---

## 一、PostbackConversion 表直接字段

**表名**: `postback_conversions`

| 占位符变量 | 数据库字段 | 数据类型 | 是否可为空 | 详细说明 | 示例值 |
|-----------|-----------|---------|-----------|---------|--------|
| `{conversion_id}` | `conversion_id` | String(255) | ❌ 必填 | 转化ID（各平台唯一标识，如上游平台的clk_id） | `"abc123xyz"` |
| `{platform}` | `platform` | String(50) | ❌ 必填 | 平台名称（如：macan, bft, addermobi等） | `"macan"` |
| `{event_name}` | `event_name` | String(100) | ✅ 可为空 | 事件名称（如：purchase, signup, install等） | `"purchase"` |
| `{event_value}` | `event_value` | Float | ✅ 可为空 | 事件价值（购买价格、订单金额等） | `99.99` |
| `{payout}` | `payout` | Float | ✅ 可为空 | 支付金额（确认的广告单元价格，已扣减后的金额） | `10.50` |
| `{devad_id}` | `devad_id` | String(255) | ✅ 可为空 | 设备广告ID（IDFA或GAID，用于移动设备追踪） | `"12345678-1234-1234-1234-123456789012"` |
| `{os}` | `os` | String(20) | ✅ 可为空 | 操作系统（IOS、Android、Windows、Linux等） | `"Android"` |
| `{carrier}` | `carrier` | String(50) | ✅ 可为空 | 用户运营商（如：China Mobile, Verizon等） | `"China Mobile"` |
| `{ip}` | `ip` | String(50) | ✅ 可为空 | 点击IP地址 | `"192.168.1.1"` |
| `{gid}` | `gid` | String(100) | ✅ 可为空 | 渠道ID（Channel ID，某些平台使用的渠道标识） | `"channel_123"` |
| `{product_id}` | `product_id` | Integer | ✅ 可为空 | 关联的产品ID（外键，关联products表） | `1` |
| `{client_id}` | `client_id` | Integer | ✅ 可为空 | 关联的客户ID（外键，关联clients表） | `1003` |
| `{click_id}` | `click_id` | String(255) | ✅ 可为空 | 关联的Click ID（CPL系统生成的点击ID，用于关联点击记录） | `"click_abc123"` |
| `{click_time}` | `click_time` | DateTime | ✅ 可为空 | 点击时间（ISO格式：YYYY-MM-DDTHH:MM:SS） | `"2025-01-15T10:30:00"` |
| `{conversion_status}` | `conversion_status` | String(20) | ❌ 必填 | 转化状态（Pending、Approved、Rejected、CapReached、ClickExpired等） | `"Approved"` |
| `{timestamp}` | `created_at` | DateTime | ❌ 必填 | 转化记录创建时间（ISO格式：YYYY-MM-DDTHH:MM:SS） | `"2025-01-15T10:35:00"` |
| `{created_at}` | `created_at` | DateTime | ❌ 必填 | 转化记录创建时间（ISO格式，与timestamp相同） | `"2025-01-15T10:35:00"` |

---

## 二、Click 表关联字段（通过 click_id 关联）

**表名**: `clicks`  
**关联方式**: `PostbackConversion.click_id` → `Click.click_id`

| 占位符变量 | 数据库字段 | 数据类型 | 是否可为空 | 详细说明 | 示例值 |
|-----------|-----------|---------|-----------|---------|--------|
| `{click_offer_id}` | `Click.offer_id` | Integer | ✅ 可为空 | 点击记录关联的Offer ID（外键，关联offers表） | `1` |
| `{click_publisher_id}` | `Click.publisher_id` | Integer | ✅ 可为空 | 点击记录关联的渠道ID（外键，关联publishers表） | `101` |
| `{click_advertiser_id}` | `Click.advertiser_id` | Integer | ✅ 可为空 | 点击记录关联的广告主ID（外键，关联advertisers表） | `5` |
| `{click_ip}` | `Click.ip` | String(50) | ✅ 可为空 | 点击时的IP地址（可能与转化时的IP不同） | `"192.168.1.100"` |
| `{click_device}` | `Click.device` | String(100) | ✅ 可为空 | 点击时的设备信息 | `"iPhone 12"` |
| `{click_country}` | `Click.country` | String(50) | ✅ 可为空 | 点击时的国家代码（从IP解析） | `"CN"` |
| `{click_user_agent}` | `Click.user_agent` | Text | ✅ 可为空 | 点击时的User Agent | `"Mozilla/5.0..."` |
| `{click_referer}` | `Click.referer` | Text | ✅ 可为空 | 点击时的来源页面URL | `"https://example.com"` |

**注意**: 这些字段需要通过 `click_id` 查询 Click 表获取，如果 `click_id` 为空或找不到对应的 Click 记录，这些占位符将无法替换。

---

## 三、Offer 表关联字段（通过 click_id → Click → offer_id 关联）

**表名**: `offers`  
**关联方式**: `PostbackConversion.click_id` → `Click.click_id` → `Click.offer_id` → `Offer.id`

| 占位符变量 | 数据库字段 | 数据类型 | 是否可为空 | 详细说明 | 示例值 |
|-----------|-----------|---------|-----------|---------|--------|
| `{offer_id}` | `Offer.id` | Integer | ✅ 可为空 | Offer ID（主键） | `1` |
| `{offer_name}` | `Offer.offer_name` | String(200) | ❌ 必填 | Offer名称 | `"iOS App Install"` |
| `{advertiser_offer_id}` | `Offer.advertiser_offer_id` | String(100) | ✅ 可为空 | 上游系统中的Offer ID（ADV Offer ID） | `"ADV_OFFER_123"` |
| `{offer_advertiser_id}` | `Offer.advertiser_id` | Integer | ❌ 必填 | Offer关联的广告主ID | `5` |
| `{offer_payout}` | `Offer.payout` | Float | ✅ 可为空 | 上游支付金额（PO，原始价格） | `15.00` |
| `{affiliate_payout}` | `Offer.affiliate_payout` | Float | ✅ 可为空 | 扣价后给渠道的金额（PO扣价后） | `12.00` |
| `{offer_country}` | `Offer.country` | String(50) | ✅ 可为空 | Offer目标国家 | `"US"` |
| `{offer_category}` | `Offer.category` | String(50) | ✅ 可为空 | Offer分类 | `"Mobile"` |
| `{offer_type}` | `Offer.type` | String(50) | ✅ 可为空 | Offer类型 | `"CPI"` |
| `{offer_status}` | `Offer.status` | String(20) | ❌ 必填 | Offer状态（Active、Inactive等） | `"Active"` |

**注意**: 这些字段需要通过 `click_id` → `Click.offer_id` → `Offer.id` 关联查询获取。

---

## 四、Publisher 表关联字段（通过 click_id → Click → publisher_id 关联）

**表名**: `publishers`  
**关联方式**: `PostbackConversion.click_id` → `Click.click_id` → `Click.publisher_id` → `Publisher.id`

| 占位符变量 | 数据库字段 | 数据类型 | 是否可为空 | 详细说明 | 示例值 |
|-----------|-----------|---------|-----------|---------|--------|
| `{publisher_id}` | `Publisher.id` | Integer | ✅ 可为空 | 渠道ID（主键） | `101` |
| `{channel_id}` | `Publisher.id` | Integer | ✅ 可为空 | 渠道ID（publisher_id的别名） | `101` |
| `{publisher_name}` | `Publisher.publisher_name` | String(100) | ❌ 必填 | 渠道名称 | `"渠道A"` |
| `{publisher_email}` | `Publisher.email` | String(255) | ✅ 可为空 | 渠道邮箱 | `"publisher@example.com"` |

**注意**: 
- `{publisher_id}` 和 `{channel_id}` 是同一个字段的不同名称，都指向 `Publisher.id`
- 这些字段需要通过 `click_id` → `Click.publisher_id` → `Publisher.id` 关联查询获取

---

## 五、Advertiser 表关联字段（通过 click_id → Click → advertiser_id 关联）

**表名**: `advertisers`  
**关联方式**: `PostbackConversion.click_id` → `Click.click_id` → `Click.advertiser_id` → `Advertiser.id`

| 占位符变量 | 数据库字段 | 数据类型 | 是否可为空 | 详细说明 | 示例值 |
|-----------|-----------|---------|-----------|---------|--------|
| `{advertiser_id}` | `Advertiser.id` | Integer | ✅ 可为空 | 广告主ID（主键） | `5` |
| `{advertiser_name}` | `Advertiser.advertiser_name` | String(100) | ❌ 必填 | 广告主名称 | `"广告主A"` |
| `{advertiser_email}` | `Advertiser.email` | String(255) | ✅ 可为空 | 广告主邮箱 | `"advertiser@example.com"` |

**注意**: 这些字段需要通过 `click_id` → `Click.advertiser_id` → `Advertiser.id` 关联查询获取。

---

## 六、常用占位符别名映射

为了兼容不同的命名习惯，以下占位符支持别名：

| 标准占位符 | 支持的别名 | 说明 |
|-----------|-----------|------|
| `{click_id}` | `{clickid}`, `{clickId}`, `{clk_id}`, `{cid}` | 点击ID的各种写法 |
| `{conversion_id}` | `{conversionId}`, `{conv_id}` | 转化ID的各种写法 |
| `{publisher_id}` | `{channel_id}`, `{publisherId}`, `{channelId}` | 渠道ID的各种写法 |
| `{offer_id}` | `{offerId}`, `{offer_id}` | Offer ID的各种写法 |
| `{event_name}` | `{eventName}`, `{event_id}`, `{eventId}` | 事件名称的各种写法 |

**注意**: 实现时建议统一转换为小写加下划线的标准格式（如 `click_id`），然后再进行替换。

---

## 七、参数获取优先级和关联关系

### 7.1 直接字段（最高优先级）
直接从 `PostbackConversion` 表获取，无需关联查询：
- `{conversion_id}`, `{platform}`, `{event_name}`, `{event_value}`, `{payout}`, `{devad_id}`, `{os}`, `{carrier}`, `{ip}`, `{gid}`, `{product_id}`, `{client_id}`, `{click_id}`, `{click_time}`, `{conversion_status}`, `{timestamp}`, `{created_at}`

### 7.2 一级关联（需要查询 Click 表）
如果 `PostbackConversion.click_id` 存在，可以通过 Click 表获取：
- `{click_offer_id}`, `{click_publisher_id}`, `{click_advertiser_id}`, `{click_ip}`, `{click_device}`, `{click_country}`, `{click_user_agent}`, `{click_referer}`

### 7.3 二级关联（需要查询 Click → Offer/Publisher/Advertiser）
如果 `PostbackConversion.click_id` 存在且对应的 Click 记录有 `offer_id`/`publisher_id`/`advertiser_id`，可以进一步关联：
- Offer 相关：`{offer_id}`, `{offer_name}`, `{advertiser_offer_id}`, `{offer_advertiser_id}`, `{offer_payout}`, `{affiliate_payout}`, `{offer_country}`, `{offer_category}`, `{offer_type}`, `{offer_status}`
- Publisher 相关：`{publisher_id}`, `{channel_id}`, `{publisher_name}`, `{publisher_email}`
- Advertiser 相关：`{advertiser_id}`, `{advertiser_name}`, `{advertiser_email}`

---

## 八、实现建议

### 8.1 占位符识别
使用正则表达式识别 `{变量名}` 格式的占位符：
```python
import re
pattern = r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}'
placeholders = re.findall(pattern, url)
```

### 8.2 参数值获取策略
1. **直接字段**: 从 `conversion` 对象直接获取
2. **Click 关联字段**: 
   - 如果 `conversion.click_id` 存在，查询 Click 表
   - 如果查询失败或字段为空，占位符保持原样或替换为空字符串
3. **Offer/Publisher/Advertiser 关联字段**:
   - 通过 Click 记录的 `offer_id`/`publisher_id`/`advertiser_id` 查询
   - 如果任一环节缺失，占位符保持原样或替换为空字符串

### 8.3 数据类型转换
- **字符串类型**: 直接转换为字符串（`str(value)`）
- **数值类型**: 转换为字符串（`str(value)`）
- **日期时间类型**: 转换为 ISO 格式字符串（`value.isoformat()`）
- **空值处理**: 如果值为 `None`，可以：
  - 保持占位符不变：`{click_id}` → `{click_id}`
  - 替换为空字符串：`{click_id}` → ``（空）
  - 替换为默认值：`{click_id}` → `""` 或 `"N/A"`

### 8.4 性能优化建议
- 对于需要关联查询的字段，建议一次性查询所有需要的关联对象（Click、Offer、Publisher、Advertiser）
- 使用 SQLAlchemy 的 `joinedload` 或 `selectinload` 进行预加载，避免 N+1 查询问题
- 对于不存在的占位符，可以记录警告日志，但不影响主流程

---

## 九、示例

### 9.1 URL 示例
```
原始URL: http://kombiadcps.xyz/service/offer/postback?clickid={click_id}&payout={payout}&offer_id={offer_id}&publisher_id={publisher_id}
```

### 9.2 替换后的URL
假设：
- `click_id` = `"click_abc123"`
- `payout` = `10.50`
- `offer_id` = `1`（通过 Click 表关联获取）
- `publisher_id` = `101`（通过 Click 表关联获取）

```
替换后: http://kombiadcps.xyz/service/offer/postback?clickid=click_abc123&payout=10.50&offer_id=1&publisher_id=101
```

### 9.3 复杂示例
```
原始URL: http://example.com/postback?click_id={click_id}&conversion_id={conversion_id}&event_name={event_name}&payout={payout}&offer_name={offer_name}&publisher_name={publisher_name}&advertiser_name={advertiser_name}&timestamp={timestamp}
```

替换后（假设所有字段都有值）:
```
http://example.com/postback?click_id=click_abc123&conversion_id=conv_xyz789&event_name=purchase&payout=10.50&offer_name=iOS%20App%20Install&publisher_name=渠道A&advertiser_name=广告主A&timestamp=2025-01-15T10:35:00
```

---

## 十、注意事项

1. **URL 编码**: 替换后的值如果包含特殊字符（如空格、中文等），需要进行 URL 编码
2. **空值处理**: 建议在文档中明确说明空值的处理方式（保持占位符、替换为空字符串、或使用默认值）
3. **性能考虑**: 关联查询会增加数据库负载，建议对常用字段进行缓存或优化
4. **错误处理**: 如果关联查询失败，应该记录日志但不影响主流程
5. **安全性**: 确保替换后的 URL 不会引入安全漏洞（如 SQL 注入、XSS 等）

---

**文档版本**: v1.0  
**最后更新**: 2025-01-15  
**维护者**: CPL 系统开发团队

