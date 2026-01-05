# CPL系统扣减功能详细实施方案

## 一、需求概述

### 1.1 核心需求
实现CPL系统的两种扣减方式：
- **按比例扣量**：按转化数量进行扣减
- **按比例扣金额**：按转化金额进行扣减

### 1.2 扣减层级
扣减需要在三个层级进行配置和分配：
- **广告主（Advertiser）**：上游来源
- **Offer（单子）**：广告主下的具体单子
- **渠道（Publisher）**：下游渠道

### 1.3 组合方式
- 可以单独按比例扣量，不按比例扣减金额
- 可以按比例扣减金额，不按比例扣量
- 可以按比例扣量并且按比例扣金额

### 1.4 默认配置
- 全部扣减比例为0，即不扣量也不扣金额

### 1.5 核心要求
**让渠道（下游/客户）感觉不出来扣了量**，即：
- 扣减后的数据要自然分布，不能有明显的规律
- 扣减要分散到各个层级，避免集中扣减
- 统计报表中要隐藏扣减信息

---

## 二、数据库设计

### 2.1 扣减配置表（conversion_deduction_configs）

```sql
CREATE TABLE conversion_deduction_configs (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '配置ID',
    
    -- 配置层级（三选一）
    advertiser_id INT NULL COMMENT '广告主ID（如果配置在广告主级别）',
    offer_id INT NULL COMMENT 'Offer ID（如果配置在Offer级别）',
    publisher_id INT NULL COMMENT '渠道ID（如果配置在渠道级别）',
    
    -- 扣减类型配置
    volume_deduction_ratio DECIMAL(5,4) DEFAULT 0.0000 COMMENT '按比例扣量比例（0-1，如0.10表示扣量10%）',
    amount_deduction_ratio DECIMAL(5,4) DEFAULT 0.0000 COMMENT '按比例扣金额比例（0-1，如0.10表示扣金额10%）',
    
    -- 扣减策略配置
    deduction_strategy VARCHAR(50) DEFAULT 'random' COMMENT '扣减策略：random（随机）/proportional（按比例）/round_robin（轮询）',
    enable_volume_deduction BOOLEAN DEFAULT FALSE COMMENT '是否启用按比例扣量',
    enable_amount_deduction BOOLEAN DEFAULT FALSE COMMENT '是否启用按比例扣金额',
    
    -- 优先级配置
    priority INT DEFAULT 0 COMMENT '优先级（数字越大优先级越高）',
    
    -- 状态
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',
    
    -- 时间戳
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    -- 索引
    INDEX idx_advertiser_id (advertiser_id),
    INDEX idx_offer_id (offer_id),
    INDEX idx_publisher_id (publisher_id),
    INDEX idx_is_active (is_active),
    INDEX idx_priority (priority),
    
    -- 约束：确保同一层级只有一个激活的配置
    UNIQUE KEY uk_advertiser_active (advertiser_id, is_active),
    UNIQUE KEY uk_offer_active (offer_id, is_active),
    UNIQUE KEY uk_publisher_active (publisher_id, is_active),
    
    -- 外键
    FOREIGN KEY (advertiser_id) REFERENCES advertisers(id) ON DELETE CASCADE,
    FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE CASCADE,
    FOREIGN KEY (publisher_id) REFERENCES publishers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='转化扣减配置表';
```

### 2.2 扣减执行记录表（conversion_deduction_logs）

