from datetime import datetime, date

from pydantic import BaseModel, Field, ConfigDict


class ProductBase(BaseModel):
    name: str | None = None
    ecpm_deduct_ratio: float | None = Field(None, ge=0, le=1)
    revenue_deduct_ratio: float | None = Field(None, ge=0, le=1)
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
    name: str
    ecpm_deduct_ratio: float = Field(..., ge=0, le=1)
    revenue_deduct_ratio: float = Field(..., ge=0, le=1)
    client_id: int


class ProductUpdate(ProductBase):
    pass


class ProductInDBBase(ProductBase):
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ProductResponse(ProductInDBBase):
    pass


class ProductListResponse(BaseModel):
    data: list[ProductResponse]
    total: int
    page: int
    page_size: int
