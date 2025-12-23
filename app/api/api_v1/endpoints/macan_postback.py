"""
Macan S2S PostBack 接收接口
用于接收 Macan 发送的转化事件回调

参考文档：https://macan-native.com/docs/advertiser/S2S/

注意：此接口已优化，内部调用统一的 postback 服务进行处理
保留此接口是为了向后兼容，建议使用 /api/v1/postback/macan 接口

此接口支持接收任意参数，不限制参数名称和类型
"""
import logging
import json
from typing import Optional, Dict, Any

from fastapi import APIRouter, Request, HTTPException, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.postback import PostbackProcessor
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode

# 创建路由实例
router = APIRouter()
# 获取日志记录器
logger = logging.getLogger(__name__)


# ====== API端点 ======
@router.api_route(
    "/macan/postback",
    methods=["GET", "POST"],
    summary="接收 Macan PostBack 回调（支持 GET 和 POST，接收任意参数）"
)
async def receive_macan_postback(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    接收 Macan S2S PostBack 回调（同时支持 GET 和 POST 请求）
    
    这是 Macan 转化事件追踪的回调接口。当用户在 Macan 平台上发生转化事件时，
    Macan 会向此接口发送回调请求。
    
    此接口支持接收任意参数，不限制参数名称和类型：
    - GET 请求：通过 Query 参数传递所有数据
    - POST 请求：支持 JSON Body 和 Query 参数，可以混合使用，body 中的值优先
    
    **推荐参数**（非必填）：
    - clk_id: Macan click ID
    - event_name: Event ID（事件ID）
    """
    try:
        # 收集所有参数
        raw_data: Dict[str, Any] = {}
        
        # 从 Query 参数获取所有数据
        for key, value in request.query_params.items():
            raw_data[key] = value
        
        # 如果是 POST 请求，尝试从 Body 获取数据
        if request.method == "POST":
            content_type = request.headers.get("content-type", "").lower()
            
            try:
                # 优先尝试读取 JSON Body（适用于 application/json）
                if "application/json" in content_type or not content_type:
                    try:
                        body_data = await request.json()
                        if isinstance(body_data, dict):
                            # Body 中的数据会覆盖 Query 参数中的同名参数
                            raw_data.update(body_data)
                    except (json.JSONDecodeError, ValueError, Exception):
                        # JSON 解析失败，body 已被消耗，无法再读取
                        pass
                # 尝试读取 form data（适用于 application/x-www-form-urlencoded 或 multipart/form-data）
                elif "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
                    try:
                        form_data = await request.form()
                        for key, value in form_data.items():
                            raw_data[key] = value
                    except Exception:
                        pass
                # 其他格式，尝试读取原始 body 并解析为 key=value 格式
                else:
                    try:
                        body_bytes = await request.body()
                        if body_bytes:
                            body_str = body_bytes.decode('utf-8')
                            if '=' in body_str:
                                for pair in body_str.split('&'):
                                    if '=' in pair:
                                        key, value = pair.split('=', 1)
                                        raw_data[key] = value
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"读取 POST Body 数据时发生错误: {e}")
        
        # 验证推荐参数（但不强制要求）
        clk_id = raw_data.get("clk_id")
        event_name = raw_data.get("event_name")
        
        return await _process_macan_postback(
            request=request,
            raw_data=raw_data,
            db=db
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"接收 Macan PostBack 回调时发生错误: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"处理 PostBack 回调失败：{str(e)}"
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


def _collect_request_info(request: Request) -> Dict[str, Any]:
    """收集请求的软硬件详细信息"""
    info = {
        "请求方法": request.method,
        "请求URL": str(request.url),
        "请求路径": request.url.path,
        "查询参数": dict(request.query_params),
        "协议": request.url.scheme,
        "主机": request.url.hostname,
        "端口": request.url.port,
    }
    
    # 客户端信息
    if request.client:
        info["客户端IP"] = request.client.host
        info["客户端端口"] = request.client.port
    else:
        info["客户端IP"] = "未知"
        info["客户端端口"] = "未知"
    
    # 从请求头获取真实IP
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        info["X-Forwarded-For"] = forwarded_for
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        info["X-Real-IP"] = real_ip
    
    # 收集所有请求头
    headers = {}
    for key, value in request.headers.items():
        headers[key] = value
    info["请求头"] = headers
    
    # User-Agent 详细信息
    user_agent = request.headers.get("User-Agent", "未知")
    info["User-Agent"] = user_agent
    
    # 其他重要请求头
    important_headers = [
        "Accept", "Accept-Language", "Accept-Encoding",
        "Content-Type", "Content-Length", "Referer",
        "Origin", "Connection", "Cache-Control",
        "X-Forwarded-Proto", "X-Forwarded-Host", "X-Forwarded-Port"
    ]
    for header_name in important_headers:
        header_value = request.headers.get(header_name)
        if header_value:
            info[f"请求头-{header_name}"] = header_value
    
    return info


async def _process_macan_postback(
    request: Request,
    raw_data: Dict[str, Any],
    db: AsyncSession
) -> Response:
    """
    处理 Macan PostBack 回调的核心逻辑
    
    优化：内部调用统一的 postback 服务进行处理
    保留此函数是为了向后兼容，实际处理由统一服务完成
    """
    try:
        # 收集并记录请求的软硬件详细信息
        request_info = _collect_request_info(request)
        clk_id = raw_data.get("clk_id", "未知")
        event_name = raw_data.get("event_name", "未知")
        
        logger.info("=" * 80)
        logger.info(f"Macan PostBack 请求详细信息 - clk_id: {clk_id}, event_name: {event_name}")
        logger.info("-" * 80)
        for key, value in request_info.items():
            if isinstance(value, dict):
                logger.info(f"{key}:")
                for sub_key, sub_value in value.items():
                    logger.info(f"  {sub_key}: {sub_value}")
            else:
                logger.info(f"{key}: {value}")
        logger.info("=" * 80)
        
        # 获取客户端IP
        client_ip = _get_client_ip(request) or raw_data.get("ip")
        
        # 如果 raw_data 中没有 ip，则添加客户端IP
        if client_ip and "ip" not in raw_data:
            raw_data["ip"] = client_ip
        
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
            
            # 添加其他重要参数到通知
            payout = raw_data.get("payout")
            product_id = raw_data.get("product_id")
            client_id = raw_data.get("client_id")
            
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

        # 返回纯文本 "ok"，确保所有语言（Java、Go、Python 等）都能正确识别
        # 使用 UTF-8 编码，明确设置 Content-Type 为 text/plain
        return Response(
            content="ok",
            media_type="text/plain; charset=utf-8",
            status_code=200
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理 Macan PostBack 回调时发生错误: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"处理 PostBack 回调失败：{str(e)}"
        )