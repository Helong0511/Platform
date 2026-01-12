# 短链接点击与Postback转发操作原理详解

## 一、完整流程分析

### 1.1 实际案例追踪

根据提供的实际案例，我们来追踪完整的流程：

#### 阶段1：短链接点击

**原始请求URL：**
```
https://client.btfrx.online/s/kDCT?offer_id=10&channel_id=4&click_id=1230180&sub_channel_id={pub_id}
```

**参数分析：**
- `offer_id=10` - 系统必须参数（Offer ID）
- `channel_id=4` - 系统必须参数（渠道ID）
- `click_id=1230180` - **渠道提供的原始click_id**（渠道参数）
- `sub_channel_id={pub_id}` - 渠道参数，但包含占位符，会被过滤掉

**系统处理：**
1. 系统生成新的click_id：`bpt7KMtEX497DrdtKWMPMweTXEYA4wKkpmbhFjHE`
2. 提取渠道参数：
   - `click_id=1230180` → 保存到 `clicks.url_params`
   - `sub_channel_id={pub_id}` → 包含占位符，被过滤掉
3. 替换短链接原始URL中的占位符（如果有）
4. 构建最终跳转URL

**最终跳转URL：**
```
http://keplerads.fuse-ad.com/tl?a=3058&o=7360&aff_click_id=bpt7KMtEX497DrdtKWMPMweTXEYA4wKkpmbhFjHE&sub_affid=4
```

**关键点：**
- `aff_click_id` 使用的是**系统生成的click_id**（`bpt7KMtEX497DrdtKWMPMweTXEYA4wKkpmbhFjHE`）
- `sub_affid` 使用的是 `channel_id` 的值（`4`）
- 渠道提供的原始 `click_id=1230180` 被保存到数据库的 `clicks.url_params` 字段

#### 阶段2：转化发生（Postback接收）

**广告主回调：**
```
click_id=bpt7KMtEX497DrdtKWMPMweTXEYA4wKkpmbhFjHE&payout=2.80
```

**系统处理：**
1. 使用系统生成的click_id（`bpt7KMtEX497DrdtKWMPMweTXEYA4wKkpmbhFjHE`）查找Click记录
2. 从Click记录中获取 `url_params`：
   ```json
   {
     "click_id": "1230180"
   }
   ```
3. 接收原始金额：`2.80`
4. 应用扣量逻辑：`2.80` → `2.42`（扣减了约13.6%）

#### 阶段3：转发给渠道

**渠道Postback URL配置：**
```
https://www.qqpqq.com/back/p_back?m=tp&c_id={click_id}&payout={payout}
```

**系统处理：**
1. 替换URL占位符：
   - `{click_id}` → 从 `click_params` 中获取渠道提供的原始click_id（`1230180`）
   - `{payout}` → 使用扣减后的金额（`2.42`）

**最终转发URL：**
```
https://www.qqpqq.com/back/p_back?m=tp&c_id=1230180&payout=2.42
```

**关键点：**
- `c_id` 使用的是**渠道提供的原始click_id**（`1230180`），而不是系统生成的click_id
- `payout` 使用的是**扣减后的金额**（`2.42`），而不是原始金额（`2.80`）

## 二、核心操作原理

### 2.1 Click ID的双重身份

系统中有两种click_id：

#### 1. 系统生成的click_id
- **用途：**
  - 用于替换短链接原始URL中的占位符（如 `{click_id}`, `{aff_click_id}`）
  - 用于关联Click记录和转化记录
  - 存储在 `clicks.click_id` 字段
  - 传递给广告主（在最终跳转URL中）

- **特点：**
  - 系统自动生成，唯一标识
  - 格式：随机字符串（如 `bpt7KMtEX497DrdtKWMPMweTXEYA4wKkpmbhFjHE`）
  - 用于系统内部追踪

#### 2. 渠道提供的原始click_id
- **用途：**
  - 保存在 `clicks.url_params` 字段（JSON格式）
  - 用于转化时转发给渠道
  - 渠道用于识别自己的点击记录

- **特点：**
  - 由渠道在短链接URL中提供
  - 格式：渠道自定义（如 `1230180`）
  - 用于渠道内部追踪

### 2.2 参数处理流程

#### 短链接点击时的参数分类

