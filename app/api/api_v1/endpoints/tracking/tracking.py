"""
点击追踪 API 端点
处理点击追踪、Click ID 生成、Tracklink 生成等功能
"""
import logging
import asyncio
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, Path, Request, BackgroundTasks
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db, AsyncSessionLocal
from app.core.security import get_current_user
from app.core.utils import get_app_now_naive
from app.core.tracking.click_id_generator import generate_click_id_from_timestamp, generate_unique_click_id
from app.core.tracking.tracklink_generator import generate_downstream_tracklink
from app.core.device_info import collect_request_info
from app.models.models import User, Offer, Publisher, Click
from app.schemas.base import ResponseBaseSchema
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode

router = APIRouter()
logger = logging.getLogger(__name__)


# 后台任务：创建点击记录（带重试机制）
async def create_click_background(click_data: dict, max_retries: int = 3):
    """
    异步创建点击记录，带重试机制
    
    如果检测到重复的 click_id，会自动重新生成并重试。
    
    Args:
        click_data: 点击记录数据
        max_retries: 最大重试次数
    """
    
    async with AsyncSessionLocal() as session:
        for attempt in range(max_retries):
            try:
                # 在插入前检查 click_id 是否已存在
                click_id = click_data.get('click_id')
                if click_id:
                    existing_click = await session.execute(
                        select(Click).where(Click.click_id == click_id)
                    )
                    if existing_click.scalars().first():
                        # click_id 已存在，重新生成
                        logger.warning(
                            f"检测到重复的 click_id: {click_id}，将重新生成"
                        )
                        click_data['click_id'] = generate_click_id_from_timestamp()
                        click_id = click_data['click_id']
                
                click = Click(**click_data)
                session.add(click)
                
                await session.commit()
                logger.debug(f"点击记录保存成功: click_id={click_data.get('click_id')}")
                return  # 成功则返回
            except IntegrityError as e:
                # 处理唯一性约束错误（重复的 click_id）
                error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
                if 'Duplicate entry' in error_msg or 'UNIQUE constraint' in error_msg or 'click_id' in error_msg:
                    # 检测到重复的 click_id，重新生成并重试
                    old_click_id = click_data.get('click_id')
                    click_data['click_id'] = generate_click_id_from_timestamp()
                    logger.warning(
                        f"检测到重复的 click_id（尝试 {attempt + 1}/{max_retries}）: "
                        f"旧ID={old_click_id}, 新ID={click_data['click_id']}"
                    )
                    await session.rollback()
                    # 立即重试，不需要等待
                    continue
                else:
                    # 其他完整性约束错误，按正常流程处理
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"异步保存点击记录失败（尝试 {attempt + 1}/{max_retries}）: {e}, "
                            f"click_id={click_data.get('click_id')}"
                        )
                        await session.rollback()
                        # 等待后重试（指数退避）
                        await asyncio.sleep(2 ** attempt)
                    else:
                        raise
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"异步保存点击记录失败（尝试 {attempt + 1}/{max_retries}）: {e}, "
                        f"click_id={click_data.get('click_id')}"
                    )
                    await session.rollback()
                    # 等待后重试（指数退避）
                    await asyncio.sleep(2 ** attempt)
                else:
                    # 最后一次尝试失败，记录错误
                    logger.error(
                        f"异步保存点击记录最终失败（已重试 {max_retries} 次）: {e}, "
                        f"click_id={click_data.get('click_id')}",
                        exc_info=True
                    )
                    await session.rollback()


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
    """
    try:
        # 1. 查询 Offer
        result = await db.execute(
            select(Offer).where(Offer.id == offer_id)
        )
        offer = result.scalars().first()
        
        if not offer:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"Offer ID {offer_id} 不存在"
            )
        
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
        
        if not publisher:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"渠道ID {publisher_id} 不存在"
            )
        
        # 3. 生成 Click ID
        # 先检查是否有重复的 Click ID
        existing_click_ids = set()
        # 这里可以优化：只检查最近生成的 Click ID，而不是全部
        click_id = generate_click_id_from_timestamp()
        
        # 4. 收集完整的请求信息（包括软件、硬件信息和URL参数）
        request_info = collect_request_info(request) if request else {}
        
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
        
        # 使用后台任务异步写入
        # 注意：使用 BackgroundTasks 不会阻塞响应
        background_tasks.add_task(create_click_background, click_data)
        
        # 原同步代码注释掉
        # click = Click(...)
        # db.add(click)
        # await db.commit()
        
        logger.info(f"点击请求已接收 (异步写入): click_id={click_id}, offer_id={offer_id}")
        
        # 6. 生成重定向 URL（使用下游 Tracklink 或 Preview Link）
        if offer.downstream_tracklink:
            # 如果有下游 Tracklink，使用它
            redirect_url = offer.downstream_tracklink.replace('{click_id}', click_id)
            if publisher:
                redirect_url = redirect_url.replace('{publisher_id}', str(publisher.id))
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
        
    except Exception as e:
        logger.error(f"点击追踪失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"点击追踪失败: {str(e)}"
        )

