"""
CPL 系统 Schema
"""
from app.schemas.cpl.advertiser import (
    AdvertiserBase,
    AdvertiserCreate,
    AdvertiserUpdate,
    AdvertiserResponse
)
from app.schemas.cpl.publisher import (
    PublisherBase,
    PublisherCreate,
    PublisherUpdate,
    PublisherResponse
)
from app.schemas.cpl.offer import (
    OfferBase,
    OfferCreate,
    OfferUpdate,
    OfferResponse
)
from app.schemas.cpl.click import ClickResponse
from app.schemas.cpl.cap import (
    OfferCapBase,
    OfferCapCreate,
    OfferCapUpdate,
    OfferCapResponse
)
from app.schemas.cpl.discount import (
    OfferDiscountBase,
    OfferDiscountCreate,
    OfferDiscountUpdate,
    OfferDiscountResponse
)
from app.schemas.cpl.test import (
    AdvertiserTestBase,
    AdvertiserTestCreate,
    AdvertiserTestResponse,
    AffiliateTestBase,
    AffiliateTestCreate,
    AffiliateTestResponse
)

__all__ = [
    "AdvertiserBase", "AdvertiserCreate", "AdvertiserUpdate", "AdvertiserResponse",
    "PublisherBase", "PublisherCreate", "PublisherUpdate", "PublisherResponse",
    "OfferBase", "OfferCreate", "OfferUpdate", "OfferResponse",
    "ClickResponse",
    "OfferCapBase", "OfferCapCreate", "OfferCapUpdate", "OfferCapResponse",
    "OfferDiscountBase", "OfferDiscountCreate", "OfferDiscountUpdate", "OfferDiscountResponse",
    "AdvertiserTestBase", "AdvertiserTestCreate", "AdvertiserTestResponse",
    "AffiliateTestBase", "AffiliateTestCreate", "AffiliateTestResponse",
]

