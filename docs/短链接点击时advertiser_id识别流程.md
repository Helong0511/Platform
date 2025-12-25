# 短链接点击时 advertiser_id 识别流程详解

## 一、数据模型关系

### 1.1 数据库表结构

```
advertisers (广告主表)
  ├── id (主键)
  └── advertiser_name

offers (Offer表)
  ├── id (主键)
  ├── advertiser_id (外键 → advertisers.id) ⭐ 关键字段
  └── offer_name

clicks (点击记录表)
  ├── id (主键)
  ├── offer_id (外键 → offers.id)
  ├── advertiser_id (外键 → advertisers.id) ⭐ 需要填充的字段
  └── publisher_id (外键 → publishers.id)
```

### 1.2 数据关系链

```
URL参数: offer_id
    ↓
查询 offers 表 (WHERE id = offer_id)
    ↓
获取 Offer 对象
    ↓
读取 Offer.advertiser_id 字段
    ↓
保存到 clicks.advertiser_id
```

---

## 二、识别流程详解

### 2.1 完整流程步骤

#### 步骤1：接收短链接点击请求

**URL示例**：
```
https://client.btfrx.online/s/aNyj?offer_id=1&channel_id=101
```

**代码位置**：
- `app/main.py` - `/s/{short_code}` 路由（主路由）
- `app/api/api_v1/endpoints/short_links.py` - `/api/v1/short-links/{short_code}` 路由（API路由）

**提取参数**：
```python
offer_id: Optional[int] = Query(None, description="Offer ID（从URL参数获取）")
channel_id: Optional[int] = Query(None, description="渠道ID（从URL参数获取）")
```

---

#### 步骤2：检查是否有 offer_id 参数

**代码逻辑**：
```python
# 只使用URL参数中的offer_id（如果有的话）
final_offer_id = offer_id  # 只使用URL参数

# 如果URL参数中没有offer_id，则不保存
if final_offer_id:
    # 继续处理...
else:
    advertiser_id = None  # 没有offer_id，无法获取advertiser_id
```

**关键点**：
- ✅ 只有当URL参数中存在 `offer_id` 时，才会尝试获取 `advertiser_id`
- ❌ 如果URL参数中没有 `offer_id`，`advertiser_id` 将保存为 `None`

---

#### 步骤3：查询 Offer 表获取 advertiser_id

**代码位置**：
- `app/main.py` (缓存路径和数据库路径)
- `app/api/api_v1/endpoints/short_links.py`

**查询代码**：
```python
if final_offer_id:
    try:
        from app.models.models import Offer
        offer_result = await db.execute(
            select(Offer).where(Offer.id == final_offer_id)
        )
        offer = offer_result.scalars().first()
        if offer:
            advertiser_id = offer.advertiser_id  # ⭐ 从Offer对象中获取advertiser_id
        else:
            # Offer不存在，advertiser_id保持为None
            logger.warning(f"短链接点击时提供的offer_id无效: offer_id={final_offer_id}")
    except Exception as e:
        logger.warning(f"查询Offer失败: offer_id={final_offer_id}, error={e}")
        advertiser_id = None
```

**SQL查询**：
```sql
SELECT * FROM offers WHERE id = {final_offer_id}
```

**数据来源**：
- `offers` 表中的 `advertiser_id` 字段
- 该字段是外键，关联到 `advertisers` 表的 `id`

---

#### 步骤4：保存到 clicks 表

**代码位置**：
- `app/main.py` (缓存路径和数据库路径)
- `app/api/api_v1/endpoints/short_links.py`

**保存代码**：
```python
click_data = {
    "click_id": click_id,
    "short_link_id": short_link_id,
    "offer_id": final_offer_id,        # 从URL参数获取
    "publisher_id": final_channel_id,   # 从URL参数获取（对应channel_id）
    "advertiser_id": advertiser_id,     # ⭐ 从Offer对象获取
    "click_time": datetime.now(timezone.utc),
    "ip": client_ip,
    "user_agent": user_agent,
    "referer": referer,
    "country": None
}

# 异步保存到数据库
background_tasks.add_task(create_click_background, click_data)
```

