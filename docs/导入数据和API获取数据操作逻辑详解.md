# 导入数据和API获取数据操作逻辑详解

本文档详细说明系统中**Excel导入数据**和**API获取数据**的完整操作逻辑。

---

## 一、Excel导入数据操作逻辑

### 1.1 API端点

- **路由**: `POST /api/v1/excel/import/ad-data`
- **权限**: 仅管理员可访问（`require_admin`）
- **参数**:
  - `file`: Excel文件（.xlsx或.xls格式）
  - `client_id` (可选): 指定客户ID，覆盖Excel中的客户信息

### 1.2 导入流程概览

```
上传Excel文件
    ↓
文件验证（类型、大小、格式）
    ↓
读取Excel内容（pandas DataFrame）
    ↓
列名映射处理（智能识别Excel列名）
    ↓
数据验证（必要字段检查）
    ↓
检查Excel内部重复数据
    ↓
构建产品映射表
    ↓
批量预查询数据库中的重复记录
    ↓
逐行处理数据
    ├─ 查找或创建产品
    ├─ 计算扣减后的值
    ├─ 检查数据库重复
    └─ 插入新记录或更新现有记录
    ↓
提交事务
    ↓
返回导入结果
```

### 1.3 详细步骤说明

#### 步骤1: 文件验证和读取 (`validate_and_read_excel`)

**功能**: 验证Excel文件的有效性并读取内容

**验证项**:
1. **文件类型验证**:
   - 检查MIME类型（`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` 或 `application/vnd.ms-excel`）
   - 检查文件扩展名（.xlsx或.xls）

2. **文件大小验证**:
   - 检查文件大小是否超过限制（`settings.MAX_UPLOAD_SIZE`）
   - 默认限制通常为几十MB

3. **文件格式检测**:
   - 通过文件头（magic bytes）检测文件格式
   - `.xlsx`: ZIP格式（文件头: `PK\x03\x04`）
   - `.xls`: OLE格式（文件头: `\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1`）

4. **读取Excel**:
   - 根据文件格式选择解析引擎（`openpyxl` 或 `xlrd`）
   - 使用pandas读取为DataFrame
   - 如果第一次尝试失败，自动尝试另一个引擎

**返回**: `(DataFrame, 文件内容bytes)`

---

#### 步骤2: 列名映射处理 (`process_column_mapping`)

**功能**: 智能识别Excel列名并映射到数据库字段

**处理流程**:

1. **列名规范化**:
   - 去除空格、转换为小写、统一格式
   - 例如: "日期" → "日期", "Date" → "date"

2. **智能列名映射**:
   - 使用`ColumnMappingService.smart_column_mapping()`进行映射
   - **基于训练数据**进行相似度匹配（相似度阈值：60%）
   - 支持多种匹配方式：
     - 精确匹配
     - 模糊匹配（相似度计算）
     - 规则匹配（基于历史训练数据）

3. **映射验证**:
   - 检查映射是否完整（`mapping_complete`）
   - 必要字段必须全部映射成功：
     - `date` (日期)
     - `product_name` (产品名称)
     - `request_count` (请求数)
     - `match_count` (匹配数)
     - `display_count` (展示数)
     - `click_count` (点击数)
     - `revenue_before_deduct` (扣减前收益)
   - 可选字段（如果不存在会自动计算）：
     - `coverage_rate` (覆盖率)
     - `display_rate` (展示率)
     - `click_rate` (点击率)
     - `ecpm_before_deduct` (扣减前eCPM)

4. **应用映射**:
   - 将Excel列名重命名为数据库字段名
   - 例如: "日期" → "date", "产品名称" → "product_name"

5. **计算缺失字段**:
   - 如果Excel中没有比率字段，使用`calculate_rates()`自动计算：
     - `coverage_rate = match_count / request_count * 100`
     - `display_rate = display_count / match_count * 100`
     - `click_rate = click_count / display_count * 100`
     - `ecpm_before_deduct = revenue_before_deduct / display_count * 1000`

**重要规则**:
- **规则2**: 如果字段映射不完整，**拒绝导入**，并返回详细错误信息
- 系统完全基于训练数据进行智能识别，无法识别的列将不导入
- 如果映射完整但产品不存在，可以自动创建产品

**返回**: `(处理后的DataFrame, 映射结果字典)`

---

#### 步骤3: Excel内部重复检查 (`check_excel_duplicates`)

