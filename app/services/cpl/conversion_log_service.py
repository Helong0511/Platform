"""
转化日志服务层
封装转化日志查询和更新的业务逻辑
"""
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_

from app.models.models import (
    PostbackConversion,
    Click,
    Offer,
    Publisher,
    Advertiser,
    User
)
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.utils import parse_date_to_app_timezone
import logging

logger = logging.getLogger(__name__)


class ConversionLogService:
    """转化日志服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_conversion_logs(
        self,
        page: int = 1,
        page_size: int = 20,
        click_id: Optional[str] = None,
        offer_id: Optional[int] = None,
        publisher_id: Optional[int] = None,
        advertiser_id: Optional[int] = None,
        conversion_status: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        获取转化日志列表

        Args:
            page: 页码
            page_size: 每页数量
            click_id: Click ID过滤
            offer_id: Offer ID过滤
            publisher_id: 渠道ID过滤
            advertiser_id: 广告主ID过滤
            conversion_status: 转化状态过滤
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）

        Returns:
            Tuple[List[Dict], int]: (转化日志列表, 总数)
        """
        # 解析日期（使用应用时区，与数据库时间一致）
        start_datetime = None
        end_datetime = None
        if start_date:
            start_datetime = parse_date_to_app_timezone(start_date, is_end_date=False)
        if end_date:
            end_datetime = parse_date_to_app_timezone(end_date, is_end_date=True)

        # 构建查询条件
        # 如果需要通过 Click 表筛选 offer_id、publisher_id 或 advertiser_id，需要 JOIN
        need_join_click = offer_id is not None or publisher_id is not None or advertiser_id is not None

        if need_join_click:
            # 需要 JOIN Click 表来筛选 offer_id、publisher_id 或 advertiser_id
            query = select(PostbackConversion).join(Click, PostbackConversion.click_id == Click.click_id)
        else:
            query = select(PostbackConversion)

        conditions = []

        if click_id:
            # PostbackConversion 表已有 click_id 字段和索引，直接查询
            conditions.append(PostbackConversion.click_id == click_id)

        if offer_id:
            # 通过 Click 表筛选 offer_id（PostbackConversion 没有直接的 offer_id 字段）
            # 关联路径：PostbackConversion.click_id → Click.click_id → Click.offer_id
            conditions.append(Click.offer_id == offer_id)

        if publisher_id:
            # 通过 Click 表筛选 publisher_id
            conditions.append(Click.publisher_id == publisher_id)

        if advertiser_id:
            # 通过 Click 表筛选 advertiser_id
            conditions.append(Click.advertiser_id == advertiser_id)

        if conversion_status:
            # 通过 conversion_status 字段查询
            if hasattr(PostbackConversion, 'conversion_status'):
                conditions.append(PostbackConversion.conversion_status == conversion_status)

        if start_datetime:
            conditions.append(PostbackConversion.created_at >= start_datetime)
        if end_datetime:
            conditions.append(PostbackConversion.created_at <= end_datetime)

        if conditions:
            query = query.where(and_(*conditions))

        # 总数（使用相同的查询条件）
        total_query = select(func.count(PostbackConversion.id))
        if need_join_click:
            total_query = total_query.select_from(
                PostbackConversion.__table__.join(Click.__table__, PostbackConversion.click_id == Click.click_id)
            )
        else:
            total_query = total_query.select_from(PostbackConversion.__table__)

        if conditions:
            total_query = total_query.where(and_(*conditions))

        total_result = await self.db.execute(total_query)
        total = total_result.scalar() or 0

        # 分页
        query = query.order_by(PostbackConversion.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        conversions = result.scalars().all()

        # 批量加载Click记录（优化N+1查询）
        click_ids = [conv.click_id for conv in conversions if hasattr(conv, 'click_id') and conv.click_id]
        clicks_map = {}

        if click_ids:
            # 从 Click 表获取详细信息
            clicks_result = await self.db.execute(
                select(Click).where(Click.click_id.in_(click_ids))
            )
            clicks = clicks_result.scalars().all()
            clicks_map = {click.click_id: click for click in clicks}

        # 批量加载关联的Offer、Publisher、Advertiser（进一步优化）
        offer_ids = set()
        publisher_ids = set()
        advertiser_ids = set()
        # 从 Click 表获取
        for click in clicks_map.values():
            if click.offer_id:
                offer_ids.add(click.offer_id)
            if click.publisher_id:
                publisher_ids.add(click.publisher_id)
            if click.advertiser_id:
                advertiser_ids.add(click.advertiser_id)

        offers_map = {}
        if offer_ids:
            offers_result = await self.db.execute(
                select(Offer).where(Offer.id.in_(offer_ids))
            )
            offers = offers_result.scalars().all()
            offers_map = {offer.id: offer for offer in offers}

        publishers_map = {}
        if publisher_ids:
            publishers_result = await self.db.execute(
                select(Publisher).where(Publisher.id.in_(publisher_ids))
            )
            publishers = publishers_result.scalars().all()
            publishers_map = {publisher.id: publisher for publisher in publishers}

        advertisers_map = {}
        if advertiser_ids:
            advertisers_result = await self.db.execute(
                select(Advertiser).where(Advertiser.id.in_(advertiser_ids))
            )
            advertisers = advertisers_result.scalars().all()
            advertisers_map = {advertiser.id: advertiser for advertiser in advertisers}

        # 构建返回数据
        log_list = []
        for conv in conversions:
            click_record = None
            if hasattr(conv, 'click_id') and conv.click_id:
                click_record = clicks_map.get(conv.click_id)

            # 从批量加载的map中获取关联信息
            offer_name = None
            publisher_name = None
            advertiser_name = None
            click_time = None

            if click_record:
                click_time = click_record.click_time
                offer_id_val = click_record.offer_id
                publisher_id_val = click_record.publisher_id
                advertiser_id_val = click_record.advertiser_id

                if offer_id_val:
                    offer = offers_map.get(offer_id_val)
                    if offer:
                        offer_name = offer.offer_name

                if publisher_id_val:
                    publisher = publishers_map.get(publisher_id_val)
                    if publisher:
                        publisher_name = publisher.publisher_name

                if advertiser_id_val:
                    advertiser = advertisers_map.get(advertiser_id_val)
                    if advertiser:
                        advertiser_name = advertiser.advertiser_name

            # 从 Click 表获取详细信息或使用 PostbackConversion 中的值
            ip = conv.ip
            device = None
            country = None
            if click_record:
                ip = click_record.ip or ip
                device = click_record.device
                country = click_record.country

            log_data = {
                "id": conv.id,
                "click_id": getattr(conv, 'click_id', None),
                "click_time": click_time.isoformat() if click_time else None,
                "conversion_time": conv.created_at.isoformat() if conv.created_at else None,
                "conversion_status": getattr(conv, 'conversion_status', 'Pending'),
                "offer_id": click_record.offer_id if click_record else None,
                "offer_name": offer_name,
                "publisher_id": click_record.publisher_id if click_record else None,
                "publisher_name": publisher_name,
                "advertiser_id": click_record.advertiser_id if click_record else None,
                "advertiser_name": advertiser_name,
                "ip": ip,
                "device": device,
                "country": country,
                "platform": conv.platform,
                "original_payout": float(conv.original_payout) if conv.original_payout else None,
                "payout": float(conv.payout) if conv.payout else None,
                "event_name": conv.event_name,
                "created_at": conv.created_at.isoformat() if conv.created_at else None
            }
            log_list.append(log_data)

        return log_list, total

    async def update_conversion_status(
        self,
        conversion_id: int,
        status: str,
        current_user: User
    ) -> None:
        """
        更新转化状态

        Args:
            conversion_id: 转化记录ID
            status: 转化状态（Approved/Pending）
            current_user: 当前用户
        """
        result = await self.db.execute(
            select(PostbackConversion).where(PostbackConversion.id == conversion_id)
        )
        conversion = result.scalars().first()

        if not conversion:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"转化记录ID {conversion_id} 不存在"
            )

        # 更新转化状态
        if hasattr(conversion, 'conversion_status'):
            conversion.conversion_status = status
            await self.db.commit()
            await self.db.refresh(conversion)
            logger.info(f"转化状态已更新: conversion_id={conversion_id}, status={status}")
        else:
            logger.warning(f"PostbackConversion 模型缺少 conversion_status 字段")

