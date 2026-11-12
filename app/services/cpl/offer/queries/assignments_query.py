"""
Offer 渠道分配查询。
"""
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.models import OfferPublisherAssignment, Publisher, User
from app.services.cpl.offer.helpers import assignment_to_dict, get_client_ids_for_user


class OfferAssignmentsQuery:
    """Offer 渠道分配查询。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def fetch_for_offer(self, offer_id: int, current_user: User) -> List[Dict[str, Any]]:
        """获取单个 Offer 的激活渠道分配列表。"""
        pub_query = (
            select(OfferPublisherAssignment, Publisher)
            .join(Publisher, OfferPublisherAssignment.publisher_id == Publisher.id)
            .where(OfferPublisherAssignment.offer_id == offer_id)
            .where(OfferPublisherAssignment.is_active == True)
            .where(Publisher.is_active == True)
        )

        client_ids = await get_client_ids_for_user(self.db, current_user)
        if client_ids is not None:
            if not client_ids:
                return []
            pub_query = pub_query.where(Publisher.client_id.in_(client_ids))

        pub_result = await self.db.execute(pub_query)
        return [
            assignment_to_dict(assignment, pub)
            for assignment, pub in pub_result.all()
        ]

    async def fetch_batch_for_offers(
        self,
        offer_ids: List[int],
        current_user: User,
    ) -> Dict[int, List[Dict[str, Any]]]:
        """批量加载多个 Offer 的渠道分配，避免 N+1。"""
        if not offer_ids:
            return {}

        pub_query = (
            select(OfferPublisherAssignment, Publisher)
            .join(Publisher, OfferPublisherAssignment.publisher_id == Publisher.id)
            .where(OfferPublisherAssignment.offer_id.in_(offer_ids))
            .where(OfferPublisherAssignment.is_active == True)
            .where(Publisher.is_active == True)
        )

        client_id = await get_client_id_for_user(self.db, current_user)
        if client_id:
            pub_query = pub_query.where(Publisher.client_id == client_id)

        assignments_map: Dict[int, List[Dict[str, Any]]] = {}
        pub_result = await self.db.execute(pub_query)
        for assignment, publisher in pub_result.all():
            assignments_map.setdefault(assignment.offer_id, []).append(
                assignment_to_dict(assignment, publisher)
            )
        return assignments_map
