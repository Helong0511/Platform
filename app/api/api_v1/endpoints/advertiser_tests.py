"""
上游测试 API
"""
import logging
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.models.models import User, AdvertiserTest, Advertiser, Offer
from app.schemas.cpl.test import AdvertiserTestCreate, AdvertiserTestResponse
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.core.tracking.click_id_generator import generate_click_id_from_timestamp
from app.core.tracking.tracklink_generator import generate_upstream_tracklink
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/",
             response_model=ResponseBaseSchema[AdvertiserTestResponse],
             summary="创建上游测试记录",
             dependencies=[Depends(require_admin)])
async def create_advertiser_test(
    test_in: AdvertiserTestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建上游测试记录（仅管理员）"""
    # 验证广告主和Offer是否存在
    adv_result = await db.execute(
        select(Advertiser).where(Advertiser.id == test_in.advertiser_id)
    )
    advertiser = adv_result.scalars().first()
    if not advertiser:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"广告主ID {test_in.advertiser_id} 不存在"
        )
    
    offer_result = await db.execute(
        select(Offer).where(Offer.id == test_in.offer_id)
    )
    offer = offer_result.scalars().first()
    if not offer:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"Offer ID {test_in.offer_id} 不存在"
        )
    
    # 生成 Click ID
    click_id = generate_click_id_from_timestamp()
    
    # 生成 Click Url（使用上游 Tracklink）
    click_url = None
    if offer.advertiser_tracklink:
        click_url = generate_upstream_tracklink(
            advertiser_tracklink=offer.advertiser_tracklink,
            click_id=click_id,
            offer_id=offer.id,
            publisher_id=None
        )
    
    test = AdvertiserTest(
        advertiser_id=test_in.advertiser_id,
        advertiser_name=advertiser.advertiser_name,
        advertiser_offer_id=offer.advertiser_offer_id,
        offer_id=test_in.offer_id,
        offer_name=offer.offer_name,
        price=offer.payout,
        country=offer.country,
        click_id=click_id,
        click_url=click_url,
        test_time=datetime.now(timezone.utc)
    )
    
    try:
        db.add(test)
        await db.commit()
        await db.refresh(test)
        
        logger.info(f"上游测试记录创建成功: test_id={test.id}, click_id={click_id}")
        return ResponseBaseSchema.success(data=AdvertiserTestResponse.model_validate(test))
    except Exception as e:
        await db.rollback()
        logger.error(f"创建上游测试记录失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"创建上游测试记录失败: {str(e)}"
        )


@router.get("/",
            response_model=PaginatedResponseBaseSchema[list[AdvertiserTestResponse]],
            summary="获取上游测试记录列表",
            dependencies=[Depends(require_admin)])
async def get_advertiser_tests(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    advertiser_id: Optional[int] = Query(None, description="广告主ID过滤"),
    offer_id: Optional[int] = Query(None, description="Offer ID过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取上游测试记录列表（仅管理员）"""
    query = select(AdvertiserTest)
    
    if advertiser_id:
        query = query.where(AdvertiserTest.advertiser_id == advertiser_id)
    
    if offer_id:
        query = query.where(AdvertiserTest.offer_id == offer_id)
    
    # 总数
    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar() or 0
    
    # 分页
    query = query.order_by(AdvertiserTest.test_time.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    tests = result.scalars().all()
    
    return PaginatedResponseBaseSchema.success(
        data=[AdvertiserTestResponse.model_validate(test) for test in tests],
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{test_id}",
            response_model=ResponseBaseSchema[AdvertiserTestResponse],
            summary="获取上游测试记录详情",
            dependencies=[Depends(require_admin)])
async def get_advertiser_test(
    test_id: int = Path(..., ge=1, description="测试记录ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取上游测试记录详情（仅管理员）"""
    result = await db.execute(
        select(AdvertiserTest).where(AdvertiserTest.id == test_id)
    )
    test = result.scalars().first()
    
    if not test:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"测试记录ID {test_id} 不存在"
        )
    
    return ResponseBaseSchema.success(data=AdvertiserTestResponse.model_validate(test))

