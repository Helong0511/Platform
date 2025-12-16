# 统一 Postback 服务文档

## 一、概述

已实现统一的 Postback 服务，支持多平台的 postback 回调处理。该服务提供了：

1. **统一的数据存储**：所有平台的 postback 数据统一存储到 `postback_conversions` 表
2. **可扩展的处理器架构**：通过注册机制轻松添加新平台支持
3. **完整的查询和统计功能**：管理员可以查询转化记录和统计信息
4. **向后兼容**：保留原有的 Macan postback 接口，内部调用统一服务

## 二、架构设计

### 1. 目录结构

```
app/
├── core/
│   └── postback/
│       ├── __init__.py          # 模块导出
│       ├── handlers.py          # 处理器基类和注册机制
│       ├── processor.py         # 统一处理逻辑
│       └── macan_handler.py    # Macan 平台处理器
├── models/
│   └── models.py                # PostbackConversion 数据模型
├── schemas/
│   └── postback.py              # Postback 相关的 Schema
└── api/
    └── api_v1/
        └── endpoints/
            ├── postback.py      # 统一 Postback 路由接口
            └── macan_postback.py # Macan 专用接口（已优化）
```

### 2. 数据模型

**PostbackConversion 表结构：**

- `id`: 主键
- `platform`: 平台名称（macan, addermobi等）
- `conversion_id`: 转化ID（各平台唯一标识）
- `event_name`: 事件名称
- `event_value`: 事件价值
- `payout`: 支付金额
- `devad_id`: 设备广告ID
- `os`: 操作系统
- `carrier`: 运营商
- `ip`: IP地址
- `gid`: 渠道ID
- `product_id`: 关联的产品ID
- `client_id`: 关联的客户ID
- `raw_data`: 原始回调数据（JSON格式）
- `created_at`: 创建时间

**唯一性约束：** `(platform, conversion_id, event_name)` - 防止重复处理

## 三、API 接口

### 1. 接收 Postback 回调

#### 统一接口（推荐）

**POST /api/v1/postback/{platform}**
- 支持平台：macan（可扩展）
- 请求体：JSON 格式的 postback 数据

**GET /api/v1/postback/{platform}**
- 支持平台：macan（可扩展）
- 参数：通过查询字符串传递

#### Macan 专用接口（向后兼容）

**POST /api/v1/macan/postback**
**GET /api/v1/macan/postback**

保留原有接口，内部调用统一服务处理。

### 2. 查询转化记录（管理员）

**GET /api/v1/postback/conversions**

查询参数：
- `platform`: 平台名称（可选）
- `product_id`: 产品ID（可选）
- `client_id`: 客户ID（可选）
- `event_name`: 事件名称（可选）
- `start_date`: 起始日期 YYYY-MM-DD（可选）
- `end_date`: 结束日期 YYYY-MM-DD（可选）
- `page`: 页码（默认1）
- `page_size`: 每页数量（默认20，最大100）

### 3. 统计信息（管理员）

**GET /api/v1/postback/stats**

查询参数：
- `platform`: 平台名称（可选）
- `start_date`: 起始日期 YYYY-MM-DD（可选）
- `end_date`: 结束日期 YYYY-MM-DD（可选）

返回各平台的统计信息：
- 总转化数
- 总支付金额
- 总事件价值
- 唯一事件数

## 四、使用示例

### 1. Macan Postback 回调

**POST 方式：**
```bash
curl -X POST "http://your-domain.com/api/v1/postback/macan" \
  -H "Content-Type: application/json" \
  -d '{
    "clk_id": "12345",
    "event_name": "purchase",
    "devad_id": "abc123",
    "event_value": 99.99,
    "payout": 10.5,
    "os": "IOS",
    "carrier": "China Mobile",
    "product_id": 1,
    "client_id": 1
  }'
```

**GET 方式：**
```bash
curl "http://your-domain.com/api/v1/postback/macan?clk_id=12345&event_name=purchase&payout=10.5"
```

### 2. 查询转化记录

```bash
curl "http://your-domain.com/api/v1/postback/conversions?platform=macan&page=1&page_size=20" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 3. 获取统计信息

```bash
curl "http://your-domain.com/api/v1/postback/stats?platform=macan&start_date=2024-01-01&end_date=2024-01-31" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## 五、扩展新平台

要添加新平台的 postback 支持，只需：

1. **创建平台处理器**（继承 `PostbackHandler`）：

```python
# app/core/postback/addermobi_handler.py
from app.core.postback.handlers import PostbackHandler

class AddermobiPostbackHandler(PostbackHandler):
    @property
    def platform_name(self) -> str:
        return "addermobi"
    
    async def validate(self, data: dict) -> tuple[bool, Optional[str]]:
        # 验证逻辑
        pass
    
    async def normalize(self, data: dict) -> dict:
        # 标准化数据
        pass
```

