"""
Offer 分页列表查询。
"""
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from app.models.models import Offer, OfferPublisherAssignment, Publisher, User, UserRole
from app.services.cpl.offer.helpers import get_client_id_for_user
from app.services.cpl.offer.queries.assignments_query import OfferAssignmentsQuery


class OfferListQuery:
    """Offer 分页列表查询。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def fetch(
        self,
        current_user: User,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        advertiser_id: Optional[int] = None,
        publisher_id: Optional[int] = None,
        status: Optional[str] = None,
        country: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Tuple[List[Offer], int, Dict[int, List[Dict[str, Any]]]]:
        query = select(Offer)
        has_join = False

        if current_user.role == UserRole.CLIENT:
            client_id = await get_client_id_for_user(self.db, current_user)
            if client_id:
                query = (
                    query.join(
                        OfferPublisherAssignment,
                        Offer.id == OfferPublisherAssignment.offer_id,
                    )
                    .join(
                        Publisher,
                        OfferPublisherAssignment.publisher_id == Publisher.id,
                    )
                    .where(
                        and_(
                            Publisher.client_id == client_id,
                            Publisher.is_active == True,
                            OfferPublisherAssignment.is_active == True,
                        )
                    )
                    .distinct()
                )
                has_join = True
            else:
                return [], 0, {}

        conditions = self._build_filter_conditions(search, advertiser_id, status, country, is_active)

        if publisher_id:
            if not has_join:
                query = (
                    query.join(
                        OfferPublisherAssignment,
                        Offer.id == OfferPublisherAssignment.offer_id,
                    )
                    .where(
                        and_(
                            OfferPublisherAssignment.publisher_id == publisher_id,
                            OfferPublisherAssignment.is_active == True,
                        )
                    )
                    .distinct()
                )
            else:
                conditions.append(OfferPublisherAssignment.publisher_id == publisher_id)

        if conditions:
            query = query.where(and_(*conditions))

        total = (
            await self.db.execute(select(func.count()).select_from(query.subquery()))
        ).scalar() or 0

        offset = (page - 1) * page_size
        query = (
            query.options(joinedload(Offer.advertiser))
            .order_by(Offer.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        offers = (await self.db.execute(query)).unique().scalars().all()

        offer_ids = [offer.id for offer in offers]
        assignments_map = await OfferAssignmentsQuery(self.db).fetch_batch_for_offers(
            offer_ids, current_user
        )
        return offers, total, assignments_map

    def _build_filter_conditions(
        self,
        search: Optional[str],
        advertiser_id: Optional[int],
        status: Optional[str],
        country: Optional[str],
        is_active: Optional[bool],
    ):
        conditions = []
        if search:
            search_trimmed = search.strip()
            search_conditions = []
            try:
                search_conditions.append(Offer.id == int(search_trimmed))
            except ValueError:
                pass

            if search_trimmed:
                search_conditions.append(Offer.advertiser_offer_id == search_trimmed)

            try:
                fulltext_condition = text(
                    "MATCH(offer_name) AGAINST(:search_term IN NATURAL LANGUAGE MODE)"
                ).bindparams(search_term=search_trimmed)
                search_conditions.append(fulltext_condition)
            except Exception:
                search_conditions.append(Offer.offer_name.like(f"{search_trimmed}%"))

            if search_conditions:
                conditions.append(or_(*search_conditions))

        if advertiser_id:
            conditions.append(Offer.advertiser_id == advertiser_id)
        if status:
            conditions.append(Offer.status == status)
        if country:
            conditions.append(Offer.country == country)
        if is_active is not None:
            conditions.append(Offer.is_active == is_active)
        return conditions
