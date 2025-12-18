"""
下游测试 API
"""
import logging
from typing import Optional
from datetime import datetime, timezone
import httpx
from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.models.models import User, AffiliateTest, Publisher, Offer
from app.schemas.cpl.test import AffiliateTestCreate, AffiliateTestResponse
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/",
             response_model=ResponseBaseSchema[AffiliateTestResponse],
             summary="创建下游测试记录并发送Postback",
             dependencies=[Depends(require_admin)])
async def create_affiliate_test(
    test_in: AffiliateTestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建下游测试记录并发送Postback（仅管理员）"""
    # 验证渠道和Offer是否存在
    pub_result = await db.execute(
        select(Publisher).where(Publisher.id == test_in.publisher_id)
    )
    publisher = pub_result.scalars().first()
    if not publisher:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"渠道ID {test_in.publisher_id} 不存在"
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
    
    # 发送Postback
    postback_url = offer.postback_url
    postback_method = offer.postback_method or 'GET'
    status = "Failed"
    affiliate_return_content = None
    
    if postback_url:
        try:
            # 替换URL中的占位符
            postback_url = postback_url.replace('{click_id}', test_in.click_id)
            postback_url = postback_url.replace('{offer_id}', offer.offer_id)
            postback_url = postback_url.replace('{publisher_id}', publisher.publisher_id)
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                if postback_method.upper() == 'POST':
                    response = await client.post(postback_url, json={
                        'click_id': test_in.click_id,
                        'offer_id': offer.offer_id,
                        'publisher_id': publisher.publisher_id
                    })
                else:
                    response = await client.get(postback_url)
                
                status = "Send Success" if response.status_code == 200 else "Failed"
                affiliate_return_content = response.text[:1000]  # 限制长度
        except Exception as e:
            logger.error(f"发送Postback失败: {str(e)}", exc_info=True)
            status = "Failed"
            affiliate_return_content = str(e)[:1000]
    else:
        status = "Failed"
        affiliate_return_content = "Offer未配置Postback URL"
    
    test = AffiliateTest(
        publisher_id=test_in.publisher_id,
        click_id=test_in.click_id,
        offer_id=test_in.offer_id,
        offer_name=offer.offer_name,
        price=offer.affiliate_payout,
        country=offer.country,
        platform=None,
        postback_time=datetime.now(timezone.utc),
        status=status,
        affiliate_return_content=affiliate_return_content
    )
    
    try:
        db.add(test)
        await db.commit()
        await db.refresh(test)
        
        # 加载关联信息
        test_data = AffiliateTestResponse.model_validate(test)
        test_data.publisher_name = publisher.publisher_name
        
        logger.info(f"下游测试记录创建成功: test_id={test.id}, status={status}")
        return ResponseBaseSchema.success(data=test_data)
    except Exception as e:
        await db.rollback()
        logger.error(f"创建下游测试记录失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"创建下游测试记录失败: {str(e)}"
        )


@router.get("/",
            response_model=PaginatedResponseBaseSchema[list[AffiliateTestResponse]],
            summary="获取下游测试记录列表",
            dependencies=[Depends(require_admin)])
async def get_affiliate_tests(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    publisher_id: Optional[int] = Query(None, description="渠道ID过滤"),
    offer_id: Optional[int] = Query(None, description="Offer ID过滤"),
    status: Optional[str] = Query(None, description="状态过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取下游测试记录列表（仅管理员）"""
    query = select(AffiliateTest)
    
    if publisher_id:
        query = query.where(AffiliateTest.publisher_id == publisher_id)
    
    if offer_id:
        query = query.where(AffiliateTest.offer_id == offer_id)
    
    if status:
        query = query.where(AffiliateTest.status == status)
    
    # 总数
    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar() or 0
    
    # 分页
    query = query.order_by(AffiliateTest.postback_time.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    tests = result.scalars().all()
    
    # 加载关联信息
    test_list = []
    for test in tests:
        pub_result = await db.execute(
            select(Publisher).where(Publisher.id == test.publisher_id)
        )
        publisher = pub_result.scalars().first()
        
        test_data = AffiliateTestResponse.model_validate(test)
        test_data.publisher_name = publisher.publisher_name if publisher else None
        test_list.append(test_data)
    
    return PaginatedResponseBaseSchema.success(
        data=test_list,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{test_id}",
            response_model=ResponseBaseSchema[AffiliateTestResponse],
            summary="获取下游测试记录详情",
            dependencies=[Depends(require_admin)])
async def get_affiliate_test(
    test_id: int = Path(..., ge=1, description="测试记录ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取下游测试记录详情（仅管理员）"""
    result = await db.execute(
        select(AffiliateTest).where(AffiliateTest.id == test_id)
    )
    test = result.scalars().first()
    
    if not test:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"测试记录ID {test_id} 不存在"
        )
    
    # 加载关联信息
    pub_result = await db.execute(
        select(Publisher).where(Publisher.id == test.publisher_id)
    )
    publisher = pub_result.scalars().first()
    
    test_data = AffiliateTestResponse.model_validate(test)
    test_data.publisher_name = publisher.publisher_name if publisher else None
    
    return ResponseBaseSchema.success(data=test_data)

