"""点击追踪 API

职责：接收渠道点击、生成 Click ID、拼装下游 Tracklink 并 302 跳转至上游 Offer。

权限：追踪跳转端点公开；调试/查询接口需登录。

主要端点（无前缀，注意路由顺序）：
- GET /track/{offer_id}           主追踪入口（生成 click 并跳转）
- GET /track/click/{click_id}     按已有 Click ID 重定向。

说明：点击追踪与短链接服务，记录访问并对接斗篷跳转。"""
import json
import logging
import asyncio
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Path, Request, BackgroundTasks
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db, AsyncSessionLocal
from app.core.security import get_current_user
from app.core.utils import get_app_now_naive
from app.core.tracking.click_id_generator import (
    generate_click_id_from_timestamp,
    generate_click_id_unified,
    generate_unique_click_id,
)
from app.core.tracking.click_token import regenerate_click_id_from_click_data
from app.core.tracking.tracklink_generator import generate_downstream_tracklink
from app.core.device_info import collect_request_info
from app.models.models import User, Offer, Publisher, Click, OfferPublisherAssignment
from app.schemas.base import ResponseBaseSchema
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode

router = APIRouter()
logger = logging.getLogger(__name__)


# 后台任务：创建点击记录（带重试机制）
async def create_click_background(click_data: dict, max_retries: int = 3):
    """
    异步创建点击记录，带有限重试。

    click_id 是单次点击的幂等键。重复 ID 表示同一事件已入库，必须跳过，
    不能重新生成 ID，否则 Redis 队列回退与后台直写并发时会重复记录同一次点击。
    """
    async with AsyncSessionLocal() as session:
        for attempt in range(max(1, int(max_retries))):
            try:
                click_id = click_data.get("click_id")
                if click_id:
                    existing_click = await session.execute(
                        select(Click.id).where(Click.click_id == click_id).limit(1)
                    )
                    if existing_click.scalar_one_or_none() is not None:
                        logger.info(
                            "点击记录已存在，按 click_id 幂等跳过: click_id=%s",
                            click_id,
                        )
                        await session.rollback()
                        return

                session.add(Click(**click_data))
                await session.commit()
                logger.debug("点击记录保存成功: click_id=%s", click_id)
                return

            except IntegrityError as exc:
                error_msg = str(
                    exc.orig if getattr(exc, "orig", None) else exc
                ).lower()
                duplicate_click_id = (
                    ("duplicate entry" in error_msg and "click_id" in error_msg)
                    or (
                        "unique constraint" in error_msg
                        and "click_id" in error_msg
                    )
                    or (
                        "duplicate key" in error_msg
                        and "click_id" in error_msg
                    )
                )
                await session.rollback()
                if duplicate_click_id:
                    logger.info(
                        "并发写入已先完成该点击，按 click_id 幂等跳过: click_id=%s",
                        click_data.get("click_id"),
                    )
                    return

                if attempt < max(1, int(max_retries)) - 1:
                    logger.warning(
                        "异步保存点击记录遇到完整性错误，将重试: attempt=%s error_type=%s",
                        attempt + 1,
                        type(exc).__name__,
                    )
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise

            except Exception as exc:
                await session.rollback()
                if attempt < max(1, int(max_retries)) - 1:
                    logger.warning(
                        "异步保存点击记录失败，将重试: attempt=%s error_type=%s",
                        attempt + 1,
                        type(exc).__name__,
                    )
                    await asyncio.sleep(2 ** attempt)
                    continue
                logger.error(
                    "异步保存点击记录最终失败: error_type=%s",
                    type(exc).__name__,
                )
                raise