**数据库插入**：
```sql
INSERT INTO clicks (
    click_id,
    short_link_id,
    offer_id,
    publisher_id,
    advertiser_id,  -- ⭐ 这里保存从Offer获取的advertiser_id
    click_time,
    ip,
    user_agent,
    referer,
    country
) VALUES (...)
```

---

## 三、数据流转示例

### 示例1：正常情况（有offer_id参数）

**请求URL**：
```
https://client.btfrx.online/s/aNyj?offer_id=1&channel_id=101
```

**流程**：
1. 提取参数：`offer_id = 1`, `channel_id = 101`
2. 查询数据库：
   ```sql
   SELECT * FROM offers WHERE id = 1
   ```
3. 获取Offer对象：
   ```python
   offer = {
       "id": 1,
       "offer_name": "Test Offer",
       "advertiser_id": 5,  # ⭐ 从数据库读取
       ...
   }
   ```
4. 提取advertiser_id：
   ```python
   advertiser_id = offer.advertiser_id  # = 5
   ```
5. 保存到clicks表：
   ```python
   {
       "offer_id": 1,
       "publisher_id": 101,
       "advertiser_id": 5,  # ⭐ 成功获取并保存
       ...
   }
   ```

---

### 示例2：没有offer_id参数

**请求URL**：
```
https://client.btfrx.online/s/aNyj
```

**流程**：
1. 提取参数：`offer_id = None`, `channel_id = None`
2. 跳过Offer查询（因为没有offer_id）
3. 保存到clicks表：
   ```python
   {
       "offer_id": None,
       "publisher_id": None,
       "advertiser_id": None,  # ⭐ 没有offer_id，无法获取advertiser_id
       ...
   }
   ```

---

### 示例3：offer_id无效

**请求URL**：
```
https://client.btfrx.online/s/aNyj?offer_id=99999&channel_id=101
```

**流程**：
1. 提取参数：`offer_id = 99999`, `channel_id = 101`
2. 查询数据库：
   ```sql
   SELECT * FROM offers WHERE id = 99999
   ```
3. 查询结果：`offer = None`（Offer不存在）
4. 记录警告日志：
   ```python
   logger.warning("短链接点击时提供的offer_id无效: offer_id=99999")
   ```
5. 保存到clicks表：
   ```python
   {
       "offer_id": 99999,
       "publisher_id": 101,
       "advertiser_id": None,  # ⭐ Offer不存在，无法获取advertiser_id
       ...
   }
   ```

---

## 四、代码位置汇总

### 4.1 主路由（app/main.py）

**路由**：`/s/{short_code}`

**两个处理路径**：

1. **缓存路径**（第1051-1100行）：
   - 从Redis缓存获取短链接数据
   - 如果缓存中有数据，使用缓存路径
   - 代码位置：`app/main.py:1056-1068`

2. **数据库路径**（第1221-1250行）：
   - 缓存未命中，从数据库查询短链接
   - 代码位置：`app/main.py:1226-1238`

---

### 4.2 API路由（app/api/api_v1/endpoints/short_links.py）

**路由**：`/api/v1/short-links/{short_code}`

**代码位置**：第174-191行

---

## 五、关键代码片段

### 5.1 Offer模型定义

**文件**：`app/models/models.py`

```python
class Offer(Base):
    __tablename__ = "offers"
    
    id = Column(Integer, primary_key=True, ...)
    advertiser_id = Column(
        Integer, 
        ForeignKey("advertisers.id", ondelete="RESTRICT"), 
        nullable=False, 
        index=True, 
        comment='关联的广告主ID'
    )  # ⭐ 关键字段：每个Offer都关联一个Advertiser
```

**说明**：
- `advertiser_id` 是必填字段（`nullable=False`）
- 外键约束：关联到 `advertisers` 表
- 有索引，查询速度快

---

### 5.2 查询和提取逻辑

```python
# 1. 检查是否有offer_id参数
final_offer_id = offer_id  # 只使用URL参数

# 2. 如果有offer_id，查询Offer
advertiser_id = None
if final_offer_id:
    offer_result = await db.execute(
        select(Offer).where(Offer.id == final_offer_id)
    )
    offer = offer_result.scalars().first()
    
    # 3. 如果Offer存在，提取advertiser_id
    if offer:
        advertiser_id = offer.advertiser_id  # ⭐ 关键：从Offer对象获取
```

