"""
短链接重定向路由模块
定义短链接重定向的 API 端点
"""
import base64
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
from app.core.device_info import collect_request_info
from app.core.short_link_cache import get_short_link_from_cache, update_short_link_cache
from app.core.redis_client import get_redis_client
from app.core.tracking.click_id_generator import generate_click_id_from_timestamp
from app.models.models import ShortLink, CloakConfig
from app.core.auto_bot import send_telegram_message
from app.core.config import settings
from app.core.third_party_report import send_third_party_report
from app.services.cloak_pixel_mapping import get_cloak_pixel_config
from app.core.cloak_scripts_paths import read_bridge_html_template_cached, resolve_bridge_html_read_path
# 引入短链接处理函数
from app.routes.short_link.handlers import handle_cached_redirect, handle_database_redirect
from app.routes.short_link.placeholder import replace_short_link_placeholders
from app.routes.short_link.url_builder import build_final_url
from app.routes.short_link.utils import resolve_offer_id, resolve_default_publisher_for_offer
from app.routes.short_link_redirect import _create_click_record

logger = logging.getLogger(__name__)

# 创建FastAPI路由实例
router = APIRouter()

# 桥页注入：在 DOMContentLoaded 时请求 /report?phase=load（与 cloak_configs.load_report_enabled 配合）
_CLOAK_LOAD_REPORT_INJECT = (
    "<script>(function(){document.addEventListener('DOMContentLoaded',function(){try{"
    "var M=window.__CLOAK_META__||{};if(!M.load_report_enabled)return;"
    "if(sessionStorage.getItem('cloak_load_fb_done'))return;"
    "var segs=location.pathname.split('/').filter(function(x){return x;});"
    "var shortId=segs[segs.length-1]||'';if(!shortId)return;"
    "var email=sessionStorage.getItem('ad_event_email');var phone=sessionStorage.getItem('ad_event_phone');"
    "if(!email){var u=['user','uk_shopper','customer','member','save'];"
    "var d=['gmail.com','outlook.com','yahoo.co.uk','btinternet.com'];"
    "email=u[Math.floor(Math.random()*u.length)]+Math.floor(Math.random()*10000)+'@'+d[Math.floor(Math.random()*d.length)];"
    "sessionStorage.setItem('ad_event_email',email);}"
    "if(!phone){phone=String(Math.floor(7e9+Math.random()*9e9));sessionStorage.setItem('ad_event_phone',phone);}"
    "var fbc=(function(){try{var p=new URLSearchParams(location.search);var f=p.get('fbclid');"
    "if(f&&String(f).trim())return String(f).trim().substring(0,200);}catch(e1){}"
    "return 'xxxxxxxxxxxx4xxxyxxxxxxxxxxxxxxx'.replace(/[xy]/g,function(c){var r=Math.random()*16|0,v=c==='x'?r:(r&0x3|0x8);return v.toString(16);});})();"
    "var dpv=(M.dp||'');var qs='id='+encodeURIComponent(shortId)+'&phase=load&fbclid='+encodeURIComponent(fbc)+"
    "'&email='+encodeURIComponent(email)+'&phone='+encodeURIComponent(phone);"
    "if(dpv)qs+='&dp='+encodeURIComponent(dpv);"
    "if(typeof cloakReportQuerySuffix==='function'){qs+=cloakReportQuerySuffix();}"
    "fetch(location.origin+'/report?'+qs,{method:'GET'}).then(function(r){if(r&&r.ok)sessionStorage.setItem('cloak_load_fb_done','1');}).catch(function(){});"
    "}catch(e){}});})();</script>"
)


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
    - 当 dp 为纯数字（如 145）时，与平台 Offer 主键对齐，用于占位符替换、渠道回退及 /report 点击归因
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

        # 与 /s/{short_code} 一致：替换 {click_id}、{channel_id} 等占位符，并合并本次请求的查询参数
        request_params = {k.lower(): v for k, v in request.query_params.items()}
        offer_id_q: Optional[int] = None
        channel_id_q: Optional[int] = None
        for key, raw in (
            ("offer_id", request.query_params.get("offer_id")),
            ("channel_id", request.query_params.get("channel_id")),
        ):
            if raw is None or (isinstance(raw, str) and raw.strip() == ""):
                continue
            try:
                val = int(raw) if not isinstance(raw, list) else int(raw[0])
                if key == "offer_id":
                    offer_id_q = val
                else:
                    channel_id_q = val
            except (TypeError, ValueError):
                pass
        meta = cached_data if cached_data else {}
        if offer_id_q is None and meta.get("offer_id") is not None:
            try:
                offer_id_q = int(meta["offer_id"])
            except (TypeError, ValueError):
                pass
        if channel_id_q is None and meta.get("channel_id") is not None:
            try:
                channel_id_q = int(meta["channel_id"])
            except (TypeError, ValueError):
                pass
        if offer_id_q is None or channel_id_q is None:
            try:
                sl_res = await db.execute(select(ShortLink).where(ShortLink.short_code == short_code))
                sl_for_meta = sl_res.scalars().first()
                if sl_for_meta:
                    if offer_id_q is None and sl_for_meta.offer_id is not None:
                        offer_id_q = int(sl_for_meta.offer_id)
                    if channel_id_q is None and sl_for_meta.channel_id is not None:
                        channel_id_q = int(sl_for_meta.channel_id)
            except Exception as exc:
                logger.warning("[斗篷服务] 读取短链 offer/channel 用于占位符: %s", exc)

        # 纯数字 dp（如 145）= 平台 Offer 主键：覆盖短链上的 offer_id，保证与斗篷页一致
        if dp is not None:
            dp_s = str(dp).strip()
            if dp_s.isdigit():
                try:
                    offer_id_q = int(dp_s)
                except (TypeError, ValueError):
                    pass

        click_id_cloak = generate_click_id_from_timestamp()
        request_info_cloak = collect_request_info(request) if request else {}
        final_channel_id_cloak = channel_id_q
        final_offer_id_cloak, advertiser_id_cloak = await resolve_offer_id(offer_id_q, db)
        # 短链未填 channel_id 时，从该产品已绑定的启用渠道中回退（使用解析后的 Offer 主键）
        if final_channel_id_cloak is None and final_offer_id_cloak is not None:
            fallback_pub = await resolve_default_publisher_for_offer(final_offer_id_cloak, db)
            if fallback_pub is not None:
                final_channel_id_cloak = fallback_pub
                channel_id_q = fallback_pub
                logger.info(
                    "[斗篷服务] 短链未配置渠道，已按产品绑定回退: short_code=%s offer_id=%s publisher_id=%s",
                    short_code,
                    final_offer_id_cloak,
                    fallback_pub,
                )
        original_url_before_replace = original_url
        original_url_after_replace = await replace_short_link_placeholders(
            original_url_before_replace,
            click_id_cloak,
            final_offer_id_cloak,
            final_channel_id_cloak,
            advertiser_id_cloak,
            request_info_cloak,
            db,
        )
        original_url = build_final_url(
            original_url_before_replace,
            original_url_after_replace,
            click_id_cloak,
            offer_id_q,
            channel_id_q,
            final_channel_id_cloak,
            request_params,
            request_info_cloak,
            advertiser_id_cloak,
        )
        logger.debug(
            "[斗篷服务] 斗篷跳转基址（占位符已处理）: short_code=%s click_id=%s url=%s",
            short_code,
            click_id_cloak,
            original_url[:200] + ("..." if len(original_url) > 200 else ""),
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

        # 注入与 cloak_configs 一致的「上报事件 / 金额 / 货币」，供桥页 /report 请求携带（与服务端实际 CAPI 一致）
        cloak_key = bridge_page_name[:-5] if bridge_page_name.endswith(".html") else "master"

        # 写入短链接访问记录（clicks 表）：与 /s/ 重定向相同走 Redis 队列 / 后台任务，便于「短链接访问记录」统一查询
        if background_tasks:
            try:
                sl_pk = (cached_data or {}).get("id")
                if not sl_pk:
                    sid_row = await db.execute(select(ShortLink.id).where(ShortLink.short_code == short_code))
                    sl_pk = sid_row.scalar()
                if sl_pk:
                    request_info_visit = dict(request_info_cloak)
                    try:
                        up_m: dict = {}
                        if request_info_visit.get("url_params"):
                            up_m = json.loads(request_info_visit["url_params"])
                    except Exception:
                        up_m = {}
                    up_m["cloak_visit"] = True
                    up_m["cloak_dp_effective"] = cloak_key
                    q_dp = request.query_params.get("dp") if request else None
                    if q_dp:
                        up_m["cloak_dp_query"] = str(q_dp).strip()[:200]
                    request_info_visit["url_params"] = json.dumps(up_m, ensure_ascii=False)
                    await _create_click_record(
                        click_id_cloak,
                        int(sl_pk),
                        final_offer_id_cloak,
                        final_channel_id_cloak,
                        advertiser_id_cloak,
                        request_info_visit,
                        background_tasks,
                        original_request_url=str(request.url) if request else None,
                        final_redirect_url=original_url,
                    )
                    logger.info(
                        "[斗篷服务] 已排队短链接访问记录（桥页）short_code=%s click_id=%s cloak_dp_effective=%s",
                        short_code,
                        click_id_cloak,
                        cloak_key,
                    )
            except Exception as exc:
                logger.warning("[斗篷服务] 排队桥页访问记录失败: %s", exc, exc_info=True)

        try:
            cc_res = await db.execute(select(CloakConfig).where(CloakConfig.cloak_name == cloak_key))
            cloak_cfg_row = cc_res.scalars().first()
        except Exception as exc:
            logger.warning("[斗篷服务] 读取斗篷上报元数据失败 cloak_key=%s: %s", cloak_key, exc)
            cloak_cfg_row = None
        if cloak_cfg_row:
            cloak_meta = {
                "report_event": (cloak_cfg_row.report_event or "ViewContent").strip() or "ViewContent",
                "report_value": cloak_cfg_row.report_value,
                "report_currency": (cloak_cfg_row.report_currency or "USD").strip() or "USD",
                "dp": cloak_key,
                "click_report_enabled": bool(getattr(cloak_cfg_row, "click_report_enabled", True)),
                "load_report_enabled": bool(getattr(cloak_cfg_row, "load_report_enabled", False)),
                "load_report_event": (getattr(cloak_cfg_row, "load_report_event", None) or "PageView").strip()
                or "PageView",
                "load_report_value": getattr(cloak_cfg_row, "load_report_value", None),
                "load_report_currency": (getattr(cloak_cfg_row, "load_report_currency", None) or "USD").strip()
                or "USD",
            }
        else:
            cloak_meta = {
                "report_event": "ViewContent",
                "report_value": None,
                "report_currency": "USD",
                "dp": cloak_key,
                "click_report_enabled": True,
                "load_report_enabled": False,
                "load_report_event": "PageView",
                "load_report_value": None,
                "load_report_currency": "USD",
            }
        meta_b64 = base64.b64encode(json.dumps(cloak_meta, separators=(",", ":")).encode("utf-8")).decode("ascii")
        cloak_meta_snippet = (
            f'<script type="text/plain" id="cloak-report-meta-b64">{meta_b64}</script>'
            "<script>(function(){try{var t=document.getElementById('cloak-report-meta-b64');"
            "window.__CLOAK_META__=JSON.parse(atob(t.textContent.trim()));}catch(e){"
            "window.__CLOAK_META__={report_event:'ViewContent',report_value:null,report_currency:'USD',"
            "dp:'',click_report_enabled:true,load_report_enabled:false,load_report_event:'PageView',"
            "load_report_value:null,load_report_currency:'USD'};}"
            "window.cloakReportQuerySuffix=function(){var m=window.__CLOAK_META__||{},q='';"
            "if(m.report_event)q+='&report_event='+encodeURIComponent(m.report_event);"
            "if(m.report_event==='Purchase'&&m.report_value!=null&&m.report_value!==''){"
            "q+='&report_value='+encodeURIComponent(String(m.report_value));"
            "q+='&report_currency='+encodeURIComponent(m.report_currency||'USD');}"
            "return q;};})();</script>"
        )
        if "<head>" in html_content:
            html_content = html_content.replace("<head>", "<head>\n" + cloak_meta_snippet + "\n", 1)
        else:
            html_content = cloak_meta_snippet + "\n" + html_content

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

        if re.search(r"</body\s*>", html_content, flags=re.IGNORECASE):
            html_content = re.sub(
                r"</body\s*>",
                _CLOAK_LOAD_REPORT_INJECT + "</body>",
                html_content,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            html_content = html_content + "\n" + _CLOAK_LOAD_REPORT_INJECT

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
        phase: str = Query(
            "click",
            description="上报阶段：click=按钮点击（默认）, load=页面加载完成",
        ),
        request: Request = None,
        background_tasks: BackgroundTasks = None,
        db: AsyncSession = Depends(get_db)
):
    """
    处理短链接点击上报，更新点击次数并发送 Facebook 像素事件
    
    功能说明：
    - 前端通过 fetch("/report?id=509220&fbclid=xxx&email=xxx&phone=xxx&dp=master") 调用
    - 支持 dp 参数识别不同的桥页
    - 事件名与金额以「斗篷管理」保存的配置为准（来自 cloak_configs）；桥页可由 /change 注入的 cloakReportQuerySuffix() 在 URL 中带 report_* 参数以便核对，与服务端不一致时仍以服务端为准
    
    参数说明：
    - id: 短链接代码
    - fbclid: Facebook 点击 ID
    - email: 用户邮箱（用于 Facebook 像素上报）
    - phone: 用户手机号（用于 Facebook 像素上报）
    - dp: 桥页标识（可选，用于区分不同的桥页）
    - report_event / report_value / report_currency: 可选，须与斗篷配置一致（由桥页自动附加）
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

        report_phase_raw = (phase or "click").strip().lower()
        report_phase = report_phase_raw if report_phase_raw in ("load", "click") else "click"

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

        ua_from_request = request.headers.get("user-agent", "未知") if request else "未知"

        # 检查是否重复上报（加载与点击分 key，避免互相占用）
        session_id = request.cookies.get("session_id") if request else None
        dedupe_key = None
        if report_phase == "load":
            dedupe_id = session_id or fbclid or "anon"
            dedupe_key = f"cloak_load_fb:{id}:{dedupe_id}"
        elif session_id:
            dedupe_key = f"click_count:{id}:{session_id}"

        if dedupe_key:
            redis = await get_redis_client()
            if redis:
                try:
                    first_hit = await redis.set(dedupe_key, "1", ex=86400, nx=True)
                    if not bool(first_hit):
                        logger.debug(
                            "[斗篷上报] 重复请求跳过：phase=%s id=%s key=%s",
                            report_phase,
                            id,
                            dedupe_key,
                        )
                        dup_msg = (
                            "load report duplicate skip"
                            if report_phase == "load"
                            else "Report received (duplicate)"
                        )
                        return {
                            "status": "success",
                            "message": dup_msg,
                            "client_ip": client_ip,
                            "fbclid": fbclid,
                            "phase": report_phase,
                        }
                except Exception as e:
                    logger.warning(f"Redis检查上报去重失败: {e}")

        # 仅按钮点击阶段更新点击统计与 Click 记录
        if report_phase == "click":
            cached_data = await get_short_link_from_cache(id)

            if cached_data:
                logger.warning(
                    f"[斗篷点击] 从缓存获取数据: short_code={id}, 原始click_count={cached_data.get('click_count', 0)}")
                cached_data["click_count"] = (cached_data.get("click_count", 0)) + 1
                logger.warning(f"[斗篷点击] 更新缓存: short_code={id}, 新click_count={cached_data['click_count']}")
                update_result = await update_short_link_cache(id, cached_data)
                logger.warning(f"[斗篷点击] 缓存更新结果: {update_result}")

                if background_tasks:
                    async def create_click_and_update_db():
                        try:
                            db_session = AsyncSessionLocal()

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

                            from app.models.models import Click
                            from app.core.utils import get_app_now_naive

                            click = Click(
                                click_id=str(uuid.uuid4()),
                                short_link_id=None,
                                click_time=get_app_now_naive(),
                                ip=client_ip,
                                user_agent=ua_from_request,
                                referer=referer,
                                url_params=url_params_json,
                                original_request_url=str(request.url) if request else None,
                                is_bot=False
                            )

                            result = await db_session.execute(
                                select(ShortLink).where(ShortLink.short_code == id)
                            )
                            short_link = result.scalars().first()

                            if short_link:
                                click.short_link_id = short_link.id
                                # 纯数字 dp 与平台 Offer 主键对齐（如 dp=145 → offer 145），避免斗篷页未写短链 offer 时点击无单子、无渠道
                                offer_for_click = short_link.offer_id
                                if resolved_dp and str(resolved_dp).strip().isdigit():
                                    try:
                                        offer_for_click = int(str(resolved_dp).strip())
                                    except (TypeError, ValueError):
                                        pass
                                click.offer_id = offer_for_click
                                pub_for_click = short_link.channel_id
                                if pub_for_click is None and offer_for_click is not None:
                                    pub_for_click = await resolve_default_publisher_for_offer(
                                        offer_for_click, db_session
                                    )
                                click.publisher_id = pub_for_click
                                short_link.click_count = (short_link.click_count or 0) + 1
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
                logger.warning(f"[斗篷点击] 缓存未命中，从数据库查询: short_code={id}")
                result = await db.execute(select(ShortLink).where(ShortLink.short_code == id))
                short_link = result.scalars().first()

                if short_link:
                    logger.warning(
                        f"[斗篷点击] 数据库查询结果: short_code={id}, id={short_link.id}, 原始click_count={short_link.click_count or 0}")
                    short_link.click_count = (short_link.click_count or 0) + 1
                    logger.warning(f"[斗篷点击] 更新数据库: short_code={id}, 新click_count={short_link.click_count}")
                    try:
                        await db.commit()
                        logger.warning(f"[斗篷点击] 数据库提交成功")

                    except StaleDataError:
                        logger.warning(f"[斗篷点击] 数据库更新冲突，忽略StaleDataError")
                        await db.rollback()
                else:
                    logger.warning(f"[斗篷点击] 短链接不存在: short_code={id}")

        # Facebook CAPI：分 load / click
        if email and phone and background_tasks:
            dp_param = resolved_dp if resolved_dp else "master"
            logger.info(f"[第三方上报] phase={report_phase} dp={dp_param}, short_code={id}")

            pixel_config = None
            report_kwargs_fb: dict = {}
            try:
                pixel_config = await get_cloak_pixel_config(db, dp=dp_param, short_code=id, use_cache=True)
                if pixel_config:
                    report_kwargs_fb = {
                        "facebook_pixel_id": pixel_config["facebook_pixel_id"],
                        "facebook_access_token": pixel_config["facebook_access_token"],
                        "facebook_api_version": pixel_config["facebook_api_version"],
                    }
                else:
                    report_kwargs_fb = {
                        "facebook_pixel_id": settings.FACEBOOK_PIXEL_ID,
                        "facebook_access_token": settings.FACEBOOK_ACCESS_TOKEN,
                        "facebook_api_version": settings.FACEBOOK_API_VERSION,
                    }
                    logger.info(f"[第三方上报] 未找到斗篷像素配置，将使用全局配置：dp={dp_param}, short_code={id}")
            except Exception as e:
                logger.error(
                    f"[第三方上报] 获取像素配置失败：dp={dp_param}, short_code={id}, error={str(e)}",
                    exc_info=True,
                )
                report_kwargs_fb = {
                    "facebook_pixel_id": settings.FACEBOOK_PIXEL_ID,
                    "facebook_access_token": settings.FACEBOOK_ACCESS_TOKEN,
                    "facebook_api_version": settings.FACEBOOK_API_VERSION,
                }

            send_fb = False
            report_event = "ViewContent"
            report_value = None
            report_currency = "USD"
            source = "short_link"
            conv_seg = "click"

            if report_phase == "load":
                load_on = bool(pixel_config and pixel_config.get("cloak_load_report_enabled"))
                if not load_on:
                    logger.info("[斗篷加载上报] 未启用或无可选配置，跳过 CAPI")
                else:
                    send_fb = True
                    report_event = (pixel_config.get("cloak_load_report_event") or "PageView").strip() or "PageView"
                    rv = pixel_config.get("cloak_load_report_value")
                    if rv is not None:
                        try:
                            report_value = float(rv)
                        except (TypeError, ValueError):
                            report_value = None
                    report_currency = (
                        (pixel_config.get("cloak_load_report_currency") or "USD").strip().upper() or "USD"
                    )
                    source = f"short_link_load_dp_{dp_param}"
                    conv_seg = "load"
                    logger.info(
                        f"[第三方上报] 加载阶段：event={report_event}, pixel_id="
                        f"{pixel_config['facebook_pixel_id'][:10] if pixel_config.get('facebook_pixel_id') else ''}..."
                    )
            else:
                click_on = bool(not pixel_config or pixel_config.get("cloak_click_report_enabled", True))
                if not click_on:
                    logger.info("[斗篷点击上报] 已关闭，跳过 CAPI")
                else:
                    send_fb = True
                    if resolved_dp:
                        source = f"short_link_dp_{resolved_dp}"
                        logger.warning(f"[第三方上报] 检测到 dp 参数：{resolved_dp}，已更新 source 标识")
                    if pixel_config:
                        cloak_evt = pixel_config.get("cloak_report_event") or "ViewContent"
                        report_event = cloak_evt
                        rv = pixel_config.get("cloak_report_value")
                        if rv is not None:
                            try:
                                report_value = float(rv)
                            except (TypeError, ValueError):
                                report_value = None
                        report_currency = (
                            (pixel_config.get("cloak_report_currency") or "USD").strip().upper() or "USD"
                        )
                        logger.info(
                            f"[第三方上报] 点击阶段：event={report_event}, "
                            f"pixel_id={pixel_config['facebook_pixel_id'][:10] if pixel_config.get('facebook_pixel_id') else ''}..."
                        )

            if send_fb and request is not None and report_phase == "click":
                q_evt = request.query_params.get("report_event")
                q_val = request.query_params.get("report_value")
                q_cur = request.query_params.get("report_currency")
                if q_evt and q_evt != report_event:
                    logger.warning(
                        "[斗篷点击] URL 中 report_event=%s 与当前生效事件 %s 不一致，已以服务端配置为准",
                        q_evt,
                        report_event,
                    )
                if report_event == "Purchase" and report_value is not None and q_val is not None:
                    try:
                        if abs(float(q_val) - float(report_value)) > 1e-6:
                            logger.warning(
                                "[斗篷点击] URL 中 report_value=%s 与配置金额 %s 不一致，已以服务端配置为准",
                                q_val,
                                report_value,
                            )
                    except (TypeError, ValueError):
                        logger.warning("[斗篷点击] URL 中 report_value 无法解析: %s", q_val)
                if (
                    q_cur
                    and report_event == "Purchase"
                    and q_cur.strip().upper() != (report_currency or "").strip().upper()
                ):
                    logger.warning(
                        "[斗篷点击] URL 中 report_currency=%s 与配置 %s 不一致，已以服务端配置为准",
                        q_cur,
                        report_currency,
                    )

            if send_fb:
                report_kwargs = {
                    "adsid": fbclid,
                    "event": report_event,
                    "email": email,
                    "ip": client_ip,
                    "phone": phone,
                    "ua": ua_from_request,
                    "source": source,
                    **report_kwargs_fb,
                }
                if report_event == "Purchase":
                    report_kwargs["currency"] = report_currency
                    report_kwargs["amount"] = report_value
                    report_kwargs["conversion_id"] = f"cloak_{conv_seg}_{id}_{fbclid}"[:200]

                if report_event == "Purchase" and (report_value is None or report_value <= 0):
                    logger.error(
                        "[第三方上报] 事件为 Purchase 但未配置有效金额，跳过 Facebook 上报："
                        "short_code=%s dp=%s phase=%s",
                        id,
                        dp_param,
                        report_phase,
                    )
                else:
                    background_tasks.add_task(send_third_party_report, **report_kwargs)
                    logger.warning(
                        f"[第三方上报] 已添加到后台任务队列：phase={report_phase}, adsid={fbclid}, ip={client_ip}, "
                        f"source={source}, event={report_event}, pixel_config={'自定义' if pixel_config else '全局'}"
                    )

        # 返回成功响应
        logger.warning(f"[斗篷上报] 处理完成：phase={report_phase}, id={id}, fbclid={fbclid}, client_ip={client_ip}")
        return {
            "status": "success",
            "message": "Report received",
            "client_ip": client_ip,
            "fbclid": fbclid,
            "phase": report_phase,
        }
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
