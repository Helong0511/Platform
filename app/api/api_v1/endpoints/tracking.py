"""
点击追踪 API 端点
处理点击追踪、Click ID 生成、Tracklink 生成等功能
"""
import logging
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi.responses import RedirectResponse
from fastapi import BackgroundTasks
from app.core.database import AsyncSessionLocal

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.tracking.click_id_generator import generate_click_id_from_timestamp, generate_unique_click_id
from app.core.tracking.tracklink_generator import generate_downstream_tracklink
from app.models.models import User, Offer, Publisher, Click
from app.schemas.base import ResponseBaseSchema
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode

router = APIRouter()
logger = logging.getLogger(__name__)


# 后台任务：创建点击记录
async def create_click_background(click_data: dict):
    """异步创建点击记录"""
    async with AsyncSessionLocal() as session:
        try:
            click = Click(**click_data)
            session.add(click)
            await session.commit()
            # 不需要refresh，因为不需要返回给用户
        except Exception as e:
            logger.error(f"异步保存点击记录失败: {e}", exc_info=True)


@router.get("/track/click/{offer_id}", summary="点击追踪", tags=["点击追踪"])
async def track_click(
    offer_id: str = Path(..., description="Offer ID"),
    publisher_id: Optional[int] = Query(None, description="渠道ID"),
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
            select(Offer).where(Offer.offer_id == offer_id)
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
        
        # 2. 查询 Publisher（如果提供了 publisher_id）
        publisher = None
        if publisher_id:
            pub_result = await db.execute(
                select(Publisher).where(Publisher.id == publisher_id)
            )
            publisher = pub_result.scalars().first()
        
        # 3. 生成 Click ID
        # 先检查是否有重复的 Click ID
        existing_click_ids = set()
        # 这里可以优化：只检查最近生成的 Click ID，而不是全部
        click_id = generate_click_id_from_timestamp()
        
        # 4. 获取点击信息
        def get_client_ip(req: Request) -> Optional[str]:
            """获取客户端真实IP"""
            if not req:
                return None
            # 优先从 X-Forwarded-For 获取（经过代理时）
            forwarded_for = req.headers.get("X-Forwarded-For")
            if forwarded_for:
                return forwarded_for.split(",")[0].strip()
            # 其次从 X-Real-IP 获取
            real_ip = req.headers.get("X-Real-IP")
            if real_ip:
                return real_ip
            # 最后从 client.host 获取
            if req.client:
                return req.client.host
            return None
        
        client_ip = get_client_ip(request)
        user_agent = request.headers.get("user-agent") if request else None
        referer = request.headers.get("referer") if request else None
        
        # 5. 创建点击记录
        click_data = {
            "click_id": click_id,
            "offer_id": offer.id,
            "publisher_id": publisher.id if publisher else None,
            "advertiser_id": offer.advertiser_id,
            "click_time": datetime.now(timezone.utc),
            "ip": client_ip,
            "user_agent": user_agent,
            "referer": referer,
            "country": None
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

