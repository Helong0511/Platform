"""
斗篷 /report 点击上报路由

桥页前端在加载完成（phase=load）或按钮点击（phase=click）时请求本接口：
- 校验 email/phone、解析 dp 与客户端信息
- Redis 去重后更新短链点击计数
- 后台任务向 Facebook CAPI 发送对应阶段事件
"""
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.log_utils import mask_email, mask_phone
from app.routes.short_link.cloak_report_service import (
    duplicate_report_response,
    ensure_fbclid,
    extract_request_client_meta,
    normalize_report_phase,
    record_cloak_click_count,
    resolve_report_dp,
    schedule_cloak_facebook_report,
    build_dedupe_key,
    try_mark_report_dedupe,
)

logger = logging.getLogger(__name__)


def register_cloak_report_routes(router: APIRouter) -> None:
    """将 /report 路由注册到短链接路由器。"""

    @router.get(
        "/report",
        summary="处理短链接点击上报（支持 dp 参数和 Facebook 像素上报）",
        tags=["短链接服务"],
    )
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
            db: AsyncSession = Depends(get_db),
    ):
        """
        处理桥页前端发起的 load/click 阶段上报请求。

        处理流程：
        1. 解析客户端 IP/UA/Referer、dp 参数、上报阶段 phase
        2. 校验 email、phone 非空；fbclid 缺失时用 UUID 占位
        3. Redis 去重（load 同会话一次；click 同 session 计一次点击）
        4. phase=click 时递增 short_links.click_count 并排队写入 clicks 表
        5. 后台任务向 Facebook CAPI 发送对应阶段事件（见 cloak_report_service）

        注意：postback 转化上报不走本接口，由下游转化处理器单独触发。
        """
        try:
            # 提取客户端信息，供日志、落库与 CAPI user_data 使用
            meta = extract_request_client_meta(request)
            client_ip = meta["client_ip"]
            user_agent = meta["user_agent"]
            referer = meta["referer"]

            resolved_dp = resolve_report_dp(dp, request, referer)
            report_phase = normalize_report_phase(phase)

            if not email or not email.strip():
                logger.error("[斗篷点击] email 参数为空：email=%s", email)
                return {
                    "status": "error",
                    "message": "email 参数不能为空",
                    "client_ip": client_ip,
                }

            if not phone or not phone.strip():
                logger.error("[斗篷点击] phone 参数为空：phone=%s", phone)
                return {
                    "status": "error",
                    "message": "phone 参数不能为空",
                    "client_ip": client_ip,
                }

            fbclid = ensure_fbclid(fbclid)
            logger.debug("[斗篷点击] fbclid: %s", fbclid)

            logger.info(
                "report [斗篷点击] 收到上报: id=%s, fbclid=%s, client_ip=%s, "
                "email=%s, phone=%s, referer=%s",
                id, fbclid, client_ip, mask_email(email), mask_phone(phone), referer,
            )

            ua_from_request = (
                request.headers.get("user-agent", "未知") if request else "未知"
            )
            session_id = request.cookies.get("session_id") if request else None
            dedupe_key = build_dedupe_key(report_phase, id, session_id, fbclid)
            if dedupe_key and await try_mark_report_dedupe(dedupe_key):
                logger.debug(
                    "[斗篷上报] 重复请求跳过：phase=%s id=%s key=%s",
                    report_phase,
                    id,
                    dedupe_key,
                )
                return duplicate_report_response(report_phase, client_ip, fbclid)

            if report_phase == "click":
                await record_cloak_click_count(
                    id,
                    db,
                    background_tasks,
                    fbclid=fbclid,
                    resolved_dp=resolved_dp,
                    email=email,
                    phone=phone,
                    client_ip=client_ip,
                    user_agent=ua_from_request,
                    referer=referer,
                    original_request_url=str(request.url) if request else None,
                )

            if background_tasks:
                await schedule_cloak_facebook_report(
                    short_code=id,
                    report_phase=report_phase,
                    resolved_dp=resolved_dp,
                    fbclid=fbclid,
                    email=email,
                    phone=phone,
                    client_ip=client_ip,
                    ua_from_request=ua_from_request,
                    request=request,
                    db=db,
                    background_tasks=background_tasks,
                )

            logger.info(
                "[斗篷上报] 处理完成：phase=%s, id=%s, fbclid=%s, client_ip=%s",
                report_phase,
                id,
                fbclid,
                client_ip,
            )
            return {
                "status": "success",
                "message": "Report received",
                "client_ip": client_ip,
                "fbclid": fbclid,
                "phase": report_phase,
            }
        except Exception as exc:
            logger.error("[斗篷点击] 处理异常：error=%s", exc, exc_info=True)
            return {"status": "error", "message": "Failed to process report"}
