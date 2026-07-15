"""
斗篷 /report 业务逻辑层。

功能说明：
- dp 解析与校验、phase 规范化（load/click）、fbclid 补全
- Redis 去重（``build_dedupe_key`` + ``try_mark_report_dedupe``），避免重复计数与重复 CAPI
- 短链 click_count 递增、缓存同步；click 阶段调度 ``cloak_click_persist`` 落库
- 后台任务调用 ``send_third_party_report`` 向 Facebook CAPI 发送对应阶段事件

与路由层分工：
- ``cloak_report.py``：HTTP 入参、脱敏日志、JSON 响应
- 本模块：可复用的纯业务函数，亦可被测试或其它入口调用

在系统中的位置：
- 依赖 ``app.services.cloak_pixel_mapping`` 获取像素配置（短链 / 启用中的斗篷，无全局回退）

注意事项：
1. dp 合法字符集与 Schema、像素映射服务保持一致（``_DP_RE``）
2. StaleDataError 等并发更新异常需捕获，避免阻断用户跳转体验
3. postback 转化上报不在此处理，勿在此模块发送 Purchase 等转化事件
"""
import logging
import re
import uuid
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from fastapi import BackgroundTasks, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm.exc import StaleDataError

from app.core.redis_client import get_redis_client
from app.core.short_link_cache import get_short_link_from_cache, update_short_link_cache
from app.core.third_party_report import send_third_party_report
from app.models.models import ShortLink
from app.routes.short_link.cloak_click_persist import schedule_cloak_report_click_persist
from app.services.cloak_pixel_mapping import get_cloak_pixel_config

logger = logging.getLogger(__name__)

# dp 参数合法字符集（与 Schema、像素映射服务一致）
_DP_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
# /report 接口支持的上报阶段（postback 由转化处理器单独处理，不走本模块）
_VALID_PHASES = frozenset({"load", "click"})


def extract_request_client_meta(request: Optional[Request]) -> Dict[str, str]:
    """从 FastAPI Request 提取客户端 IP、UA、Referer，用于日志与 CAPI user_data。"""
    if not request:
        return {"client_ip": "未知", "user_agent": "未知", "referer": "未知"}
    return {
        "client_ip": request.client.host if request.client else "未知",
        "user_agent": request.headers.get("user-agent", "未知"),
        "referer": request.headers.get("referer", "未知"),
    }


def resolve_report_dp(
        dp: Optional[str],
        request: Optional[Request],
        referer: str,
) -> Optional[str]:
    """
    解析本次上报关联的斗篷名（dp）。

    优先级：Query 参数 dp → 请求 query 中大小写变体 → Referer URL 中的 dp。
    格式非法时返回 None 并打警告日志。
    """
    resolved = dp.strip() if dp and dp.strip() else None
    if not resolved and request:
        for key in ("dp", "DP", "Dp"):
            query_dp = request.query_params.get(key)
            if query_dp and query_dp.strip():
                resolved = query_dp.strip()
                break
    if not resolved and referer and referer != "未知":
        try:
            referer_dp = parse_qs(urlparse(referer).query).get("dp", [])
            if referer_dp and referer_dp[0].strip():
                resolved = referer_dp[0].strip()
                logger.info("[斗篷点击] 从 Referer 回填 dp 参数：dp=%s", resolved)
        except Exception as exc:
            logger.warning("[斗篷点击] 从 Referer 解析 dp 失败：%s", exc)
    if resolved and not _DP_RE.match(resolved):
        logger.warning("[斗篷点击] dp 参数格式非法，忽略：dp=%s", resolved)
        return None
    return resolved


def normalize_report_phase(phase: Optional[str]) -> str:
    """将 phase 规范为 load 或 click，未知值默认 click。"""
    raw = (phase or "click").strip().lower()
    return raw if raw in _VALID_PHASES else "click"


def build_dedupe_key(
        report_phase: str,
        short_code: str,
        session_id: Optional[str],
        fbclid: str,
) -> Optional[str]:
    """
    构造 Redis 去重键。

    - load：同会话/同 short_code 仅上报一次 Facebook（键含 session 或 fbclid）
    - click：同 session 仅计一次点击（与 click_count 统计一致）
    """
    if report_phase == "load":
        dedupe_id = session_id or fbclid or "anon"
        return f"cloak_load_fb:{short_code}:{dedupe_id}"
    if session_id:
        return f"click_count:{short_code}:{session_id}"
    return None


async def try_mark_report_dedupe(dedupe_key: str) -> bool:
    """
    尝试在 Redis 中标记去重键（SET NX，TTL 24 小时）。

    Returns:
        True 表示重复请求（键已存在）；False 表示首次请求或 Redis 不可用。
    """
    redis = await get_redis_client()
    if not redis:
        return False
    try:
        first_hit = await redis.set(dedupe_key, "1", ex=86400, nx=True)
        return not bool(first_hit)
    except Exception as exc:
        logger.warning("Redis检查上报去重失败: %s", exc)
        return False


