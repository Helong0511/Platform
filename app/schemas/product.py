"""产品（Product）Schema：扣量比例、下游 Postback 转发、通知地址、客户转移日期等。

产品归属下游客户，与 Offer、广告数据、转化回传链路关联。

说明：请求/响应 JSON 结构定义，供 FastAPI 校验与 OpenAPI 文档生成。"""
from datetime import datetime, date
from decimal import Decimal

from pydantic import Field, ConfigDict

from app.schemas.base import BaseSchema


class ProductBase(BaseSchema):
    """
    产品公共字段：扣量比例、下游 Postback、通知地址、客户转移日期等
    
    公共字段基类，供 Create/Update/Response 等子模型复用，避免重复定义。
    """
    name: str | None = None
    ecpm_deduct_ratio: Decimal | None = Field(None, ge=0, le=1)
    revenue_deduct_ratio: Decimal | None = Field(None, ge=0, le=1)
    cplpo_deduct_ratio: Decimal | None = Field(None, ge=0, le=1)
    is_active: bool | None = True
    client_id: int | None = None
    downstream_postback_url: str | None = Field(
        None,
        description="下游 Postback URL（可选，配置后将自动转发转化数据）"
    )
    downstream_postback_method: str | None = Field(
        None,
        description="下游 Postback 请求方式：GET 或 POST（默认GET）"
    )
    downstream_postback_success_check: str | None = Field(
        None,
        description="下游转发成功检查配置（JSON格式，用于检查响应内容是否表示成功）"
    )
    notification_address: str | None = Field(
        None,
        max_length=500,
        description="通知地址（Telegram Chat ID、邮箱地址、Webhook URL等，用于接收转化通知）"
    )
    transfer_date: date | None = Field(
        None,
        description="产品转移日期（新客户开始拥有该产品的日期，可选，仅在更改client_id时生效）。如果不指定，默认使用当前日期。用于补录历史转移记录。"
    )
    old_client_end_date: date | None = Field(
        None,
        description="上一个客户拥有该产品的结束日期（可选，仅在更改client_id时生效）。如果不指定，自动计算为transfer_date的前一天。"
    )


class ProductCreate(ProductBase):
    """
    创建产品请求（名称、扣量比例、归属客户为必填）
    
    创建请求体：包含新建记录所需字段，提交前由 Pydantic 自动校验类型与取值范围。
    """
    name: str
    ecpm_deduct_ratio: Decimal = Field(..., ge=0, le=1)
    revenue_deduct_ratio: Decimal = Field(..., ge=0, le=1)
    cplpo_deduct_ratio: Decimal = Field(default=Decimal('0'), ge=0, le=1)
    client_id: int


class ProductUpdate(ProductBase):
    """
    更新产品请求，支持变更 client_id 并指定转移日期
    
    更新请求体：字段均为可选，客户端仅提交需要修改的列。
    """
    pass


class ProductInDBBase(ProductBase):
    """
    数据库产品记录，含主键与时间戳
    
    公共字段基类，供 Create/Update/Response 等子模型复用，避免重复定义。
    """
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ProductResponse(ProductInDBBase):
    """
    单条产品 API 响应
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    client_name 来自关联 Client.company_name，列表/详情在加载 client 时填充。
    """
    client_name: str | None = Field(
        None,
        description="所属客户公司名（来自 clients.company_name）",
    )


def build_product_response(product, *, include_deduct_ratios: bool = True) -> ProductResponse:
    """将 ORM Product 转为响应；仅在 client 已预加载时填充 client_name（避免异步懒加载）。

    include_deduct_ratios=False 时清空减扣比例，供客户角色使用（避免暴露扣减配置）。
    """
    response = ProductResponse.model_validate(product)
    client = None
    try:
        from sqlalchemy import inspect as sa_inspect

        state = sa_inspect(product)
        # client 未加载时不要触发 lazy load（异步会话会 greenlet 报错）
        if "client" not in state.unloaded:
            client = product.client
    except Exception:
        client = None
    if client is not None:
        company_name = getattr(client, "company_name", None)
        if company_name:
            response = response.model_copy(update={"client_name": company_name})
    if not include_deduct_ratios:
        response = response.model_copy(
            update={
                "ecpm_deduct_ratio": None,
                "revenue_deduct_ratio": None,
                "cplpo_deduct_ratio": None,
            }
        )
    return response


class ProductListResponse(BaseSchema):
    """
    产品分页列表响应
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    """
    data: list[ProductResponse]
    total: int
    page: int
    page_size: int