```sql
CREATE TABLE conversion_deduction_logs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '记录ID',
    
    -- 关联信息
    conversion_id BIGINT NOT NULL COMMENT '转化记录ID（关联postback_conversions.id）',
    click_id VARCHAR(255) NULL COMMENT '点击ID',
    advertiser_id INT NULL COMMENT '广告主ID',
    offer_id INT NULL COMMENT 'Offer ID',
    publisher_id INT NULL COMMENT '渠道ID',
    
    -- 扣减前数据
    original_volume INT DEFAULT 1 COMMENT '原始转化数量（通常为1）',
    original_amount DECIMAL(10,2) NOT NULL COMMENT '原始转化金额',
    
    -- 扣减后数据
    deducted_volume INT DEFAULT 0 COMMENT '扣减的转化数量',
    deducted_amount DECIMAL(10,2) DEFAULT 0.00 COMMENT '扣减的转化金额',
    final_volume INT DEFAULT 1 COMMENT '最终转化数量（扣减后）',
    final_amount DECIMAL(10,2) NOT NULL COMMENT '最终转化金额（扣减后）',
    
    -- 扣减配置信息
    deduction_config_id INT NULL COMMENT '使用的扣减配置ID',
    volume_deduction_ratio DECIMAL(5,4) COMMENT '使用的扣量比例',
    amount_deduction_ratio DECIMAL(5,4) COMMENT '使用的扣金额比例',
    deduction_strategy VARCHAR(50) COMMENT '使用的扣减策略',
    
    -- 扣减原因
    deduction_reason TEXT NULL COMMENT '扣减原因说明',
    
    -- 时间戳
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    
    -- 索引
    INDEX idx_conversion_id (conversion_id),
    INDEX idx_click_id (click_id),
    INDEX idx_advertiser_id (advertiser_id),
    INDEX idx_offer_id (offer_id),
    INDEX idx_publisher_id (publisher_id),
    INDEX idx_created_at (created_at),
    INDEX idx_deduction_config_id (deduction_config_id),
    
    -- 外键
    FOREIGN KEY (conversion_id) REFERENCES postback_conversions(id) ON DELETE CASCADE,
    FOREIGN KEY (advertiser_id) REFERENCES advertisers(id) ON DELETE SET NULL,
    FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE SET NULL,
    FOREIGN KEY (publisher_id) REFERENCES publishers(id) ON DELETE SET NULL,
    FOREIGN KEY (deduction_config_id) REFERENCES conversion_deduction_configs(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='转化扣减执行记录表';
```

### 2.3 修改现有表结构

#### 2.3.1 postback_conversions表增加字段

```sql
ALTER TABLE postback_conversions 
ADD COLUMN is_deducted BOOLEAN DEFAULT FALSE COMMENT '是否已被扣减',
ADD COLUMN deduction_type VARCHAR(20) NULL COMMENT '扣减类型：volume（扣量）/amount（扣金额）/both（两者）',
ADD COLUMN original_volume INT DEFAULT 1 COMMENT '原始转化数量',
ADD COLUMN deducted_volume INT DEFAULT 0 COMMENT '扣减的转化数量',
ADD INDEX idx_is_deducted (is_deducted),
ADD INDEX idx_deduction_type (deduction_type);
```

---

## 三、扣减算法设计

### 3.1 配置优先级规则

扣减配置的查找优先级（从高到低）：
1. **Offer级别配置**（最高优先级）
2. **广告主级别配置**
3. **渠道级别配置**（最低优先级）

如果某个层级没有配置，则向下查找下一层级。

### 3.2 按比例扣量算法

#### 3.2.1 批量扣量分配算法

当上游PostBack通知100个成功转化，扣量比例0.10时：

**步骤1：按广告主分配**
- 统计所有相关广告主的转化数量
- 按广告主转化数量比例分配总扣量
- 例如：广告主A有60个转化，广告主B有40个转化
  - 广告主A应扣量：100 × 0.10 × (60/100) = 6个
  - 广告主B应扣量：100 × 0.10 × (40/100) = 4个

**步骤2：按Offer分配**
- 在每个广告主内部，按Offer的转化数量比例分配
- 例如：广告主A有OfferA（40个转化）和OfferB（20个转化）
  - OfferA应扣量：6 × (40/60) = 4个
  - OfferB应扣量：6 × (20/60) = 2个

**步骤3：按渠道分配**
- 在每个Offer内部，按渠道的转化数量比例分配
- 例如：OfferA有3个渠道（渠道1: 15个，渠道2: 15个，渠道3: 10个）
  - 渠道1应扣量：4 × (15/40) = 1.5 ≈ 2个（向上取整）
  - 渠道2应扣量：4 × (15/40) = 1.5 ≈ 2个
  - 渠道3应扣量：4 × (10/40) = 1.0 = 1个
  - 如果总和超过，则最后一个渠道调整