```python
# 系统必须参数（System Required Parameters）
- offer_id: 必须，用于识别Offer
- channel_id: 必须，用于识别渠道

# 渠道参数（Channel Parameters）
- click_id: 渠道提供的原始click_id
- sub_channel_id: 子渠道ID
- 其他渠道自定义参数...
```

#### 参数保存逻辑

```python
# 1. 提取渠道参数（排除系统参数和占位符）
channel_params = {
    "click_id": "1230180",  # 渠道提供的原始click_id
    # sub_channel_id={pub_id} 被过滤掉（包含占位符）
}

# 2. 保存到 clicks.url_params（JSON格式）
clicks.url_params = json.dumps(channel_params)
```

**代码位置：** `app/routes/short_link_redirect.py`
- `_extract_and_filter_channel_params()` - 提取并过滤渠道参数
- `_create_click_record()` - 创建点击记录，保存url_params

### 2.3 占位符替换机制

#### 短链接跳转时的占位符替换

**原始URL模板：**
```
http://keplerads.fuse-ad.com/tl?a=3058&o=7360&aff_click_id={click_id}&sub_affid={channel_id}
```

**替换后：**
```
http://keplerads.fuse-ad.com/tl?a=3058&o=7360&aff_click_id=bpt7KMtEX497DrdtKWMPMweTXEYA4wKkpmbhFjHE&sub_affid=4
```

**替换规则：**
- `{click_id}` → 系统生成的click_id
- `{channel_id}` → channel_id参数值

**代码位置：** `app/routes/short_link_redirect.py`
- `_replace_short_link_placeholders()` - 替换短链接URL中的占位符

#### Postback转发时的占位符替换

**渠道Postback URL模板：**
```
https://www.qqpqq.com/back/p_back?m=tp&c_id={click_id}&payout={payout}
```

**替换后：**
```
https://www.qqpqq.com/back/p_back?m=tp&c_id=1230180&payout=2.42
```

**替换规则：**
- `{click_id}` → **从click_params中获取渠道提供的原始click_id**
- `{payout}` → 扣减后的金额

**关键代码逻辑：**

```python
# 1. 获取click_params（从clicks.url_params解析）
click_params = json.loads(click_record.url_params)
# 结果: {"click_id": "1230180"}

# 2. 构建转发数据
forward_data = {
    "click_id": "1230180",  # 优先使用click_params中的click_id
    "payout": 2.42  # 扣减后的金额
}

# 3. 替换URL占位符
# 对于 {click_id}，会从forward_data中获取，即渠道提供的原始click_id
```

**代码位置：** `app/core/postback/forwarder.py`
- `_replace_url_placeholders()` - 替换Postback URL中的占位符
- `_build_forward_data()` - 构建转发数据，优先使用click_params中的click_id

### 2.4 扣量扣价机制

#### 扣量流程

```
原始金额 (original_payout): 2.80
    ↓
应用扣量逻辑
    ↓
扣减后金额 (payout): 2.42
```

**扣量类型：**
1. **按比例扣减**：`扣减金额 = 原始金额 × (扣减比例 / 100)`
2. **按固定金额扣减**：`扣减金额 = 固定扣减金额`

**扣量优先级：**
1. Offer级别扣量配置（优先级最高）
2. Channel级别扣量配置
3. 渠道默认扣量（Publisher表的price_discount字段）

**代码位置：** `app/core/postback/processor.py`
- `calculate_discount()` - 计算扣量
- `DeductionManager` - 新的扣减逻辑（按比例扣量和扣金额）

#### 转发时的金额使用

**转发给渠道的金额：**
- 使用 `conversion.payout`（扣减后的金额）
- 而不是 `conversion.original_payout`（原始金额）

**代码位置：** `app/core/postback/forwarder.py`
```python
# 在 _replace_url_placeholders() 中
if conversion.payout is not None:
    values['payout'] = str(conversion.payout)  # 使用扣减后的金额
```

## 三、关键代码逻辑对比

### 3.1 短链接点击处理

**文件：** `app/routes/short_link_redirect.py`

**关键函数：**
1. `_extract_and_filter_channel_params()` - 提取渠道参数
   - 排除系统参数（offer_id, channel_id）
   - 过滤包含占位符的参数

