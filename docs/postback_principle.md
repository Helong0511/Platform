# Postback 原理详解

## 一、什么是 Postback？

**Postback（回传）** 是一种服务器到服务器（Server-to-Server，S2S）的数据传输机制，用于在广告追踪场景中，当用户完成特定动作（如购买、注册、安装等）时，广告平台主动向我们的服务器发送通知。

### 类比理解

想象一下：
- **你** = 我们的服务器（接收方）
- **快递公司** = 广告平台（Macan、Addermobi 等）
- **包裹** = 转化事件数据（用户完成了购买等动作）

当用户在你的网站上完成购买后，广告平台就像快递公司一样，主动"送货上门"（发送 postback），告诉你："嘿，你投放的广告产生了一个转化！"

## 二、为什么需要 Postback？

### 传统方式的问题

在移动广告追踪中，传统方式是通过客户端（App）直接上报数据：

```
用户完成购买 → App 上报 → 我们的服务器
```

**问题：**
1. **数据不准确**：客户端可能被篡改、网络不稳定、用户卸载 App
2. **隐私限制**：iOS 14.5+ 的 ATT（App Tracking Transparency）限制了客户端追踪
3. **延迟和丢失**：网络问题导致数据延迟或丢失

### Postback 的优势

```
用户完成购买 → 广告平台服务器 → Postback → 我们的服务器
```

**优势：**
1. **数据准确**：服务器到服务器，不受客户端影响
2. **隐私友好**：符合 iOS ATT 等隐私政策
3. **实时可靠**：广告平台保证数据送达
4. **数据完整**：包含完整的转化信息（金额、设备信息等）

## 三、Postback 工作流程

### 完整流程示意图

```
┌─────────────┐
│   用户      │
│  (User)     │
└──────┬──────┘
       │ 1. 点击广告
       ▼
┌─────────────────┐
│   广告平台      │
│  (Macan/等)     │
│                 │
│  - 记录点击     │
│  - 生成 click_id│
│  - 跳转到产品   │
└──────┬──────────┘
       │ 2. 用户完成转化（购买/注册等）
       ▼
┌─────────────────┐
│   产品服务器    │
│  (我们的产品)   │
│                 │
│  用户完成购买   │
└──────┬──────────┘
       │ 3. 通知广告平台（可选）
       ▼
┌─────────────────┐
│   广告平台      │
│  (Macan/等)     │
│                 │
│  - 确认转化     │
│  - 计算收益     │
└──────┬──────────┘
       │ 4. 发送 Postback
       │    GET/POST /api/v1/postback/macan
       ▼
┌─────────────────┐
│   我们的服务器  │
│  (Platform)     │
│                 │
│  - 接收数据     │
│  - 验证数据     │
│  - 存储数据库   │
│  - 返回成功     │
└─────────────────┘
```

### 详细步骤说明

#### 步骤 1：用户点击广告

用户在广告平台（如 Macan）上看到广告并点击：

```
原始广告链接：https://your-product.com/app
```

广告平台会自动添加追踪参数：

```
实际跳转链接：https://your-product.com/app?click_id=abc123&ios_idfa=xyz789&source=channel1
```

**关键参数：**
- `click_id` (或 `[sid]`)：广告平台生成的唯一点击ID
- `ios_idfa`：iOS 设备的广告标识符
- `source`：渠道ID

#### 步骤 2：用户完成转化

用户在我们的产品中完成转化动作（购买、注册、安装等）：

```
用户操作：购买商品 $99.99
产品服务器记录：订单ID、金额、设备信息等
```

#### 步骤 3：广告平台检测转化

广告平台通过以下方式之一检测到转化：

**方式 A：产品服务器主动通知**
```
产品服务器 → POST → 广告平台
"用户 abc123 完成了购买，金额 $99.99"
```

**方式 B：广告平台主动检测**
```
广告平台定期检查用户行为
发现用户 abc123 完成了转化
```

#### 步骤 4：广告平台发送 Postback

广告平台向我们在 Macan 平台配置的 Postback URL 发送请求：

**GET 方式：**
```
GET /api/v1/postback/macan?
  clk_id=abc123&
  event_name=purchase&
  event_value=99.99&
  payout=10.5&
  devad_id=xyz789&
  os=IOS&
  carrier=China Mobile
```

**POST 方式：**
```
POST /api/v1/postback/macan
Content-Type: application/json

{
  "clk_id": "abc123",
  "event_name": "purchase",
  "event_value": 99.99,
  "payout": 10.5,
  "devad_id": "xyz789",
  "os": "IOS",
  "carrier": "China Mobile"
}
```

#### 步骤 5：我们的服务器处理

我们的服务器接收到 Postback 后：

1. **验证数据**：检查必填参数（clk_id、event_name）
2. **标准化数据**：将各平台的数据格式统一
3. **防重复处理**：检查是否已存在相同的转化记录
4. **存储数据库**：保存到 `postback_conversions` 表
5. **返回成功**：返回 200 状态码确认接收

## 四、我们实现的架构原理

### 1. 统一处理架构