**步骤4：随机选择扣减目标**
- 使用扣减策略（random/proportional/round_robin）选择具体的转化记录进行扣减
- **random策略**：随机选择转化记录，确保分布自然
- **proportional策略**：按时间顺序等比例选择
- **round_robin策略**：轮询选择

#### 3.2.2 单条转化扣量判断算法

对于每条转化记录，需要判断是否应该被扣减：

```python
def should_deduct_volume(conversion, config, recent_conversions):
    """
    判断单条转化是否应该被扣减
    
    Args:
        conversion: 转化记录
        config: 扣减配置
        recent_conversions: 最近的转化记录列表（用于统计）
    
    Returns:
        bool: 是否应该扣减
    """
    if not config.enable_volume_deduction:
        return False
    
    # 获取该转化所属的层级统计
    stats = get_conversion_stats(conversion)
    
    # 计算应该扣减的数量
    total_conversions = stats['total']
    should_deduct_count = int(total_conversions * config.volume_deduction_ratio)
    already_deducted_count = stats['deducted']
    
    # 如果已经扣减够了，不再扣减
    if already_deducted_count >= should_deduct_count:
        return False
    
    # 根据策略决定是否扣减这条
    if config.deduction_strategy == 'random':
        # 随机扣减，但确保总体比例正确
        remaining_to_deduct = should_deduct_count - already_deducted_count
        remaining_conversions = total_conversions - stats['processed']
        if remaining_conversions == 0:
            return False
        probability = remaining_to_deduct / remaining_conversions
        return random.random() < probability
    
    elif config.deduction_strategy == 'proportional':
        # 按比例扣减
        return (stats['processed'] + 1) % int(1 / config.volume_deduction_ratio) == 0
    
    elif config.deduction_strategy == 'round_robin':
        # 轮询扣减
        return stats['processed'] % int(1 / config.volume_deduction_ratio) == 0
    
    return False
```

### 3.3 按比例扣金额算法

按比例扣金额相对简单，每条转化都按比例扣减：

```python
def calculate_amount_deduction(original_amount, config):
    """
    计算扣减后的金额
    
    Args:
        original_amount: 原始金额
        config: 扣减配置
    
    Returns:
        tuple: (扣减后金额, 扣减金额)
    """
    if not config.enable_amount_deduction:
        return original_amount, 0.0
    
    deduction_amount = original_amount * config.amount_deduction_ratio
    final_amount = original_amount - deduction_amount
    
    return final_amount, deduction_amount
```

### 3.4 组合扣减算法

当同时启用扣量和扣金额时：

```python
def apply_deduction(conversion, config, recent_conversions):
    """
    应用扣减（可能同时扣量和扣金额）
    
    Returns:
        dict: {
            'should_deduct_volume': bool,
            'should_deduct_amount': bool,
            'original_volume': int,
            'original_amount': float,
            'final_volume': int,
            'final_amount': float,
            'deducted_volume': int,
            'deducted_amount': float
        }
    """
    result = {
        'original_volume': 1,
        'original_amount': conversion.original_payout or 0.0,
        'final_volume': 1,
        'final_amount': conversion.original_payout or 0.0,
        'deducted_volume': 0,
        'deducted_amount': 0.0
    }
    
    # 判断是否扣量
    if config.enable_volume_deduction:
        result['should_deduct_volume'] = should_deduct_volume(
            conversion, config, recent_conversions
        )
        if result['should_deduct_volume']:
            result['final_volume'] = 0
            result['deducted_volume'] = 1
    
    # 计算扣金额
    if config.enable_amount_deduction:
        result['should_deduct_amount'] = True
        result['final_amount'], result['deducted_amount'] = calculate_amount_deduction(
            result['original_amount'], config
        )
    
    return result
```

---

## 四、扣减执行流程

### 4.1 PostBack接收时的扣减流程

