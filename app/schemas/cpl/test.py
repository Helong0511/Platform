"""下游联调测试记录 Pydantic 数据模型。

定义渠道侧 Postback 联调测试的请求与响应字段，
包括 click_id、Offer、渠道及回调结果状态等信息。

说明：CPL 业务字段模型，与数据库表及前端表单校验保持一致。

说明：CPL 子系统接口，涵盖广告主（上游）、渠道（下游）、Offer、Cap、扣量与转化。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class AffiliateTestBase(BaseModel):
    """
    下游测试基础模型
    
    继承 BaseModel。公共字段基类，供 Create/Update/Response 等模型复用。
    """
    publisher_id: int = Field(..., description="渠道ID")
    click_id: str = Field(..., description="下游提供的Click ID")
    """
    创建下游测试记录
    
    继承 AffiliateTestBase。创建请求体：提交新记录所需字段，由 Pydantic 校验必填项与取值范围。
    """

"""

下游测试响应



继承 AffiliateTestBase。单条或列表项的 API 响应数据结构。

"""

class AffiliateTestCreate(AffiliateTestBase):
    """
    创建下游测试记录
    
    创建请求体：包含新建记录所需字段，提交前由 Pydantic 自动校验类型与取值范围。
    """
    pass


class AffiliateTestResponse(AffiliateTestBase):
    """
    下游测试响应
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    """
    id: int
    offer_name: Optional[str] = None
    price: Optional[float] = None
    country: Optional[str] = None
    platform: Optional[str] = None
    postback_time: Optional[datetime] = None
    status: Optional[str] = None
    affiliate_return_content: Optional[str] = None
    created_at: datetime
    # 关联信息
    publisher_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