2. `_replace_short_link_placeholders()` - 替换占位符
   - 使用系统生成的click_id替换 `{click_id}`
   - 使用channel_id替换 `{channel_id}`

3. `_create_click_record()` - 创建点击记录
   - 保存系统生成的click_id到 `clicks.click_id`
   - 保存渠道参数到 `clicks.url_params`（JSON格式）

### 3.2 Postback转发处理

**文件：** `app/core/postback/forwarder.py`

**关键函数：**
1. `forward_to_publisher()` - 转发给渠道
   - 通过系统生成的click_id查找Click记录
   - 从 `clicks.url_params` 解析渠道参数

2. `_build_forward_data()` - 构建转发数据
   ```python
   # 特别处理：优先使用渠道提供的click_id
   if click_params and 'click_id' in click_params:
       data['click_id'] = click_params['click_id']  # 渠道提供的原始click_id
   ```

3. `_replace_url_placeholders()` - 替换URL占位符
   ```python
   # 从conversion中获取click_id（系统生成的）
   values['click_id'] = conversion.click_id
   
   # 但是，在GET请求中，forward_data中的click_id会覆盖URL参数
   # 所以最终使用的是渠道提供的click_id
   ```

**注意：** 对于GET请求，`_forward_get()`会将`forward_data`中的参数合并到URL中，所以最终URL中的`click_id`参数是渠道提供的原始click_id。

## 四、数据流转图

```
┌─────────────────────────────────────────────────────────────┐
│ 阶段1：短链接点击                                            │
└─────────────────────────────────────────────────────────────┘
                    ↓
渠道请求: /s/kDCT?offer_id=10&channel_id=4&click_id=1230180
                    ↓
系统生成click_id: bpt7KMtEX497DrdtKWMPMweTXEYA4wKkpmbhFjHE
                    ↓
保存到数据库:
- clicks.click_id = "bpt7KMtEX497DrdtKWMPMweTXEYA4wKkpmbhFjHE"
- clicks.url_params = '{"click_id": "1230180"}'
                    ↓
跳转到广告主:
http://keplerads.fuse-ad.com/tl?aff_click_id=bpt7KMtEX497DrdtKWMPMweTXEYA4wKkpmbhFjHE

┌─────────────────────────────────────────────────────────────┐
│ 阶段2：转化发生（Postback接收）                               │
└─────────────────────────────────────────────────────────────┘
                    ↓
广告主回调: click_id=bpt7KMtEX497DrdtKWMPMweTXEYA4wKkpmbhFjHE&payout=2.80
                    ↓
查找Click记录（通过系统生成的click_id）
                    ↓
解析url_params: {"click_id": "1230180"}
                    ↓
应用扣量: 2.80 → 2.42
                    ↓
保存转化记录:
- conversion.click_id = "bpt7KMtEX497DrdtKWMPMweTXEYA4wKkpmbhFjHE"
- conversion.original_payout = 2.80
- conversion.payout = 2.42

┌─────────────────────────────────────────────────────────────┐
│ 阶段3：转发给渠道                                            │
└─────────────────────────────────────────────────────────────┘
                    ↓
渠道Postback URL: https://www.qqpqq.com/back/p_back?c_id={click_id}&payout={payout}
                    ↓
替换占位符:
- {click_id} → 从click_params获取: "1230180"
- {payout} → 从conversion.payout获取: "2.42"
                    ↓
最终转发URL:
https://www.qqpqq.com/back/p_back?c_id=1230180&payout=2.42
```

## 五、核心规律总结

### 5.1 Click ID映射规律

| 阶段 | 使用的Click ID | 来源 | 用途 |
|------|---------------|------|------|
| **短链接跳转** | 系统生成的click_id | `clicks.click_id` | 传递给广告主，用于追踪 |
| **Postback接收** | 系统生成的click_id | `conversion.click_id` | 查找Click记录 |
| **转发给渠道** | 渠道提供的原始click_id | `clicks.url_params` | 渠道用于识别自己的点击 |

### 5.2 金额处理规律

| 阶段 | 金额类型 | 字段 | 用途 |
|------|---------|------|------|
| **Postback接收** | 原始金额 | `conversion.original_payout` | 广告主提供的原始金额 |
| **扣量处理** | 扣减后金额 | `conversion.payout` | 系统计算的扣减后金额 |
| **转发给渠道** | 扣减后金额 | `conversion.payout` | 实际支付给渠道的金额 |