```
1. 接收上游PostBack通知
   ↓
2. 解析转化数据，获取advertiser_id, offer_id, publisher_id
   ↓
3. 查找扣减配置（按优先级：Offer > Advertiser > Publisher）
   ↓
4. 如果找到配置且启用扣减：
   a. 查询最近的转化记录（用于统计和分配）
   b. 判断是否应该扣量（should_deduct_volume）
   c. 计算扣减后的金额（calculate_amount_deduction）
   ↓
5. 保存转化记录：
   - 如果扣量：不保存到postback_conversions，或标记为已扣减
   - 如果扣金额：保存但使用扣减后的金额
   ↓
6. 记录扣减日志（conversion_deduction_logs）
   ↓
7. 如果未扣量，继续后续流程（Cap检查、下游转发等）
```

### 4.2 批量扣减处理流程

对于批量PostBack通知（如一次通知100个转化）：

```
1. 接收批量PostBack数据
   ↓
2. 按广告主分组统计转化数量
   ↓
3. 计算每个广告主应扣减的数量
   ↓
4. 在每个广告主内，按Offer分组统计
   ↓
5. 计算每个Offer应扣减的数量
   ↓
6. 在每个Offer内，按渠道分组统计
   ↓
7. 计算每个渠道应扣减的数量
   ↓
8. 使用随机策略选择具体的转化记录进行扣减
   ↓
9. 批量保存转化记录和扣减日志
```

---

## 五、前端界面设计

### 5.1 扣减配置管理页面

**路径**：`/app/admin/conversion-deductions`

**功能模块**：

#### 5.1.1 配置列表

显示所有扣减配置，包括：
- 配置层级（广告主/Offer/渠道）
- 配置对象名称
- 扣量比例
- 扣金额比例
- 扣减策略
- 启用状态
- 操作按钮（编辑/删除/启用/禁用）

#### 5.1.2 添加/编辑配置对话框

**表单字段**：
1. **配置层级选择**（单选）
   - 广告主级别
   - Offer级别
   - 渠道级别

2. **配置对象选择**（根据层级动态显示）
   - 广告主级别：选择广告主
   - Offer级别：选择Offer
   - 渠道级别：选择渠道

3. **扣量配置**
   - 启用按比例扣量（开关）
   - 扣量比例（0-100%，输入框，带滑块）
   - 扣减策略（下拉选择：随机/按比例/轮询）

4. **扣金额配置**
   - 启用按比例扣金额（开关）
   - 扣金额比例（0-100%，输入框，带滑块）

5. **优先级**（数字输入，默认0）

6. **状态**（启用/禁用开关）

#### 5.1.3 扣减统计报表

显示扣减执行情况：
- 按时间范围统计
- 按广告主/Offer/渠道分组
- 显示原始转化数、扣减转化数、扣减比例
- 显示原始金额、扣减金额、扣减比例
- 支持导出Excel

### 5.2 界面布局设计

```
┌─────────────────────────────────────────────────────────┐
│  转化扣减配置管理                                        │
├─────────────────────────────────────────────────────────┤
│  [搜索框] [层级筛选] [状态筛选] [搜索] [重置] [添加配置] │
├─────────────────────────────────────────────────────────┤
│  配置列表表格：                                          │
│  ┌──┬──────┬──────┬──────┬──────┬──────┬──────┬────┐  │
│  │ID│层级  │对象  │扣量  │扣金额│策略  │状态  │操作│  │
│  ├──┼──────┼──────┼──────┼──────┼──────┼──────┼────┤  │
│  │1 │广告主│广告主A│10%  │5%   │随机  │启用  │...│  │
│  │2 │Offer │OfferA │0%   │10%  │按比例│启用  │...│  │
│  └──┴──────┴──────┴──────┴──────┴──────┴──────┴────┘  │
├─────────────────────────────────────────────────────────┤
│  扣减统计报表（标签页）：                                 │
│  [按时间] [按广告主] [按Offer] [按渠道]                  │
│  ┌──────────────────────────────────────────────┐      │
│  │  时间范围：[选择器]                           │      │
│  │  原始转化：1000  扣减转化：100  扣减率：10%   │      │
│  │  原始金额：$10000  扣减金额：$1000  扣减率：10%│      │
│  │  [导出Excel]                                 │      │
│  └──────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────┘
```