---

### 5.3 保存到clicks表

```python
click_data = {
    "click_id": click_id,
    "short_link_id": short_link_id,
    "offer_id": final_offer_id,        # 从URL参数
    "publisher_id": final_channel_id,   # 从URL参数
    "advertiser_id": advertiser_id,     # ⭐ 从Offer对象获取
    ...
}
```

---

## 六、数据验证和错误处理

### 6.1 验证流程

1. **参数验证**：
   - 检查URL参数中是否有 `offer_id`
   - 如果没有，`advertiser_id` 为 `None`

2. **Offer存在性验证**：
   - 查询数据库验证 `offer_id` 是否存在
   - 如果不存在，记录警告日志，`advertiser_id` 为 `None`

3. **数据完整性**：
   - Offer表中的 `advertiser_id` 是必填字段
   - 如果Offer存在，`advertiser_id` 一定存在

---

### 6.2 错误处理

**情况1：Offer不存在**
```python
if offer:
    advertiser_id = offer.advertiser_id
else:
    logger.warning(f"短链接点击时提供的offer_id无效: offer_id={final_offer_id}")
    advertiser_id = None  # 保存为None
```

**情况2：数据库查询异常**
```python
try:
    offer_result = await db.execute(...)
    offer = offer_result.scalars().first()
    if offer:
        advertiser_id = offer.advertiser_id
except Exception as e:
    logger.warning(f"查询Offer失败: offer_id={final_offer_id}, error={e}")
    advertiser_id = None  # 异常时保存为None
```

---

## 七、日志输出

### 7.1 参数信息日志

**代码位置**：所有三个路由都有日志输出

**日志内容**：
```
[短链接点击] 参数信息: 
    short_code=aNyj, 
    URL参数_offer_id=1, 
    URL参数_channel_id=101, 
    最终保存_offer_id=1, 
    最终保存_channel_id=101, 
    advertiser_id=5
```

---

### 7.2 Offer信息日志

**代码位置**：`app/api/api_v1/endpoints/short_links.py`

**日志内容**：
```
[短链接点击] Offer信息: 
    offer_id=1, 
    offer_name=Test Offer, 
    advertiser_id=5
```

---

## 八、总结

### 8.1 advertiser_id 识别流程

1. **前提条件**：URL参数中必须有 `offer_id`
2. **查询步骤**：根据 `offer_id` 查询 `offers` 表
3. **提取步骤**：从Offer对象的 `advertiser_id` 字段获取
4. **保存步骤**：将 `advertiser_id` 保存到 `clicks` 表

### 8.2 数据来源

- **直接来源**：`offers` 表的 `advertiser_id` 字段
- **间接来源**：`advertisers` 表（通过外键关联）
- **获取方式**：通过 `offer_id` 查询 `offers` 表获取

### 8.3 关键点

- ✅ 只有当URL参数中有 `offer_id` 时，才会获取 `advertiser_id`
- ✅ `advertiser_id` 是从Offer对象中读取的，不是从URL参数直接获取
- ✅ 如果Offer不存在或查询失败，`advertiser_id` 保存为 `None`
- ✅ 所有操作都是异步的，不阻塞短链接重定向

---

## 九、数据流程图

```
用户点击短链接
    ↓
URL: /s/aNyj?offer_id=1&channel_id=101
    ↓
提取URL参数: offer_id=1, channel_id=101
    ↓
检查: offer_id 是否存在？
    ├─ 是 → 查询 offers 表 (WHERE id = 1)
    │         ↓
    │      获取 Offer 对象
    │         ↓
    │      读取 Offer.advertiser_id = 5
    │         ↓
    │      保存到 clicks.advertiser_id = 5 ✅
    │
    └─ 否 → advertiser_id = None
              ↓
           保存到 clicks.advertiser_id = None
```

---

## 十、相关代码文件

1. **主路由**：`app/main.py` (第1051-1100行, 1221-1250行)
2. **API路由**：`app/api/api_v1/endpoints/short_links.py` (第174-191行)
3. **数据模型**：`app/models/models.py` (第636-674行)
4. **后台任务**：`app/api/api_v1/endpoints/tracking.py` (第29-63行)

