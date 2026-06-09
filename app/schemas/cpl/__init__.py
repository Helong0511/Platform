"""CPL 业务 Schema 子包

职责：广告主、渠道、Offer、Cap、扣量、点击、转化扣减、下游测试等模型定义。

供 app/api_v1/cpl 与管理端表单共用。

说明：CPL 业务字段模型，与数据库表及前端表单校验保持一致。
说明：包入口，聚合子模块 router 或导出 Schema 供上层引用。

说明：CPL 子系统接口，涵盖广告主（上游）、渠道（下游）、Offer、Cap、扣量与转化。"""
from app.schemas.cpl.advertiser import (
    AdvertiserBase,
    AdvertiserCreate,
    AdvertiserUpdate,
    AdvertiserResponse
)
from app.schemas.cpl.cap import (
    OfferCapBase,
    OfferCapCreate,
    OfferCapUpdate,
    OfferCapResponse
)
from app.schemas.cpl.click import ClickResponse
from app.schemas.cpl.deduction import (
    ConversionDeductionConfigBase,
    ConversionDeductionConfigCreate,
    ConversionDeductionConfigUpdate,
    ConversionDeductionConfigResponse,
    ConversionDeductionLogResponse,
    DeductionStatsResponse
)
from app.schemas.cpl.discount import (
    OfferDiscountBase,
    OfferDiscountCreate,
    OfferDiscountUpdate,
    OfferDiscountResponse
)
from app.schemas.cpl.offer import (
    OfferBase,
    OfferCreate,
    OfferUpdate,
    OfferResponse
)
from app.schemas.cpl.publisher import (
    PublisherBase,
    PublisherCreate,
    PublisherUpdate,
    PublisherResponse
)
from app.schemas.cpl.test import (
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
    "AffiliateTestBase", "AffiliateTestCreate", "AffiliateTestResponse",
    "ConversionDeductionConfigBase", "ConversionDeductionConfigCreate", "ConversionDeductionConfigUpdate",
    "ConversionDeductionConfigResponse",
    "ConversionDeductionLogResponse", "DeductionStatsResponse",
]
