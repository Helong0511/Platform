"""Cloak /change bridge page routes."""
import json
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.core.device_info import collect_request_info
from app.core.short_link_cache import get_short_link_from_cache
from app.core.tracking.click_id_generator import generate_click_id_unified
from app.models.models import CloakConfig, ShortLink
from app.routes.short_link.cloak_bridge_html import (
    build_bridge_html_response,
    cloak_meta_from_row,
    prepare_bridge_html,
    resolve_bridge_html,
)
from app.routes.short_link.cloak_show_count import (
    resolve_cloak_change_original_url,
    resolve_session_id,
    should_persist_cloak_visit_click,
)
from app.routes.short_link.placeholder import replace_short_link_placeholders
from app.routes.short_link.url_builder import build_final_url
from app.routes.short_link.utils import (
    create_click_record,
    offer_id_from_numeric_dp,
    resolve_default_publisher_for_offer,
    resolve_offer_id,
)

logger = logging.getLogger(__name__)


def register_cloak_change_routes(router: APIRouter) -> None:
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

            session_id = resolve_session_id(request)
            original_url, is_first_visit = await resolve_cloak_change_original_url(
                short_code,
                session_id,
                cached_data,
                db,
                background_tasks,
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
            dp_as_offer = offer_id_from_numeric_dp(dp)
            if dp_as_offer is not None:
                offer_id_q = dp_as_offer

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
            # click_id 必须在渠道回退之后生成，否则令牌可能缺少 publisher_id，导致后续展示“未关联渠道”
            click_id_cloak = generate_click_id_unified(
                offer_id=final_offer_id_cloak,
                publisher_id=final_channel_id_cloak,
                advertiser_id=advertiser_id_cloak,
                short_link_id=(cached_data or {}).get("id"),
                url_params=request_info_cloak.get("url_params_dict")
                if isinstance(request_info_cloak.get("url_params_dict"), dict)
                else None,
                for_short_link=True,
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

            html_content, bridge_page_name, cloak_key = resolve_bridge_html(dp)
            logger.debug("[斗篷服务] 请求的桥页：%s", bridge_page_name)

            # 写入短链接访问记录（clicks 表）：仅本会话首次访问 + IP 短窗口去重，避免一次打开产生多条记录
            if background_tasks and is_first_visit:
                try:
                    sl_pk = (cached_data or {}).get("id")
                    if not sl_pk:
                        sid_row = await db.execute(select(ShortLink.id).where(ShortLink.short_code == short_code))
                        sl_pk = sid_row.scalar()
                    if sl_pk and await should_persist_cloak_visit_click(
                        short_code, session_id, client_ip
                    ):
                        request_info_visit = dict(request_info_cloak)
                        try:
                            up_m: dict = {}
                            if request_info_visit.get("url_params"):
                                loaded = json.loads(request_info_visit["url_params"])
                                up_m = loaded if isinstance(loaded, dict) else {}
                        except Exception:
                            up_m = {}
                        up_m["cloak_visit"] = True
                        up_m["cloak_dp_effective"] = cloak_key
                        q_dp = request.query_params.get("dp") if request else None
                        if q_dp:
                            up_m["cloak_dp_query"] = str(q_dp).strip()[:200]
                        request_info_visit["url_params"] = json.dumps(up_m, ensure_ascii=False)
                        await create_click_record(
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
                cc_res = await db.execute(
                    select(CloakConfig).where(CloakConfig.cloak_name == cloak_key)
                )
                cloak_cfg_row = cc_res.scalars().first()
            except Exception as exc:
                logger.warning(
                    "[斗篷服务] 读取斗篷上报元数据失败 cloak_key=%s: %s", cloak_key, exc
                )
                cloak_cfg_row = None

            cloak_meta = cloak_meta_from_row(cloak_cfg_row, cloak_key)
            html_content = prepare_bridge_html(
                html_content, cloak_meta, original_url, dp
            )
            logger.debug(
                "[斗篷服务] /change/%s 完成: bridge=%s url=%s",
                short_code,
                bridge_page_name,
                original_url[:120],
            )
            return build_bridge_html_response(html_content, session_id)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[斗篷服务] /change/{short_code} 请求处理异常: {str(e)}", exc_info=True)
            from app.routes.short_link.errors import raise_short_link_bad_config
            raise_short_link_bad_config(f"处理失败: {str(e)}")