**功能**: 检查Excel文件中是否存在重复数据（相同日期+产品名称）

**处理逻辑**:
- 遍历所有行，按`(日期, 产品名称)`分组
- 如果同一组合出现多次，标记为重复
- **处理策略**: 只保留最后一行，跳过前面的重复行

**返回**: 重复数据映射 `{(日期, 产品名称): [行号列表]}`

---

#### 步骤4: 构建产品映射表 (`build_product_maps`)

**功能**: 预加载所有产品信息，构建快速查找映射

**构建两个映射表**:

1. **product_map**: `{f"{client_id}_{product_name}": 产品信息}`
   - 用于精确匹配（客户ID + 产品名称）

2. **product_name_map**: `{product_name: [产品信息列表]}`
   - 用于按产品名称查找（可能一个产品名称对应多个客户）

**产品信息包含**:
- `product_id`: 产品ID
- `client_id`: 客户ID
- `client_name`: 客户名称
- `product_name`: 产品名称
- `ecpm_deduct_ratio`: eCPM扣减比例
- `revenue_deduct_ratio`: 收益扣减比例

---

#### 步骤5: 批量预查询重复记录

**功能**: 优化性能，批量查询数据库中可能重复的记录

**处理逻辑**:
1. 收集所有需要检查的`(日期, 产品ID)`组合
2. 构建批量查询条件（使用`OR`连接多个条件）
3. 一次性查询所有可能重复的记录
4. 构建缓存映射: `{(日期, 产品ID): AdData对象}`

**优化效果**: 避免在逐行处理时重复查询数据库（N+1查询问题）

---

#### 步骤6: 逐行处理数据 (`process_row_data`)

**功能**: 处理单行Excel数据，插入或更新数据库

**处理流程**:

1. **解析日期**:
   - 使用`parse_date_value()`解析日期值
   - 支持多种日期格式（字符串、datetime对象等）
   - Excel导入的日期默认是系统时区，不需要转换

2. **获取产品名称**:
   - 从Excel行中提取产品名称
   - 验证产品名称不为空

3. **查找或创建产品** (`find_or_create_product`):
   
   这是导入流程中最复杂的逻辑之一，详细说明见下方"查找或创建产品详细说明"章节。

4. **解析数值字段**:
   - `request_count`, `match_count`, `display_count`, `click_count`
   - `revenue_before_deduct`
   - 比率字段（优先使用Excel中的值，如果不存在则计算）

5. **数据验证**:
   - 验证数值非负
   - 验证数值类型正确

6. **计算扣减后的值**:
   - `ecpm_after_deduct = ecpm_before_deduct * (1 - ecpm_deduct_ratio)`
   - `revenue_after_deduct = revenue_before_deduct * (1 - revenue_deduct_ratio)`

7. **检查数据库重复**:
   - 使用预查询的缓存或单独查询
   - 检查是否存在相同`(日期, 产品ID)`的记录

8. **插入或更新**:
   - **如果存在**: 更新现有记录的所有字段
   - **如果不存在**: 创建新记录
   - 将新创建的记录添加到缓存中（避免同一批数据中的重复）

9. **错误处理**:
   - 捕获所有异常，记录到`result["errors"]`
   - 继续处理下一行，不中断整个导入流程

---

#### 步骤7: 提交事务

**功能**: 将所有更改提交到数据库

**处理逻辑**:
1. 执行`await db.commit()`
2. 如果发生`IntegrityError`（唯一性约束违反）:
   - 回滚事务
   - 返回友好的错误信息（可能是并发导入导致的重复）
3. 其他异常也会回滚并返回错误信息

---

#### 步骤8: 构建响应

**响应内容** (`ExcelImportResponse`):
- `message`: 导入结果摘要
- `status`: HTTP状态码（200）
- `imported_rows`: 成功导入的行数
- `failed_rows`: 失败的行数
- `new_rows`: 新增的行数
- `updated_rows`: 更新的行数
- `duplicate_rows`: Excel内部重复的行数
- `error_details`: 错误详情列表（如果有）

---

### 1.4 查找或创建产品详细说明

`find_or_create_product` 函数是导入流程中的核心逻辑，负责智能查找现有产品或创建新产品。以下是完整的处理流程和决策树。

#### 1.4.1 函数签名和参数

