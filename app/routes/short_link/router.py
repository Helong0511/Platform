"""
短链接重定向路由模块
定义短链接重定向的API端点
"""
import logging
import os
import re
import uuid
from typing import Optional
import time
import httpx
from fastapi import APIRouter, Depends, Query, Request, BackgroundTasks, HTTPException, status
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm.exc import StaleDataError

from app.core.database import get_db, AsyncSessionLocal
from app.core.short_link_cache import get_short_link_from_cache, update_short_link_cache
from app.core.redis_client import get_redis_client
from app.models.models import ShortLink

# 引入短链接处理函数
from app.routes.short_link.handlers import handle_cached_redirect, handle_database_redirect

logger = logging.getLogger(__name__)

# 创建FastAPI路由实例
router = APIRouter()


async def send_third_party_report(
        adsid: str,
        email: str,
        ip: str,
        phone: str,
        ua: str
):
    """
    后台任务：发送第三方广告上报
    从服务器端发送，避免浏览器CORS和广告拦截器问题
    包含智能重试机制，确保网络问题时仍能成功上报
    """
    import asyncio
    max_retries = 3
    base_delay = 1  # 基础延迟时间（秒）
    timeout = 30.0  # 超时时间（秒）
    
    for attempt in range(max_retries):
        try:
            url = "https://hhskins.com/UniqueChannelServer/UniqueChannel"
            headers = {
                "token": "HFY2Dgs07J4YjziNPGaTSmxFrY97CN5Z",
                "Content-Type": "application/json"
            }
            send_data = {
                "adsid": adsid,
                "event": "viewWebpage",
                "pixid": "2105276563598069",
                "type": "Facebook",
                "unixtime": int(time.time()),
                "userData": {
                    "email": email,
                    "ip": ip,
                    "phone": phone,
                    "ua": ua
                }
            }
            
            logger.warning(f"[第三方上报] 开始发送 (尝试 {attempt+1}/{max_retries}): adsid={adsid}, ip={ip}")
            
            # 增加超时时间，应对网络延迟
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=send_data, headers=headers)
                logger.warning(f"[第三方上报] 响应: status={response.status_code}, content={response.text[:200]}")
                
                if response.status_code == 200 and response.text.strip() == "OK":
                    logger.warning(f"[第三方上报] ✓ 成功 (尝试 {attempt+1}/{max_retries})")
                    return
                else:
                    logger.warning(f"[第三方上报] ✗ 失败 (尝试 {attempt+1}/{max_retries}): status={response.status_code}")
                    
        except httpx.TimeoutException:
            logger.warning(f"[第三方上报] ✗ 超时 (尝试 {attempt+1}/{max_retries})")
        except httpx.ConnectError:
            logger.warning(f"[第三方上报] ✗ 连接失败 (尝试 {attempt+1}/{max_retries})")
        except Exception as e:
            logger.warning(f"[第三方上报] ✗ 异常 (尝试 {attempt+1}/{max_retries}): {str(e)}")
        
        # 指数退避策略
        if attempt < max_retries - 1:
            delay = base_delay * (2 ** attempt)
            logger.warning(f"[第三方上报] 等待 {delay} 秒后重试...")
            await asyncio.sleep(delay)
    
    logger.error(f"[第三方上报] ❌ 全部 {max_retries} 次尝试失败: adsid={adsid}")
    
    # 发送告警
    try:
        from app.core.auto_bot import send_telegram_message
        from app.core.config import settings
        await send_telegram_message(
            settings.TELEGRAM_ADMIN,
            f"⚠️ 第三方上报失败\n\n"
            f"AdsID: {adsid}\n"
            f"IP: {ip}\n"
            f"尝试次数: {max_retries}\n"
            f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        logger.warning(f"[第三方上报] 告警已发送")
    except Exception as notify_err:
        logger.warning(f"[第三方上报] 发送告警失败: {notify_err}")


@router.get("/s/{short_code}",
            summary="短链接重定向（推荐）",
            tags=["短链接服务"],
            description="✅ 推荐使用的短链接重定向路由，带缓存优化，性能更好")
async def redirect_short_link_public(
        short_code: str,
        offer_id: Optional[int] = Query(None, description="Offer ID（从URL参数获取）"),
        channel_id: Optional[int] = Query(None, description="渠道ID（从URL参数获取）"),
        request: Request = None,
        background_tasks: BackgroundTasks = None,
        db: AsyncSession = Depends(get_db)
):
    """
    短链接重定向（公开接口，无需认证）
    
    ✅ **推荐路由**：这是系统推荐使用的短链接重定向路由
    
    性能优化：
    - 使用Redis缓存减少数据库查询，提高响应速度
    - 异步更新点击次数，不阻塞重定向
    - 适合高并发场景
    
    功能特性：
    - 支持查询参数自动合并到原始URL
    - 自动生成click_id并添加到重定向URL
    - 完整的点击记录追踪（IP、设备信息、浏览器信息等）
    """
    try:
        request_url = str(request.url)
        request_params = {k.lower(): v for k, v in request.query_params.items()}
        logger.warning(
            f"[短链接重定向] 收到请求: short_code={short_code}"
            f"\n完整URL={request_url}\n查询参数={request_params}"
        )

        # 尝试从缓存获取
        cached_data = await get_short_link_from_cache(short_code)

        if cached_data:
            return await handle_cached_redirect(
                short_code, cached_data, offer_id, channel_id,
                request, background_tasks, db, request_params
            )
        else:
            return await handle_database_redirect(
                short_code, offer_id, channel_id,
                request, background_tasks, db, request_params
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[短链接重定向] 处理异常: short_code={short_code}, error={str(e)}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"短链接重定向失败: {str(e)}"
        )


@router.get("/change/{short_code}",
            summary="打开master.html并跳转到指定URL",
            tags=["斗篷服务"])
async def open_master_html_with_redirect(
        short_code: str,
        request: Request,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db)
):
    """
    先打开E:\Platform\scripts\master.html，然后根据短码跳转到指定的original_url
    """
    try:
        # 记录请求信息
        client_ip = request.client.host if request.client else "未知"
        user_agent = request.headers.get("user-agent", "未知")
        referer = request.headers.get("referer", "未知")
        logger.warning(
            f"[斗篷服务] 收到 /change/{short_code} 请求: \nclient_ip={client_ip},\nuser_agent={user_agent},\nreferer={referer}")

        # 尝试从缓存获取短链接信息
        logger.warning(f"[斗篷服务] 尝试从缓存获取短链接信息: short_code={short_code}")
        cached_data = await get_short_link_from_cache(short_code)
        if cached_data:
            logger.warning(f"[斗篷服务] 缓存命中: short_code={short_code}")
        else:
            logger.warning(f"[斗篷服务] 缓存未命中: short_code={short_code}")

        original_url = None

        # 检查是否是重复请求（通过会话标识）
        session_id = request.cookies.get('session_id')
        if not session_id:
            # 如果没有会话ID，生成一个
            session_id = str(uuid.uuid4())
            logger.warning(f"[斗篷服务] 生成新会话ID: {session_id}")
        else:
            logger.warning(f"[斗篷服务] 使用现有会话ID: {session_id}")

        # 检查是否已经统计过展示次数
        redis = await get_redis_client()
        show_key = f"show_count:{short_code}:{session_id}"
        logger.warning(f"[斗篷服务] 检查展示次数: key={show_key}")

        has_shown = False  # 是否已经统计过展示次数
        if redis:  # 如果Redis客户端可用
            try:
                has_shown = await redis.exists(show_key)  # 检查是否存在展示次数记录
                logger.warning(f"[斗篷服务] Redis检查结果: has_shown={has_shown}")
                if not has_shown:  # 如果没有展示记录
                    # 设置过期时间为6小时
                    await redis.setex(show_key, 21600, '1')  # 标记为已展示
                    logger.warning(f"[斗篷服务] 设置展示标记: key={show_key}, 过期时间=6小时")
            except Exception as e:
                logger.error(f"[斗篷服务] Redis检查展示次数失败: {e}")
        else:  # 如果Redis客户端不可用
            logger.warning(f"[斗篷服务] Redis客户端不可用")

        if not has_shown:
            logger.warning(f"[斗篷服务] 首次访问，开始统计展示次数: short_code={short_code}")
            if cached_data:  # 如果缓存中存在数据
                original_url = cached_data.get("original_url")  # 获取原始URL
                logger.warning(
                    f"[斗篷服务] 从缓存获取数据: short_code={short_code}, 原始show_count={cached_data.get('show_count', 0)}")

                cached_data["show_count"] = (cached_data.get("show_count", 0)) + 1
                logger.warning(
                    f"[斗篷服务] 更新缓存: short_code={short_code}, 新show_count={cached_data['show_count']}")
                update_result = await update_short_link_cache(short_code, cached_data)
                logger.warning(f"[斗篷服务] 缓存更新结果: {update_result}")

                # 后台任务更新数据库，确保数据一致性
                async def update_show_count_db():
                    try:
                        # 创建新的数据库会话
                        db_session = AsyncSessionLocal()

                        # 乐观锁更新，避免并发冲突
                        result = await db_session.execute(
                            select(ShortLink).where(ShortLink.short_code == short_code)
                        )
                        short_link = result.scalars().first()

                        if short_link:
                            # 仅当数据库中的值小于缓存中的值时才更新
                            if (short_link.show_count or 0) < cached_data["show_count"]:
                                short_link.show_count = cached_data["show_count"]
                                await db_session.commit()
                                logger.warning(
                                    f"[斗篷服务] 后台任务更新数据库: short_code={short_code}, 新show_count={short_link.show_count}")
                            else:
                                logger.warning(f"[斗篷服务] 数据库值已最新，无需更新: short_code={short_code}")
                        else:
                            logger.warning(f"[斗篷服务] 后台任务: 短链接不存在: short_code={short_code}")
                    except Exception as e:
                        logger.error(f"[斗篷服务] 后台任务更新数据库失败: {e}", exc_info=True)
                    finally:
                        if 'db_session' in locals():
                            await db_session.close()

                background_tasks.add_task(update_show_count_db)
                logger.warning(f"[斗篷服务] 添加后台任务: 更新数据库展示次数")
            else:
                # 从数据库查询
                logger.warning(f"[斗篷服务] 缓存未命中，从数据库查询: short_code={short_code}")
                result = await db.execute(
                    select(ShortLink).where(ShortLink.short_code == short_code)
                )
                short_link = result.scalars().first()

                if short_link:
                    original_url = short_link.original_url
                    logger.warning(
                        f"[斗篷服务] 数据库查询结果: short_code={short_code}, id={short_link.id}, 原始show_count={short_link.show_count or 0}")
                    # 更新展示次数（数据库）
                    short_link.show_count = (short_link.show_count or 0) + 1
                    logger.warning(
                        f"[斗篷服务] 更新数据库: short_code={short_code}, 新show_count={short_link.show_count}")
                    try:
                        await db.commit()
                        logger.warning(f"[斗篷服务] 数据库提交成功")
                    except StaleDataError:
                        logger.warning(f"[斗篷服务] 数据库更新冲突，忽略StaleDataError")
                        # 回滚事务以避免会话处于不一致状态
                        await db.rollback()
                else:
                    logger.warning(f"[斗篷服务] 短链接不存在: short_code={short_code}")
        else:
            # 已经统计过展示次数，直接获取原始URL
            logger.warning(f"[斗篷服务] 重复访问，跳过统计: short_code={short_code}")
            if cached_data:
                original_url = cached_data.get("original_url")
                logger.warning(f"[斗篷服务] 从缓存获取原始URL: {original_url}")
            else:
                # 从数据库查询
                logger.warning(f"[斗篷服务] 缓存未命中，从数据库查询原始URL: short_code={short_code}")
                result = await db.execute(
                    select(ShortLink).where(ShortLink.short_code == short_code)
                )
                short_link = result.scalars().first()

                if short_link:
                    original_url = short_link.original_url
                    logger.warning(f"[斗篷服务] 从数据库获取原始URL: {original_url}")
                else:
                    original_url = None
                    logger.warning(f"[斗篷服务] 短链接不存在: short_code={short_code}")

        if not original_url:
            logger.error(f"[斗篷服务] 未找到原始URL: short_code={short_code}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="斗篷不存在或未配置原始URL"
            )

        # 优先使用服务器路径，本地开发时会自动回退到本地路径
        master_html_path = "/data/Platform/scripts/master.html"
        logger.warning(f"[斗篷服务] 尝试使用服务器路径: {master_html_path}")

        # 如果服务器路径不存在，尝试本地路径（用于开发环境）
        if not os.path.exists(master_html_path):
            logger.warning(f"[斗篷服务] 服务器路径不存在，尝试本地路径")
            # 使用相对路径，确保在不同操作系统上都能正确工作
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            master_html_path = os.path.join(current_dir, "scripts", "master.html")
            logger.warning(f"[斗篷服务] 本地路径: {master_html_path}")

        if not os.path.exists(master_html_path):
            logger.error(f"[斗篷服务] master.html文件不存在: {master_html_path}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="master.html文件不存在"
            )

        logger.warning(f"[斗篷服务] 找到master.html文件: {master_html_path}")
        with open(master_html_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # 将original_url直接注入到HTML中，同时保留处理fbclid参数的逻辑
        # 替换getOriginalUrl函数，使其返回原始URL并处理fbclid参数
        logger.warning(f"[斗篷服务] 注入原始URL到HTML: {original_url}")
        # 对原始URL进行转义，避免语法错误
        escaped_original_url = original_url.replace('\\', '\\\\').replace('"', '\\"')
        # 使用更精确的正则表达式，匹配完整的函数定义
        pattern = r'function getOriginalUrl\(\) \{[\s\S]*?return originalUrl;[\s\S]*?\}'
        replacement = f'function getOriginalUrl() {{ let originalUrl = "{escaped_original_url}"; const fbclid = getFbclid(); if (fbclid) {{ try {{ const url = new URL(originalUrl); url.searchParams.set("fbclid", fbclid); originalUrl = url.toString(); console.log("[URL] 已添加 fbclid 参数:", originalUrl); }} catch (err) {{ console.log("[URL] 添加 fbclid 参数失败:", err); if (originalUrl.includes("?")) {{ originalUrl += "&fbclid=" + encodeURIComponent(fbclid); }} else {{ originalUrl += "?fbclid=" + encodeURIComponent(fbclid); }} console.log("[URL] 简单拼接 fbclid 参数:", originalUrl); }} }} return originalUrl; }}'
        html_content = re.sub(pattern, replacement, html_content)
        # 验证替换是否成功
        if replacement in html_content:
            logger.warning(f"[斗篷服务] 原始URL注入成功")
        else:
            logger.error(f"[斗篷服务] 原始URL注入失败，检查正则表达式")
            # 尝试使用更简单的匹配方式
            pattern2 = r'function getOriginalUrl\(\)'
            if pattern2 in html_content:
                logger.error(f"[斗篷服务] 找到getOriginalUrl函数定义，但替换失败")
            else:
                logger.error(f"[斗篷服务] 未找到getOriginalUrl函数定义")

        # 返回HTML内容
        response = HTMLResponse(content=html_content)
        # 直接设置CSP头，允许内联脚本和Font Awesome CDN
        response.headers[
            "Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; img-src 'self' data: https:; font-src 'self' data: https://cdnjs.cloudflare.com; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; upgrade-insecure-requests;"
        # 添加缓存控制头，防止浏览器缓存
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

        # 设置session_id到cookie，确保相同浏览器会话使用相同的标识
        logger.warning(f"[斗篷服务] 设置会话cookie: session_id={session_id}")
        response.set_cookie(
            key="session_id",
            value=session_id,
            max_age=21600,  # 6小时
            path="/",
            domain="client.btfrx.online",
            secure=True,
            httponly=True,
            samesite="lax"
        )

        logger.warning(f"[斗篷服务] /change/{short_code} 请求处理完成: 返回master.html，原始URL={original_url}")
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[斗篷服务] /change/{short_code} 请求处理异常: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"处理失败: {str(e)}"
        )


@router.get("/report",
            summary="处理短链接点击上报",
            tags=["短链接服务"])
async def handle_report(
        id: str = Query(..., description="短链接代码"),
        fbclid: str = Query(None, description="Facebook点击ID"),
        email: str = Query(None, description="用户邮箱"),
        phone: str = Query(None, description="用户手机号"),
        request: Request = None,
        background_tasks: BackgroundTasks = None,
        db: AsyncSession = Depends(get_db)
):
    """
    处理短链接点击上报，更新点击次数
    
    前端通过 fetch("/report?id=509220&fbclid=xxx&email=xxx&phone=xxx") 调用
    """
    try:
        # 获取客户端IP和请求头信息
        client_ip = "未知"
        user_agent = "未知"
        referer = "未知"
        if request:
            client_ip = request.client.host if request.client else "未知"
            user_agent = request.headers.get("user-agent", "未知")
            referer = request.headers.get("referer", "未知")

        # 如果没有获取到fbclid，生成一个UUID
        if not fbclid:
            fbclid = str(uuid.uuid4())
            logger.warning(f"[斗篷点击] 生成UUID作为fbclid: {fbclid}")

        # 构建日志信息
        log_message = f"report [斗篷点击] 收到上报请求:\nid={id},\nfbclid={fbclid},\nclient_ip={client_ip},\nuser_agent={user_agent},\nreferer={referer}"

        # 添加第三方广告数据到日志
        if email:
            log_message += f",\nemail={email}"
        if phone:
            log_message += f",\nphone={phone}"

        logger.warning(log_message)

        # 检查是否重复上报
        session_id = request.cookies.get('session_id') if request else None
        if session_id:
            redis = await get_redis_client()
            if redis:
                click_key = f"click_count:{id}:{session_id}"
                try:
                    has_clicked = await redis.exists(click_key)
                    if has_clicked:
                        logger.warning(f"[斗篷点击] 重复上报，跳过统计: id={id}, session_id={session_id}")
                        return {"status": "success", "message": "Report received (duplicate)", "client_ip": client_ip,
                                "fbclid": fbclid}
                    # 设置过期时间为24小时
                    await redis.setex(click_key, 86400, '1')
                except Exception as e:
                    logger.warning(f"Redis检查点击次数失败: {e}")

        # 尝试从缓存获取短链接信息
        cached_data = await get_short_link_from_cache(id)

        if cached_data:
            logger.warning(
                f"[斗篷点击] 从缓存获取数据: short_code={id}, 原始click_count={cached_data.get('click_count', 0)}")
            # 更新点击次数（缓存）
            cached_data["click_count"] = (cached_data.get("click_count", 0)) + 1
            logger.warning(f"[斗篷点击] 更新缓存: short_code={id}, 新click_count={cached_data['click_count']}")
            update_result = await update_short_link_cache(id, cached_data)
            logger.warning(f"[斗篷点击] 缓存更新结果: {update_result}")

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
                                    f"[斗篷点击] 后台任务更新数据库: short_code={id}, 新click_count={short_link.click_count}")
                    except Exception as e:
                        logger.error(f"[斗篷点击] 后台任务更新数据库失败: {e}")
                    finally:
                        if 'db_session' in locals():
                            await db_session.close()

                background_tasks.add_task(update_click_count_db)
        else:
            # 从数据库查询
            logger.warning(f"[斗篷点击] 缓存未命中，从数据库查询: short_code={id}")
            result = await db.execute(select(ShortLink).where(ShortLink.short_code == id))
            short_link = result.scalars().first()

            if short_link:
                logger.warning(
                    f"[斗篷点击] 数据库查询结果: short_code={id}, id={short_link.id}, 原始click_count={short_link.click_count or 0}")
                # 更新点击次数（数据库）
                short_link.click_count = (short_link.click_count or 0) + 1
                logger.warning(f"[斗篷点击] 更新数据库: short_code={id}, 新click_count={short_link.click_count}")
                try:
                    await db.commit()
                    logger.warning(f"[斗篷点击] 数据库提交成功")

                except StaleDataError:
                    logger.warning(f"[斗篷点击] 数据库更新冲突，忽略StaleDataError")
                    # 回滚事务以避免会话处于不一致状态
                    await db.rollback()
            else:
                logger.warning(f"[斗篷点击] 短链接不存在: short_code={id}")

        # 后台任务发送第三方上报（如果有参数）
        if email and phone and background_tasks:
            # 从 request 头中获取 User-Agent
            ua_from_request = request.headers.get("user-agent", "未知") if request else "未知"
            background_tasks.add_task(
                send_third_party_report,
                adsid=fbclid,  # 使用 fbclid 作为 adsid
                email=email,
                ip=client_ip,  # 使用后端获取的客户端 IP
                phone=phone,
                ua=ua_from_request
            )
            logger.warning(f"[第三方上报] 已添加到后台任务队列: adsid={fbclid}, ip={client_ip}")

        # 返回成功响应
        logger.warning(f"[斗篷点击] 处理完成: id={id}, fbclid={fbclid}, client_ip={client_ip}")
        return {"status": "success", "message": "Report received", "client_ip": client_ip, "fbclid": fbclid}
    except Exception as e:
        logger.error(f"[斗篷点击] 处理异常: error={str(e)}", exc_info=True)
        return {"status": "error", "message": "Failed to process report"}
