# 缓存使用指南

**版本：** 2.0  
**更新日期：** 2026-03-14  
**作者：** 钳钳 🦀

---

## 📦 快速开始

### 基础用法

```python
from app.core.infrastructure.cache_compat import get_cached, set_cached

# 设置缓存
await set_cached("user:123", {"name": "John"}, ttl=300)

# 获取缓存
user = await get_cached("user:123")
```

### 带监控的用法（推荐）

```python
from app.core.infrastructure.cache_compat import get_cached, set_cached

# 设置缓存（带监控指标）
await set_cached("user:123", data, ttl=300, key_prefix="user")

# 获取缓存（带监控指标）
user = await get_cached("user:123", key_prefix="user")
```

---

## 🛡️ 高级功能

### 1. 缓存穿透保护

**问题：** 查询不存在的数据，每次都要查数据库

**解决方案：** 使用 `get_with_none_cache()`

```python
from app.core.infrastructure.cache_advanced import get_with_none_cache

async def get_user(user_id: int):
    return await get_with_none_cache(
        f"user:{user_id}",
        lambda: query_user_from_db(user_id),
        none_ttl=60,      # None 值缓存 60 秒
        normal_ttl=300    # 正常值缓存 5 分钟
    )
```

**效果：**
- ✅ 不存在的用户 ID 也会缓存（短 TTL）
- ✅ 防止恶意请求打穿缓存
- ✅ 数据库压力大幅降低

---

### 2. 缓存雪崩防护

**问题：** 大量 Key 同时过期，导致数据库压力激增

**解决方案：** 使用 `set_with_jitter()`

```python
from app.core.infrastructure.cache_advanced import set_with_jitter

# 设置缓存（带随机 TTL 偏移）
await set_with_jitter(
    f"user:{user_id}",
    user_data,
    base_ttl=300,
    jitter_range=30  # ±30 秒随机
)
```

**效果：**
- ✅ TTL 在 270-330 秒之间随机
- ✅ 避免同时过期
- ✅ 系统负载更平稳

---

### 3. 缓存击穿保护

**问题：** 热点 Key 过期时，大量并发请求同时查数据库

**解决方案：** 使用 `get_with_lock_protection()`

```python
from app.core.infrastructure.cache_advanced import get_with_lock_protection

async def get_hot_user(user_id: int):
    return await get_with_lock_protection(
        f"user:{user_id}",
        lambda: query_user_from_db(user_id),
        ttl=300,
        lock_timeout=10  # 锁超时 10 秒
    )
```

**效果：**
- ✅ 使用分布式锁保证只有一个请求查数据库
- ✅ 其他请求等待锁释放后从缓存读取
- ✅ 数据库压力大幅降低

**底层原理：**
```python
# 使用 Redis 分布式锁
async with distributed_lock(f"user:{user_id}") as acquired:
    if acquired:
        # 双重检查
        cached = await cache.get(key)
        if not cached:
            # 只有持有锁的进程查数据库
            data = await query_db()
            await cache.set(key, data)
```

---

### 4. 缓存监控

**查看缓存健康状态：**

```python
from app.core.infrastructure.cache_metrics import (
    get_metrics_collector,
    get_cache_health_status
)

# 获取全局指标
collector = get_metrics_collector()
metrics = collector.get_metrics('global')

print(f"命中率：{metrics.hit_rate * 100:.2f}%")
print(f"错误率：{metrics.error_rate * 100:.2f}%")
print(f"平均响应时间：{metrics.avg_response_time_ms:.2f}ms")

# 获取健康状态
health = await get_cache_health_status()
print(f"健康分数：{health['score']}/100")
print(f"健康等级：{health['level']}")
# health['level']: 'excellent' | 'good' | 'fair' | 'poor'
```

**监控指标：**
- `hits` - 命中次数
- `misses` - 未命中次数
- `errors` - 错误次数
- `hit_rate` - 命中率
- `error_rate` - 错误率
- `avg_response_time_ms` - 平均响应时间

---

## 📋 最佳实践

### 1. Key 命名规范

```python
# 推荐格式
{module}:{type}:{id}:{field}

# 示例
"user:profile:123:name"
"cpl:deduction:offer:456:config"
"cpl:cap:daily:789:2026-03-14"
"publisher:info:101:basic"
```

### 2. TTL 设置建议

| 数据类型 | 推荐 TTL | 说明 |
|---------|---------|------|
| 用户信息 | 5-10 分钟 | 变化频繁 |
| 配置信息 | 5-15 分钟 | 变化较少 |
| 统计数据 | 1-5 分钟 | 实时性要求高 |
| Cap 计数 | 48 小时 | 每日重置 |
| 会话数据 | 30 分钟 | 用户活跃期 |

### 3. 缓存策略选择

