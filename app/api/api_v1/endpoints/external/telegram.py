"""
Telegram Bot API 端点
提供 Telegram Bot 相关的管理功能，包括：
- 发送消息
- 查询 Bot 状态
- 测试连接
"""
import logging
import threading
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.security import get_current_user, require_admin
from app.core.utils import get_app_now
from app.core.auto_bot import (
    send_telegram_message, bot_initialized, get_bot_status_info, bot, TELEBOT_AVAILABLE
)
from app.models.models import User
from app.schemas.base import ResponseBaseSchema

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


class DiagnosticResponse(BaseModel):
    """诊断响应模型"""
    bot_initialized: bool = Field(..., description="Bot 是否已初始化")
    bot_thread_alive: bool = Field(..., description="轮询线程是否运行")
    webhook_url: str | None = Field(None, description="Webhook URL（如果有）")
    handlers_count: int = Field(..., description="消息处理器数量")
    connection_test: str = Field(..., description="连接测试结果")
    recommendations: list[str] = Field(default_factory=list, description="修复建议")


# ====== API 端点 ======
@router.get("/status", response_model=ResponseBaseSchema[BotStatusResponse], summary="查询 Telegram Bot 状态")
async def get_bot_status(
    current_user: User = Depends(require_admin)
):
    """
    查询 Telegram Bot 的当前状态
    
    需要管理员权限
    """

    # 检查是否启用 Telegram
    telegram_enabled = getattr(settings, 'TELEGRAM_ENABLE', True)
    if not telegram_enabled:
        return ResponseBaseSchema.success(data=BotStatusResponse(
            initialized=False,
            token_configured=False,
            admin_configured=False,
            message="Telegram Bot 功能已禁用（TELEGRAM_ENABLE=false）"
        ))

    try:
        
        # 获取详细状态信息
        status_info = get_bot_status_info()
        
        token_configured = status_info.get("token_configured", False)
        admin_configured = status_info.get("admin_configured", False)
        bot_thread_alive = status_info.get("bot_thread_alive", False)
        connection_test = status_info.get("connection_test", "未测试")
        
        # 构建状态消息
        if bot_initialized and token_configured:
            if bot_thread_alive:
                status_message = "Telegram Bot 已初始化并运行中"
            else:
                status_message = "Telegram Bot 已初始化，但轮询线程未运行"
        elif token_configured:
            status_message = "Token 已配置，但 Bot 未初始化"
        else:
            status_message = "Token 未配置，请设置 TELEGRAM_TOKEN 环境变量"
        
        # 添加连接测试信息
        if connection_test != "成功" and bot_initialized:
            status_message += f" | 连接测试: {connection_test}"

        return ResponseBaseSchema.success(data=BotStatusResponse(
            initialized=bot_initialized,
            token_configured=token_configured,
            admin_configured=admin_configured,
            message=status_message
        ))
    except Exception as e:
        logger.error(f"查询 Telegram Bot 状态时发生错误: {e}", exc_info=True)
        raise_api_exception(
            error_code=ErrorCode.INTERNAL_ERROR,
            message=f"查询状态失败: {str(e)}"
        )