@router.get("/track/click/{offer_id}", summary="点击追踪", tags=["点击追踪"])
async def track_click(
    offer_id: int = Path(..., ge=1, description="Offer ID"),
    publisher_id: int = Query(..., ge=1, description="渠道ID"),
    background_tasks: BackgroundTasks = None,  # 注入 BackgroundTasks
    request: Request = None,
    db: AsyncSession = Depends(get_db)
):
    """
    点击追踪接口（公开接口，无需认证）
    记录点击信息并生成 Click ID，然后重定向到目标 URL
    
    功能：处理业务请求（track_click）。
    实现：异步端点，通过 Service 层访问数据库/缓存。
    鉴权：由 Depends(get_current_user) 或 require_admin 控制访问范围。
    响应：统一 ResponseBaseSchema / PaginatedResponseBaseSchema 包装。
    """
    # ---------- 入口：参数与依赖准备 ----------
    # ---------- 异常处理 ----------
    try:
        # 1. 查询 Offer
        result = await db.execute(
            select(Offer).where(Offer.id == offer_id)
        )
        offer = result.scalars().first()
        
        # ---------- 条件分支 ----------
        if not offer:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"Offer ID {offer_id} 不存在"
            )
        
        # ---------- 条件分支 ----------
        if not offer.is_active or offer.status != 'Active':
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail="Offer 已下线"
            )
        
        # 2. 查询 Publisher
        pub_result = await db.execute(
            select(Publisher).where(Publisher.id == publisher_id)
        )
        publisher = pub_result.scalars().first()
        
        # ---------- 条件分支 ----------
        if not publisher:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"渠道ID {publisher_id} 不存在"
            )

        if not publisher.is_active:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail="渠道已停用"
            )

        # 2.1 校验 Offer–渠道分配（防止未授权归因）
        assignment_result = await db.execute(
            select(OfferPublisherAssignment.id).where(
                OfferPublisherAssignment.offer_id == offer_id,
                OfferPublisherAssignment.publisher_id == publisher_id,
                OfferPublisherAssignment.is_active.is_(True),
            ).limit(1)
        )
        if assignment_result.scalar_one_or_none() is None:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail="Offer 未分配给该渠道"
            )
        
        # 3. 生成 Click ID
        # 先检查是否有重复的 Click ID
        existing_click_ids = set()
        # 这里可以优化：只检查最近生成的 Click ID，而不是全部
        # 4. 收集完整的请求信息（包括软件、硬件信息和URL参数）
        request_info = collect_request_info(request) if request else {}

        # 令牌生成使用 dict 版本；落库使用 url_params（JSON 字符串，含重复参数）
        url_params_dict = (
            request_info.get("url_params_dict")
            if isinstance(request_info.get("url_params_dict"), dict)
            else None
        )

        click_id = generate_click_id_unified(
            offer_id=offer.id,
            publisher_id=publisher.id,
            advertiser_id=offer.advertiser_id,
            url_params=url_params_dict,
        )
        
        # 5. 创建点击记录
        click_data = {
            "click_id": click_id,
            "offer_id": offer.id,
            "publisher_id": publisher.id,
            "advertiser_id": offer.advertiser_id,
            "click_time": get_app_now_naive(),  # 使用北京时间
            "ip": request_info.get('ip'),
            "user_agent": request_info.get('user_agent'),
            "referer": request_info.get('referer'),
            "country": None,
            # 软件信息
            "os": request_info.get('os'),
            "os_version": request_info.get('os_version'),
            "browser": request_info.get('browser'),
            "browser_version": request_info.get('browser_version'),
            "accept_language": request_info.get('accept_language'),
            "accept_encoding": request_info.get('accept_encoding'),
            "is_bot": request_info.get('is_bot', False),
            # 硬件信息
            "device_type": request_info.get('device_type'),
            "device_brand": request_info.get('device_brand'),
            "device_model": request_info.get('device_model'),
            # URL参数和请求头
            "url_params": request_info.get('url_params'),
            "all_headers": request_info.get('all_headers'),
            # 兼容旧字段
            "device": request_info.get('device_type')  # 使用device_type作为device字段的值
        }
        
        from app.core.tracking.click_persist import persist_click_record

        await persist_click_record(click_data, background_tasks)
        
        # 原同步代码注释掉
        # click = Click(...)
        # db.add(click)
        # await db.commit()
        
        logger.info(f"点击请求已接收 (异步写入): click_id={click_id}, offer_id={offer_id}")
        
        # 6. 生成重定向 URL（使用下游 Tracklink 或 Preview Link）
        # ---------- 条件分支 ----------
        if offer.downstream_tracklink:
            # 如果有下游 Tracklink，使用它
            redirect_url = offer.downstream_tracklink.replace('{click_id}', click_id)
            # ---------- 条件分支 ----------
            if publisher:
                redirect_url = redirect_url.replace('{publisher_id}', str(publisher.id))
        # ---------- 条件分支 ----------
        elif offer.preview_link:
            # 否则使用 Preview Link，添加 Click ID 参数
            separator = '&' if '?' in offer.preview_link else '?'
            redirect_url = f"{offer.preview_link}{separator}click_id={click_id}"
        else:
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail="Offer 未配置预览链接或下游 Tracklink"
            )
        
        # 7. 重定向
        return RedirectResponse(url=redirect_url, status_code=302)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("点击追踪失败: error_type=%s", type(e).__name__)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail="点击追踪失败，请稍后重试"
        )

