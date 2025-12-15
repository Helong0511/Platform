from datetime import date, datetime
from pydantic import BaseModel

class TBSearchDataBase(BaseModel):
    date: date
    product_id: int
    product_name: str | None = None
    country_code: str | None = None
    country_name_zh: str | None = None
    redirects: int | None = 0
    searches: int | None = 0
    monetized: int | None = 0
    clicks: int | None = 0
    revenue: float | None = 0.0
    rpm: float | None = 0.0
    revenue_before_deduct: float | None = 0.0
    rpm_before_deduct: float | None = 0.0

class TBSearchDataInDBBase(TBSearchDataBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class TBSearchDataResponse(TBSearchDataInDBBase):
    client_id: int | None = None
    client_name: str | None = None
    user_name: str | None = None

class TBSearchDataListResponse(BaseModel):
    data: list[TBSearchDataResponse]
    total: int
    page: int
    page_size: int

class TBSearchDataUpdate(BaseModel):
    product_id: int | None = None
    country_code: str | None = None
    redirects: int | None = None
    searches: int | None = None
    monetized: int | None = None
    clicks: int | None = None
    revenue: float | None = None
    rpm: float | None = None
    revenue_before_deduct: float | None = None
    rpm_before_deduct: float | None = None