```python
async def find_or_create_product(
    product_name: str,              # 产品名称（从Excel中提取）
    target_client_id: int | None,   # Excel中的客户ID（如果存在）
    client_id: int | None,          # 查询参数指定的客户ID（优先级最高）
    mapping_complete: bool,          # 列名映射是否完整
    product_map: dict,              # 产品映射表 {f"{client_id}_{product_name}": 产品信息}
    product_name_map: dict,         # 产品名称映射表 {product_name: [产品信息列表]}
    db: AsyncSession,               # 数据库会话
    current_user: User             # 当前用户（管理员）
) -> dict[str, Any]                 # 返回产品信息字典
```

**参数优先级**:
- `client_id` (查询参数) > `target_client_id` (Excel中的客户ID)
- 如果两者都存在，优先使用查询参数指定的`client_id`

---

#### 1.4.2 处理流程决策树

```
开始
  ↓
确定目标客户ID（client_id 或 target_client_id）
  ↓
按产品名称查找 (product_name_map.get(product_name))
  ↓
┌─────────────────────────────────────┐
│ 是否找到匹配的产品？                │
└─────────────────────────────────────┘
  │                    │
 是                   否
  ↓                    ↓
┌─────────────┐    ┌──────────────────────────┐
│ 规则1.1     │    │ 规则1.2                  │
│ 找到产品    │    │ 未找到产品               │
└─────────────┘    └──────────────────────────┘
  │                    │
  ↓                    ↓
┌─────────────┐    ┌──────────────────────────┐
│ 匹配数量？  │    │ 映射是否完整？           │
└─────────────┘    └──────────────────────────┘
  │                    │
  │                    │
  ├─ 1个匹配           ├─ 映射完整 → 创建产品
  │   ↓                │   ↓
  │   使用该产品       │   ┌──────────────────────┐
  │   ✅ 返回          │   │ 获取或创建默认客户   │
  │                    │   └──────────────────────┘
  └─ 多个匹配          │       ↓
      ↓                │   ┌──────────────────────┐
  ┌─────────────────┐  │   │ 创建新产品            │
  │ 是否指定client_id?│  │   │ - 扣减比例=0         │
  └─────────────────┘  │   │ - is_active=True     │
      │                │   └──────────────────────┘
      ├─ 是            │       ↓
      │   ↓            │   ┌──────────────────────┐
      │   查找匹配     │   │ 更新映射表            │
      │   ├─ 找到 → 使用│   └──────────────────────┘
      │   └─ 未找到 → 使用第一个（警告）│
      │                │   ✅ 返回
      └─ 否            │
          ↓            │
          使用第一个（警告）│
          ✅ 返回      │
                      │
                      └─ 映射不完整 → ❌ 抛出异常
```

---

#### 1.4.3 规则1.1：产品名称能找到客户

当通过产品名称在`product_name_map`中找到匹配的产品时，进入此分支。

##### 情况1.1.1：唯一匹配（1个产品）

**处理逻辑**:
```python
if len(matches) == 1:
    product_info = matches[0]
    target_client_id = product_info["client_id"]
    # 直接使用该产品，返回产品信息
    return product_info
```

**示例**:
- Excel产品名称: "产品A"
- 数据库中存在: 1个"产品A"（客户ID=1）
- **结果**: 使用该产品，客户ID=1

---

##### 情况1.1.2：多个匹配（多个产品）

当同一个产品名称对应多个客户时，需要智能选择。

**处理逻辑**:

1. **如果指定了`target_client_id`（查询参数或Excel中的客户ID）**:
   ```python
   if target_client_id:
       # 尝试在匹配列表中找到指定客户ID的产品
       matched_product = next(
           (m for m in matches if m["client_id"] == target_client_id), 
           None
       )
       if matched_product:
           # 找到匹配 → 使用该产品
           product_info = matched_product
       else:
           # 未找到匹配 → 使用第一个（记录警告）
           product_info = matches[0]
           target_client_id = product_info["client_id"]
           logger.warning(f"产品名称'{product_name}'对应多个客户，但指定的客户ID {target_client_id} 不匹配，使用第一个匹配的产品")
   ```

2. **如果未指定`target_client_id`**:
   ```python
   else:
       # 使用第一个匹配的产品（记录警告）
       product_info = matches[0]
       target_client_id = product_info["client_id"]
       logger.warning(f"产品名称'{product_name}'对应多个客户: {客户列表}，使用第一个匹配的产品")
   ```

**示例场景**:

