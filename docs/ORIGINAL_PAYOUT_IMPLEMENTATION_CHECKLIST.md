# Original Payout (PO) 和扣后 Payout (PO(扣)) 实现检查清单

## 概述
本次更新为 postback 数据添加了原始 payout (PO) 和扣后 payout (PO(扣)) 两个字段，确保系统能够同时记录和显示原始金额和扣量后的金额。

## 数据库层 ✅

### 1. 数据库模型 (`app/models/models.py`)
- ✅ 添加了 `original_payout` 字段（原始支付金额 PO）
- ✅ 更新了 `payout` 字段注释（扣后支付金额 PO(扣)）
- ✅ 字段位置：在 `event_value` 之后

### 2. 数据库迁移脚本 (`scripts/data/migration_add_original_payout.sql`)
- ✅ 创建了迁移脚本
- ✅ 添加 `original_payout` 字段
- ✅ 将旧数据的 `payout` 值复制到 `original_payout`（向后兼容）

## 后端处理层 ✅

### 3. Postback 处理器 (`app/core/postback/processor.py`)
- ✅ 保存原始 payout 到 `original_payout` 字段
- ✅ 保存扣后 payout 到 `payout` 字段
- ✅ 更新日志输出，显示原始和扣后的 payout
- ✅ 逻辑：`original_payout = normalized_data.get("payout")` → 扣量计算 → `payout = final_payout`

### 4. Schema 定义 (`app/schemas/postback.py`)
- ✅ `PostbackConversionResponse` 添加 `original_payout` 字段
- ✅ `PostbackStatsResponse` 添加 `total_original_payout` 字段
- ✅ 字段描述清晰（原始支付金额（PO）和扣后支付金额（PO(扣)））

### 5. 下游转发 (`app/core/postback/forwarder.py`)
- ✅ 支持 `{original_payout}` URL 占位符
- ✅ POST 请求数据包含 `original_payout` 字段
- ✅ 更新注释说明支持的占位符

### 6. 转化日志 API (`app/api/api_v1/endpoints/conversion_log.py`)
- ✅ 返回数据包含 `original_payout` 字段

### 7. 转化统计 API (`app/api/api_v1/endpoints/conversion_summary.py`)
- ✅ PO 统计使用 `original_payout`（原始总金额）
- ✅ PO（扣价后）使用 `payout`（扣后总金额）
- ✅ 修复了重复计算扣量的逻辑（直接使用已存储的扣后 payout）

### 8. Postback 统计 API (`app/api/api_v1/endpoints/postback.py`)
- ✅ 添加 `total_original_payout` 统计查询
- ✅ 响应包含 `total_original_payout` 字段

### 9. 通知系统 (`app/core/postback/notifier.py`)
- ✅ 单条通知显示原始和扣后收益
- ✅ 汇总通知显示原始和扣后总收益
- ✅ 平台统计显示原始和扣后金额

## 前端显示层 ✅

### 10. Postback 管理页面 (`frontend/src/views/admin/PostbackManagement.vue`)
- ✅ 表格添加"原始支付金额 (PO)"列
- ✅ 表格保留"扣后支付金额 (PO(扣))"列
- ✅ 详情对话框显示两个字段
- ✅ 统计卡片显示原始和扣后总金额

### 11. 转化日志页面 (`frontend/src/views/admin/ConversionLog.vue`)
- ✅ 表格添加"原始支付金额 (PO)"列
- ✅ 表格保留"扣后支付金额 (PO(扣))"列

### 12. 转化总览页面 (`frontend/src/views/admin/ConversionSummary.vue`)
- ✅ 已正确显示 PO 和 PO(扣)（使用后端返回的数据）

### 13. API 调用层
- ✅ `frontend/src/api/postback.js` - 无需修改（自动接收新字段）
- ✅ `frontend/src/api/conversionLog.js` - 无需修改（自动接收新字段）
- ✅ `frontend/src/api/conversionSummary.js` - 无需修改（自动接收新字段）

## 字段说明

### 字段定义
- **`original_payout` (PO)**: 原始支付金额，从上游平台收到的原始金额
- **`payout` (PO(扣))**: 扣后支付金额，应用扣量后的实际金额

### 使用场景

1. **统计查询**：
   - PO 统计 → 使用 `original_payout`
   - PO（扣价后）统计 → 使用 `payout`

2. **下游转发**：
   - URL 占位符：`{original_payout}` 和 `{payout}`
   - POST 数据：包含两个字段

3. **通知消息**：
   - 显示原始和扣后金额

4. **API 响应**：
   - 所有相关接口返回两个字段

5. **前端显示**：
   - 表格和详情页面显示两个字段

## 向后兼容性

- ✅ 旧数据的 `payout` 值会复制到 `original_payout`
- ✅ 如果旧数据中 `payout` 已经是扣后的，迁移脚本会正确处理
- ✅ API 响应保持向后兼容（新字段为可选）

## 测试建议

1. **数据库迁移测试**：
   - 运行迁移脚本
   - 验证字段添加成功
   - 验证旧数据迁移正确

2. **后端 API 测试**：
   - 测试 postback 接收，验证两个字段都保存
   - 测试统计查询，验证使用正确的字段
   - 测试下游转发，验证占位符替换正确

3. **前端显示测试**：
   - 验证表格显示两个字段
   - 验证详情对话框显示两个字段
   - 验证统计卡片显示正确

## 注意事项

1. **数据库迁移**：必须先运行 `scripts/data/migration_add_original_payout.sql`
2. **字段逻辑**：确保所有统计和计算使用正确的字段
3. **前端显示**：确保用户能清楚区分原始和扣后金额

## 完成状态

✅ 所有后端代码已更新
✅ 所有前端代码已更新
✅ 数据库迁移脚本已创建
✅ 无 linter 错误
✅ 向后兼容性已考虑