### 5.3 参数处理规律

1. **系统参数**（offer_id, channel_id）
   - 不保存到 `url_params`
   - 用于系统内部处理

2. **渠道参数**（click_id, sub_channel_id等）
   - 保存到 `url_params`（JSON格式）
   - 用于转发给渠道

3. **占位符参数**
   - 在渠道参数中：被过滤掉，不保存
   - 在URL模板中：被替换为实际值

## 六、与项目代码逻辑的对比验证

### 6.1 短链接点击处理验证

**代码位置：** `app/routes/short_link_redirect.py:60-103`

```python
def _extract_and_filter_channel_params(request_params: dict) -> dict:
    """
    提取并过滤渠道参数
    - 排除系统参数（offer_id, channel_id）
    - 过滤包含占位符的参数
    """
    excluded_params = {'offer_id', 'channel_id', 'publisher_id'}
    # 过滤逻辑...
```

**验证结果：** ✅ 符合实际案例
- `click_id=1230180` 被提取为渠道参数
- `sub_channel_id={pub_id}` 被过滤掉（包含占位符）

### 6.2 Postback转发处理验证

**代码位置：** `app/core/postback/forwarder.py:629-639`

```python
# 特别处理：如果click_params中有click_id（渠道提供的），确保添加到转发数据中
if click_params and 'click_id' in click_params:
    click_id_value = click_params['click_id']
    if click_id_value:
        # 使用渠道提供的click_id，而不是系统生成的click_id
        data['click_id'] = click_id_value
```

**验证结果：** ✅ 符合实际案例
- URL中的 `{click_id}` 被替换为渠道提供的原始click_id（`1230180`）

### 6.3 扣量处理验证

**代码位置：** `app/core/postback/processor.py:330-396`

```python
# 计算扣量
final_payout, discount_amount, discount_info = await calculate_discount(
    db=db,
    offer_id=offer_id,
    publisher_id=publisher_id,
    original_payout=final_payout
)
```

**验证结果：** ✅ 符合实际案例
- 原始金额：2.80
- 扣减后金额：2.42（扣减了约13.6%）

### 6.4 URL占位符替换验证

**代码位置：** `app/core/postback/forwarder.py:957-965`

```python
# payout 使用扣后的 payout（给下游的实际金额）
if conversion.payout is not None:
    values['payout'] = str(conversion.payout)
```

**验证结果：** ✅ 符合实际案例
- URL中的 `{payout}` 被替换为扣减后的金额（`2.42`）

## 七、总结

### 7.1 核心原理

1. **Click ID的双重身份**
   - 系统生成的click_id：用于系统内部追踪和传递给广告主
   - 渠道提供的原始click_id：保存在url_params中，用于转发给渠道

2. **参数分离机制**
   - 系统参数：不保存到url_params，用于系统处理
   - 渠道参数：保存到url_params，用于转发给渠道

3. **占位符替换机制**
   - 短链接跳转：使用系统生成的click_id替换占位符
   - Postback转发：使用渠道提供的原始click_id替换占位符

4. **扣量扣价机制**
   - 接收原始金额，应用扣量逻辑，转发扣减后的金额

### 7.2 关键设计点

1. **数据隔离**
   - 系统生成的click_id和渠道提供的click_id分开存储和使用
   - 避免混淆，保证数据准确性

2. **参数传递**
   - 通过url_params保存渠道参数，实现参数透传
   - 支持渠道自定义参数，提高灵活性

3. **金额处理**
   - 原始金额和扣减后金额分开存储
   - 转发时使用扣减后的金额，保证利润控制

4. **占位符机制**
   - 支持URL模板配置，提高配置灵活性
   - 自动替换占位符，减少手动配置错误

### 7.3 实际应用价值

1. **追踪准确性**
   - 系统可以准确追踪每次点击和转化
   - 渠道可以识别自己的点击记录

2. **利润控制**
   - 通过扣量机制控制成本
   - 保证系统利润空间

3. **配置灵活性**
   - 支持渠道自定义参数
   - 支持URL模板配置

4. **数据完整性**
   - 保存原始金额和扣减后金额
   - 便于数据分析和审计