**场景A**: 指定了客户ID且匹配成功
- Excel产品名称: "产品A"
- 查询参数: `client_id=2`
- 数据库中存在:
  - "产品A"（客户ID=1）
  - "产品A"（客户ID=2）✅
- **结果**: 使用客户ID=2的产品

**场景B**: 指定了客户ID但未匹配
- Excel产品名称: "产品A"
- 查询参数: `client_id=3`
- 数据库中存在:
  - "产品A"（客户ID=1）
  - "产品A"（客户ID=2）
- **结果**: 使用客户ID=1的产品（第一个），记录警告

**场景C**: 未指定客户ID
- Excel产品名称: "产品A"
- 数据库中存在:
  - "产品A"（客户ID=1）
  - "产品A"（客户ID=2）
- **结果**: 使用客户ID=1的产品（第一个），记录警告

---

#### 1.4.4 规则1.2：产品名称不能找到客户

当通过产品名称在`product_name_map`中**未找到**任何匹配的产品时，进入此分支。

##### 情况1.2.1：映射完整 → 创建产品

**前提条件**: `mapping_complete = True`（列名映射完整）

**处理流程**:

**步骤1: 确定目标客户ID**

```python
# 如果未指定target_client_id，需要获取或创建管理员的默认客户
if not target_client_id:
    # 步骤1.1: 查找管理员的默认客户（"默认客户（导入数据）"）
    admin_client_query = select(Client).where(
        Client.user_id == current_user.id,
        Client.company_name == "默认客户（导入数据）"
    ).limit(1)
    create_client = await db.execute(admin_client_query).scalars().first()
    
    # 步骤1.2: 如果未找到，查找管理员的任意客户
    if not create_client:
        admin_client_query = select(Client).where(
            Client.user_id == current_user.id
        ).limit(1)
        create_client = await db.execute(admin_client_query).scalars().first()
    
    # 步骤1.3: 如果管理员没有任何客户，创建默认客户
    if not create_client:
        client_key = str(uuid.uuid4())  # 生成唯一UUID
        create_client = Client(
            user_id=current_user.id,
            key=client_key,
            company_name="默认客户（导入数据）",
            is_active=True
        )
        db.add(create_client)
        await db.flush()
        await db.refresh(create_client)
        logger.info(f"✅ 已创建管理员的默认客户（ID: {create_client.id}）")
    
    target_client_id = create_client.id
else:
    # 如果指定了target_client_id，验证客户是否存在
    client_result = await db.execute(
        select(Client).where(Client.id == target_client_id)
    )
    create_client = client_result.scalars().first()
    if not create_client:
        raise ValueError(f"客户ID {target_client_id} 不存在")
```

**重要说明：防止重复创建默认客户**

系统有完善的检查机制，**不会重复创建默认客户**：

1. **第一次导入**:
   - 如果管理员没有任何客户 → 创建"默认客户（导入数据）"

2. **第二次导入**:
   - **步骤1.1**会先查找"默认客户（导入数据）"
   - 如果找到（第一次已创建）→ **直接使用，不会重复创建** ✅
   - 如果未找到，但管理员有其他客户 → 使用其他客户，不会创建默认客户
   - 只有在管理员确实没有任何客户时，才会创建默认客户

3. **检查逻辑**:
   ```
   步骤1.1: 查找"默认客户（导入数据）" → 找到 → 使用 ✅
            ↓ 未找到
   步骤1.2: 查找管理员的任意客户 → 找到 → 使用
            ↓ 未找到
   步骤1.3: 创建"默认客户（导入数据）"
   ```

**结论**: 第二次及后续导入时，如果第一次已经创建了默认客户，系统会直接使用它，**不会重复创建**。

**步骤2: 创建新产品**

```python
new_product = Product(
    client_id=target_client_id,
    name=product_name,
    ecpm_deduct_ratio=0.0,      # 新建产品默认不扣减
    revenue_deduct_ratio=0.0,   # 新建产品默认不扣减
    is_active=True
)
db.add(new_product)
await db.flush()  # 刷新以获取产品ID
await db.refresh(new_product)
```

**步骤3: 构建产品信息并更新映射表**

```python
product_info = {
    "product_id": new_product.id,
    "client_id": target_client_id,
    "client_name": create_client.company_name,
    "product_name": product_name,
    "ecpm_deduct_ratio": 0.0,
    "revenue_deduct_ratio": 0.0
}

# 更新映射表（供后续行使用）
key = f"{target_client_id}_{product_name}"
product_map[key] = product_info
product_name_map[product_name] = [product_info]
```