2. **注册处理器**：

```python
# 在 app/api/api_v1/endpoints/postback.py 中
from app.core.postback.addermobi_handler import AddermobiPostbackHandler

addermobi_handler = AddermobiPostbackHandler()
register_handler(addermobi_handler)
```

3. **使用新接口**：

```bash
curl -X POST "http://your-domain.com/api/v1/postback/addermobi" \
  -H "Content-Type: application/json" \
  -d '{...}'
```

## 六、特性

### 1. 防重复处理

通过唯一性约束 `(platform, conversion_id, event_name)` 防止重复处理相同的转化事件。

### 2. 数据完整性

- 保存完整的原始回调数据（JSON格式）
- 自动验证产品和客户（如果提供）
- 自动获取客户端IP地址

### 3. 日志记录

所有 postback 回调都会记录详细日志，包括：
- 请求时间
- 所有参数值
- 处理结果
- 错误信息（如果有）

### 4. Telegram 通知

Macan postback 接口保留 Telegram 通知功能（向后兼容）。

## 七、数据库迁移

需要创建 `postback_conversions` 表。可以使用 Alembic 或直接执行 SQL：

```sql
-- Postback 转化事件表
-- 用于统一存储所有平台的 postback 回调数据
CREATE TABLE postback_conversions (
    -- 主键
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '转化记录ID',
    
    -- 平台和转化信息
    platform VARCHAR(50) NOT NULL COMMENT '平台名称：macan, addermobi等',
    conversion_id VARCHAR(255) NOT NULL COMMENT '转化ID（各平台唯一标识，如Macan的clk_id）',
    event_name VARCHAR(100) COMMENT '事件名称（如purchase, install等）',
    event_value FLOAT COMMENT '事件价值（购买价格等）',
    payout FLOAT COMMENT '支付金额（确认的广告单元价格）',
    
    -- 设备信息
    devad_id VARCHAR(255) COMMENT '设备广告ID（IDFA或GAID）',
    os VARCHAR(20) COMMENT '操作系统（IOS或Android）',
    carrier VARCHAR(50) COMMENT '用户运营商',
    ip VARCHAR(50) COMMENT '点击IP地址',
    gid VARCHAR(100) COMMENT '渠道ID（Channel ID）',
    
    -- 关联信息（可选）
    product_id INT COMMENT '关联的产品ID（可选，用于关联产品）',
    client_id INT COMMENT '关联的客户ID（可选，用于关联客户）',
    
    -- 原始数据
    raw_data TEXT COMMENT '原始回调数据（JSON格式，保存完整回调数据以便后续分析）',
    
    -- 元数据
    created_at DATETIME NOT NULL COMMENT '创建时间（记录回调接收时间）',
    
    -- 索引（优化查询性能）
    INDEX idx_postback_platform_conversion (platform, conversion_id) COMMENT '平台和转化ID复合索引（优化平台查询）',
    INDEX idx_postback_product (product_id) COMMENT '产品ID索引（优化产品关联查询）',
    INDEX idx_postback_client (client_id) COMMENT '客户ID索引（优化客户关联查询）',
    INDEX idx_postback_created_at (created_at) COMMENT '创建时间索引（优化时间范围查询）',
    INDEX idx_postback_platform_event (platform, event_name) COMMENT '平台和事件名称复合索引（优化事件统计查询）',
    
    -- 唯一性约束（防止重复处理相同的转化事件）
    UNIQUE KEY uq_postback_platform_conversion_event (platform, conversion_id, event_name) COMMENT '防止同一平台的同一转化ID和事件名称重复处理',
    
    -- 外键约束（关联产品和客户表）
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL COMMENT '关联产品表，删除产品时设置为NULL',
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL COMMENT '关联客户表，删除客户时设置为NULL'
) COMMENT='Postback转化事件表，统一存储所有平台的postback回调数据';
```

## 八、注意事项

1. **向后兼容**：原有的 `/api/v1/macan/postback` 接口仍然可用，内部调用统一服务
2. **权限控制**：查询和统计接口仅管理员可访问
3. **数据存储**：所有 postback 数据都会存储到数据库，便于后续分析和报表生成
4. **性能优化**：使用数据库索引优化查询性能，支持分页查询

## 九、后续扩展建议

1. **添加更多平台支持**：Addermobi、Skymobi 等
2. **数据分析功能**：转化率分析、ROI 计算等
3. **实时通知**：WebSocket 推送转化事件
4. **数据导出**：Excel/CSV 导出功能
5. **告警机制**：异常转化事件告警

