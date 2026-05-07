"""
短链接重定向路由模块
定义短链接重定向的 API 端点
"""
import logging
import os
import re
import uuid
import json
from typing import Optional
import time
import httpx
from urllib.parse import urlparse, parse_qs
from fastapi import APIRouter, Depends, Query, Request, BackgroundTasks, HTTPException, status
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm.exc import StaleDataError

from app.core.database import get_db, AsyncSessionLocal
from app.core.short_link_cache import get_short_link_from_cache, update_short_link_cache
from app.core.redis_client import get_redis_client
from app.models.models import ShortLink
from app.core.auto_bot import send_telegram_message
from app.core.config import settings
from app.core.third_party_report import send_third_party_report
from app.services.cloak_pixel_mapping import get_cloak_pixel_config
from app.core.cloak_scripts_paths import read_bridge_html_template_cached, resolve_bridge_html_read_path
# 引入短链接处理函数
from app.routes.short_link.handlers import handle_cached_redirect, handle_database_redirect

logger = logging.getLogger(__name__)

# 创建FastAPI路由实例
router = APIRouter()


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
            summary="打开桥页并跳转到指定 URL（支持 dp 参数动态加载不同桥页）",
            tags=["斗篷服务"])
async def open_master_html_with_redirect(
        short_code: str,
        request: Request,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db),
        dp: Optional[str] = Query(None, description="桥页标识参数，用于动态加载不同的桥页文件")
):
    """
    根据 dp 参数动态加载不同的桥页文件，然后根据短码跳转到指定的 original_url
    
    功能说明：
    - 当访问 /change/{short_code}?dp=master 时，加载 master.html
    - 当访问 /change/{short_code}?dp=other 时，加载 other.html
    - 当 dp 参数不存在或无效时，默认加载第一个可用的 HTML 文件
    - 支持安全验证，防止路径遍历攻击
    """
    try:
        # 记录请求信息
        client_ip = request.client.host if request.client else "未知"
        user_agent = request.headers.get("user-agent", "未知")
        referer = request.headers.get("referer", "未知")
        logger.debug(
            "[斗篷服务] 收到 /change/%s 请求: client_ip=%s, ua=%s, referer=%s",
            short_code,
            client_ip,
            user_agent,
            referer,
        )

        # 尝试从缓存获取短链接信息
        logger.debug(f"[斗篷服务] 尝试从缓存获取短链接信息: short_code={short_code}")
        cached_data = await get_short_link_from_cache(short_code)
        if cached_data:
            logger.debug(f"[斗篷服务] 缓存命中: short_code={short_code}")
        else:
            logger.debug(f"[斗篷服务] 缓存未命中: short_code={short_code}")

        original_url = None

        # 检查是否是重复请求（通过会话标识）
        session_id = request.cookies.get('session_id')
        if not session_id:
            # 如果没有会话ID，生成一个
            session_id = str(uuid.uuid4())
            logger.debug(f"[斗篷服务] 生成新会话ID: {session_id}")
        else:
            logger.debug(f"[斗篷服务] 使用现有会话ID: {session_id}")

        # 检查是否已经统计过展示次数
        redis = await get_redis_client()
        show_key = f"show_count:{short_code}:{session_id}"
        logger.debug(f"[斗篷服务] 检查展示次数: key={show_key}")

        # SET key NX：一次往返完成「是否已展示」判断与标记（首次访问返回 True，已存在键返回 None）
        has_shown = False
        if redis:
            try:
                first_show = await redis.set(show_key, "1", ex=21600, nx=True)
                # 各 redis 驱动返回值略有差异，统一按「有返回值且真」视为首次写入成功
                has_shown = not bool(first_show)
                logger.debug(
                    "[斗篷服务] Redis 展示标记: key=%s 首次访问=%s",
                    show_key,
                    not has_shown,
                )
            except Exception as e:
                logger.error(f"[斗篷服务] Redis检查展示次数失败: {e}")
        else:  # 如果Redis客户端不可用
            logger.debug(f"[斗篷服务] Redis客户端不可用")

        if not has_shown:
            logger.debug(f"[斗篷服务] 首次访问，开始统计展示次数: short_code={short_code}")
            if cached_data:  # 如果缓存中存在数据
                original_url = cached_data.get("original_url")  # 获取原始URL
                logger.debug(
                    "[斗篷服务] 从缓存获取数据: short_code=%s, 原始show_count=%s",
                    short_code,
                    cached_data.get("show_count", 0),
                )

                cached_data["show_count"] = (cached_data.get("show_count", 0)) + 1
                logger.debug(
                    "[斗篷服务] 更新缓存: short_code=%s, 新show_count=%s",
                    short_code,
                    cached_data["show_count"],
                )
                update_result = await update_short_link_cache(short_code, cached_data)
                logger.debug(f"[斗篷服务] 缓存更新结果: {update_result}")

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
                                logger.debug(
                                    "[斗篷服务] 后台任务更新数据库: short_code=%s, 新show_count=%s",
                                    short_code,
                                    short_link.show_count,
                                )
                            else:
                                logger.debug(f"[斗篷服务] 数据库值已最新，无需更新: short_code={short_code}")
                        else:
                            logger.debug(f"[斗篷服务] 后台任务: 短链接不存在: short_code={short_code}")
                    except Exception as e:
                        logger.error(f"[斗篷服务] 后台任务更新数据库失败: {e}", exc_info=True)
                    finally:
                        if 'db_session' in locals():
                            await db_session.close()

                background_tasks.add_task(update_show_count_db)
                logger.debug(f"[斗篷服务] 添加后台任务: 更新数据库展示次数")
            else:
                # 从数据库查询
                logger.debug(f"[斗篷服务] 缓存未命中，从数据库查询: short_code={short_code}")
                result = await db.execute(
                    select(ShortLink).where(ShortLink.short_code == short_code)
                )
                short_link = result.scalars().first()

                if short_link:
                    original_url = short_link.original_url
                    logger.debug(
                        "[斗篷服务] 数据库查询结果: short_code=%s, id=%s, 原始show_count=%s",
                        short_code,
                        short_link.id,
                        short_link.show_count or 0,
                    )
                    # 更新展示次数（数据库）
                    short_link.show_count = (short_link.show_count or 0) + 1
                    logger.debug(
                        "[斗篷服务] 更新数据库: short_code=%s, 新show_count=%s",
                        short_code,
                        short_link.show_count,
                    )
                    try:
                        await db.commit()
                        logger.debug(f"[斗篷服务] 数据库提交成功")
                    except StaleDataError:
                        logger.debug(f"[斗篷服务] 数据库更新冲突，忽略StaleDataError")
                        # 回滚事务以避免会话处于不一致状态
                        await db.rollback()
                else:
                    logger.debug(f"[斗篷服务] 短链接不存在: short_code={short_code}")
        else:
            # 已经统计过展示次数，直接获取原始URL
            logger.debug(f"[斗篷服务] 重复访问，跳过统计: short_code={short_code}")
            if cached_data:
                original_url = cached_data.get("original_url")
                logger.debug(f"[斗篷服务] 从缓存获取原始URL: {original_url}")
            else:
                # 从数据库查询
                logger.debug(f"[斗篷服务] 缓存未命中，从数据库查询原始URL: short_code={short_code}")
                result = await db.execute(
                    select(ShortLink).where(ShortLink.short_code == short_code)
                )
                short_link = result.scalars().first()

                if short_link:
                    original_url = short_link.original_url
                    logger.debug(f"[斗篷服务] 从数据库获取原始URL: {original_url}")
                else:
                    original_url = None
                    logger.debug(f"[斗篷服务] 短链接不存在: short_code={short_code}")

        if not original_url:
            logger.error(f"[斗篷服务] 未找到原始 URL: short_code={short_code}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="斗篷不存在或未配置原始 URL"
            )

        # ========== 桥页动态加载逻辑 ==========
        # 1. 安全验证：防止路径遍历攻击
        # 2. 根据 dp 参数确定要加载的 HTML 文件
        # 3. 如果文件不存在，使用默认文件
        
        # 安全验证：只允许字母、数字、连字符和下划线
        if dp and not re.match(r'^[a-zA-Z0-9_-]+$', dp):
            logger.debug(f"[斗篷服务] dp 参数包含非法字符：{dp}，使用默认桥页")
            dp = None
        
        # 确定桥页文件名
        if dp:
            bridge_page_name = f"{dp}.html"
        else:
            # 默认使用 master.html
            bridge_page_name = "master.html"
        
        logger.debug(f"[斗篷服务] 请求的桥页：{bridge_page_name}")

        bridge_page_path = resolve_bridge_html_read_path(bridge_page_name)
        if bridge_page_path:
            logger.debug(f"[斗篷服务] 使用桥页路径：{bridge_page_path}")
        else:
            if bridge_page_name != "master.html":
                logger.debug(f"[斗篷服务] 桥页文件不存在：{bridge_page_name}，尝试使用 master.html")
                bridge_page_path = resolve_bridge_html_read_path("master.html")
                if bridge_page_path:
                    logger.debug(f"[斗篷服务] 使用默认桥页路径：{bridge_page_path}")
            if not bridge_page_path:
                logger.error(f"[斗篷服务] 桥页文件不存在：{bridge_page_name}，且 master.html 也不存在")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="桥页文件不存在"
                )
        
        logger.debug("[斗篷服务] 读取桥页文件（模板缓存）：%s", bridge_page_path)
        html_content = read_bridge_html_template_cached(bridge_page_path)

        # 将original_url直接注入到HTML中，同时保留处理fbclid参数的逻辑
        # 替换getOriginalUrl函数，使其返回原始URL并处理fbclid参数
        logger.debug(f"[斗篷服务] 注入原始URL到HTML: {original_url}")
        # 对原始URL进行转义，避免语法错误
        escaped_original_url = original_url.replace('\\', '\\\\').replace('"', '\\"')
        escaped_dp = (dp or "").replace('\\', '\\\\').replace('"', '\\"')
        # 使用更精确的正则表达式，匹配完整的函数定义（支持带参数的版本）
        pattern = r'function getOriginalUrl\([^)]*\) \{[\s\S]*?return originalUrl;[\s\S]*?\}'
        replacement = (
            f'function getOriginalUrl(adEventData) {{ '
            f'let originalUrl = "{escaped_original_url}"; '
            f'const dpParam = "{escaped_dp}"; '
            f'const email = adEventData?.email || sessionStorage.getItem("ad_event_email") || ""; '
            f'const phone = adEventData?.phone || sessionStorage.getItem("ad_event_phone") || ""; '
            f'console.log("[URL] 使用的参数 - email:", email, "phone:", phone, "dp:", dpParam); '
            f'try {{ '
            f'const url = new URL(originalUrl); '
            f'if (email) {{ url.searchParams.set("email", email); console.log("[URL] 已添加 email 参数:", email); }} '
            f'if (phone) {{ url.searchParams.set("phone", phone); console.log("[URL] 已添加 phone 参数:", phone); }} '
            f'const fbclid = getFbclid(); '
            f'if (fbclid) {{ url.searchParams.set("fbclid", fbclid); console.log("[URL] 已添加 fbclid 参数:", fbclid); }} '
            f'if (dpParam) {{ url.searchParams.set("dp", dpParam); console.log("[URL] 已添加 dp 参数:", dpParam); }} '
            f'originalUrl = url.toString(); '
            f'console.log("[URL] 最终URL:", originalUrl); '
            f'}} catch (err) {{ '
            f'console.log("[URL] 添加参数失败:", err); '
            f'const fbclid = getFbclid(); '
            f'if (originalUrl.includes("?")) {{ '
            f'if (email) originalUrl += "&email=" + encodeURIComponent(email); '
            f'if (phone) originalUrl += "&phone=" + encodeURIComponent(phone); '
            f'if (fbclid) originalUrl += "&fbclid=" + encodeURIComponent(fbclid); '
            f'if (dpParam) originalUrl += "&dp=" + encodeURIComponent(dpParam); '
            f'}} else {{ '
            f'let params = []; '
            f'if (email) params.push("email=" + encodeURIComponent(email)); '
            f'if (phone) params.push("phone=" + encodeURIComponent(phone)); '
            f'if (fbclid) params.push("fbclid=" + encodeURIComponent(fbclid)); '
            f'if (dpParam) params.push("dp=" + encodeURIComponent(dpParam)); '
            f'if (params.length > 0) {{ originalUrl += "?" + params.join("&"); }} '
            f'}} '
            f'console.log("[URL] 简单拼接参数:", originalUrl); '
            f'}} '
            f'return originalUrl; '
            f'}}'
        )
        html_content = re.sub(pattern, replacement, html_content)
        # 验证替换是否成功
        if replacement in html_content:
            logger.debug(f"[斗篷服务] 原始URL注入成功")
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
        logger.debug(f"[斗篷服务] 设置会话 cookie: session_id={session_id}")
        response.set_cookie(
            key="session_id",
            value=session_id,
            max_age=21600,  # 6 小时
            path="/",
            domain="client.btfrx.online",
            secure=True,
            httponly=True,
            samesite="lax"
        )

        logger.debug(f"[斗篷服务] /change/{short_code} 请求处理完成：返回{bridge_page_name}，原始 URL={original_url}")
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
            summary="处理短链接点击上报（支持 dp 参数和 Facebook 像素上报）",
            tags=["短链接服务"])
