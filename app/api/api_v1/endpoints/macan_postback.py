"""
Macan S2S PostBack 接收接口
用于接收 Macan 发送的转化事件回调

参考文档：https://macan-native.com/docs/advertiser/S2S/
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request, Query, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_

from app.core.database import get_db
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.models.models import Client, Product

# 创建路由实例
router = APIRouter()
# 获取日志记录器
logger = logging.getLogger(__name__)


# ====== 请求模型 ======
class MacanPostBackRequest(BaseModel):
    """Macan PostBack 请求模型"""
    clk_id: str = Field(..., description="Macan click ID（必填）")
    event_name: str = Field(..., description="Event ID（事件ID，必填）")
    devad_id: Optional[str] = Field(None, description="Apple IDFA 或 Google Advertising ID")
    event_value: Optional[float] = Field(None, description="purchase price（购买价格）")
    payout: Optional[float] = Field(None, description="payout confirmed ad unit price（确认的广告单元价格）")
    carrier: Optional[str] = Field(None, description="User carrier（用户运营商）")
    os: Optional[str] = Field(None, description="IOS 或 Android")
    ip: Optional[str] = Field(None, description="Click IP（点击IP）")
    gid: Optional[str] = Field(None, description="Channel ID（渠道ID）")
    
    # 可选：用于关联产品和客户
    product_id: Optional[int] = Field(None, description="产品ID（可选，用于关联产品）")
    client_id: Optional[int] = Field(None, description="客户ID（可选，用于关联客户）")


# ====== 响应模型 ======
class MacanPostBackResponse(BaseModel):
    """Macan PostBack 响应模型"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    clk_id: Optional[str] = Field(None, description="Macan click ID")


# ====== API端点 ======
@router.get("/macan/postback", response_model=MacanPostBackResponse, summary="接收 Macan PostBack 回调（GET）")
async def receive_macan_postback_get(
    request: Request,
    clk_id: str = Query(..., description="Macan click ID（必填）"),
    event_name: str = Query(..., description="Event ID（事件ID，必填）"),
    devad_id: Optional[str] = Query(None, description="Apple IDFA 或 Google Advertising ID"),
    event_value: Optional[float] = Query(None, description="purchase price（购买价格）"),
    payout: Optional[float] = Query(None, description="payout confirmed ad unit price（确认的广告单元价格）"),
    carrier: Optional[str] = Query(None, description="User carrier（用户运营商）"),
    os: Optional[str] = Query(None, description="IOS 或 Android"),
    ip: Optional[str] = Query(None, description="Click IP（点击IP）"),
    gid: Optional[str] = Query(None, description="Channel ID（渠道ID）"),
    product_id: Optional[int] = Query(None, description="产品ID（可选）"),
    client_id: Optional[int] = Query(None, description="客户ID（可选）"),
    db: AsyncSession = Depends(get_db)
):
    """
    接收 Macan S2S PostBack 回调（GET 方式）
    
    这是 Macan 转化事件追踪的回调接口。当用户在 Macan 平台上发生转化事件时，
    Macan 会向此接口发送回调请求。
    
    必填参数：
    - clk_id: Macan click ID
    - event_name: Event ID（事件ID）
    
    可选参数：
    - devad_id: 设备广告ID（IDFA 或 GAID）
    - event_value: 购买价格
    - payout: 确认的广告单元价格
    - carrier: 用户运营商
    - os: 操作系统（IOS 或 Android）
    - ip: 点击IP
    - gid: 渠道ID
    - product_id: 产品ID（用于关联产品）
    - client_id: 客户ID（用于关联客户）
    """
    return await _process_macan_postback(
        request=request,
        clk_id=clk_id,
        event_name=event_name,
        devad_id=devad_id,
        event_value=event_value,
        payout=payout,
        carrier=carrier,
        os=os,
        ip=ip,
        gid=gid,
        product_id=product_id,
        client_id=client_id,
        db=db
    )