**重要特性**:
- ✅ **自动创建默认客户**: 如果管理员没有任何客户，自动创建"默认客户（导入数据）"
- ✅ **默认扣减比例为0**: 新建产品不扣减，后续可手动修改
- ✅ **更新映射表**: 新创建的产品会立即添加到映射表中，同一批导入的后续行可以直接使用

**示例场景**:

**场景A**: 管理员已有默认客户
- Excel产品名称: "新产品B"
- 管理员已有客户: "默认客户（导入数据）"（ID=10）
- **结果**: 
  - 使用客户ID=10
  - 创建新产品"新产品B"（ID=新ID）
  - 扣减比例=0

**场景B**: 管理员没有任何客户
- Excel产品名称: "新产品C"
- 管理员没有客户
- **结果**: 
  - 自动创建"默认客户（导入数据）"（ID=新客户ID）
  - 创建新产品"新产品C"（ID=新产品ID）
  - 扣减比例=0

**场景C**: 指定了客户ID
- Excel产品名称: "新产品D"
- 查询参数: `client_id=5`
- **结果**: 
  - 使用客户ID=5（验证存在）
  - 创建新产品"新产品D"（ID=新产品ID）
  - 扣减比例=0

---

##### 情况1.2.2：映射不完整 → 拒绝导入

**前提条件**: `mapping_complete = False`（列名映射不完整）

**处理逻辑**:
```python
else:
    raise ValueError(
        f"字段映射不完整，无法导入数据。产品 '{product_name}' 不存在且无法自动创建。"
    )
```

**原因**: 
- 系统完全基于训练数据进行智能识别
- 如果映射不完整，说明训练数据不足，无法保证数据准确性
- 因此拒绝自动创建产品，要求先完善训练数据

**解决方案**:
1. 在"导入训练"功能中，手动映射Excel列名到数据库字段
2. 保存映射规则后，系统会自动识别相似的列名
3. 映射完整后，可以自动创建产品

---

#### 1.4.5 返回的产品信息结构

函数返回的产品信息字典包含以下字段：

```python
{
    "product_id": int,              # 产品ID
    "client_id": int,               # 客户ID
    "client_name": str,             # 客户名称
    "product_name": str,            # 产品名称
    "ecpm_deduct_ratio": float,    # eCPM扣减比例
    "revenue_deduct_ratio": float   # 收益扣减比例
}
```

这个信息字典会被用于后续的数据处理：
- 确定扣减比例，计算扣减后的值
- 确定产品ID，插入或更新广告数据

---

#### 1.4.6 关键设计决策

1. **客户ID优先级**:
   - 查询参数 `client_id` > Excel中的 `target_client_id`
   - 允许管理员在导入时统一指定客户，覆盖Excel中的客户信息

2. **多产品名称处理**:
   - 优先使用指定的客户ID匹配
   - 如果未匹配到，使用第一个匹配的产品（记录警告）
   - 避免因多匹配而中断导入流程

3. **自动创建产品的前提**:
   - 必须映射完整（`mapping_complete = True`）
   - 确保数据准确性，避免错误创建

4. **默认客户机制**:
   - 自动创建"默认客户（导入数据）"
   - 方便管理员快速导入数据，后续可手动调整

5. **扣减比例默认值**:
   - 新建产品默认扣减比例为0（不扣减）
   - 避免误扣减，后续可手动修改

---

#### 1.4.7 完整示例

**示例1: 产品存在，唯一匹配**
```
输入:
  product_name = "产品A"
  client_id = None
  target_client_id = None
  
数据库状态:
  - "产品A" (客户ID=1)
  
处理流程:
  1. 查找产品名称 → 找到1个匹配
  2. 使用该产品
  3. 返回: {product_id: 1, client_id: 1, ...}
```

**示例2: 产品存在，多个匹配，指定客户ID**
```
输入:
  product_name = "产品B"
  client_id = 2
  target_client_id = None
  
数据库状态:
  - "产品B" (客户ID=1)
  - "产品B" (客户ID=2)
  
处理流程:
  1. 查找产品名称 → 找到2个匹配
  2. 查找客户ID=2的匹配 → 找到
  3. 使用客户ID=2的产品
  4. 返回: {product_id: 2, client_id: 2, ...}
```