async def handle_report(
        id: str = Query(..., description="短链接代码"),
        fbclid: str = Query(..., description="Facebook 点击 ID"),
        email: str = Query(..., description="用户邮箱"),
        phone: str = Query(..., description="用户手机号"),
        dp: Optional[str] = Query(None, description="桥页标识参数，用于识别不同的桥页"),
        request: Request = None,
        background_tasks: BackgroundTasks = None,
        db: AsyncSession = Depends(get_db)
):
    """
    处理短链接点击上报，更新点击次数并发送 Facebook 像素事件
    
    功能说明：
    - 前端通过 fetch("/report?id=509220&fbclid=xxx&email=xxx&phone=xxx&dp=master") 调用
    - 支持 dp 参数识别不同的桥页
    - 自动发送 Facebook ViewContent 事件到第三方上报
    - 使用全局 Facebook 像素配置（从 settings 中读取）
    
    参数说明：
    - id: 短链接代码
    - fbclid: Facebook 点击 ID
    - email: 用户邮箱（用于 Facebook 像素上报）
    - phone: 用户手机号（用于 Facebook 像素上报）
    - dp: 桥页标识（可选，用于区分不同的桥页）
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

        # 统一解析 dp 参数，避免前端漏传时丢失像素映射线索
        resolved_dp = dp.strip() if dp and dp.strip() else None
        if not resolved_dp and request:
            query_dp = (
                request.query_params.get("dp")
                or request.query_params.get("DP")
                or request.query_params.get("Dp")
            )
            if query_dp and query_dp.strip():
                resolved_dp = query_dp.strip()

        # 前端 /report 可能未显式带 dp，尝试从 referer 的 /change 链接中回填
        if not resolved_dp and referer and referer != "未知":
            try:
                referer_dp = parse_qs(urlparse(referer).query).get("dp", [])
                if referer_dp and referer_dp[0].strip():
                    resolved_dp = referer_dp[0].strip()
                    logger.info(f"[斗篷点击] 从 Referer 回填 dp 参数：dp={resolved_dp}")
            except Exception as e:
                logger.warning(f"[斗篷点击] 从 Referer 解析 dp 失败：{e}")

        # 安全校验 dp，避免注入或异常字符污染配置查找
        if resolved_dp and not re.match(r'^[a-zA-Z0-9_-]+$', resolved_dp):
            logger.warning(f"[斗篷点击] dp 参数格式非法，忽略：dp={resolved_dp}")
            resolved_dp = None

        # 验证必需参数
        if not email or not email.strip():
            logger.error(f"[斗篷点击] email 参数为空：email={email}")
            return {"status": "error", "message": "email 参数不能为空", "client_ip": client_ip}
        
        if not phone or not phone.strip():
            logger.error(f"[斗篷点击] phone 参数为空：phone={phone}")
            return {"status": "error", "message": "phone 参数不能为空", "client_ip": client_ip}

        # 如果没有获取到 fbclid，生成一个 UUID
        if not fbclid:
            fbclid = str(uuid.uuid4())

        logger.warning(f"[斗篷点击] fbclid: {fbclid}")

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
                    first_click = await redis.set(click_key, "1", ex=86400, nx=True)
                    if not bool(first_click):
                        logger.debug(
                            "[斗篷点击] 重复上报，跳过统计: id=%s, session_id=%s",
                            id,
                            session_id,
                        )
                        return {"status": "success", "message": "Report received (duplicate)", "client_ip": client_ip,
                                "fbclid": fbclid}
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

            # 后台任务创建 Click 记录并更新数据库
            if background_tasks:
                async def create_click_and_update_db():
                    try:
                        # 创建新的数据库会话
                        db_session = AsyncSessionLocal()
                        
                        # 构建 url_params（JSON 格式），存储 fbclid, dp, email, phone
                        url_params_dict = {}
                        if fbclid:
                            url_params_dict["fbclid"] = fbclid
                        if resolved_dp:
                            url_params_dict["dp"] = resolved_dp
                        if email:
                            url_params_dict["email"] = email
                        if phone:
                            url_params_dict["phone"] = phone
                        
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

        # 后台任务发送第三方 Facebook 像素上报（如果有参数）
        if email and phone and background_tasks:
            # 从 request 头中获取 User-Agent
            ua_from_request = request.headers.get("user-agent", "未知") if request else "未知"
            
            # 构建上报参数
            report_kwargs = {
                "adsid": fbclid,  # 使用 fbclid 作为 adsid 事件 ID
                "event": "ViewContent",
                "email": email,
                "ip": client_ip,  # 使用后端获取的客户端 IP
                "phone": phone,
                "ua": ua_from_request,
                "source": "short_link"
            }
            
            # 如果提供了 dp 参数，添加到 source 中以便区分
            if resolved_dp:
                report_kwargs["source"] = f"short_link_dp_{resolved_dp}"
                logger.warning(f"[第三方上报] 检测到 dp 参数：{resolved_dp}，已更新 source 标识")
            
            # 使用新的映射服务获取像素配置（使用 dp 参数匹配）
            dp_param = resolved_dp if resolved_dp else "master"  # 默认使用 master
            logger.info(f"[第三方上报] 使用 dp 参数获取像素配置：dp={dp_param}, short_code={id}")
            
            # 初始化 pixel_config 为 None
            pixel_config = None
            
            try:
                # 从缓存或数据库获取像素配置
                pixel_config = await get_cloak_pixel_config(db, dp=dp_param, short_code=id, use_cache=True)
                
                if pixel_config:
                    # 使用斗篷的自定义像素配置
                    report_kwargs["facebook_pixel_id"] = pixel_config["facebook_pixel_id"]
                    report_kwargs["facebook_access_token"] = pixel_config["facebook_access_token"]
                    report_kwargs["facebook_api_version"] = pixel_config["facebook_api_version"]
                    
                    logger.info(
                        f"[第三方上报] 使用斗篷自定义像素配置："
                        f"dp={dp_param}, short_code={id}, "
                        f"pixel_id={pixel_config['facebook_pixel_id'][:10] if pixel_config['facebook_pixel_id'] else '全局配置'}..."
                    )
                else:
                    # 未找到斗篷配置，使用全局配置
                    logger.info(
                        f"[第三方上报] 未找到斗篷像素配置，将使用全局配置："
                        f"dp={dp_param}, short_code={id}"
                    )
            except Exception as e:
                logger.error(
                    f"[第三方上报] 获取像素配置失败：dp={dp_param}, short_code={id}, error={str(e)}",
                    exc_info=True
                )
            
            # 如果 pixel_config 为 None，使用全局配置
            if not pixel_config:
                report_kwargs["facebook_pixel_id"] = settings.FACEBOOK_PIXEL_ID
                report_kwargs["facebook_access_token"] = settings.FACEBOOK_ACCESS_TOKEN
                report_kwargs["facebook_api_version"] = settings.FACEBOOK_API_VERSION
                logger.info(
                    f"[第三方上报] 使用全局配置："
                    f"pixel_id={settings.FACEBOOK_PIXEL_ID[:10]}..."
                )
            
            # 添加到后台任务队列
            # background_tasks.add_task(send_third_party_report, **report_kwargs)
            # logger.warning(
            #     f"[第三方上报] 已添加到后台任务队列："
            #     f"adsid={fbclid}, ip={client_ip}, source={report_kwargs['source']}, "
            #     f"pixel_config={'自定义' if pixel_config else '全局'}"
            # )

        # 返回成功响应
        logger.warning(f"[斗篷点击] 处理完成：id={id}, fbclid={fbclid}, client_ip={client_ip}")
        return {"status": "success", "message": "Report received", "client_ip": client_ip, "fbclid": fbclid}
    except Exception as e:
        logger.error(f"[斗篷点击] 处理异常：error={str(e)}", exc_info=True)
        return {"status": "error", "message": "Failed to process report"}


@router.get("/bridge/{filename}",
            summary="服务桥页静态资源（图片、CSS、JS 等）",
            tags=["短链接服务"])
async def serve_bridge_static(
        filename: str,
        request: Request = None
):
    """
    服务桥页的静态资源文件
    
    功能说明：
    - 当 HTML 中引用 /bridge/109.png 时，返回 /data/Platform/scripts/bridge/109.png
    - 支持图片、CSS、JS 等静态资源
    - 自动检测文件类型并设置正确的 Content-Type
    """
    # 安全验证：只允许字母、数字、连字符、下划线和点
    if not re.match(r'^[a-zA-Z0-9_.-]+$', filename):
        logger.warning(f"[桥页静态资源] 文件名包含非法字符：{filename}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在"
        )
    
    # 构建文件路径
    # 服务器路径：/data/Platform/scripts/bridge/filename
    scripts_dir_server = "/data/Platform/scripts/bridge"
    
    # 本地开发路径
    current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    scripts_dir_local = os.path.join(current_dir, "scripts", "bridge")
    
    file_path_server = os.path.join(scripts_dir_server, filename)
    file_path_local = os.path.join(scripts_dir_local, filename)
    
    # 选择文件路径
    file_path = None
    if os.path.exists(file_path_server) and os.path.isfile(file_path_server):
        file_path = file_path_server
        logger.debug(f"[桥页静态资源] 使用服务器路径：{file_path}")
    elif os.path.exists(file_path_local) and os.path.isfile(file_path_local):
        file_path = file_path_local
        logger.debug(f"[桥页静态资源] 使用本地路径：{file_path}")
    else:
        logger.warning(f"[桥页静态资源] 文件不存在：{filename}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在"
        )
    
    # 根据文件扩展名设置 Content-Type
    content_type_map = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.svg': 'image/svg+xml',
        '.webp': 'image/webp',
        '.css': 'text/css',
        '.js': 'application/javascript',
        '.json': 'application/json',
        '.html': 'text/html',
    }
    
    _, ext = os.path.splitext(filename)
    content_type = content_type_map.get(ext.lower(), 'application/octet-stream')
    
    logger.debug(f"[桥页静态资源] 返回文件：{file_path}, Content-Type: {content_type}")
    
    # 返回文件响应，并设置 CSP 头
    response = FileResponse(file_path, media_type=content_type)
    response.headers[
        "Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; img-src 'self' data: https: blob:; font-src 'self' data: https://cdnjs.cloudflare.com; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; upgrade-insecure-requests"
    response.headers["Cache-Control"] = "public, max-age=604800, immutable"
    response.headers["X-Content-Type-Options"] = "nosniff"
    
    return response
