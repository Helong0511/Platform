# 缓存使用指南

**版本：** 2.1  
**更新日期：** 2026-11-24  
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
    jitter_range=30  # 基础 TTL 正向增加 1–30 秒
)
```

**效果：**
- ✅ TTL 在 301-330 秒之间随机（base_ttl + [1, jitter_range]）
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

**解决方案与边界：**
1. **数据库事务内登记持久化失效事件（强一致性场景优先）**。业务数据变更与 Outbox 事件必须使用同一个数据库事务提交；Worker 使用租约、随机 fencing token 和有限退避重试。不要在业务事务提交后才单独写 Outbox。
2. **Generation 版本隔离**。广告数据查询缓存与用户统计缓存通过数据库 Generation 生成新键；旧请求即使迟到回填，也不能覆盖新 Generation 的读取结果。
3. **Offer 热点缓存**。Offer 创建、更新、删除在业务事务内登记 first/second 两阶段事件；提交后 API 尝试立即删除 `offer:cache:{offer_id}`，Outbox 再负责持久化重试和后续复查。
4. **普通短 TTL 缓存**可接受短暂陈旧时，可使用合理 TTL，但必须明确业务允许的陈旧窗口。
5. **不要把进程内延迟双删当成可靠保证**。`asyncio.create_task()` 在进程重启、事件循环关闭时会丢失；`asyncio.sleep()` 也不能持久化任务。历史 `CacheInvalidator` 的延迟双删只属于 best-effort 兼容路径，不能代替事务性 Outbox。

**当前已接入持久化失效的范围（以代码为准）：**
- `ad_data`：数据库 Generation + Outbox。
- `user_stats`：数据库 Generation + Outbox。
- CPL 扣量配置 `cpl:deduction_config`：数据库 Generation + Outbox；扣量配置读写键包含当前事务读取的 Generation，所有单条/批量 CRUD 在业务事务内推进版本。
- Offer 热点键 `offer:cache:{offer_id}`：专用两阶段 Outbox。
- 短链接键 `short_link:{short_code}`：短链接更新/删除在业务事务内登记专用两阶段 Outbox；API 提交后尝试立即删除，Worker 只删除精确短码键。
- 不要据此推断所有 `query_cache:` 缓存、Advertiser 或其他业务域均已获得持久化失效保证。

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


## 🔐 缓存一致性与故障降级（2026-11-24）

### Redis 不可用时
- `get_cache_backend()` 可能退化为当前进程的 `MemoryCacheBackend`；它不是跨 Worker 共享缓存。
- 对持久化 Outbox，必须确认真实 Redis 共享存储成功后才能将事件标记为 `success`。仅清理本机内存缓存不算成功。
- Offer 与短链接 Outbox 直接获取 Redis 客户端；Redis 返回不可用或删除命令异常时保留任务并按退避策略重试。
- 缓存故障应尽量 fail-open，不得把可由数据库完成的正常业务操作误判为失败；权限、财务和状态判断必须回到数据库权威数据。

### 缓存键与失效模式
- `cache_query()` 使用参数 JSON 的 MD5 摘要作为键，最终形态为 `query_cache:{md5}`。只按可读业务名称（例如 `offer:list:*`）清理，不能命中这种哈希键。
- 广告数据专用键通过 `build_ad_data_query_cache_key()` 生成 `ad_data:{kind}:{md5}`，便于按 `query_cache:ad_data:` 命名空间失效。
- 旧兼容 API 的 `key_prefix` 主要用于指标分类；不要假设它必然成为 Redis key 的可读前缀。
- Offer 热点缓存 `offer:cache:{id}`、短链接缓存 `short_link:{short_code}` 与查询缓存 `query_cache:` 是独立键空间，必须分别清理。CPL 扣量配置位于 `query_cache:cpl:deduction_config:`，由独立 Generation 隔离版本。

### Outbox 运维
- Offer、广告数据与短链接缓存失效任务当前按每分钟调度；Offer/短链接第二阶段须等第一阶段结束后在后续调度轮次执行，不是精确 1 秒实时执行。
- 关注任务结果中的 `retryable`、`failed`、`lease_lost`。持续失败应进入日志/监控告警处置，不能手工把事件直接改成 success。
- 不允许使用 `FLUSHDB`、`KEYS *` 或无边界全库清理来解决缓存不一致。
- 新增缓存域时，必须先梳理读写者、键格式、业务事务边界和回填路径，再决定采用 Generation、精确键 Outbox 或其他可验证方案。

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

_文档版本：2.1_  
_最后更新：2026-11-24_