def duplicate_report_response(
        report_phase: str,
        client_ip: str,
        fbclid: str,
) -> Dict[str, Any]:
    """去重命中时返回与成功相同结构的 JSON，避免前端重试逻辑误判为失败。"""
    msg = (
        "load report duplicate skip"
        if report_phase == "load"
        else "Report received (duplicate)"
    )
    return {
        "status": "success",
        "message": msg,
        "client_ip": client_ip,
        "fbclid": fbclid,
        "phase": report_phase,
    }


async def record_cloak_click_count(
        short_code: str,
        db: AsyncSession,
        background_tasks: Optional[BackgroundTasks],
        *,
        fbclid: str,
        resolved_dp: Optional[str],
        email: str,
        phone: str,
        client_ip: str,
        user_agent: str,
        referer: str,
        original_request_url: Optional[str],
) -> None:
    """
    点击阶段（phase=click）递增短链 click_count，并排队写入 clicks 表。

    优先更新 Redis 缓存中的计数；缓存未命中则直接写库。落库细节见 cloak_click_persist。
    """
    cached_data = await get_short_link_from_cache(short_code)
    if cached_data:
        logger.debug(
            "[斗篷点击] 从缓存获取数据: short_code=%s, 原始click_count=%s",
            short_code,
            cached_data.get("click_count", 0),
        )
        cached_data["click_count"] = cached_data.get("click_count", 0) + 1
        logger.debug(
            "[斗篷点击] 更新缓存: short_code=%s, 新click_count=%s",
            short_code,
            cached_data["click_count"],
        )
        update_result = await update_short_link_cache(short_code, cached_data)
        logger.debug("[斗篷点击] 缓存更新结果: %s", update_result)
        if background_tasks:
            schedule_cloak_report_click_persist(
                background_tasks,
                short_code=short_code,
                fbclid=fbclid,
                resolved_dp=resolved_dp,
                email=email,
                phone=phone,
                client_ip=client_ip,
                user_agent=user_agent,
                referer=referer,
                original_request_url=original_request_url,
                sync_short_link_click_count=True,
            )
        return

    logger.debug("[斗篷点击] 缓存未命中，从数据库查询: short_code=%s", short_code)
    result = await db.execute(
        select(ShortLink).where(ShortLink.short_code == short_code)
    )
    short_link = result.scalars().first()
    if not short_link:
        logger.warning("[斗篷点击] 短链接不存在: short_code=%s", short_code)
        return

    logger.debug(
        "[斗篷点击] 数据库查询结果: short_code=%s, id=%s, 原始click_count=%s",
        short_code,
        short_link.id,
        short_link.click_count or 0,
    )
    short_link.click_count = (short_link.click_count or 0) + 1
    logger.debug(
        "[斗篷点击] 更新数据库: short_code=%s, 新click_count=%s",
        short_code,
        short_link.click_count,
    )
    try:
        await db.commit()
        logger.debug("[斗篷点击] 数据库提交成功")
    except StaleDataError:
        logger.debug("[斗篷点击] 数据库更新冲突，忽略 StaleDataError")
        await db.rollback()
    else:
        if background_tasks:
            schedule_cloak_report_click_persist(
                background_tasks,
                short_code=short_code,
                fbclid=fbclid,
                resolved_dp=resolved_dp,
                email=email,
                phone=phone,
                client_ip=client_ip,
                user_agent=user_agent,
                referer=referer,
                original_request_url=original_request_url,
                sync_short_link_click_count=False,
            )


def _log_url_report_mismatch(
        request: Request,
        report_event: str,
        report_value: Optional[float],
        report_currency: str,
) -> None:
    """若桥页 URL 携带 report_* 查询参数但与服务端配置不一致，仅打警告（以服务端为准）。"""
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


