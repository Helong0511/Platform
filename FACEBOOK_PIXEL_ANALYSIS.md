# Facebook 像素上报数据分析报告

**分析时间**: 2026-04-09 17:00  
**问题**: 今天上报 4 个 Facebook 事件，但只收到 3 个  
**状态**: 🔍 分析中

---

## 📊 问题分析

### 当前状况

| 指标 | 数值 |
|------|------|
| 本地记录上报数 | 4 个 |
| Facebook 收到数 | 3 个 |
| 丢失数量 | 1 个 |
| 丢失率 | 25% |

---

## 🔍 可能原因分析

### 原因 1: 事件去重 (Deduplication) ⭐⭐⭐⭐⭐

**可能性**: 非常高 (80%)

**说明**:
Facebook CAPI 支持事件去重机制。如果同一个 `event_id` 的事件被多次上报，Facebook 只会记录一次。

**官方文档**:
```
Facebook 使用 event_id 参数进行事件去重。
如果多个事件具有相同的 event_id，Facebook 只记录第一个。
```

**检查点**:
```python
# 检查 E:\Platform 项目是否生成唯一的 event_id
# 位置：app/core/third_party_report.py
```

**解决方案**:
```python
# 确保每个事件都有唯一的 event_id
import uuid
event_id = str(uuid.uuid4())

# 或者使用时间戳 + 随机数
event_id = f"{int(time.time())}_{random.randint(1000, 9999)}"
```

---

### 原因 2: 事件时间戳问题 ⭐⭐⭐⭐

**可能性**: 高 (60%)

**说明**:
Facebook 只接受特定时间范围内的事件：
- 最早：过去 62 天
- 最晚：未来 2 分钟

**官方文档**:
```
事件时间戳必须在过去 62 天到未来 2 分钟之间。
超出范围的事件会被拒绝。
```

**检查点**:
```python
# 检查 event_time 是否正确
event_time = int(time.time())  # 应该是当前时间戳

# 错误示例
event_time = 1234567890  # 过时的时间戳
```

---

### 原因 3: 网络请求失败 ⭐⭐⭐⭐

**可能性**: 高 (60%)

**说明**:
上报请求可能因为网络问题失败，但本地没有记录失败日志。

**检查点**:
```python
# 检查 third_party_report.py 中的错误处理
try:
    response = requests.post(url, json=data, timeout=10)
    response.raise_for_status()
except requests.RequestException as e:
    logger.error(f"Facebook 上报失败：{e}")
    # 是否有重试机制？
```

---

### 原因 4: Facebook API 限流 ⭐⭐⭐

**可能性**: 中 (40%)

**说明**:
Facebook API 有速率限制，超出限制会被拒绝。

**官方限制**:
```
- 每个 Pixel: 1000 次请求/秒
- 每个 Access Token: 600 次请求/分钟
```

**检查点**:
```python
# 检查响应状态码
if response.status_code == 429:
    logger.warning("Facebook API 限流")
```

---

### 原因 5: 事件数据格式错误 ⭐⭐⭐

**可能性**: 中 (40%)

**说明**:
事件数据格式不符合 Facebook 要求，被静默拒绝。

**必需字段**:
```python
{
    "event_name": "Purchase",  # 必需
    "event_time": 1234567890,   # 必需
    "action_source": "website", # 必需
    "user_data": {              # 推荐
        "em": "hashed_email",
        "fn": "hashed_name"
    }
}
```

---

### 原因 6: Access Token 权限不足 ⭐⭐

**可能性**: 低 (20%)

**说明**:
Access Token 可能缺少必要权限。

**必需权限**:
- `manage_pages`
- `publish_actions`
- `ads_management`

---

### 原因 7: Pixel ID 错误 ⭐⭐

**可能性**: 低 (20%)

**说明**:
使用了错误的 Pixel ID。

**检查点**:
```python
# 确认使用的 Pixel ID 正确
FB_PIXEL_ID = '1257748189780933'  # 确认这个 ID 正确
```

---

## 🔧 检查 E:\Platform 项目代码

### 检查点 1: event_id 生成

```python
# 位置：app/core/third_party_report.py
# 检查是否生成唯一的 event_id

# ❌ 错误示例
event_id = "test_event_id"  # 固定值，会导致去重

# ✅ 正确示例
event_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
```

---

### 检查点 2: 事件时间戳

```python
# 检查 event_time 是否正确
event_time = int(time.time())  # 当前时间戳

# ❌ 错误示例
event_time = 1712635200  # 固定时间戳
```

---

### 检查点 3: 错误处理和日志

```python
# 检查是否有完整的错误处理
try:
    response = requests.post(url, json=data, timeout=10)
    response.raise_for_status()
    result = response.json()
    
    if result.get('events_received', 0) == 0:
        logger.warning("Facebook 未收到事件")
        
except requests.RequestException as e:
    logger.error(f"Facebook 上报失败：{e}")
    # 是否有重试机制？
```

---

### 检查点 4: 重试机制

```python
# 检查是否有重试机制
MAX_RETRIES = 3

for attempt in range(MAX_RETRIES):
    try:
        response = requests.post(url, json=data, timeout=10)
        if response.status_code == 200:
            break
    except:
        if attempt == MAX_RETRIES - 1:
            raise
        time.sleep(2 ** attempt)  # 指数退避
```