@router.post("/macan/postback", response_model=MacanPostBackResponse, summary="接收 Macan PostBack 回调（POST）")
async def receive_macan_postback_post(
    request: Request,
    postback_data: MacanPostBackRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    接收 Macan S2S PostBack 回调（POST 方式）
    
    这是 Macan 转化事件追踪的回调接口。当用户在 Macan 平台上发生转化事件时，
    Macan 会向此接口发送回调请求。
    
    必填参数：
    - clk_id: Macan click ID
    - event_name: Event ID（事件ID）
    
    可选参数：
    - devad_id: 设备广告ID（IDFA 或 GAID）
    - event_value: 购买价格
    - payout: 确认的广告单元价格
    - carrier: 用户运营商
    - os: 操作系统（IOS 或 Android）
    - ip: 点击IP
    - gid: 渠道ID
    - product_id: 产品ID（用于关联产品）
    - client_id: 客户ID（用于关联客户）
    """
    return await _process_macan_postback(
        request=request,
        clk_id=postback_data.clk_id,
        event_name=postback_data.event_name,
        devad_id=postback_data.devad_id,
        event_value=postback_data.event_value,
        payout=postback_data.payout,
        carrier=postback_data.carrier,
        os=postback_data.os,
        ip=postback_data.ip,
        gid=postback_data.gid,
        product_id=postback_data.product_id,
        client_id=postback_data.client_id,
        db=db
    )


async def _process_macan_postback(
    request: Request,
    clk_id: str,
    event_name: str,
    devad_id: Optional[str],
    event_value: Optional[float],
    payout: Optional[float],
    carrier: Optional[str],
    os: Optional[str],
    ip: Optional[str],
    gid: Optional[str],
    product_id: Optional[int],
    client_id: Optional[int],
    db: AsyncSession
) -> MacanPostBackResponse:
    """
    处理 Macan PostBack 回调的核心逻辑
    
    1. 验证必填参数
    2. 验证产品和客户（如果提供）
    3. 记录日志
    4. 存储数据（可选，根据需求实现）
    """
    try:
        # 1. 验证必填参数
        if not clk_id or not clk_id.strip():
            logger.warning(f"Macan PostBack 回调失败: clk_id 为空")
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail="clk_id 参数不能为空"
            )
        
        if not event_name or not event_name.strip():
            logger.warning(f"Macan PostBack 回调失败: event_name 为空")
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail="event_name 参数不能为空"
            )
        
        # 2. 验证产品和客户（如果提供）
        if product_id:
            result = await db.execute(
                select(Product).where(Product.id == product_id, Product.is_active == True)
            )
            product = result.scalars().first()
            if not product:
                logger.warning(f"Macan PostBack 回调失败: 产品不存在或未激活, product_id={product_id}")
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail=f"产品不存在或未激活: product_id={product_id}"
                )
        
        if client_id:
            result = await db.execute(
                select(Client).where(Client.id == client_id, Client.is_active == True)
            )
            client = result.scalars().first()
            if not client:
                logger.warning(f"Macan PostBack 回调失败: 客户不存在或未激活, client_id={client_id}")
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail=f"客户不存在或未激活: client_id={client_id}"
                )
        
        # 3. 记录日志
        logger.info(
            f"Macan PostBack 回调接收成功: "
            f"clk_id={clk_id}, event_name={event_name}, "
            f"devad_id={devad_id}, event_value={event_value}, "
            f"payout={payout}, carrier={carrier}, os={os}, "
            f"ip={ip}, gid={gid}, product_id={product_id}, client_id={client_id}"
        )
        
        # 4. 存储数据（这里可以根据需求实现数据库存储逻辑）
        # 例如：创建 MacanConversion 表并存储数据
        # 或者：更新 AdData 表中的转化数据
        # 目前先记录日志，后续可以根据业务需求扩展
        
        # 5. 返回成功响应
        return MacanPostBackResponse(
            success=True,
            message="PostBack 接收成功",
            clk_id=clk_id
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理 Macan PostBack 回调时发生错误: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"处理 PostBack 回调失败：{str(e)}"
        )