**示例3: 产品不存在，映射完整**
```
输入:
  product_name = "新产品C"
  client_id = None
  target_client_id = None
  mapping_complete = True
  
数据库状态:
  - 管理员已有客户: "默认客户（导入数据）" (ID=10)
  - 不存在"新产品C"
  
处理流程:
  1. 查找产品名称 → 未找到
  2. 映射完整 → 可以创建
  3. 查找默认客户 → 找到 (ID=10)
  4. 创建新产品 "新产品C" (ID=新ID)
  5. 更新映射表
  6. 返回: {product_id: 新ID, client_id: 10, ecpm_deduct_ratio: 0.0, ...}
```

**示例4: 产品不存在，映射不完整**
```
输入:
  product_name = "新产品D"
  client_id = None
  target_client_id = None
  mapping_complete = False
  
数据库状态:
  - 不存在"新产品D"
  
处理流程:
  1. 查找产品名称 → 未找到
  2. 映射不完整 → 拒绝创建
  3. 抛出异常: "字段映射不完整，无法导入数据。产品 '新产品D' 不存在且无法自动创建。"
```

---

### 1.5 关键特性

1. **智能列名映射**: 基于训练数据自动识别Excel列名
2. **自动创建产品**: 映射完整时，自动创建不存在的产品
3. **重复数据处理**: 
   - Excel内部重复：只保留最后一行
   - 数据库重复：更新现有记录
4. **性能优化**: 批量预查询，避免N+1查询问题
5. **错误容错**: 单行错误不影响其他行的导入
6. **扣减比例**: 根据产品的扣减比例自动计算扣减后的值

---

## 二、API获取数据操作逻辑

### 2.1 API端点概览

系统提供两种方式获取广告数据：

#### 2.1.1 内部API（Web界面使用）

- **路由**: `GET /api/v1/ad-data/`
- **权限**: 
  - 管理员：可查看所有数据
  - 客户：只能查看自己的数据
- **认证**: JWT Token（通过`get_current_user`）

#### 2.1.2 外部API（客户API密钥访问）

- **路由**: `POST /client_data`
- **权限**: 客户只能查看自己的数据
- **认证**: API密钥（`client_id`, `secret_key`, `req_time`, `sign`）

---

### 2.2 内部API获取数据流程

#### 端点: `GET /api/v1/ad-data/`

**查询参数**:
- `page`: 页码（默认1）
- `page_size`: 每页条数（默认10，最大100）
- `start_date`: 开始日期（格式：YYYY-MM-DD）
- `end_date`: 结束日期（格式：YYYY-MM-DD）
- `client_id`: 客户ID过滤（仅管理员可用）
- `product_id`: 产品ID过滤
- `sort_by`: 排序字段（默认：date）
- `sort_order`: 排序方向（asc/desc，默认：desc）

**处理流程**:

```
接收查询参数
    ↓
设备类型优化（自动调整分页大小）
    ↓
检查是否使用产品分配历史表
    ↓
构建JOIN查询（AdData + Product + Client + User）
    ↓
应用权限过滤
    ├─ 管理员：可查看所有，可按client_id过滤
    └─ 客户：只能查看自己的数据（Client.user_id = current_user.id）
    ↓
应用产品状态过滤（只显示激活的产品）
    ↓
应用产品ID过滤（如果指定）
    ↓
应用日期范围过滤
    ├─ 如果指定了日期范围：使用指定范围
    └─ 如果未指定：默认查询当前月的数据
    ↓
应用排序（按指定字段和方向）
    ↓
执行分页查询
    ├─ 计算总数（优化：使用简化的计数查询）
    └─ 获取分页数据
    ↓
转换为响应格式
    ↓
返回分页结果
```

**详细说明**:

1. **设备类型优化**:
   - 自动检测设备类型（移动端/桌面端）
   - 移动端自动调整分页大小，提高性能

2. **产品分配历史表支持**:
   - 如果系统使用了产品分配历史表（`product_assignments`）:
     - 通过`ProductAssignment`表关联，根据广告数据的日期匹配正确的客户归属
     - 支持产品在不同时间段归属不同客户的历史记录
   - 否则使用旧的查询方式（直接通过`Product.client_id`关联）

3. **权限过滤**:
   - **管理员**: 可以查看所有数据，也可以按`client_id`过滤
   - **客户**: 只能查看自己的数据（通过`Client.user_id`过滤）