@router.post("/send", response_model=ResponseBaseSchema[SendMessageResponse], summary="发送 Telegram 消息")
async def send_message(
    request: SendMessageRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    发送 Telegram 消息
    
    需要管理员权限
    
    - 如果未指定 chat_id，将使用配置中的 TELEGRAM_ADMIN
    - 消息长度限制：1-4096 字符
    """

    # 检查是否启用 Telegram
    telegram_enabled = getattr(settings, 'TELEGRAM_ENABLE', True)
    if not telegram_enabled:
        raise_api_exception(
            error_code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Telegram Bot 功能已禁用（TELEGRAM_ENABLE=false）",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    try:
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
            return ResponseBaseSchema.success(data=SendMessageResponse(
                success=True,
                message="消息发送成功"
            ))
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


@router.post("/test", response_model=ResponseBaseSchema[SendMessageResponse], summary="测试 Telegram Bot 连接")
async def test_bot_connection(
    current_user: User = Depends(require_admin)
):
    """
    测试 Telegram Bot 连接
    
    向配置的管理员 Chat ID 发送一条测试消息
    
    需要管理员权限
    """

    # 检查是否启用 Telegram
    telegram_enabled = getattr(settings, 'TELEGRAM_ENABLE', True)
    if not telegram_enabled:
        raise_api_exception(
            error_code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Telegram Bot 功能已禁用（TELEGRAM_ENABLE=false）",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    try:
        if not bot_initialized:
            raise_api_exception(
                error_code=ErrorCode.SERVICE_UNAVAILABLE,
                message="Telegram Bot 未初始化，请检查 TELEGRAM_TOKEN 配置",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        # 发送测试消息
        current_time = get_app_now()
        test_message = f"🧪 Telegram Bot 连接测试\n\n发送时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}（时区: {settings.TIMEZONE}）\n测试用户: {current_user.username}"
        
        success = await send_telegram_message(message=test_message)

        if success:
            return ResponseBaseSchema.success(data=SendMessageResponse(
                success=True,
                message="测试消息发送成功，请检查 Telegram 是否收到"
            ))
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


@router.get("/diagnostic", response_model=ResponseBaseSchema[DiagnosticResponse], summary="Telegram Bot 诊断")
async def diagnostic_bot(
    current_user: User = Depends(require_admin)
):
    """
    Telegram Bot 诊断工具
    
    检查 Bot 状态，诊断命令无响应问题
    
    需要管理员权限
    """

    try:
        recommendations = []
        
        # 1. 检查 Bot 初始化
        if not bot_initialized:
            recommendations.append("❌ Bot 未初始化，请检查 TELEGRAM_TOKEN 配置")
            return ResponseBaseSchema.success(data=DiagnosticResponse(
                bot_initialized=False,
                bot_thread_alive=False,
                handlers_count=0,
                connection_test="Bot 未初始化",
                recommendations=recommendations
            ))
        
        # 2. 检查模块可用性
        if not TELEBOT_AVAILABLE:
            recommendations.append("❌ pyTelegramBotAPI 未安装，请运行: pip install pyTelegramBotAPI")
            return ResponseBaseSchema.success(data=DiagnosticResponse(
                bot_initialized=False,
                bot_thread_alive=False,
                handlers_count=0,
                connection_test="模块未安装",
                recommendations=recommendations
            ))
        
        # 3. 检查 Bot 对象
        if not bot:
            recommendations.append("❌ Bot 对象不存在")
            return ResponseBaseSchema.success(data=DiagnosticResponse(
                bot_initialized=False,
                bot_thread_alive=False,
                handlers_count=0,
                connection_test="Bot 对象不存在",
                recommendations=recommendations
            ))
        
        # 4. 检查线程状态
        bot_thread_alive = False
        for thread in threading.enumerate():
            if thread.name == "TelegramBot":
                bot_thread_alive = thread.is_alive()
                break
        
        if not bot_thread_alive:
            recommendations.append("⚠️ 轮询线程未运行，请重启应用或检查日志")
        
        # 5. 检查 Webhook
        webhook_url = None
        try:
            webhook_info = bot.get_webhook_info()
            webhook_url = webhook_info.url if webhook_info.url else None
            if webhook_url:
                recommendations.append(f"⚠️ 检测到 Webhook: {webhook_url}，这将阻止 polling 工作！请删除 webhook")
        except Exception as e:
            logger.warning(f"检查 webhook 时出错: {e}")
        
        # 6. 检查消息处理器
        handlers_count = 0
        try:
            if hasattr(bot, 'message_handlers'):
                handlers_count = len(bot.message_handlers)
                if handlers_count == 0:
                    recommendations.append("⚠️ 没有注册任何消息处理器！命令无法工作")
                else:
                    # 检查命令处理器
                    command_handlers = []
                    for handler in bot.message_handlers:
                        filters = handler.get('filters', {})
                        commands = filters.get('commands', [])
                        if commands:
                            command_handlers.extend(commands)
                    
                    expected_commands = ['id', 'test', 'clock']
                    missing_commands = [cmd for cmd in expected_commands if cmd not in command_handlers]
                    if missing_commands:
                        recommendations.append(f"⚠️ 缺少命令处理器: {missing_commands}")
                    else:
                        recommendations.append(f"✅ 所有命令处理器已注册: {command_handlers}")
        except Exception as e:
            logger.warning(f"检查消息处理器时出错: {e}")
        
        # 7. 测试连接
        connection_test = "未测试"
        try:
            bot_info = bot.get_me()
            connection_test = f"成功: @{bot_info.username} (ID: {bot_info.id})"
        except Exception as e:
            connection_test = f"失败: {str(e)}"
            recommendations.append(f"❌ Bot 连接测试失败: {str(e)}")
        
        # 8. 给出修复建议
        if not bot_thread_alive:
            recommendations.append("💡 如果轮询线程未运行，命令将无法响应。请检查应用日志或重启应用")
        
        if webhook_url:
            recommendations.append("💡 删除 webhook 后，轮询才能正常工作。可以使用 /api/v1/telegram/reset_webhook 删除")
        
        if handlers_count > 0 and bot_thread_alive and not webhook_url:
            recommendations.append("✅ 所有检查通过，如果命令仍无响应，请检查日志中的轮询信息")
            recommendations.append("💡 查看日志中是否有 '收到 X 个更新' 或 '检测到命令' 的信息")
        
        return ResponseBaseSchema.success(data=DiagnosticResponse(
            bot_initialized=bot_initialized,
            bot_thread_alive=bot_thread_alive,
            webhook_url=webhook_url,
            handlers_count=handlers_count,
            connection_test=connection_test,
            recommendations=recommendations
        ))
        
    except Exception as e:
        logger.error(f"诊断 Telegram Bot 时发生错误: {e}", exc_info=True)
        raise_api_exception(
            error_code=ErrorCode.INTERNAL_ERROR,
            message=f"诊断失败: {str(e)}"
        )


@router.post("/reset_webhook", response_model=ResponseBaseSchema[SendMessageResponse], summary="强制删除 Webhook")
async def reset_webhook(
    current_user: User = Depends(require_admin)
):
    """
    强制删除 Webhook 并重置 offset
    
    用于修复命令无响应问题
    
    需要管理员权限
    """
    
    try:
        
        if not bot_initialized or not TELEBOT_AVAILABLE or not bot:
            raise_api_exception(
                error_code=ErrorCode.SERVICE_UNAVAILABLE,
                message="Bot 未初始化",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        
        # 删除 webhook
        result = bot.delete_webhook(drop_pending_updates=True)
        
        # 检查确认
        webhook_info = bot.get_webhook_info()
        
        if webhook_info.url:
            return ResponseBaseSchema.success(data=SendMessageResponse(
                success=False,
                message=f"Webhook 删除失败，仍然存在: {webhook_info.url}"
            ))
        else:
            return ResponseBaseSchema.success(data=SendMessageResponse(
                success=True,
                message="Webhook 已成功删除。请重启应用以使轮询正常工作，或等待轮询线程自动重新连接"
            ))
        
    except Exception as e:
        logger.error(f"删除 Webhook 时发生错误: {e}", exc_info=True)
        raise_api_exception(
            error_code=ErrorCode.INTERNAL_ERROR,
            message=f"删除 Webhook 失败: {str(e)}"
        )

