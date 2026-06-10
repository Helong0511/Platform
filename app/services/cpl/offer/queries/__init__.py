"""Offer 查询子模块。"""

from app.services.cpl.offer.queries.assignments_query import OfferAssignmentsQuery
from app.services.cpl.offer.queries.detail_query import OfferDetailQuery
from app.services.cpl.offer.queries.list_query import OfferListQuery

__all__ = [
    "OfferAssignmentsQuery",
    "OfferDetailQuery",
    "OfferListQuery",
]
