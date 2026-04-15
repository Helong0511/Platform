# router.py 修改说明

## 需要修改的位置

**文件**: `app/routes/short_link/router.py`  
**函数**: `handle_report` (第 381 行开始)  
**修改位置**: 第 463-489 行

## 当前代码（第 463-489 行）

```python
            # 后台任务更新数据库，确保数据一致性
            if background_tasks:
                async def update_click_count_db():
                    try:
                        # 创建新的数据库会话
                        db_session = AsyncSessionLocal()

                        # 乐观锁更新，避免并发冲突
                        result = await db_session.execute(
                            select(ShortLink).where(ShortLink.short_code == id)
                        )
                        short_link = result.scalars().first()

                        if short_link:
                            # 仅当数据库中的值小于缓存中的值时才更新
                            if (short_link.click_count or 0) < cached_data["click_count"]:
                                short_link.click_count = cached_data["click_count"]
                                await db_session.commit()
                                logger.warning(
                                    f"[斗篷点击] 后台任务更新数据库：short_code={id}, 新 click_count={short_link.click_count}")
                    except Exception as e:
                        logger.error(f"[斗篷点击] 后台任务更新数据库失败：{e}")
                    finally:
                        if 'db_session' in locals():
                            await db_session.close()

                background_tasks.add_task(update_click_count_db)
```

## 需要修改为

```python
            # 后台任务创建 Click 记录并更新数据库
            if background_tasks:
                async def create_click_and_update_db():
                    try:
                        # 创建新的数据库会话
                        db_session = AsyncSessionLocal()
                        
                        # 构建 url_params（JSON 格式），存储 fbclid 和 dp
                        url_params_dict = {}
                        if fbclid:
                            url_params_dict["fbclid"] = fbclid
                        if dp:
                            url_params_dict["dp"] = dp
                        
                        url_params_json = json.dumps(url_params_dict) if url_params_dict else None
                        
                        # 创建 Click 记录
                        from app.models.models import Click
                        from app.core.utils import get_app_now_naive
                        
                        click = Click(
                            click_id=str(uuid.uuid4()),
                            short_link_id=None,  # 稍后查询
                            click_time=get_app_now_naive(),
                            ip=client_ip,
                            user_agent=ua_from_request,
                            referer=referer,
                            url_params=url_params_json,  # 存储 fbclid 和 dp
                            original_request_url=str(request.url) if request else None,
                            is_bot=False
                        )
                        
                        # 查询短链接
                        result = await db_session.execute(
                            select(ShortLink).where(ShortLink.short_code == id)
                        )
                        short_link = result.scalars().first()
                        
                        if short_link:
                            click.short_link_id = short_link.id
                            click.offer_id = short_link.offer_id
                            click.publisher_id = short_link.channel_id
                            
                            # 更新点击次数
                            short_link.click_count = (short_link.click_count or 0) + 1
                            
                            # 添加到数据库
                            db_session.add(click)
                            await db_session.commit()
                            
                            logger.warning(
                                f"[斗篷点击] Click 记录创建成功："
                                f"click_id={click.click_id}, short_code={id}, "
                                f"url_params={url_params_json}"
                            )
                        else:
                            logger.warning(f"[斗篷点击] 短链接不存在，无法创建 Click 记录：short_code={id}")
                            await db_session.rollback()
                    except Exception as e:
                        logger.error(f"[斗篷点击] 创建 Click 记录失败：{e}", exc_info=True)
                    finally:
                        if 'db_session' in locals():
                            await db_session.close()
                
                background_tasks.add_task(create_click_and_update_db)
```

## 修改说明

### 主要变化

1. **函数名变更**: `update_click_count_db` → `create_click_and_update_db`
2. **新增功能**: 创建 Click 记录，存储 fbclid 和 dp 参数
3. **url_params**: JSON 格式存储 `{"fbclid": xxx, "dp": xxx}`
4. **数据库操作**: 同时创建 Click 记录和更新点击次数

### 关键字段

- `url_params`: 存储 fbclid 和 dp 参数（JSON 格式）
- `click_id`: 唯一标识符（UUID）
- `click_time`: 点击时间
- `ip`, `user_agent`, `referer`: 请求信息

### 修改步骤

1. 打开文件 `e:\Platform\app\routes\short_link\router.py`
2. 定位到第 463-489 行
3. 删除原有代码
4. 粘贴新的代码
5. 保存文件

## 验证修改

修改后，运行以下命令检查语法：

```bash
python -m py_compile app/routes/short_link/router.py
```

测试数据流：

1. 访问：`/change/temp_42e8c1b0?dp=master`
2. 检查数据库 `clicks` 表：
   ```sql
   SELECT click_id, url_params FROM clicks ORDER BY id DESC LIMIT 1;
   ```
3. 应该看到：`url_params = {"fbclid": "xxx", "dp": "master"}`
