"""
Offer仓储
提供Offer相关的数据访问方法，优化查询性能
"""
from typing import Dict, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_
from sqlalchemy.orm import joinedload, selectinload

from app.repositories.base_repository import BaseRepository
from app.models.models import Offer, Advertiser, OfferPublisherAssignment, Publisher


class OfferRepository(BaseRepository[Offer]):
    """Offer仓储"""
    
    def __init__(self, db: AsyncSession):
        """绑定异步会话与 Offer 模型，供列表/统计查询复用。"""
        super().__init__(db, Offer)
    
    async def get_by_advertiser_id(
        self,
        advertiser_id: int,
        include_advertiser: bool = False
    ) -> List[Offer]:
        """根据广告主ID获取Offer列表"""
        query = select(Offer).where(Offer.advertiser_id == advertiser_id)
        
        if include_advertiser:
            query = query.options(joinedload(Offer.advertiser))
        
        result = await self.db.execute(query)
        # 使用joinedload时，为了安全起见使用unique()去重
        return result.unique().scalars().all()
    
    async def get_active_offers(
        self,
        include_advertiser: bool = False
    ) -> List[Offer]:
        """获取激活的Offer列表"""
        query = select(Offer).where(
            and_(
                Offer.is_active == True,
                Offer.status == 'Active'
            )
        )
        
        if include_advertiser:
            query = query.options(joinedload(Offer.advertiser))
        
        result = await self.db.execute(query)
        # 使用joinedload时，为了安全起见使用unique()去重
        return result.unique().scalars().all()
    
    async def get_with_assignments(
        self,
        offer_ids: List[int]
    ) -> Dict[int, List[OfferPublisherAssignment]]:
        """
        批量获取Offer的渠道分配（避免N+1查询）
        
        Args:
            offer_ids: Offer ID列表
        
        Returns:
            Dict: {offer_id: [assignments]}
        """
        if not offer_ids:
            return {}
        
        result = await self.db.execute(
            select(OfferPublisherAssignment, Publisher)
            .join(Publisher, OfferPublisherAssignment.publisher_id == Publisher.id)
            .where(OfferPublisherAssignment.offer_id.in_(offer_ids))
            .where(OfferPublisherAssignment.is_active == True)
            .where(Publisher.is_active == True)
        )
        
        assignments_map = {}
        for assignment, publisher in result.all():
            if assignment.offer_id not in assignments_map:
                assignments_map[assignment.offer_id] = []
            assignments_map[assignment.offer_id].append(assignment)
        
        return assignments_map

