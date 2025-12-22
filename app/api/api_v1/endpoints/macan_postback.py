"""
Macan S2S PostBack 接收接口
用于接收 Macan 发送的转化事件回调

参考文档：https://macan-native.com/docs/advertiser/S2S/

注意：此接口已优化，内部调用统一的 postback 服务进行处理
保留此接口是为了向后兼容，建议使用 /api/v1/postback/macan 接口
"""
import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, Request, Query, HTTPException, Depends, Body
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.postback import PostbackProcessor
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode

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
@router.api_route(
    "/macan/postback",
    methods=["GET", "POST"],
    response_model=MacanPostBackResponse,
    summary="接收 Macan PostBack 回调（支持 GET 和 POST）"
)
async def receive_macan_postback(
    request: Request,
    # POST 请求的 Body 数据（可选）
    postback_data: Optional[MacanPostBackRequest] = Body(None, description="PostBack 数据（JSON Body，仅 POST 请求使用）"),
    # Query 参数（GET 和 POST 都支持）
    clk_id: Optional[str] = Query(None, description="Macan click ID（必填，可通过 body 或 query 传递）"),
    event_name: Optional[str] = Query(None, description="Event ID（事件ID，必填，可通过 body 或 query 传递）"),
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
    接收 Macan S2S PostBack 回调（同时支持 GET 和 POST 请求）
    
    这是 Macan 转化事件追踪的回调接口。当用户在 Macan 平台上发生转化事件时，
    Macan 会向此接口发送回调请求。
    
    **GET 请求**：
    - 通过 Query 参数传递所有数据
    - 必填参数：clk_id, event_name
    - 其他参数均为可选
    
    **POST 请求**：
    支持三种方式传递数据：
    1. JSON Body（推荐）：通过请求体传递 JSON 数据
    2. Query 参数：通过 URL 查询参数传递数据
    3. 混合方式：可以同时使用 body 和 query，body 中的值优先
    
    **必填参数**（可通过 body 或 query 传递）：
    - clk_id: Macan click ID
    - event_name: Event ID（事件ID）
    
    **可选参数**：
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
    # 根据请求方法处理数据
    if request.method == "GET":
        # GET 请求：只使用 Query 参数
        final_clk_id = clk_id
        final_event_name = event_name
        final_devad_id = devad_id
        final_event_value = event_value
        final_payout = payout
        final_carrier = carrier
        final_os = os
        final_ip = ip
        final_gid = gid
        final_product_id = product_id
        final_client_id = client_id
    else:
        # POST 请求：合并 body 和 query 参数，body 优先，query 作为补充
        if postback_data:
            # 从 body 获取数据，如果 body 中某些字段为空，则使用 query 参数补充
            final_clk_id = postback_data.clk_id or clk_id
            final_event_name = postback_data.event_name or event_name
            final_devad_id = postback_data.devad_id or devad_id
            final_event_value = postback_data.event_value if postback_data.event_value is not None else event_value
            final_payout = postback_data.payout if postback_data.payout is not None else payout
            final_carrier = postback_data.carrier or carrier
            final_os = postback_data.os or os
            final_ip = postback_data.ip or ip
            final_gid = postback_data.gid or gid
            final_product_id = postback_data.product_id if postback_data.product_id is not None else product_id
            final_client_id = postback_data.client_id if postback_data.client_id is not None else client_id
        else:
            # 如果没有 body，完全使用 query 参数
            final_clk_id = clk_id
            final_event_name = event_name
            final_devad_id = devad_id
            final_event_value = event_value
            final_payout = payout
            final_carrier = carrier
            final_os = os
            final_ip = ip
            final_gid = gid
            final_product_id = product_id
            final_client_id = client_id
    
    # 验证必填参数
    if not final_clk_id:
        raise HTTPException(status_code=400, detail="clk_id 是必填参数")
    if not final_event_name:
        raise HTTPException(status_code=400, detail="event_name 是必填参数")
    
    return await _process_macan_postback(
        request=request,
        clk_id=final_clk_id,
        event_name=final_event_name,
        devad_id=final_devad_id,
        event_value=final_event_value,
        payout=final_payout,
        carrier=final_carrier,
        os=final_os,
        ip=final_ip,
        gid=final_gid,
        product_id=final_product_id,
        client_id=final_client_id,
        db=db
    )


def _get_client_ip(request: Request) -> Optional[str]:
    """获取客户端IP地址"""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host
    return None


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
    
    优化：内部调用统一的 postback 服务进行处理
    保留此函数是为了向后兼容，实际处理由统一服务完成
    """
    try:
        # 获取客户端IP
        client_ip = _get_client_ip(request) or ip
        
        # 构建原始数据字典
        raw_data: Dict[str, Any] = {
            "clk_id": clk_id,
            "event_name": event_name,
        }
        
        # 添加可选字段
        if devad_id:
            raw_data["devad_id"] = devad_id
        if event_value is not None:
            raw_data["event_value"] = event_value
        if payout is not None:
            raw_data["payout"] = payout
        if carrier:
            raw_data["carrier"] = carrier
        if os:
            raw_data["os"] = os
        if client_ip:
            raw_data["ip"] = client_ip
        if gid:
            raw_data["gid"] = gid
        if product_id is not None:
            raw_data["product_id"] = product_id
        if client_id is not None:
            raw_data["client_id"] = client_id
        
        # 调用统一服务处理
        result = await PostbackProcessor.process(
            platform="macan",
            raw_data=raw_data,
            db=db,
            request_ip=client_ip
        )
        
        # 发送 Telegram 通知（保持原有功能）
        try:
            from app.core.auto_bot import send_telegram_message
            import asyncio
            
            method = request.method
            telegram_msg = f"🔔 Macan PostBack 回调收到\n\n"
            telegram_msg += f"Method: {method}\n"
            telegram_msg += f"Event: {event_name}\n"
            telegram_msg += f"Click ID: {clk_id}\n"
            if payout:
                telegram_msg += f"Payout: {payout}\n"
            if product_id:
                telegram_msg += f"Product ID: {product_id}\n"
            if client_id:
                telegram_msg += f"Client ID: {client_id}\n"
            
            await asyncio.wait_for(
                send_telegram_message(telegram_msg),
                timeout=5.0
            )
        except Exception as e:
            logger.warning(f"发送 Macan PostBack Telegram 通知失败: {e}")

        # 返回成功响应（保持原有响应格式）
        return MacanPostBackResponse(
            success=result.get("success", True),
            message=result.get("message", "PostBack 接收成功"),
            clk_id=result.get("conversion_id", clk_id)
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理 Macan PostBack 回调时发生错误: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"处理 PostBack 回调失败：{str(e)}"
        )