4. **日期范围过滤**:
   - 如果指定了`start_date`和`end_date`，使用指定范围
   - 如果未指定，**默认查询当前月的数据**（提高用户体验）
   - `AdData.date`是`DateTime`类型，需要转换为datetime进行比较

5. **排序**:
   - 支持按多个字段排序：
     - `date`: 日期
     - `client`: 客户名称
     - `product`: 产品名称
     - `request_count`, `match_count`, `display_count`, `click_count`
     - `ecpm_after_deduct`, `revenue_after_deduct`
   - 默认按日期倒序排列

6. **分页查询优化**:
   - 使用简化的计数查询，减少不必要的JOIN
   - 复用主查询的过滤条件，确保计数准确

7. **响应格式**:
   ```json
   {
     "code": 200,
     "message": "成功获取广告数据",
     "data": {
       "items": [...],  // 广告数据列表
       "total": 100,    // 总记录数
       "page": 1,       // 当前页码
       "page_size": 10  // 每页条数
     }
   }
   ```

---

### 2.3 外部API获取数据流程

#### 端点: `POST /client_data`

**请求体** (`ClientAPIRequest`):
```json
{
  "client_id": 1,
  "secret_key": "xxx",
  "req_time": "2024-01-01T00:00:00",
  "sign": "xxx"
}
```

**处理流程**:

```
接收请求体
    ↓
验证API请求（client_id, secret_key, req_time, sign）
    ↓
计算当前月的日期范围
    ↓
检查是否使用产品分配历史表
    ↓
构建查询（AdData + Product + ProductAssignment）
    ↓
应用日期范围过滤（当前月）
    ↓
按日期升序排列
    ↓
执行查询
    ↓
转换为响应格式
    ├─ 格式化日期为ISO格式（YYYY-MM-DD）
    ├─ 计算比率（coverage_rate, display_rate, click_rate）
    └─ 确保数值类型正确（Java客户端兼容性）
    ↓
记录API访问日志
    ↓
返回数据列表
```

**详细说明**:

1. **API请求验证** (`verify_client_request`):
   - 验证`client_id`是否存在
   - 验证`secret_key`是否正确
   - 验证时间戳（防止重放攻击）
   - 验证签名（`sign`）是否正确

2. **日期范围**:
   - **固定为当前月**（从当月1日到最后一天）
   - 不支持自定义日期范围（简化API设计）

3. **产品分配历史表支持**:
   - 如果使用产品分配历史表，通过`ProductAssignment`关联
   - 根据广告数据的日期匹配正确的客户归属

4. **数据转换**:
   - 日期格式化为ISO格式字符串（`YYYY-MM-DD`）
   - 计算比率：
     - `coverage_rate = match_count / request_count * 100`
     - `display_rate = display_count / match_count * 100`
     - `click_rate = click_count / display_count * 100`
   - 确保所有数值类型正确（整数转int，浮点数转float）

5. **响应格式** (`AdDataItemResponse`):
   ```json
   {
     "code": 200,
     "message": "成功获取 100 条广告数据",
     "data": [
       {
         "date": "2024-01-01",
         "product_name": "产品A",
         "request_count": 1000,
         "match_count": 800,
         "coverage_rate": 80.0,
         "display_count": 600,
         "display_rate": 75.0,
         "click_count": 50,
         "click_rate": 8.33,
         "ecpm": 10.5,
         "revenue": 6.3
       },
       ...
     ]
   }
   ```

6. **API访问日志**:
   - 记录每次API访问的详细信息
   - 包括：客户ID、数据条数、日期范围等

---

### 2.4 关键特性

1. **权限隔离**: 
   - 管理员和客户看到的数据不同
   - 客户只能查看自己的数据

2. **产品分配历史支持**:
   - 支持产品在不同时间段归属不同客户
   - 根据广告数据的日期匹配正确的客户归属

3. **默认日期范围**:
   - 内部API：默认查询当前月数据
   - 外部API：固定查询当前月数据

4. **性能优化**:
   - 使用JOIN查询，避免N+1查询问题
   - 优化计数查询，减少不必要的JOIN
   - 移动端自动调整分页大小

5. **数据格式**:
   - 内部API：返回完整的对象结构
   - 外部API：返回扁平化的数据列表（Java客户端兼容）

---

## 三、数据模型关系

### 3.1 核心表结构

