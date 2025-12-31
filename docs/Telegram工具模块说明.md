# Telegram 工具模块说明

## 📦 新增模块

### `app/core/telegram_utils.py`

提供 Telegram 消息处理的实用工具函数，统一管理消息格式化、分割、验证等功能。

---

## 🔧 功能列表

### 1. `truncate_message(message, max_length=4096)`

**功能**: 截断消息，确保不超过 Telegram 的最大长度限制

**参数**:
- `message`: 原始消息
- `max_length`: 最大长度（默认 4096）

**返回**: 截断后的消息

**示例**:
```python
from app.core.telegram_utils import truncate_message

long_message = "..." * 5000  # 超长消息
truncated = truncate_message(long_message)
# 自动截断并添加提示信息
```

---

### 2. `split_long_message(message, max_length=4096)`

**功能**: 将长消息分割为多条消息

**参数**:
- `message`: 原始消息
- `max_length`: 每条消息的最大长度（默认 4096）

**返回**: 消息列表（如果不需要分割，返回包含一条消息的列表）

**示例**:
```python
from app.core.telegram_utils import split_long_message

long_message = "..." * 5000  # 超长消息
messages = split_long_message(long_message)
# 返回多条消息，每条消息都有序号标记
# ["📄 消息 1/2\n\n...", "📄 消息 2/2\n\n..."]
```

**特性**:
- 按行分割，保持消息完整性
- 自动添加序号标记
- 单行过长时自动截断

---

### 3. `format_telegram_message(title, fields=None, footer=None, max_length=4096)`

**功能**: 格式化 Telegram 消息（统一格式）

**参数**:
- `title`: 消息标题（带 emoji）
- `fields`: 字段字典 `{key: value}`
- `footer`: 页脚信息
- `max_length`: 最大长度

**返回**: 格式化后的消息

**示例**:
```python
from app.core.telegram_utils import format_telegram_message

message = format_telegram_message(
    title="🔔 通知标题",
    fields={
        "用户": "张三",
        "操作": "创建订单",
        "金额": "$100.00"
    },
    footer="时间: 2024-01-01 12:00:00"
)
```

**输出**:
```
🔔 通知标题

用户: 张三
操作: 创建订单
金额: $100.00

时间: 2024-01-01 12:00:00
```

---

### 4. `validate_chat_id(chat_id)`

**功能**: 验证 Telegram Chat ID 格式

**参数**:
- `chat_id`: Chat ID 字符串

**返回**: 是否有效（bool）

**示例**:
```python
from app.core.telegram_utils import validate_chat_id

# 用户 ID
validate_chat_id("123456789")  # True

# 群组 ID
validate_chat_id("-1001234567890")  # True

# 无效格式
validate_chat_id("abc123")  # False
```

---

### 5. `escape_markdown_v2(text)`

**功能**: 转义 Markdown V2 特殊字符

**参数**:
- `text`: 原始文本

**返回**: 转义后的文本

**示例**:
```python
from app.core.telegram_utils import escape_markdown_v2

text = "Hello (world)!"
escaped = escape_markdown_v2(text)
# "Hello \\(world\\)!"
```

---

### 6. `format_key_value_pairs(data, max_value_length=150)`

**功能**: 格式化键值对为消息文本

**参数**:
- `data`: 数据字典
- `max_value_length`: 单个值的最大长度

**返回**: 格式化后的文本

**示例**:
```python
from app.core.telegram_utils import format_key_value_pairs

data = {
    "clk_id": "12345",
    "event_name": "conversion",
    "amount": "$100.00"
}

formatted = format_key_value_pairs(data)
# • amount: $100.00
# • clk_id: 12345
# • event_name: conversion
```

---

## 📊 常量定义

### `MAX_TELEGRAM_MESSAGE_LENGTH`
Telegram 消息最大长度（4096 字符）

### `TRUNCATE_NOTICE_LENGTH`
消息截断时保留的提示信息长度（100 字符）

---

## 🔄 已更新的代码

### 1. `app/core/auto_bot.py`
- ✅ 使用 `truncate_message` 函数替代内联截断逻辑
- ✅ 导入 `MAX_TELEGRAM_MESSAGE_LENGTH` 常量

### 2. `app/api/api_v1/endpoints/bft_postback.py`
- ✅ 使用 `truncate_message` 函数替代内联截断逻辑

---

## 💡 使用建议

### 1. 统一使用工具函数
所有需要处理 Telegram 消息的地方，建议使用工具函数：

```python
from app.core.telegram_utils import (
    truncate_message,
    split_long_message,
    format_telegram_message,
    format_key_value_pairs
)
```

### 2. 消息格式化
使用 `format_telegram_message` 统一消息格式：

```python
message = format_telegram_message(
    title="🔔 通知",
    fields={"字段1": "值1", "字段2": "值2"},
    footer="时间: 2024-01-01"
)
```

### 3. 长消息处理
对于可能很长的消息，使用 `split_long_message`：

```python
messages = split_long_message(long_message)
for msg in messages:
    await send_telegram_message(msg)
```

---

## 🎯 优势

1. **代码复用**: 避免重复的消息处理逻辑
2. **统一格式**: 所有消息使用统一的格式化函数
3. **易于维护**: 集中管理消息处理逻辑
4. **功能扩展**: 可以轻松添加新功能（如 Markdown 支持）

---

## 📝 后续扩展

可以考虑添加以下功能：

1. **Markdown 支持**: 支持 Markdown 格式的消息
2. **HTML 支持**: 支持 HTML 格式的消息
3. **消息模板**: 支持消息模板系统
4. **通知频率控制**: 添加通知频率限制功能

---

**创建时间**: 2024年
**状态**: ✅ 已完成

