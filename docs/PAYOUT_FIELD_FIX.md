# Payout 字段提取修复说明

## 问题描述
收到 Postback 数据后，原始支付金额 (PO) 【PayOut】没有保存。

## 问题原因
上游平台可能使用不同的字段名发送 payout 数据：
- `payout` (小写)
- `PayOut` (驼峰命名)
- `pay_out` (下划线)
- `pay-out` (连字符)
- `Payout` (首字母大写)
- `PAYOUT` (全大写)

原来的代码只检查 `payout` 字段，导致其他字段名的数据无法被提取。

## 修复方案

### 1. Handler 层修复
修改了 `macan_handler.py` 和 `bft_handler.py`，在 `normalize` 方法中支持多种字段名：

```python
# 处理 payout（支持多种字段名：payout, PayOut, pay_out, pay-out 等）
payout = (
    data.get("payout") or
    data.get("PayOut") or
    data.get("pay_out") or
    data.get("pay-out") or
    data.get("Pay_Out") or
    data.get("Payout") or
    data.get("PAYOUT")
)
```

### 2. Processor 层修复
在 `processor.py` 中添加了备用逻辑，如果 handler 没有提取到 payout，会从原始数据中再次尝试：

```python
original_payout = normalized_data.get("payout")
if original_payout is None:
    # 尝试从原始数据中获取（支持多种字段名）
    original_payout = (
        raw_data.get("payout") or
        raw_data.get("PayOut") or
        raw_data.get("pay_out") or
        # ... 其他变体
    )
    # 转换和更新逻辑
```

### 3. GET 请求修复
在 `postback.py` 的 GET 请求处理中，也添加了多种字段名支持：

```python
# 处理 payout（支持多种字段名）
payout_float = _to_float(payout)
if payout_float is None:
    # 尝试从查询参数中获取其他字段名
    query_params = dict(request.query_params)
    payout_float = (
        _to_float(query_params.get("PayOut")) or
        _to_float(query_params.get("pay_out")) or
        # ... 其他变体
    )
```

### 4. 调试日志
添加了警告日志，当 original_payout 为 None 时记录：

```python
if original_payout is None:
    logger.warning(
        f"警告：转化记录缺少原始 payout (PO): conversion_id={conversion_id}, "
        f"platform={platform}, raw_data_keys={list(raw_data.keys())}"
    )
```

## 支持的字段名变体

| 字段名 | 说明 |
|--------|------|
| `payout` | 标准小写（默认） |
| `PayOut` | 驼峰命名 |
| `pay_out` | 下划线命名 |
| `pay-out` | 连字符命名 |
| `Pay_Out` | 混合命名 |
| `Payout` | 首字母大写 |
| `PAYOUT` | 全大写 |

## 处理流程

1. **Handler 标准化阶段**：
   - 尝试从原始数据中提取多种字段名
   - 转换为浮点数
   - 放入 `normalized_data["payout"]`

2. **Processor 备用提取阶段**：
   - 如果 `normalized_data` 中没有 payout
   - 从 `raw_data` 中尝试多种字段名
   - 转换并更新到 `normalized_data`

3. **保存阶段**：
   - 使用 `original_payout` 保存原始金额
   - 使用 `payout` 保存扣后金额
   - 如果为 None，记录警告日志

## 测试建议

1. **测试不同字段名**：
   - 发送 `payout=10.5` 的请求
   - 发送 `PayOut=10.5` 的请求
   - 发送 `pay_out=10.5` 的请求
   - 验证都能正确保存

2. **检查日志**：
   - 查看是否有警告日志
   - 确认 payout 是否正确提取

3. **验证数据库**：
   - 检查 `original_payout` 字段是否有值
   - 检查 `payout` 字段是否正确

## 修改的文件

1. `app/core/postback/macan_handler.py` - 支持多种 payout 字段名
2. `app/core/postback/bft_handler.py` - 支持多种 payout 字段名
3. `app/core/postback/processor.py` - 添加备用提取逻辑和警告日志
4. `app/api/api_v1/endpoints/postback.py` - GET 请求支持多种字段名

## 注意事项

- 字段名匹配优先级：按代码中的顺序，第一个匹配到的值会被使用
- 如果所有字段名都找不到，`original_payout` 将为 `None`，会记录警告日志
- 字符串值会自动转换为浮点数
- 无效的数值（无法转换为 float）会被忽略

