# CPL 系统 - 完整实施文档

## 📋 概述

CPL（Cost Per Lead）系统是一个完整的 Postback 管理中间商系统，支持上游广告平台和下游渠道的完整对接流程。

## 🎯 核心功能

### 1. 基础管理
- **广告主管理**：管理上游广告主信息
- **渠道管理**：管理下游渠道信息
- **Offer管理**：管理单子（Offer）信息，支持渠道分配

### 2. 业务规则
- **Cap管理**：支持每日Cap和总Cap限制
- **扣量管理**：支持Offer级别和Channel级别的扣量配置

### 3. 追踪系统
- **点击追踪**：自动生成Click ID，记录点击信息
- **Tracklink生成**：自动生成上游和下游Tracklink

### 4. 测试工具
- **上游测试**：测试与上游平台的对接
- **下游测试**：测试与下游渠道的对接

### 5. 统计和日志
- **转化总览**：统计点击、转化、转化率、支付金额
- **转化日志**：查看详细的转化记录，支持筛选和状态管理

---

## 🚀 快速开始

### 1. 数据库迁移

```bash
# 备份数据库
mysqldump -u username -p platform > platform_backup_$(date +%Y%m%d).sql

# 执行迁移脚本
mysql -u username -p platform < scripts/data/cpl_system_tables.sql
mysql -u username -p platform < scripts/data/alter_postback_conversions_table.sql

# 验证表结构
mysql -u username -p platform < scripts/verify_cpl_tables.sql
```

### 2. 重启应用

```bash
sudo systemctl restart your-app-service
```

### 3. 验证安装

```bash
# 运行测试脚本
python scripts/test_cpl_system.py
```

### 4. 访问系统

1. 登录系统
2. 在侧边栏找到 "CPL系统" 菜单
3. 开始使用各项功能

---

## 📚 文档索引

### 功能文档
- [`cpl_system_requirements.md`](./cpl_system_requirements.md) - 功能需求详细说明
- [`cpl_system_changes_required.md`](./cpl_system_changes_required.md) - 改动需求清单

### 实施文档
- [`cpl_system_implementation_summary.md`](./cpl_system_implementation_summary.md) - 实施总结
- [`cpl_system_final_summary.md`](./cpl_system_final_summary.md) - 最终完成总结
- [`cpl_system_complete_checklist.md`](./cpl_system_complete_checklist.md) - 完整检查清单

### 操作文档
- [`cpl_system_deployment_guide.md`](./cpl_system_deployment_guide.md) - 详细部署指南
- [`cpl_system_quick_start.md`](./cpl_system_quick_start.md) - 快速开始指南

---

## 🏗️ 系统架构

### 数据流

```
上游平台 → 点击追踪 → Click记录 → Postback回调 → Cap检查 → 扣量计算 → 转化记录 → 下游转发
```

### 核心模块

1. **追踪模块** (`app/core/tracking/`)
   - Click ID 生成
   - Tracklink 生成

2. **Cap管理模块** (`app/core/cap/`)
   - Cap 检查
   - Cap 计数
   - 每日重置

3. **扣量管理模块** (`app/core/discount/`)
   - 扣量计算
   - 优先级处理

4. **Postback处理模块** (`app/core/postback/`)
   - 数据验证
   - 标准化处理
   - Cap和扣量集成

---

## 📊 数据模型关系

```
Advertiser (广告主)
    ↓
Offer (单子)
    ↓
OfferPublisherAssignment (分配)
    ↓
Publisher (渠道)
    ↓
Click (点击记录)
    ↓
PostbackConversion (转化记录)

OfferCap (Cap配置) → Offer
OfferDiscount (扣量配置) → Offer + Publisher
```

---

## 🔧 配置说明

### 追踪基础URL

在 `app/core/config.py` 中配置：
```python
TRACKING_BASE_URL = "https://client.btfrx.online"
```

### 定时任务

系统会自动注册以下定时任务：
- **每日Cap重置**：每天 00:00 UTC 执行

可在"定时任务管理"页面查看和管理。

---

## 🧪 测试建议

### 1. 基础功能测试
- [ ] 创建广告主
- [ ] 创建渠道
- [ ] 创建Offer
- [ ] 配置Cap
- [ ] 配置扣量

### 2. 业务逻辑测试
- [ ] 测试点击追踪
- [ ] 测试Cap限制
- [ ] 测试扣量计算
- [ ] 测试Postback处理

### 3. 完整流程测试
- [ ] 创建完整的数据链路
- [ ] 模拟点击和转化
- [ ] 验证统计和日志

---

## ⚠️ 注意事项

1. **数据映射**：当前系统使用 `product_id`，新系统使用 `offer_id`，需要建立映射关系

2. **Click ID提取**：Postback处理时会从 `our_click_id` 或 `click_id` 字段提取，如果上游使用其他字段名，需要在handler中适配

3. **Cap策略**：当前实现达到Cap时仍保存转化，如需拒绝可修改代码

4. **定时任务**：确保定时任务系统正常运行，否则每日Cap重置不会执行

---

## 🐛 故障排查

### 问题：前端页面无法访问
- 检查路由配置
- 检查菜单配置
- 查看浏览器控制台错误

### 问题：API返回404
- 检查API路由注册
- 检查后端服务状态
- 查看后端日志

### 问题：数据库字段不存在
- 重新执行迁移脚本
- 检查脚本执行日志
- 使用验证脚本检查

### 问题：Cap检查不生效
- 检查Cap配置是否正确
- 检查Cap检查逻辑是否被调用
- 查看日志中的Cap相关错误

---

## 📞 支持

如遇到问题：
1. 查看日志文件：`logs/app.log`
2. 运行测试脚本：`python scripts/test_cpl_system.py`
3. 检查数据库：`mysql -u username -p platform < scripts/verify_cpl_tables.sql`

---

## 📝 更新日志

### 2025-12-17
- ✅ 完成所有代码实现
- ✅ 完成所有文档编写
- ⏳ 待执行数据库迁移和测试

---

**最后更新**: 2025-12-17

