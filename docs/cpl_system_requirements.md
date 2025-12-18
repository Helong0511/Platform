# CPL 系统功能需求文档

## 📋 术语定义

### 1.2.1 名称 (Names)
- **Advertiser (广告主)**: 平台的上游
- **Affiliate/Publisher (渠道)**: 平台的下游

### 1.2.2 参数 (Parameters)
- **Click**: CPL 系统中的点击数
- **Conversion**: CPL 系统中上游给平台的转化
- **Postback**: 平台给下游的回调
- **CVR(Advertiser)**: conversion/Click（相同统计维度下）
- **CVR(Affiliate)**: Postback/Click（相同统计维度下）
- **Revenue**: 收入，系统运行中产生的收入金额
- **Payout**: 支出，需要支出的金额
- **Profit**: 利润，收入减去支出之后的金额

### 1.2.3 Offer
- **Offer ID**: offer 在平台中的唯一 ID（系统生成）
- **Advertiser Offer ID**: offer 在上游系统中的唯一 ID
- **Price**: offer 单价
- **Affiliate Price**: 给渠道的价格（扣价后）
- **Offer Name**: offer 名称
- **Country**: offer 所在国家
- **Category**: offer 分类
- **Daily Conversion**: 每日转化数量上限

### 1.2.4 配置
- **Status**: Online/Offline（在线/下线）
- **Discount**: 扣量
  - **Price Discount**: 价格扣量，针对单价进行折扣

---

## 🎯 核心功能模块

### 1. 广告主管理 (Manage Advertisers) - 仅管理员可见

**功能描述：**
- 管理平台的所有广告主（上游）信息

**字段：**
- Advertiser ID（系统生成）
- Advertiser Name
- Email（可选）
- Mobile

**操作：**
- Add（添加 Advertiser）
- Edit（编辑 Advertiser）

---

### 2. 渠道管理 (Manage Affiliates/Publishers) - 仅管理员可见

**功能描述：**
- 管理平台的所有渠道（下游）信息

**字段：**
- Publisher/Affiliate ID（系统生成）
- Publisher/Affiliate Name
- Email（可选）
- Price Discount（渠道级别的扣量）
- Active Advertiser（活跃的广告主数量）

**操作：**
- Add（添加 Publisher）
- Edit（编辑 Publisher）

---

### 3. 上游单子建立 (Upstream Offer Setup)

**功能描述：**
- 创建和管理 Offer（单子）
- 系统自动生成唯一的 Offer ID
- 配置上游和下游的 Tracklink

**关键字段：**
- Offer Name
- ADV Offer ID（上游系统中的 Offer ID）
- Advertiser（下拉选择：Advertiser ID-Advertiser Name）
- Offer ID（系统生成的唯一 ID）
- Preview Link
- PO (Payout) - 上游支付金额
- PO (扣价后) - 扣价后给渠道的金额
- Country
- Type
- Status（Active/Inactive）
- Cap (上游) - 上游转化上限
- Cap (下游) - 下游转化上限
- ADV Tracklink（上游的，不显示给下游，建立单子时配置我们的参数）
- Publisher（下拉可分配给下游）
- 生成给下游的 Tracklink
- Postback（单子建立时把我们的参数配置进去）

**操作：**
- Add（添加 Offer）
- Edit（编辑 Offer）
- 成功添加后，系统自动生成唯一的 offerid，并加入到 offer 库中

---

### 4. Cap 管理 (Manage Cap)

**功能描述：**
- 平台支持对广告主 offer 或分配给单个渠道的 offer 设置 cap 值
- 所有 cap 设置各自独立
- 若平台检测到 offer 的其中一个 Cap 达到上限，则 offer 将会在对应渠道或广告主下线

**Cap 类型：**
1. **Advertiser Offer Cap**（广告主 Offer Cap）
   - 针对特定广告主的特定 offer 在不同渠道设置 Cap
   - Daily Cap：当达到每日上限时，该广告主的所有 offer 在该渠道下线，直到第二天重置
   - Total Cap：当累计达到总上限时，该广告主的所有 offer 在该渠道下线

