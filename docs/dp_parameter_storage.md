# dp 参数存储与 PostBack 检查逻辑

## 核心需求

1. **存储 dp 参数**：将 dp 参数和 fbclid 存储到 `clicks` 表的 `url_params` 字段（JSON 格式）
2. **PostBack 检查**：PostBack 处理时检查 `url_params` 中是否包含 fbclid 和 dp 参数

## 当前状态

### ✅ 已有的功能
- `clicks` 表有 `url_params` 字段（Text，JSON 格式）
- `ClickAssociator` 已解析 `url_params` 字段
- `/report` 路由接收 dp 和 fbclid 参数

### ❌ 缺少的功能
- `/report` 路由**没有创建 Click 记录**
- 没有将 dp 和 fbclid 存储到 `url_params`

## 实现方案

### 1. 修改 router.py 创建 Click 记录

在 `/report` 路由中添加后台任务：

```python
# 文件：app/routes/short_link/router.py
# 位置：handle_report 函数中

if background_tasks:
    async def create_click_record():
        try:
            db_session = AsyncSessionLocal()
            
            # 构建 url_params（JSON 格式）
            url_params_dict = {}
            if fbclid:
                url_params_dict["fbclid"] = fbclid
            if dp:
                url_params_dict["dp"] = dp
            
            url_params_json = json.dumps(url_params_dict) if url_params_dict else None
            
            # 创建 Click 记录
            from app.models.models import Click
            from app.core.utils import get_app_now_naive
            import uuid
            
            click = Click(
                click_id=str(uuid.uuid4()),
                short_link_id=short_link.id,  # 从短链接获取
                click_time=get_app_now_naive(),
                ip=client_ip,
                user_agent=ua_from_request,
                referer=referer,
                url_params=url_params_json,  # 存储 fbclid 和 dp
                original_request_url=str(request.url) if request else None,
                is_bot=False
            )
            
            db_session.add(click)
            await db_session.commit()
            
            logger.info(f"Click 记录创建成功：url_params={url_params_json}")
        except Exception as e:
            logger.error(f"创建 Click 记录失败：{e}")
        finally:
            await db_session.close()
    
    background_tasks.add_task(create_click_record)
```

### 2. PostBack 处理时检查 url_params

在 PostBack 转换器中检查：

```python
# 文件：app/core/postback/transformers/click_associator.py
# 位置：associate 函数中（已解析 url_params）

# 提取 fbclid 和 dp
fbclid = url_params.get("fbclid") if url_params else None
dp = url_params.get("dp") if url_params else None

if fbclid and dp:
    logger.info(f"Click 记录包含 fbclid 和 dp: fbclid={fbclid}, dp={dp}")
    # 可以用于 Facebook 像素上报或其他用途
else:
    logger.warning(f"Click 记录缺少 fbclid 或 dp 参数")
```

## 数据流

```
1. 用户访问：/change/temp_42e8c1b0?dp=master
   ↓
2. 前端调用：/report?id=temp_42e8c1b0&fbclid=xxx&dp=master
   ↓
3. router.py 创建 Click 记录：
   - url_params = {"fbclid": "xxx", "dp": "master"}
   - 存储到 clicks.url_params 字段
   ↓
4. PostBack 到达时：
   - ClickAssociator 解析 url_params
   - 提取 fbclid 和 dp
   - 用于像素上报或转化归因
```

## 存储格式

**clicks.url_params**（JSON 字符串）：
```json
{
  "fbclid": "fbclid.1234567890",
  "dp": "master"
}
```

## 优点

- ✅ 使用现有的 `url_params` 字段，无需修改数据库
- ✅ JSON 格式灵活，可以添加更多参数
- ✅ `ClickAssociator` 已支持解析 `url_params`
- ✅ 与现有 PostBack 流程完全兼容

## 下一步

1. 修改 `app/routes/short_link/router.py` 创建 Click 记录
2. 在 PostBack 处理逻辑中使用 `fbclid` 和 `dp` 参数
3. 测试验证数据流
