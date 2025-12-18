# CPL 系统 - 快速参考

## 🚀 快速开始

### 1. 部署
```bash
# 使用部署脚本（推荐）
python scripts/deploy_cpl_system.py

# 或手动部署
mysqldump -u username -p platform > backup.sql
mysql -u username -p platform < scripts/data/cpl_system_tables.sql
mysql -u username -p platform < scripts/data/alter_postback_conversions_table.sql
```

### 2. 验证
```bash
# 验证代码
python scripts/test_cpl_system.py

# 验证数据库
mysql -u username -p platform < scripts/verify_cpl_tables.sql
```

### 3. 重启
```bash
sudo systemctl restart your-app-service
```

---

## 📚 文档索引

| 文档 | 说明 |
|------|------|
| [`docs/cpl_system_final_delivery.md`](docs/cpl_system_final_delivery.md) | **最终交付文档**（从这里开始） |
| [`docs/cpl_system_readme.md`](docs/cpl_system_readme.md) | 系统总览 |
| [`docs/cpl_system_quick_start.md`](docs/cpl_system_quick_start.md) | 快速开始指南 |
| [`docs/cpl_system_deployment_guide.md`](docs/cpl_system_deployment_guide.md) | 详细部署指南 |
| [`docs/cpl_system_deployment_checklist.md`](docs/cpl_system_deployment_checklist.md) | 部署检查清单 |
| [`docs/cpl_system_requirements.md`](docs/cpl_system_requirements.md) | 功能需求文档 |
| [`docs/cpl_system_changes_required.md`](docs/cpl_system_changes_required.md) | 改动需求清单 |
| [`docs/cpl_system_complete_checklist.md`](docs/cpl_system_complete_checklist.md) | 完整检查清单 |

---

## 🎯 核心功能

- ✅ **广告主管理** - 管理上游广告主
- ✅ **渠道管理** - 管理下游渠道
- ✅ **Offer管理** - 管理单子，支持渠道分配
- ✅ **Cap管理** - 每日Cap和总Cap限制
- ✅ **扣量管理** - Offer级别和Channel级别扣量
- ✅ **点击追踪** - 自动生成Click ID和Tracklink
- ✅ **上游测试** - 测试与上游平台对接
- ✅ **下游测试** - 测试与下游渠道对接
- ✅ **转化统计** - 转化总览和详细日志

---

## 📊 系统架构

```
上游平台 → 点击追踪 → Click记录 → Postback回调 → Cap检查 → 扣量计算 → 转化记录 → 下游转发
```

---

## 🔧 配置

### 追踪基础URL
在 `app/core/config.py` 中配置：
```python
TRACKING_BASE_URL = "https://client.btfrx.online"
```

### 定时任务
- **每日Cap重置**：每天 00:00 UTC 执行

---

## 🐛 故障排查

| 问题 | 解决方案 |
|------|----------|
| 前端页面404 | 检查路由和菜单配置 |
| API返回404 | 检查API路由注册 |
| 数据库字段不存在 | 重新执行迁移脚本 |
| Cap检查不生效 | 检查Cap配置和日志 |

详细排查步骤请参考 [`docs/cpl_system_deployment_checklist.md`](docs/cpl_system_deployment_checklist.md)

---

## 📞 支持

- 查看文档：`docs/cpl_system_*.md`
- 运行测试：`python scripts/test_cpl_system.py`
- 验证数据库：`mysql -u username -p platform < scripts/verify_cpl_tables.sql`

---

**版本**: v1.0  
**日期**: 2025-12-17  
**状态**: ✅ 已完成