2. **Offer Cap**（单子 Cap）
   - 针对特定 offer 在不同渠道设置 Cap
   - Daily Cap：当达到每日上限时，该 offer 在该渠道下线，直到第二天重置
   - Total Cap：当累计达到总上限时，该 offer 在该渠道下线

**控制维度：**
- 转化数（conversion）

**操作按钮：**
- MaxCap（默认 Cap 设置）
- Add（添加 Cap）
- Edit（编辑 Cap）
- Delete（删除 Cap）

---

### 5. 扣量管理 (Discount Management)

**功能描述：**
- 平台允许设置 offer 级别的扣量给渠道
- 支持价格扣量（Price Discount）

**扣量类型：**
1. **Offer Discount**（单子扣量）
   - 针对特定 offer 设置扣量比例
   - 优先级最高

2. **Channel Discount**（渠道扣量）
   - 针对整个渠道设置扣量比例
   - 优先级较低

**扣量优先级：**
- Offer discounts > Channel discounts

**操作：**
- Add（添加 Discount）
- Edit（编辑 Discount）
- Delete（删除 Discount）

**添加扣量：**
- 输入 offerid
- 选择对应的渠道
- 填写扣量比例（留空表示无限制）
- 扣量立即生效

---

### 6. 转化总览 (Summary/Conversion Overview)

**功能描述：**
- 展示所有 Offer 的转化统计数据

**字段：**
- Offer ID
- Offer Name
- Advertiser（仅管理员可见）
- Publisher
- Click（点击数）
- Conversion（转化数）
- CR（Conversion Rate，转化率）
- PO（仅管理员可见，上游支付金额）
- PO (扣价后)（给渠道的金额）

**筛选：**
- 可筛选 Offer ID/Advertiser/Publisher

**示例数据：**
- Offer ID: 1
- Offer Name: Dating-SOI
- Advertiser: 1-Macan
- Publisher: 1-My Show
- Click: 71
- Conversion: 2
- CR: 2.82%
- PO (仅管理): $2
- PO (扣价后): $1.80

---

### 7. Conversion Log（转化日志） - 仅管理员可见

**功能描述：**
- 记录所有转化事件的详细信息

**字段：**
- Click ID
- Click Time（点击时间）
- Conversion Time（转化时间）
- Status（Approved/Pending）
- Offer ID
- Offer Name
- Publisher
- IP
- Device
- Country
- Action

**筛选：**
- 可筛选 Offer ID/Publisher/Status

**示例数据：**
- Click ID: 476Tag24r
- Click Time: 2025/12/17 7:00:00
- Conversion Time: 2025/12/17 7:15:00
- Status: Approved/Pending
- Offer ID: 2
- Offer Name: Dating-SO
- Publisher: 3
- Country: US

---

### 8. 上游测试 (Advertiser Test)

**功能描述：**
- 平台提供网盟对接测试工具
- 可以对上游对接情况进行测试
- 得到实时的测试结果

**测试记录字段：**
- Advertiser ID
- Advertiser Name
- Advertiser Offer ID
- Offer Name
- Price
- Country

**操作：**
- Add（添加测试记录）
- Delete（删除测试记录）
- Test（模拟点击测试）

**测试流程：**
1. 点击 Add 按钮，填写平台内的 offerid
2. 添加完成后点击 Test 按钮
3. 系统进行模拟点击测试
4. 显示模拟点击生成的 Click Id 和 Click Url
5. 将 clickid 给上游手动回传
6. 若收到对应转化，则测试成功（该转化在 conversion log 里可见）

**筛选：**
- 可通过 Advertiser 对列表数据进行筛选

---

### 9. 下游测试 (Affiliate Test)

**功能描述：**
- 平台提供渠道对接测试工具
- 可以测试下游渠道的对接情况
- 提供实时的测试结果

