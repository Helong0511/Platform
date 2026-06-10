"""
Offer 详情查询（含客户权限校验）。
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload, selectinload

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.models.models import Offer, OfferPublisherAssignment, User
from app.services.cpl.offer.helpers import assert_client_can_access_offer


class OfferDetailQuery:
    """Offer 单条详情查询。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def fetch_by_id(
        self,
        offer_id: int,
        current_user: User,
        include_advertiser: bool = True,
        include_assignments: bool = False,
    ) -> Offer:
        await assert_client_can_access_offer(self.db, offer_id, current_user)

        query = select(Offer).where(Offer.id == offer_id)
        options = []
        if include_advertiser:
            options.append(joinedload(Offer.advertiser))
        if include_assignments:
            options.append(
                selectinload(Offer.offer_assignments).joinedload(
                    OfferPublisherAssignment.publisher
                )
            )

        if options:
            query = query.options(*options)

        result = await self.db.execute(query)
        if options:
            offer = result.unique().scalars().one_or_none()
        else:
            offer = result.scalars().one_or_none()

        if not offer:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"Offer ID {offer_id} 不存在",
            )
        return offer
