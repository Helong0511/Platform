# CPL 系统快速开始指南

## 🚀 快速部署（5分钟）

### 步骤1：备份数据库（1分钟）
```bash
mysqldump -u username -p platform > platform_backup_$(date +%Y%m%d).sql
```

### 步骤2：执行数据库迁移（2分钟）
```bash
# 创建新表
mysql -u username -p platform < scripts/data/cpl_system_tables.sql

# 修改现有表
mysql -u username -p platform < scripts/data/alter_postback_conversions_table.sql
```

### 步骤3：重启应用（1分钟）
```bash
# 根据你的部署方式重启
sudo systemctl restart your-app-service
# 或
supervisorctl restart your-app
```

### 步骤4：验证功能（1分钟）
1. 登录系统
2. 检查侧边栏是否有 "CPL系统" 菜单
3. 访问"广告主管理"页面，尝试创建一个测试广告主

---

## 📖 基本使用流程

### 1. 创建广告主
- 访问：**CPL系统 > 广告主管理**
- 点击"添加广告主"
- 填写广告主名称等信息
- 保存

### 2. 创建渠道
- 访问：**CPL系统 > 渠道管理**
- 点击"添加渠道"
- 填写渠道名称、扣量比例等信息
- 保存

### 3. 创建Offer
- 访问：**CPL系统 > Offer管理**
- 点击"添加Offer"
- 选择广告主
- 填写Offer信息（名称、价格、国家等）
- 配置上游Tracklink
- 分配渠道
- 保存（系统会自动生成下游Tracklink和Postback URL）

### 4. 配置Cap（可选）
- 访问：**CPL系统 > Cap管理**
- 点击"添加Cap配置"
- 选择Cap类型（offer 或 advertiser_offer）
- 选择Offer和渠道
- 设置每日Cap和总Cap
- 保存

### 5. 配置扣量（可选）
- 访问：**CPL系统 > 扣量管理**
- 点击"添加扣量配置"
- 选择扣量类型（offer 或 channel）
- 选择Offer和渠道
- 设置扣量比例（0-100%）
- 保存

### 6. 测试上游对接
- 访问：**CPL系统 > 上游测试**
- 点击"创建测试"
- 选择广告主和Offer
- 系统自动生成 Click ID 和 Click Url
- 将 Click ID 手动传给上游
- 等待上游回传转化

### 7. 测试下游对接
- 访问：**CPL系统 > 下游测试**
- 点击"创建测试"
- 选择渠道和Offer
- 输入下游提供的 Click ID
- 系统自动发送Postback并显示返回内容

### 8. 查看统计
- 访问：**CPL系统 > 转化总览**
- 选择日期范围
- 查看总点击、总转化、转化率、总支付等统计
- 查看按Offer的详细统计

### 9. 查看日志
- 访问：**CPL系统 > 转化日志**
- 使用筛选条件查找特定转化记录
- 可以更新转化状态（Approved/Pending）

---

## 🔑 关键概念

### Click ID
- 系统自动生成的唯一标识
- 用于追踪点击和关联转化
- 格式：32位随机字符串（排除易混淆字符）

### Tracklink
- **上游Tracklink**：给上游平台的链接，包含我们的参数
- **下游Tracklink**：给下游渠道的链接，用于点击追踪

### Cap（上限）
- **每日Cap**：每天允许的最大转化数
- **总Cap**：总共允许的最大转化数
- 达到Cap后，系统会记录日志（可选择拒绝转化）

### 扣量
- **优先级**：offer级别 > channel级别 > 渠道默认
- **计算方式**：原始金额 × (1 - 扣量比例%)
- 扣量后的金额会保存到转化记录的 `payout` 字段

---

## 💡 常见问题

### Q: 如何查看生成的Tracklink？
A: 在Offer管理页面，编辑Offer可以看到"下游Tracklink"字段。

### Q: Cap达到上限后转化会被拒绝吗？
A: 当前实现：转化仍然保存，但会记录警告日志。如需拒绝，可修改代码。

### Q: 扣量如何计算？
A: 系统按优先级查找扣量配置，找到第一个匹配的配置后应用扣量。

### Q: 如何重置每日Cap计数？
A: 系统会自动在每天00:00 UTC执行重置任务。也可手动在定时任务管理中执行。

### Q: Click ID在哪里使用？
A: Click ID会在点击追踪时生成，并在Postback回调时通过 `our_click_id` 参数传递回来。

---

## 📚 更多文档

- `docs/cpl_system_requirements.md` - 功能需求文档
- `docs/cpl_system_changes_required.md` - 改动需求清单
- `docs/cpl_system_implementation_summary.md` - 实施总结
- `docs/cpl_system_final_summary.md` - 最终完成总结
- `docs/cpl_system_deployment_guide.md` - 部署指南

---

**最后更新**: 2025-12-17