### 5.3 添加/编辑配置对话框设计

```
┌─────────────────────────────────────────────┐
│  添加扣减配置                          [×]  │
├─────────────────────────────────────────────┤
│  配置层级：○ 广告主  ○ Offer  ○ 渠道       │
│                                             │
│  配置对象：[下拉选择框]                     │
│                                             │
│  ┌─ 按比例扣量 ────────────────────────┐   │
│  │ ☑ 启用按比例扣量                      │   │
│  │ 扣量比例： [10] %  [━━━━━━━━━━━━━━] │   │
│  │ 扣减策略： [随机 ▼]                  │   │
│  └──────────────────────────────────────┘   │
│                                             │
│  ┌─ 按比例扣金额 ──────────────────────┐   │
│  │ ☑ 启用按比例扣金额                    │   │
│  │ 扣金额比例： [5] % [━━━━━━━━━━━━━━] │   │
│  └──────────────────────────────────────┘   │
│                                             │
│  优先级： [0]                               │
│                                             │
│  状态： ☑ 启用                              │
│                                             │
│  [取消]  [确定]                            │
└─────────────────────────────────────────────┘
```

---

## 六、隐藏扣减的实现策略

### 6.1 数据隐藏策略

1. **不保存被扣量的转化记录**
   - 如果转化被扣量，不保存到`postback_conversions`表
   - 只记录到`conversion_deduction_logs`表（仅管理员可见）

2. **金额扣减后保存**
   - 保存转化记录，但使用扣减后的金额
   - 原始金额保存在`conversion_deduction_logs`表中

3. **下游PostBack转发**
   - 只转发未扣量的转化
   - 转发时使用扣减后的金额（如果扣了金额）

### 6.2 统计报表隐藏

1. **渠道可见的报表**
   - 只显示未扣量的转化
   - 只显示扣减后的金额
   - 不显示任何扣减相关信息

2. **管理员可见的报表**
   - 显示原始数据和扣减数据
   - 显示扣减统计信息
   - 可以查看扣减日志

### 6.3 随机化策略

1. **随机选择扣减目标**
   - 使用随机策略选择要扣减的转化
   - 避免固定模式（如每10个扣1个）
   - 使用时间戳+转化ID生成随机种子

2. **分散扣减**
   - 扣减分散到不同时间段
   - 扣减分散到不同渠道
   - 避免集中扣减

---

## 七、API接口设计

### 7.1 扣减配置管理接口

#### 7.1.1 获取扣减配置列表
```
GET /api/v1/conversion-deductions
Query参数：
- page: 页码
- page_size: 每页数量
- level: 层级筛选（advertiser/offer/publisher）
- is_active: 状态筛选
```

#### 7.1.2 创建扣减配置
```
POST /api/v1/conversion-deductions
Body:
{
  "level": "advertiser",  // advertiser/offer/publisher
  "target_id": 1,  // 广告主ID/Offer ID/渠道ID
  "enable_volume_deduction": true,
  "volume_deduction_ratio": 0.10,
  "deduction_strategy": "random",
  "enable_amount_deduction": true,
  "amount_deduction_ratio": 0.05,
  "priority": 0,
  "is_active": true
}
```

#### 7.1.3 更新扣减配置
```
PUT /api/v1/conversion-deductions/{id}
Body: 同创建接口
```

#### 7.1.4 删除扣减配置
```
DELETE /api/v1/conversion-deductions/{id}
```

### 7.2 扣减统计接口

#### 7.2.1 获取扣减统计
```
GET /api/v1/conversion-deductions/stats
Query参数：
- start_date: 开始日期
- end_date: 结束日期
- group_by: 分组方式（advertiser/offer/publisher）
- advertiser_id: 广告主ID（可选）
- offer_id: Offer ID（可选）
- publisher_id: 渠道ID（可选）
```

### 7.3 扣减日志接口

#### 7.3.1 获取扣减日志
```
GET /api/v1/conversion-deductions/logs
Query参数：
- page: 页码
- page_size: 每页数量
- start_date: 开始日期
- end_date: 结束日期
- advertiser_id: 广告主ID（可选）
- offer_id: Offer ID（可选）
- publisher_id: 渠道ID（可选）
```

