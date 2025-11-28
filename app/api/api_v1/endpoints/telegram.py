"""
Telegram Bot API 端点
提供 Telegram Bot 相关的管理功能，包括：
- 发送消息
- 查询 Bot 状态
- 测试连接
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.security import get_current_user
from app.models.models import User, UserRole

# 创建路由实例
router = APIRouter()
# 获取日志记录器
logger = logging.getLogger(__name__)


# ====== 请求/响应模型 ======
class SendMessageRequest(BaseModel):
    """发送消息请求模型"""
    message: str = Field(..., description="要发送的消息内容", min_length=1, max_length=4096)
    chat_id: Optional[str] = Field(None, description="目标聊天ID（可选，默认使用配置中的 TELEGRAM_ADMIN）")


class SendMessageResponse(BaseModel):
    """发送消息响应模型"""
    success: bool = Field(..., description="是否发送成功")
    message: str = Field(..., description="响应消息")


class BotStatusResponse(BaseModel):
    """Bot 状态响应模型"""
    initialized: bool = Field(..., description="Bot 是否已初始化")
    token_configured: bool = Field(..., description="Token 是否已配置")
    admin_configured: bool = Field(..., description="管理员 Chat ID 是否已配置")
    message: str = Field(..., description="状态描述")


# ====== API 端点 ======
@router.get("/status", response_model=BotStatusResponse, summary="查询 Telegram Bot 状态")
async def get_bot_status(
    current_user: User = Depends(get_current_user)
):
    """
    查询 Telegram Bot 的当前状态
    
    需要管理员权限
    """
    # 检查权限（仅管理员）
    if current_user.role != UserRole.ADMIN:
        raise_api_exception(
            error_code=ErrorCode.FORBIDDEN,
            message="仅管理员可以查询 Telegram Bot 状态",
            status_code=status.HTTP_403_FORBIDDEN
        )

    # 检查是否启用 Telegram
    telegram_enabled = getattr(settings, 'TELEGRAM_ENABLE', True)
    if not telegram_enabled:
        return BotStatusResponse(
            initialized=False,
            token_configured=False,
            admin_configured=False,
            message="Telegram Bot 功能已禁用（TELEGRAM_ENABLE=false）"
        )

    try:
        from app.core.auto_bot import bot_initialized
        
        token_configured = bool(
            getattr(settings, 'TELEGRAM_TOKEN', None) and 
            isinstance(getattr(settings, 'TELEGRAM_TOKEN', None), str) and
            getattr(settings, 'TELEGRAM_TOKEN', None).strip()
        )
        
        admin_configured = bool(
            getattr(settings, 'TELEGRAM_ADMIN', None) and
            isinstance(getattr(settings, 'TELEGRAM_ADMIN', None), str) and
            getattr(settings, 'TELEGRAM_ADMIN', None).strip()
        )

        if bot_initialized and token_configured:
            status_message = "Telegram Bot 已初始化并运行中"
        elif token_configured:
            status_message = "Token 已配置，但 Bot 未初始化"
        else:
            status_message = "Token 未配置，请设置 TELEGRAM_TOKEN 环境变量"

        return BotStatusResponse(
            initialized=bot_initialized,
            token_configured=token_configured,
            admin_configured=admin_configured,
            message=status_message
        )
    except Exception as e:
        logger.error(f"查询 Telegram Bot 状态时发生错误: {e}", exc_info=True)
        raise_api_exception(
            error_code=ErrorCode.INTERNAL_ERROR,
            message=f"查询状态失败: {str(e)}"
        )


@router.post("/send", response_model=SendMessageResponse, summary="发送 Telegram 消息")
async def send_message(
    request: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    发送 Telegram 消息
    
    需要管理员权限
    
    - 如果未指定 chat_id，将使用配置中的 TELEGRAM_ADMIN
    - 消息长度限制：1-4096 字符
    """
    # 检查权限（仅管理员）
    if current_user.role != UserRole.ADMIN:
        raise_api_exception(
            error_code=ErrorCode.FORBIDDEN,
            message="仅管理员可以发送 Telegram 消息",
            status_code=status.HTTP_403_FORBIDDEN
        )

    # 检查是否启用 Telegram
    telegram_enabled = getattr(settings, 'TELEGRAM_ENABLE', True)
    if not telegram_enabled:
        raise_api_exception(
            error_code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Telegram Bot 功能已禁用（TELEGRAM_ENABLE=false）",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    try:
        from app.core.auto_bot import send_telegram_message, bot_initialized

        if not bot_initialized:
            raise_api_exception(
                error_code=ErrorCode.SERVICE_UNAVAILABLE,
                message="Telegram Bot 未初始化，请检查 TELEGRAM_TOKEN 配置",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        # 发送消息
        success = await send_telegram_message(
            message=request.message,
            chat_id=request.chat_id
        )

        if success:
            logger.info(f"用户 {current_user.username} 通过 API 发送了 Telegram 消息")
            return SendMessageResponse(
                success=True,
                message="消息发送成功"
            )
        else:
            raise_api_exception(
                error_code=ErrorCode.INTERNAL_ERROR,
                message="消息发送失败，请检查日志或 TELEGRAM_ADMIN 配置"
            )

    except HTTPException:
        # 重新抛出 HTTPException（包括 raise_api_exception 抛出的）
        raise
    except Exception as e:
        logger.error(f"发送 Telegram 消息时发生错误: {e}", exc_info=True)
        raise_api_exception(
            error_code=ErrorCode.INTERNAL_ERROR,
            message=f"发送消息失败: {str(e)}"
        )


@router.post("/test", response_model=SendMessageResponse, summary="测试 Telegram Bot 连接")
async def test_bot_connection(
    current_user: User = Depends(get_current_user)
):
    """
    测试 Telegram Bot 连接
    
    向配置的管理员 Chat ID 发送一条测试消息
    
    需要管理员权限
    """
    # 检查权限（仅管理员）
    if current_user.role != UserRole.ADMIN:
        raise_api_exception(
            error_code=ErrorCode.FORBIDDEN,
            message="仅管理员可以测试 Telegram Bot 连接",
            status_code=status.HTTP_403_FORBIDDEN
        )

    # 检查是否启用 Telegram
    telegram_enabled = getattr(settings, 'TELEGRAM_ENABLE', True)
    if not telegram_enabled:
        raise_api_exception(
            error_code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Telegram Bot 功能已禁用（TELEGRAM_ENABLE=false）",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    try:
        from app.core.auto_bot import send_telegram_message, bot_initialized

        if not bot_initialized:
            raise_api_exception(
                error_code=ErrorCode.SERVICE_UNAVAILABLE,
                message="Telegram Bot 未初始化，请检查 TELEGRAM_TOKEN 配置",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        # 发送测试消息
        from app.core.utils import get_app_now
        current_time = get_app_now()
        test_message = f"🧪 Telegram Bot 连接测试\n\n发送时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}（时区: {settings.TIMEZONE}）\n测试用户: {current_user.username}"
        
        success = await send_telegram_message(message=test_message)

        if success:
            return SendMessageResponse(
                success=True,
                message="测试消息发送成功，请检查 Telegram 是否收到"
            )
        else:
            raise_api_exception(
                error_code=ErrorCode.INTERNAL_ERROR,
                message="测试消息发送失败，请检查 TELEGRAM_ADMIN 配置和日志"
            )

    except HTTPException:
        # 重新抛出 HTTPException
        raise
    except Exception as e:
        logger.error(f"测试 Telegram Bot 连接时发生错误: {e}", exc_info=True)
        raise_api_exception(
            error_code=ErrorCode.INTERNAL_ERROR,
            message=f"测试连接失败: {str(e)}"
        )