```
User (用户)
  ├─ id
  └─ username

Client (客户)
  ├─ id
  ├─ user_id (关联User)
  ├─ company_name
  └─ secret_key (API密钥)

Product (产品)
  ├─ id
  ├─ client_id (关联Client)
  ├─ name
  ├─ ecpm_deduct_ratio (eCPM扣减比例)
  └─ revenue_deduct_ratio (收益扣减比例)

ProductAssignment (产品分配历史)
  ├─ id
  ├─ product_id (关联Product)
  ├─ client_id (关联Client)
  ├─ start_date (开始日期)
  └─ end_date (结束日期，NULL表示当前)

AdData (广告数据)
  ├─ id
  ├─ date (日期，DateTime类型)
  ├─ product_id (关联Product)
  ├─ request_count (请求数)
  ├─ match_count (匹配数)
  ├─ display_count (展示数)
  ├─ click_count (点击数)
  ├─ ecpm_before_deduct (扣减前eCPM)
  ├─ ecpm_after_deduct (扣减后eCPM)
  ├─ revenue_before_deduct (扣减前收益)
  └─ revenue_after_deduct (扣减后收益)
```

### 3.2 数据关系

1. **User → Client**: 一对多（一个用户可以有多个客户）
2. **Client → Product**: 一对多（一个客户可以有多个产品）
3. **Product → AdData**: 一对多（一个产品可以有多个广告数据记录）
4. **ProductAssignment**: 记录产品在不同时间段的客户归属关系

### 3.3 唯一性约束

- **AdData**: `(date, product_id)` 唯一（同一产品同一天只能有一条记录）

---

## 四、关键业务规则总结

### 4.1 导入数据规则

1. **字段映射规则**:
   - 必须基于训练数据进行智能识别
   - 映射不完整时拒绝导入
   - 映射完整时可以自动创建产品

2. **产品查找规则**:
   - 优先按产品名称查找
   - 如果产品名称对应多个客户，优先使用查询参数指定的客户ID
   - 如果找不到产品且映射完整，自动创建（默认客户为管理员）

3. **重复数据处理**:
   - Excel内部重复：只保留最后一行
   - 数据库重复：更新现有记录

4. **扣减比例**:
   - 根据产品的扣减比例自动计算扣减后的值
   - 新建产品默认扣减比例为0（不扣减）

### 4.2 API获取数据规则

1. **权限规则**:
   - 管理员：可查看所有数据
   - 客户：只能查看自己的数据

2. **产品分配历史规则**:
   - 如果使用产品分配历史表，根据广告数据的日期匹配正确的客户归属
   - 支持产品在不同时间段归属不同客户

3. **日期范围规则**:
   - 内部API：默认查询当前月，支持自定义范围
   - 外部API：固定查询当前月

4. **数据过滤规则**:
   - 只显示激活状态的产品（`is_active = True`）
   - 支持按客户ID、产品ID、日期范围过滤

---

## 五、错误处理

### 5.1 导入数据错误

1. **文件验证错误**:
   - 不支持的文件类型
   - 文件大小超限
   - 文件格式无效或损坏

2. **列名映射错误**:
   - 映射不完整（缺少必要字段）
   - 训练数据不存在

3. **数据验证错误**:
   - 数值字段格式错误
   - 数值为负数
   - 产品名称为空

4. **数据库错误**:
   - 唯一性约束违反（并发导入）
   - 事务提交失败

### 5.2 API获取数据错误

1. **认证错误**:
   - Token无效或过期（内部API）
   - API密钥错误（外部API）
   - 签名验证失败（外部API）

2. **权限错误**:
   - 客户尝试访问其他客户的数据

3. **查询错误**:
   - 数据库查询失败
   - 参数格式错误

---

## 六、性能优化要点

1. **批量查询**: 导入时批量预查询重复记录，避免N+1查询
2. **JOIN查询**: API查询时使用JOIN，一次性获取关联数据
3. **索引优化**: 数据库表有适当的索引（date, product_id等）
4. **分页优化**: 移动端自动调整分页大小
5. **计数查询优化**: 使用简化的计数查询，减少不必要的JOIN

---

## 七、总结

### 导入数据流程
1. 文件验证 → 2. 列名映射 → 3. 数据验证 → 4. 产品查找/创建 → 5. 数据导入/更新

### API获取数据流程
1. 权限验证 → 2. 构建查询 → 3. 应用过滤 → 4. 执行查询 → 5. 返回结果

两个流程都支持**产品分配历史表**，能够正确处理产品在不同时间段归属不同客户的情况。