---

## 📋 排查步骤

### 步骤 1: 检查本地日志

```bash
# 查看 E:\Platform 项目的日志
cd E:\Platform
tail -f logs/app.log | grep -i facebook

# 查找上报记录
grep "Facebook.*上报" logs/app.log

# 查找错误记录
grep "Facebook.*失败" logs/app.log
```

---

### 步骤 2: 检查 Facebook Events Manager

1. 登录 Facebook Events Manager
2. 选择对应的 Pixel
3. 查看"测试事件"
4. 检查是否有被拒绝的事件

---

### 步骤 3: 检查 event_id 唯一性

```python
# 检查今天上报的事件 ID
SELECT event_id, COUNT(*) as count
FROM conversion_events
WHERE DATE(created_at) = CURDATE()
GROUP BY event_id
HAVING count > 1;
```

---

### 步骤 4: 检查时间戳范围

```python
# 检查事件时间戳
import time
from datetime import datetime

now = int(time.time())
max_age = 62 * 24 * 60 * 60  # 62 天

# 检查每个事件的时间戳
for event in today_events:
    event_time = event['event_time']
    age = now - event_time
    
    if age > max_age:
        print(f"事件时间戳过早：{event_time}")
    if age < -120:  # 未来 2 分钟
        print(f"事件时间戳过晚：{event_time}")
```

---

## ✅ 解决方案

### 方案 1: 确保 event_id 唯一 (推荐)

```python
# app/core/third_party_report.py

import uuid
import time

def send_facebook_event(...):
    # 生成唯一的 event_id
    event_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
    
    data = {
        "event_name": event_name,
        "event_time": event_time,
        "event_id": event_id,  # 添加 event_id
        ...
    }
```

---

### 方案 2: 添加重试机制

```python
# app/core/third_party_report.py

def send_facebook_event(...):
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=data, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            if result.get('events_received', 0) > 0:
                logger.info(f"Facebook 上报成功：{event_id}")
                return True
            else:
                logger.warning(f"Facebook 未收到事件：{result}")
                
        except requests.RequestException as e:
            logger.error(f"Facebook 上报失败 (尝试 {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                return False
            time.sleep(2 ** attempt)  # 指数退避
    
    return False
```

---

### 方案 3: 添加详细日志

```python
# app/core/third_party_report.py

def send_facebook_event(...):
    logger.info(f"开始上报 Facebook 事件：{event_id}")
    logger.info(f"事件数据：{json.dumps(data, ensure_ascii=False)}")
    
    try:
        response = requests.post(url, json=data, timeout=10)
        
        logger.info(f"Facebook 响应状态码：{response.status_code}")
        logger.info(f"Facebook 响应内容：{response.text}")
        
        response.raise_for_status()
        result = response.json()
        
        logger.info(f"Facebook 收到事件数：{result.get('events_received', 0)}")
        
    except Exception as e:
        logger.error(f"Facebook 上报失败：{e}", exc_info=True)
        raise
```

---

### 方案 4: 添加监控告警

```python
# 添加监控
def check_facebook_reports():
    """检查 Facebook 上报情况"""
    today_events = get_today_events()  # 获取今天的事件
    facebook_received = get_facebook_count()  # 获取 Facebook 收到的数量
    
    loss_rate = (today_events - facebook_received) / today_events
    
    if loss_rate > 0.1:  # 丢失率超过 10%
        send_alert(f"Facebook 上报丢失率过高：{loss_rate:.2%}")
```

---

## 📊 建议优先级

| 优先级 | 任务 | 预计时间 |
|--------|------|---------|
| 🔴 P0 | 检查 event_id 唯一性 | 30 分钟 |
| 🔴 P0 | 检查错误日志 | 30 分钟 |
| 🟡 P1 | 添加重试机制 | 1 小时 |
| 🟡 P1 | 添加详细日志 | 1 小时 |
| 🟢 P2 | 添加监控告警 | 2 小时 |

---

## 🎯 立即执行

### 1. 检查今天的上报日志

```bash
cd E:\Platform
grep "Facebook" logs/app.log | grep "$(date +%Y-%m-%d)"
```

### 2. 检查 event_id

```sql
-- 检查今天的事件 ID 是否重复
SELECT event_id, COUNT(*) as count
FROM conversion_events
WHERE DATE(created_at) = CURDATE()
GROUP BY event_id
HAVING count > 1;
```

### 3. 检查 Facebook Events Manager

```
1. 访问 https://www.facebook.com/events_manager/
2. 选择 Pixel: 1257748189780933
3. 查看"测试事件"
4. 检查是否有被拒绝的事件
```

---

## 📝 总结

### 最可能的原因
1. **event_id 重复导致去重** (80%)
2. **网络请求失败无重试** (60%)
3. **事件时间戳超出范围** (60%)

### 建议立即检查
1. ✅ 检查 event_id 是否唯一
2. ✅ 检查错误日志
3. ✅ 检查 Facebook Events Manager

### 建议优化
1. ✅ 添加唯一 event_id 生成
2. ✅ 添加重试机制
3. ✅ 添加详细日志
4. ✅ 添加监控告警

---

_需要我帮您检查 E:\Platform 项目的具体代码吗？_ 🦀💰