def _resolve_fb_report_params(
        report_phase: str,
        pixel_config: Optional[Dict[str, Any]],
        resolved_dp: Optional[str],
        dp_param: str,
) -> tuple[bool, str, Optional[float], str, str, str]:
    """
    根据阶段与像素配置决定是否发送 CAPI，并解析事件名、金额、货币、source 标识。

    Returns:
        (send_fb, report_event, report_value, report_currency, source, conv_seg)
    """
    send_fb = False
    report_event = "ViewContent"
    report_value: Optional[float] = None
    report_currency = "USD"
    source = "short_link"
    conv_seg = "click"

    if report_phase == "load":
        load_on = bool(pixel_config and pixel_config.get("cloak_load_report_enabled"))
        if not load_on:
            logger.info("[斗篷加载上报] 未启用或无可选配置，跳过 CAPI")
        else:
            send_fb = True
            report_event = (
                (pixel_config.get("cloak_load_report_event") or "PageView").strip()
                or "PageView"
            )
            rv = pixel_config.get("cloak_load_report_value")
            if rv is not None:
                try:
                    report_value = float(rv)
                except (TypeError, ValueError):
                    report_value = None
            report_currency = (
                (pixel_config.get("cloak_load_report_currency") or "USD").strip().upper()
                or "USD"
            )
            source = f"short_link_load_dp_{dp_param}"
            conv_seg = "load"
    else:
        # 无像素配置时不报；有配置则看点击阶段开关
        click_on = bool(
            pixel_config and pixel_config.get("cloak_click_report_enabled", True)
        )
        if not click_on:
            logger.info("[斗篷点击上报] 已关闭或无可选配置，跳过 CAPI")
        else:
            send_fb = True
            if resolved_dp:
                source = f"short_link_dp_{resolved_dp}"
                logger.info("[第三方上报] 检测到 dp 参数：%s，已更新 source 标识", resolved_dp)
            report_event = pixel_config.get("cloak_report_event") or "ViewContent"
            rv = pixel_config.get("cloak_report_value")
            if rv is not None:
                try:
                    report_value = float(rv)
                except (TypeError, ValueError):
                    report_value = None
            report_currency = (
                (pixel_config.get("cloak_report_currency") or "USD").strip().upper()
                or "USD"
            )

    return send_fb, report_event, report_value, report_currency, source, conv_seg


async def schedule_cloak_facebook_report(
        *,
        short_code: str,
        report_phase: str,
        resolved_dp: Optional[str],
        fbclid: str,
        email: str,
        phone: str,
        client_ip: str,
        ua_from_request: str,
        request: Optional[Request],
        db: AsyncSession,
        background_tasks: BackgroundTasks,
) -> None:
    """
    解析像素配置与阶段参数后，将 send_third_party_report 加入后台任务队列。

    无 dp 时默认按 master 查斗篷配置；Purchase 无有效金额时跳过上报并记错误日志。
    """
    if not (email and phone and background_tasks):
        return

    dp_param = resolved_dp if resolved_dp else "master"
    logger.info("[第三方上报] phase=%s dp=%s, short_code=%s", report_phase, dp_param, short_code)

    pixel_config = None
    try:
        pixel_config = await get_cloak_pixel_config(
            db, dp=dp_param, short_code=short_code, use_cache=True
        )
    except Exception as exc:
        logger.error(
            "[第三方上报] 获取像素配置失败：dp=%s, short_code=%s, error=%s",
            dp_param,
            short_code,
            exc,
            exc_info=True,
        )
        return

    if not pixel_config:
        logger.info(
            "[第三方上报] 无可用像素配置，跳过 Facebook 上报：dp=%s, short_code=%s, phase=%s",
            dp_param,
            short_code,
            report_phase,
        )
        return

    report_kwargs_fb: Dict[str, Any] = {
        "facebook_pixel_id": pixel_config["facebook_pixel_id"],
        "facebook_access_token": pixel_config["facebook_access_token"],
        "facebook_api_version": pixel_config["facebook_api_version"],
    }

    send_fb, report_event, report_value, report_currency, source, conv_seg = (
        _resolve_fb_report_params(report_phase, pixel_config, resolved_dp, dp_param)
    )

    if send_fb and request is not None and report_phase == "click":
        _log_url_report_mismatch(request, report_event, report_value, report_currency)

    if not send_fb:
        return

    report_kwargs: Dict[str, Any] = {
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
        report_kwargs["conversion_id"] = f"cloak_{conv_seg}_{short_code}_{fbclid}"[:200]

    if report_event == "Purchase" and (report_value is None or report_value <= 0):
        logger.error(
            "[第三方上报] 事件为 Purchase 但未配置有效金额，跳过 Facebook 上报："
            "short_code=%s dp=%s phase=%s",
            short_code,
            dp_param,
            report_phase,
        )
        return

    background_tasks.add_task(send_third_party_report, **report_kwargs)
    logger.info(
        "[第三方上报] 已添加到后台任务队列：phase=%s, adsid=%s, ip=%s, "
        "source=%s, event=%s, pixel_config=%s",
        report_phase,
        fbclid,
        client_ip,
        source,
        report_event,
        "斗篷/短链配置",
    )


def ensure_fbclid(fbclid: Optional[str]) -> str:
    """桥页未传 fbclid 时用 UUID 占位，保证 CAPI fbc 链路可构造。"""
    return fbclid if fbclid else str(uuid.uuid4())