```python
# 场景 1：普通查询（无特殊要求）
data = await get_cached(key)

# 场景 2：可能查询不存在的数据
data = await get_with_none_cache(key, factory)

# 场景 3：热点数据（高并发）
data = await get_with_lock_protection(key, factory)

# 场景 4：批量设置缓存
for item in items:
    await set_with_jitter(key, item, base_ttl=300)
```

### 4. 错误处理

```python
from app.core.infrastructure.cache_compat import get_cached

try:
    data = await get_cached("user:123")
    if data is None:
        # 缓存未命中，查数据库
        data = await query_db()
except Exception as e:
    logger.error(f"缓存操作失败：{e}", exc_info=True)
    # Fail Open：缓存失败不影响业务
    data = await query_db()
```

---

## 🔧 配置说明

### TTL 配置（建议放在 config.py）

```python
class CacheTTL:
    # 用户相关
    USER_PROFILE = 600        # 10 分钟
    USER_STATS = 300          # 5 分钟
    
    # 配置相关
    DEDUCTION_CONFIG = 300    # 5 分钟
    CAP_DAILY = 172800        # 48 小时
    CAP_TOTAL = 2592000       # 30 天
    
    # 业务相关
    PUBLISHER_INFO = 300      # 5 分钟
    OFFER_INFO = 300          # 5 分钟
    STATS_HOURLY = 300        # 5 分钟
```

### 监控上报（定时任务）

```python
# 每分钟上报一次指标
from app.core.infrastructure.cache_metrics import report_metrics_to_redis

async def periodic_cache_metrics_report():
    while True:
        await asyncio.sleep(60)
        await report_metrics_to_redis()
```

---

## 🚨 常见问题

### Q1: 缓存穿透、击穿、雪崩的区别？

**缓存穿透：**
- 查询**不存在**的数据
- 每次都要查数据库
- 解决：缓存 None 值

**缓存击穿：**
- **热点 Key**过期
- 大量并发同时查数据库
- 解决：分布式锁

**缓存雪崩：**
- **大量 Key 同时**过期
- 数据库压力激增
- 解决：随机 TTL 偏移

### Q2: 如何选择合适的 TTL？

**考虑因素：**
1. 数据变化频率
2. 业务实时性要求
3. 数据库承受能力

**经验法则：**
- 配置类：5-15 分钟
- 统计类：1-5 分钟
- 用户信息：5-10 分钟
- 会话类：30 分钟

### Q3: 缓存不一致怎么办？

**场景：** 数据库更新了，缓存还是旧的

**解决方案：**
1. **主动失效** - 数据更新时删除缓存
   ```python
   await cache.delete(f"user:{user_id}")
   ```

2. **短 TTL** - 让缓存自动过期
   ```python
   await set_cached(key, data, ttl=300)
   ```

3. **延迟双删** - 更新 DB 后删缓存，延迟后再删一次
   ```python
   await db.update(...)
   await cache.delete(key)
   await asyncio.sleep(0.5)
   await cache.delete(key)
   ```

### Q4: 如何监控缓存性能？

```python
# 1. 查看实时指标
metrics = get_metrics_collector().get_metrics('user')
print(f"命中率：{metrics.hit_rate * 100:.2f}%")

# 2. 查看健康状态
health = await get_cache_health_status()
print(f"健康等级：{health['level']}")

# 3. 上报到 Redis（集中监控）
await report_metrics_to_redis()
```

---

## 📊 性能对比

| 场景 | 无缓存 | 普通缓存 | 高级缓存 |
|------|--------|---------|---------|
| 普通查询 | 50ms | 1ms | 1ms |
| 穿透保护 | 50ms | 50ms | 1ms |
| 击穿保护 | 50ms | 200ms* | 5ms |
| 雪崩防护 | 50ms | 500ms* | 50ms |

*无保护情况下的高负载

---

## 🎯 总结

**核心原则：**
1. ✅ 永远不要信任缓存（总是准备降级方案）
2. ✅ 设置合理的 TTL（不要永久缓存）
3. ✅ 监控缓存指标（及时发现问题）
4. ✅ 保护三大风险（穿透/击穿/雪崩）

**推荐用法：**
```python
# 最佳实践示例
from app.core.infrastructure.cache_advanced import (
    get_with_none_cache,
    get_with_lock_protection
)

async def get_user_profile(user_id: int):
    # 普通用户：使用穿透保护
    return await get_with_none_cache(
        f"user:profile:{user_id}",
        lambda: query_user_from_db(user_id),
        none_ttl=60,
        normal_ttl=600
    )

async def get_hot_user_profile(user_id: int):
    # 热点用户：使用击穿保护
    return await get_with_lock_protection(
        f"user:profile:{user_id}",
        lambda: query_user_from_db(user_id),
        ttl=600,
        lock_timeout=10
    )
```

---

_文档版本：2.0_  
_最后更新：2026-03-14_