---

## 八、实施步骤

### 8.1 第一阶段：数据库设计
1. 创建`conversion_deduction_configs`表
2. 创建`conversion_deduction_logs`表
3. 修改`postback_conversions`表，增加扣减相关字段
4. 创建必要的索引

### 8.2 第二阶段：后端核心逻辑
1. 创建扣减配置模型（Model）
2. 创建扣减配置Schema
3. 实现扣减配置查找逻辑（按优先级）
4. 实现按比例扣量算法
5. 实现按比例扣金额算法
6. 实现组合扣减逻辑
7. 修改PostBack处理器，集成扣减逻辑
8. 创建扣减配置管理API
9. 创建扣减统计API
10. 创建扣减日志API

### 8.3 第三阶段：前端界面
1. 创建扣减配置管理页面
2. 实现配置列表展示
3. 实现添加/编辑配置对话框
4. 实现扣减统计报表
5. 实现扣减日志查看
6. 添加路由配置

### 8.4 第四阶段：测试与优化
1. 单元测试扣减算法
2. 集成测试PostBack处理流程
3. 性能测试批量扣减
4. 测试隐藏扣减效果
5. 优化扣减算法性能

---

## 九、注意事项

### 9.1 数据一致性
- 确保扣减配置的优先级正确
- 确保扣减日志记录完整
- 确保统计数据准确

### 9.2 性能考虑
- 批量扣减时使用批量操作
- 扣减统计查询使用合适的索引
- 考虑使用Redis缓存扣减配置

### 9.3 安全性
- 扣减配置管理需要管理员权限
- 扣减日志仅管理员可见
- 防止扣减配置被恶意修改

### 9.4 可追溯性
- 所有扣减操作都要记录日志
- 日志要包含完整的扣减信息
- 支持扣减数据的审计

---

## 十、示例场景

### 10.1 场景1：只扣量，不扣金额

**配置**：
- 广告主A：扣量比例10%，不扣金额

**执行**：
- 上游通知100个转化，每个转化$10
- 扣减10个转化（随机选择）
- 下游收到90个转化，每个$10
- 下游总金额：$900

### 10.2 场景2：只扣金额，不扣量

**配置**：
- OfferA：不扣量，扣金额比例5%

**执行**：
- 上游通知100个转化，每个转化$10
- 不扣减转化数量
- 每个转化金额扣减5%，即$9.5
- 下游收到100个转化，每个$9.5
- 下游总金额：$950

### 10.3 场景3：既扣量又扣金额

**配置**：
- 广告主A：扣量比例10%，扣金额比例5%

**执行**：
- 上游通知100个转化，每个转化$10
- 扣减10个转化（随机选择）
- 剩余90个转化，每个金额扣减5%，即$9.5
- 下游收到90个转化，每个$9.5
- 下游总金额：$855

### 10.4 场景4：多层级配置

**配置**：
- 广告主A：扣量比例10%
- OfferA（属于广告主A）：扣金额比例5%

**执行**：
- 上游通知100个转化，其中60个属于OfferA，40个属于其他Offer
- 广告主A总共扣减10个转化（按比例分配到各Offer）
- OfferA的转化：扣量后剩余54个，每个金额扣减5%
- 其他Offer的转化：扣量后剩余36个，金额不变
- 下游收到90个转化，其中54个是OfferA（$9.5），36个是其他Offer（$10）

---

## 十一、总结

本方案提供了完整的CPL系统扣减功能实施方案，包括：
1. 数据库设计（配置表和日志表）
2. 扣减算法（按比例扣量和扣金额）
3. 前端界面设计（配置管理和统计报表）
4. API接口设计
5. 隐藏扣减策略
6. 实施步骤和注意事项

该方案确保了：
- 扣减配置的灵活性（三个层级，两种方式，可组合）
- 扣减算法的准确性（按比例分配，随机选择）
- 扣减效果的隐蔽性（渠道无法察觉）
- 系统的可追溯性（完整的日志记录）

