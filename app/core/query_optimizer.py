"""
查询优化工具
提供查询优化方法，解决N+1查询问题
"""
from typing import List, Dict, Any, Optional, TypeVar, Type
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload, selectinload, Load
from sqlalchemy import inspect

T = TypeVar('T')


class QueryOptimizer:
    """查询优化器"""
    
    @staticmethod
    def optimize_offer_query(
        query,
        include_advertiser: bool = True,
        include_assignments: bool = False,
        include_caps: bool = False,
        include_discounts: bool = False
    ):
        """
        优化Offer查询，按需加载关联数据
        
        Args:
            query: SQLAlchemy查询对象
            include_advertiser: 是否加载广告主信息
            include_assignments: 是否加载渠道分配信息
            include_caps: 是否加载Cap配置
            include_discounts: 是否加载扣量配置
        
        Returns:
            优化后的查询对象
        """
        from app.models.models import Offer, OfferPublisherAssignment
        
        options = []
        
        if include_advertiser:
            options.append(joinedload(Offer.advertiser))
        if include_assignments:
            options.append(
                selectinload(Offer.offer_assignments)
                .joinedload(OfferPublisherAssignment.publisher)
            )
        if include_caps:
            from app.models.models import OfferCap
            options.append(selectinload(Offer.caps))
        if include_discounts:
            from app.models.models import OfferDiscount
            options.append(selectinload(Offer.discounts))
        
        if options:
            query = query.options(*options)
        
        return query
    
    @staticmethod
    async def batch_load_related_offers(
        db: AsyncSession,
        offer_ids: List[int],
        load_advertisers: bool = True,
        load_assignments: bool = True
    ) -> Dict[int, Dict[str, Any]]:
        """
        批量加载Offer的关联数据（避免N+1查询）
        
        Args:
            db: 数据库会话
            offer_ids: Offer ID列表
            load_advertisers: 是否加载广告主信息
            load_assignments: 是否加载渠道分配信息
        
        Returns:
            Dict: {offer_id: {advertiser: ..., assignments: [...]}}
        """
        if not offer_ids:
            return {}
        
        result = {}
        
        # 批量加载广告主信息
        if load_advertisers:
            from app.models.models import Offer, Advertiser
            offers_result = await db.execute(
                select(Offer, Advertiser)
                .join(Advertiser, Offer.advertiser_id == Advertiser.id)
                .where(Offer.id.in_(offer_ids))
            )
            for offer, advertiser in offers_result.all():
                if offer.id not in result:
                    result[offer.id] = {}
                result[offer.id]['advertiser'] = advertiser
        
        # 批量加载渠道分配信息
        if load_assignments:
            from app.models.models import OfferPublisherAssignment, Publisher
            assignments_result = await db.execute(
                select(OfferPublisherAssignment, Publisher)
                .join(Publisher, OfferPublisherAssignment.publisher_id == Publisher.id)
                .where(OfferPublisherAssignment.offer_id.in_(offer_ids))
                .where(OfferPublisherAssignment.is_active == True)
                .where(Publisher.is_active == True)
            )
            for assignment, publisher in assignments_result.all():
                if assignment.offer_id not in result:
                    result[assignment.offer_id] = {}
                if 'assignments' not in result[assignment.offer_id]:
                    result[assignment.offer_id]['assignments'] = []
                result[assignment.offer_id]['assignments'].append({
                    'assignment': assignment,
                    'publisher': publisher
                })
        
        return result
    
    @staticmethod
    async def batch_load_publishers_with_clients(
        db: AsyncSession,
        publisher_ids: List[int]
    ) -> Dict[int, Dict[str, Any]]:
        """
        批量加载渠道及其客户信息（避免N+1查询）
        
        Args:
            db: 数据库会话
            publisher_ids: 渠道ID列表
        
        Returns:
            Dict: {publisher_id: {publisher: ..., client: ..., user: ...}}
        """
        if not publisher_ids:
            return {}
        
        from app.models.models import Publisher, Client, User
        from sqlalchemy.orm import selectinload
        
        result = await db.execute(
            select(Publisher)
            .where(Publisher.id.in_(publisher_ids))
            .options(
                selectinload(Publisher.client).selectinload(Client.user)
            )
        )
        
        publishers_map = {}
        for publisher in result.scalars().all():
            publishers_map[publisher.id] = {
                'publisher': publisher,
                'client': publisher.client,
                'user': publisher.client.user if publisher.client else None
            }
        
        return publishers_map
    
    @staticmethod
    def optimize_ad_data_query(
        query,
        include_product: bool = True,
        include_client: bool = True,
        include_user: bool = False,
        include_country: bool = True
    ):
        """
        优化广告数据查询
        
        Args:
            query: SQLAlchemy查询对象
            include_product: 是否加载产品信息
            include_client: 是否加载客户信息
            include_user: 是否加载用户信息
            include_country: 是否加载国家信息
        
        Returns:
            优化后的查询对象
        """
        from app.models.models import AdData, Product, Client, User, CountryInfo
        
        options = []
        
        if include_product:
            options.append(joinedload(AdData.product))
        if include_client:
            options.append(joinedload(AdData.product).joinedload(Product.client))
        if include_user:
            options.append(
                joinedload(AdData.product)
                .joinedload(Product.client)
                .joinedload(Client.user)
            )
        if include_country:
            options.append(joinedload(AdData.country))
        
        if options:
            query = query.options(*options)
        
        return query