**测试记录字段：**
- Affiliate
- Click id
- Offerid
- Offer Name
- Price
- Country
- Platform
- Postback Time
- Status（Send Success/Failed）
- Affiliate Return Content（渠道返回内容）

**操作：**
- Send Postback（发送 Postback）
- Delete（删除测试记录）

**测试流程：**
1. 点击 Send Postback 按钮，弹出测试页面
2. 在 Affiliate 中选择需要测试的渠道
3. 在下游渠道模拟点击请求之后，将得到的 click id 填入输入框
4. 正确填写信息后，点击 Send Postback 按钮
5. 系统自动根据该渠道的 Click，生成一个对应的 Postback
6. 将 Postback 发送给下游渠道
7. 在列表中显示 Status（发送状态，成功或失败）和 Affiliate Return Content（渠道返回内容）
8. 根据渠道返回的详细内容，判断与下游是否对接成功

**筛选：**
- 可通过 Affiliate 对列表数据进行筛选

**注意事项：**
- Click id 应该在 30 分钟内点击

---

## 📊 报表功能

### 报表类型
1. **日报表 (Daily Data)**
2. **渠道报表 (Affiliate Report)**
3. **广告主报表 (Advertiser Report)**
4. **Offer 报表 (Offer Report)**

---

## 🔄 数据流转

### 上游流程
```
上游平台 → 发送 Postback → 系统接收 → 保存 Conversion → 触发下游 Postback
```

### 下游流程
```
用户点击 → 生成 Click ID → 记录点击 → 等待转化 → 发送 Postback 给下游
```

---

## 🎯 关键功能点

1. **点击追踪系统**
   - 生成唯一的 Click ID
   - 记录点击时间、IP、Device、Country 等信息
   - 生成 Tracklink（包含系统参数）

2. **转化追踪**
   - 接收上游的 Conversion
   - 关联到对应的 Click ID
   - 计算转化率（CVR）

3. **Postback 回调**
   - 建立单子时配置 Postback 参数
   - 自动生成下游的 Postback URL
   - 转化后自动发送 Postback 给下游

4. **Cap 限制**
   - 支持 Daily Cap 和 Total Cap
   - 支持 Advertiser Offer Cap 和 Offer Cap
   - 达到上限时自动下线

5. **扣量系统**
   - 支持 Offer 级别和 Channel 级别的扣量
   - 价格扣量（Price Discount）
   - 扣量优先级：Offer > Channel

6. **测试工具**
   - 上游测试：模拟点击，生成 Click ID 和 Click Url
   - 下游测试：手动发送 Postback，查看返回结果

---

## 📝 数据库设计需求

### 需要新增的表

1. **advertisers**（广告主表）
2. **publishers/affiliates**（渠道表）
3. **offers**（单子表）
4. **clicks**（点击记录表）
5. **offer_caps**（Cap 配置表）
6. **offer_discounts**（扣量配置表）
7. **advertiser_tests**（上游测试记录表）
8. **affiliate_tests**（下游测试记录表）

### 需要修改的表

1. **postback_conversions**（需要关联 Click ID）
2. **products**（可能需要重命名为 offers 或添加映射）

---

## ⚠️ 与当前系统的差异

### 当前系统
- Client（客户） = 下游
- Product（产品） = 单子
- 没有明确的 Advertiser（广告主）概念
- 没有 Click 追踪系统
- 没有 Cap 管理
- 没有 Discount 管理
- 没有测试工具

### 需要改动
1. 引入 Advertiser（广告主）概念
2. 引入 Publisher/Affiliate（渠道）概念
3. 建立 Click 追踪系统
4. 实现 Cap 管理功能
5. 实现 Discount 管理功能
6. 实现测试工具（上游测试和下游测试）
7. 修改 Offer/Product 模型，添加更多字段
8. 实现 Tracklink 生成功能
9. 实现 Postback 参数配置功能

