"""
BFT S2S PostBack 接收接口
用于接收 BFT 发送的转化事件回调

注意：此接口已优化，内部调用统一的 postback 服务进行处理
保留此接口是为了向后兼容，建议使用 /api/v1/postback/bft 接口

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
    "/bft/postback",
    methods=["GET", "POST"],
    summary="接收 BFT PostBack 回调（支持 GET 和 POST，接收任意参数）"
)
async def receive_bft_postback(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    接收 BFT S2S PostBack 回调（同时支持 GET 和 POST 请求）
    
    这是 BFT 转化事件追踪的回调接口。当用户在 BFT 平台上发生转化事件时，
    BFT 会向此接口发送回调请求。
    
    此接口支持接收任意参数，不限制参数名称和类型：
    - GET 请求：通过 Query 参数传递所有数据
    - POST 请求：支持 JSON Body 和 Query 参数，可以混合使用，body 中的值优先
    
    **推荐参数**（非必填）：
    - clk_id: BFT click ID
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
        
        # 立即发送 Telegram 通知（接收到数据就通知）
        try:
            from app.core.auto_bot import send_telegram_message
            import asyncio
            from datetime import datetime
            
            # 获取客户端IP
            client_ip = None
            forwarded_for = request.headers.get("X-Forwarded-For")
            if forwarded_for:
                client_ip = forwarded_for.split(",")[0].strip()
            if not client_ip:
                real_ip = request.headers.get("X-Real-IP")
                if real_ip:
                    client_ip = real_ip.strip()
            if not client_ip and request.client:
                client_ip = request.client.host
            client_ip = client_ip or "未知"
            
            # 构建通知消息
            method = request.method
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            telegram_msg = f"🔔 BFT PostBack 收到数据\n\n"
            telegram_msg += f"⏰ 时间: {current_time}\n"
            telegram_msg += f"📡 方法: {method}\n"
            telegram_msg += f"🌐 IP: {client_ip}\n"
            
            if event_name:
                telegram_msg += f"📌 事件: {event_name}\n"
            if clk_id:
                telegram_msg += f"🆔 Click ID: {clk_id}\n"
            
            telegram_msg += f"\n📋 接收到的参数 ({len(raw_data)} 个):\n"
            telegram_msg += "-" * 40 + "\n"
            
            # 遍历所有收到的参数，添加到通知中
            if raw_data:
                for key, value in sorted(raw_data.items()):
                    # 格式化参数值
                    if value is None:
                        value_str = "None"
                    elif isinstance(value, (dict, list)):
                        # 如果是复杂类型，转换为 JSON 字符串
                        try:
                            value_str = json.dumps(value, ensure_ascii=False)
                        except:
                            value_str = str(value)
                    else:
                        value_str = str(value)
                    
                    # 限制单个参数值的长度，避免消息过长
                    if len(value_str) > 150:
                        value_str = value_str[:150] + "..."
                    
                    telegram_msg += f"• {key}: {value_str}\n"
            else:
                telegram_msg += "无参数\n"
            
            # 检查消息长度（Telegram 最大 4096 字符）
            from app.core.telegram_utils import truncate_message
            if len(telegram_msg) > 4096:
                telegram_msg = truncate_message(telegram_msg)
            
            # 异步发送通知，不阻塞主流程
            # 使用 asyncio.create_task 创建任务，不等待完成（fire and forget）
            # 但使用 asyncio.wait_for 确保有超时保护
            asyncio.create_task(
                asyncio.wait_for(
                    send_telegram_message(telegram_msg),
                    timeout=10.0
                )
            )
        except asyncio.TimeoutError:
            logger.warning(f"发送 BFT PostBack Telegram 通知超时（超过10秒）")
        except Exception as e:
            logger.warning(f"发送 BFT PostBack Telegram 通知失败: {e}")
        
        return await _process_bft_postback(
            request=request,
            raw_data=raw_data,
            db=db
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"接收 BFT PostBack 回调时发生错误: {str(e)}", exc_info=True)
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


async def _process_bft_postback(
    request: Request,
    raw_data: Dict[str, Any],
    db: AsyncSession
) -> Response:
    """
    处理 BFT PostBack 回调的核心逻辑
    
    优化：内部调用统一的 postback 服务进行处理
    保留此函数是为了向后兼容，实际处理由统一服务完成
    """
    try:
        # 收集并记录请求的软硬件详细信息
        request_info = _collect_request_info(request)
        
        # 先尝试从原始数据获取（用于日志显示）
        clk_id = (
            raw_data.get("clk_id") or
            raw_data.get("click_id") or
            raw_data.get("cid") or
            raw_data.get("conversion_id") or
            "未知"
        )
        event_name = (
            raw_data.get("event_name") or
            raw_data.get("event_id") or
            raw_data.get("event") or
            "未知"
        )
        
        # 只在开发环境或需要调试时打印详细请求信息（避免生产环境日志过多）
        from app.core.config import settings
        if not settings.is_production:
            logger.debug("=" * 80)
            logger.debug(f"BFT PostBack 请求详细信息 - clk_id: {clk_id}, event_name: {event_name}")
            logger.debug("-" * 80)
            for key, value in request_info.items():
                if isinstance(value, dict):
                    logger.debug(f"{key}:")
                    for sub_key, sub_value in value.items():
                        logger.debug(f"  {sub_key}: {sub_value}")
                else:
                    logger.debug(f"{key}: {value}")
            logger.debug("=" * 80)
        else:
            # 生产环境只记录关键信息
            logger.info(f"BFT PostBack - clk_id: {clk_id}, event_name: {event_name}")
        
        # 获取客户端IP
        client_ip = _get_client_ip(request) or raw_data.get("ip")
        
        # 如果 raw_data 中没有 ip，则添加客户端IP
        if client_ip and "ip" not in raw_data:
            raw_data["ip"] = client_ip
        
        # 参数映射：支持多种参数名变体，映射到标准参数名
        # 这样可以让接口更灵活，支持任意参数名传入
        mapped_data = raw_data.copy()
        
        # 映射 click ID 相关参数（按优先级）
        if not mapped_data.get("clk_id"):
            # 尝试从其他可能的参数名获取
            click_id = (
                mapped_data.get("click_id") or
                mapped_data.get("cid") or
                mapped_data.get("clickid") or
                mapped_data.get("clickId") or
                mapped_data.get("ClickId") or
                mapped_data.get("conversion_id") or
                mapped_data.get("conversionId")
            )
            if click_id:
                mapped_data["clk_id"] = click_id
        
        # 映射 event_name 相关参数（按优先级，可选）
        if not mapped_data.get("event_name"):
            # 尝试从其他可能的参数名获取
            event_name = (
                mapped_data.get("event_id") or
                mapped_data.get("eventId") or
                mapped_data.get("event") or
                mapped_data.get("eventName") or
                mapped_data.get("EventName")
            )
            if event_name:
                mapped_data["event_name"] = event_name
            # 如果没有提供 event_name，不设置默认值，因为它是可选的
        
        # 调用统一服务处理（使用映射后的数据）
        result = await PostbackProcessor.process(
            platform="bft",
            raw_data=mapped_data,
            db=db,
            request_ip=client_ip
        )
        
        # 注意：Telegram 通知已在 receive_bft_postback 函数中发送（接收到数据时立即通知）
        # 这里不再重复发送，避免重复通知

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
        # 注意：外层已经记录了错误日志，这里只记录简要信息避免重复
        # 详细错误信息由全局异常处理器记录
        logger.warning(f"处理 BFT PostBack 回调时发生错误: {type(e).__name__}: {str(e)[:200]}")
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"处理 PostBack 回调失败：{str(e)}"
        )

