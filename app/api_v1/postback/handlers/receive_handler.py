"""PostBack 接收处理模块"""
import json
import logging
from typing import Dict, Any

from fastapi import Request, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.postback import PostbackProcessor
from app.core.utils import get_client_ip

logger = logging.getLogger(__name__)


class ReceiveHandler:
    """PostBack 接收处理器"""

    async def receive_postback(
            self,
            request: Request,
            platform: str,
            db: AsyncSession
    ):
        """
        接收任意平台的 PostBack 回调（同时支持 GET 和 POST 请求）
        
        这是通用的 PostBack 转化事件追踪接口，支持任意平台的回调。
        当用户在广告平台上发生转化事件时，平台会向此接口发送回调请求。
        
        此接口支持接收任意参数，不限制参数名称和类型：
        - GET 请求：通过 Query 参数传递所有数据
        - POST 请求：支持 JSON Body 和 Query 参数，可以混合使用，body 中的值优先
        
        **参数说明**：
        - platform: 平台名称（如 bft、facebook、google 等）
        - 其他参数：根据各平台的要求自行传递
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

            # 获取客户端IP
            client_ip = get_client_ip(request)

            # 如果 raw_data 中没有 ip，则添加客户端IP（仅用于数据记录，不用于白名单验证）
            if client_ip and client_ip != "unknown" and "ip" not in raw_data:
                raw_data["ip"] = client_ip

            # 调用统一服务处理
            result = await PostbackProcessor.process(
                platform=platform,
                raw_data=raw_data,
                db=db,
                request_ip=client_ip
            )

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
            logger.error(f"接收 PostBack 回调时发生错误: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"处理 PostBack 回调失败：{str(e)}"
            )


receive_handler = ReceiveHandler()