```
┌─────────────────────────────────────┐
│     统一 Postback 服务              │
│  /api/v1/postback/{platform}        │
└──────────────┬──────────────────────┘
               │
       ┌───────┴────────┐
       │                │
       ▼                ▼
┌─────────────┐  ┌─────────────┐
│ Macan       │  │ Addermobi   │
│ Handler     │  │ Handler     │
│             │  │ (可扩展)    │
└──────┬──────┘  └──────┬──────┘
       │                │
       └────────┬───────┘
                │
                ▼
        ┌───────────────┐
        │   Processor   │
        │  (统一处理)   │
        └───────┬───────┘
                │
                ▼
        ┌───────────────┐
        │   数据库      │
        │ postback_     │
        │ conversions   │
        └───────────────┘
```

### 2. 处理器注册机制

**设计模式：策略模式 + 注册表模式**

```python
# 1. 定义处理器基类
class PostbackHandler(ABC):
    @abstractmethod
    async def validate(self, data):  # 验证数据
        pass
    
    @abstractmethod
    async def normalize(self, data):  # 标准化数据
        pass

# 2. 实现各平台处理器
class MacanPostbackHandler(PostbackHandler):
    platform_name = "macan"
    # Macan 特定的验证和标准化逻辑

# 3. 注册处理器
register_handler(MacanPostbackHandler())

# 4. 统一处理
processor = PostbackProcessor()
result = await processor.process(platform="macan", data=raw_data)
```

**优势：**
- **可扩展**：添加新平台只需实现 Handler
- **统一接口**：所有平台使用相同的处理流程
- **易于维护**：各平台逻辑独立，互不影响

### 3. 数据标准化流程

```
原始数据（各平台格式不同）
    ↓
Macan Handler.normalize()
    ↓
标准化数据（统一格式）
    ↓
{
  "conversion_id": "abc123",    # 统一字段名
  "event_name": "purchase",
  "event_value": 99.99,
  "payout": 10.5,
  ...
}
    ↓
存储到数据库（统一表结构）
```

### 4. 防重复处理机制

**唯一性约束：**
```sql
UNIQUE KEY (platform, conversion_id, event_name)
```

**处理流程：**
```
接收 Postback
    ↓
查询数据库：是否存在 (macan, abc123, purchase)？
    ↓
存在？ → 返回"已存在，跳过重复处理"
    ↓
不存在？ → 创建新记录 → 返回"接收成功"
```

## 五、关键技术点

### 1. 路由设计

**问题：** 如何区分 `/postback/conversions` 和 `/postback/{platform}`？

**解决方案：**
- **路由顺序**：具体路径在前，动态路径在后
- **保留路径检查**：拒绝 "conversions" 和 "stats" 作为平台名

```python
# 1. 具体路径（优先匹配）
@router.get("/postback/conversions")  # 查询接口
@router.get("/postback/stats")        # 统计接口

# 2. 动态路径（最后匹配）
@router.get("/postback/{platform}")  # 接收回调
```

### 2. 数据验证

**两层验证：**

1. **平台特定验证**（Handler.validate）
   - Macan：必须要有 clk_id 和 event_name
   - Addermobi：可能有不同的必填字段

2. **通用验证**（Processor）
   - 产品和客户是否存在
   - 数据格式是否正确

### 3. 错误处理

```python
try:
    # 处理 postback
    result = await processor.process(...)
    return success_response
except ValidationError:
    # 数据验证失败 → 返回 422
except NotFoundError:
    # 平台不支持 → 返回 404
except DuplicateError:
    # 重复处理 → 返回成功（已存在）
except Exception:
    # 其他错误 → 记录日志 → 返回 500
```

## 六、实际应用场景

### 场景 1：广告效果追踪

```
广告投放 → 用户点击 → 用户购买 → Postback → 数据分析
```

**数据用途：**
- 计算 ROI（投资回报率）
- 分析哪个渠道效果最好
- 优化广告投放策略

### 场景 2：收益结算

```
Postback 包含 payout（支付金额）
    ↓
记录到数据库
    ↓
生成收益报表
    ↓
与广告平台对账
```

### 场景 3：实时监控

```
Postback 到达
    ↓
存储数据库
    ↓
发送 Telegram 通知（可选）
    ↓
更新实时统计
```

## 七、与其他追踪方式的对比

| 方式 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| **客户端追踪** | 实时、详细 | 不准确、隐私限制 | 简单场景 |
| **Postback (S2S)** | 准确、可靠、隐私友好 | 需要配置 | **推荐：移动广告** |
| **像素追踪** | 简单 | 容易被屏蔽 | Web 广告 |

## 八、安全考虑

### 1. 防重复攻击

- **唯一性约束**：数据库层面防止重复
- **幂等性**：相同请求多次处理结果一致

### 2. 数据验证

- **必填参数检查**：防止恶意请求
- **数据格式验证**：防止注入攻击
- **产品和客户验证**：防止关联错误数据

### 3. 日志记录

- **完整日志**：记录所有请求和响应
- **错误追踪**：记录异常情况
- **审计追踪**：便于问题排查

## 九、总结

Postback 的核心原理：

1. **事件驱动**：用户完成转化 → 触发 Postback
2. **服务器通信**：广告平台 → 我们的服务器
3. **数据标准化**：各平台格式 → 统一格式
4. **持久化存储**：内存 → 数据库
5. **可扩展架构**：新平台 → 添加 Handler

**关键优势：**
- ✅ 数据准确可靠
- ✅ 符合隐私政策
- ✅ 实时性高
- ✅ 易于扩展和维护

这就是我们实现的统一 Postback 服务的核心原理！

