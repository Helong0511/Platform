"""Telegram Bot API 端点
提供 Telegram Bot 相关的管理功能，包括：
- 发送消息
- 查询 Bot 状态
- 测试连接。

说明：对外开放接口，含客户 API（密钥+签名鉴权）与 Telegram 管理。"""
import logging
import threading
from typing import Optional, List
from sqlalchemy import select

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.telegram import (
    send_telegram_message,
    bot_initialized,
    get_bot_status_info,
    bot,
    TELEBOT_AVAILABLE,
)
from app.core.config import settings
from app.core.audit_log import log_user_action, commit_audit_log
from app.core.database import get_db
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.security import require_admin
from app.core.utils import get_app_now
from app.models.models import User, PostbackConversion
from app.schemas.base import ResponseBaseSchema
from app.services.telegram_notification_service import TelegramNotificationService

# 创建路由实例
router = APIRouter()
# 获取日志记录器
logger = logging.getLogger(__name__)


# ====== 请求/响应模型 ======
class SendMessageRequest(BaseModel):
    """
    发送消息请求模型
    
    API 请求体，描述客户端提交的参数格式与约束。
    """
    message: str = Field(..., description="要发送的消息内容", min_length=1, max_length=4096)
    chat_id: Optional[str] = Field(None, description="目标聊天ID（可选，默认使用配置中的 TELEGRAM_ADMIN）")


class SendMessageResponse(BaseModel):
    """
    发送消息响应模型
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    """
    success: bool = Field(..., description="是否发送成功")
    message: str = Field(..., description="响应消息")


class BotStatusResponse(BaseModel):
    """
    Bot 状态响应模型
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    """
    initialized: bool = Field(..., description="Bot 是否已初始化")
    token_configured: bool = Field(..., description="Token 是否已配置")
    admin_configured: bool = Field(..., description="管理员 Chat ID 是否已配置")
    message: str = Field(..., description="状态描述")


class DiagnosticResponse(BaseModel):
    """
    诊断响应模型
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    """
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
    # ---------- 入口：参数与依赖准备 ----------
   
    # 检查是否启用 Telegram
    telegram_enabled = getattr(settings, 'TELEGRAM_ENABLE', True)
    # ---------- 条件分支 ----------
    if not telegram_enabled:
        return ResponseBaseSchema.success(data=BotStatusResponse(
            initialized=False,
            token_configured=False,
            admin_configured=False,
            message="Telegram Bot 功能已禁用（TELEGRAM_ENABLE=false）"
        ))

    # ---------- 异常处理 ----------
    try:

        # 获取详细状态信息
        status_info = get_bot_status_info()

        token_configured = status_info.get("token_configured", False)
        admin_configured = status_info.get("admin_configured", False)
        bot_thread_alive = status_info.get("bot_thread_alive", False)
        connection_test = status_info.get("connection_test", "未测试")

        # 构建状态消息
        # ---------- 条件分支 ----------
        if bot_initialized and token_configured:
            # ---------- 条件分支 ----------
            if bot_thread_alive:
                status_message = "Telegram Bot 已初始化并运行中"
            else:
                status_message = "Telegram Bot 已初始化，但轮询线程未运行"
        # ---------- 条件分支 ----------
        elif token_configured:
            status_message = "Token 已配置，但 Bot 未初始化"
        else:
            status_message = (
                "Token 未配置，请设置 TELEGRAM_TOKEN_LOCAL / "
                "TELEGRAM_TOKEN_PRODUCTION 或 TELEGRAM_TOKEN"
            )

        # 添加连接测试信息
        # ---------- 条件分支 ----------
        if connection_test != "成功" and bot_initialized:
            status_message += f" | 连接测试: {connection_test}"

        return ResponseBaseSchema.success(data=BotStatusResponse(
            initialized=bot_initialized,
            token_configured=token_configured,
            admin_configured=admin_configured,
            message=status_message
        ))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("查询 Telegram Bot 状态时发生错误: error_type=%s", type(e).__name__)
        raise_api_exception(
            error_code=ErrorCode.INTERNAL_ERROR,
            message="查询状态失败，请稍后重试"
        )


@router.post("/send", response_model=ResponseBaseSchema[SendMessageResponse], summary="发送 Telegram 消息")
async def send_message(
        http_request: Request,
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
    # ---------- 入口：参数与依赖准备 ----------
   
    # 检查是否启用 Telegram
    telegram_enabled = getattr(settings, 'TELEGRAM_ENABLE', True)
    # ---------- 条件分支 ----------
    if not telegram_enabled:
        raise_api_exception(
            error_code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Telegram Bot 功能已禁用（TELEGRAM_ENABLE=false）",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    # ---------- 异常处理 ----------
    try:
        # ---------- 条件分支 ----------
        if not bot_initialized:
            raise_api_exception(
                error_code=ErrorCode.SERVICE_UNAVAILABLE,
                message="Telegram Bot 未初始化，请检查 TELEGRAM_TOKEN 配置",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        # 发送消息
        success = send_telegram_message(
            request.chat_id,
            request.message
        )

        # ---------- 条件分支 ----------
        if success:
            logger.info(f"用户 {current_user.username} 通过 API 发送了 Telegram 消息")
            await log_user_action(
                db=db,
                action_type="API_ACCESS",
                user=current_user,
                resource_type="TELEGRAM",
                resource_id=0,
                resource_name="发送Telegram消息",
                request=http_request,
                details={"chat_id": request.chat_id},
            )
            await commit_audit_log(db)
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error("发送 Telegram 消息时发生错误: error_type=%s", type(e).__name__)
        raise_api_exception(
            error_code=ErrorCode.INTERNAL_ERROR,
            message="发送消息失败，请稍后重试"
        )


@router.post("/test", response_model=ResponseBaseSchema[SendMessageResponse], summary="测试 Telegram Bot 连接")
async def test_bot_connection(
        http_request: Request,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    测试 Telegram Bot 连接
    
    向配置的管理员 Chat ID 发送一条测试消息
    
    需要管理员权限
    """
    # ---------- 入口：参数与依赖准备 ----------
   
    # 检查是否启用 Telegram
    telegram_enabled = getattr(settings, 'TELEGRAM_ENABLE', True)
    # ---------- 条件分支 ----------
    if not telegram_enabled:
        raise_api_exception(
            error_code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Telegram Bot 功能已禁用（TELEGRAM_ENABLE=false）",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    # ---------- 异常处理 ----------
    try:
        # ---------- 条件分支 ----------
        if not bot_initialized:
            raise_api_exception(
                error_code=ErrorCode.SERVICE_UNAVAILABLE,
                message="Telegram Bot 未初始化，请检查 TELEGRAM_TOKEN 配置",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        # 发送测试消息
        current_time = get_app_now()
        test_message = f"🧪 Telegram Bot 连接测试\n\n发送时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}（时区: {settings.TIMEZONE}）\n测试用户: {current_user.username}"

        success = send_telegram_message(test_message)

        # ---------- 条件分支 ----------
        if success:
            await log_user_action(
                db=db,
                action_type="API_ACCESS",
                user=current_user,
                resource_type="TELEGRAM",
                resource_id=0,
                resource_name="测试Telegram连接",
                request=http_request,
            )
            await commit_audit_log(db)
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
        raise
    except Exception as e:
        logger.error("测试 Telegram Bot 连接时发生错误: error_type=%s", type(e).__name__)
        raise_api_exception(
            error_code=ErrorCode.INTERNAL_ERROR,
            message="测试连接失败，请稍后重试"
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
    # ---------- 入口：参数与依赖准备 ----------
   
    # ---------- 异常处理 ----------
    try:
        recommendations = []

        # 1. 检查 Bot 初始化
        # ---------- 条件分支 ----------
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
        # ---------- 条件分支 ----------
        if not TELEBOT_AVAILABLE:
            recommendations.append("❌ python-telegram-bot 未安装，请运行: pip install 'python-telegram-bot==22.8'")
            return ResponseBaseSchema.success(data=DiagnosticResponse(
                bot_initialized=False,
                bot_thread_alive=False,
                handlers_count=0,
                connection_test="模块未安装",
                recommendations=recommendations
            ))

        # 3. 检查发送能力（Token / PTB）；轮询 Application 可能尚未挂到 bot_state.bot
        token = getattr(settings, "TELEGRAM_TOKEN", None)
        if not token or not str(token).strip():
            recommendations.append("❌ TELEGRAM_TOKEN 未配置")
            return ResponseBaseSchema.success(data=DiagnosticResponse(
                bot_initialized=False,
                bot_thread_alive=False,
                handlers_count=0,
                connection_test="无 Token",
                recommendations=recommendations
            ))

        # 4. 检查线程状态
        bot_thread_alive = False
        # ---------- 循环处理 ----------
        for thread in threading.enumerate():
            # ---------- 条件分支 ----------
            if thread.name == "TelegramBot":
                bot_thread_alive = thread.is_alive()
                break

        # ---------- 条件分支 ----------
        if not bot_thread_alive:
            recommendations.append("⚠️ 轮询线程未运行，请重启应用或检查日志")

        from app.core.telegram import bot_state as bot_state_mod
        from app.core.telegram.ptb_runtime import (
            count_application_handlers,
            get_send_bot,
            run_on_send_loop,
        )

        send_bot = get_send_bot(str(token).strip(), connect_timeout=3.0, read_timeout=10.0)

        # 5. 检查 Webhook
        webhook_url = None
        # ---------- 异常处理 ----------
        try:
            webhook_info = run_on_send_loop(send_bot.get_webhook_info(), timeout=15.0)
            webhook_url = webhook_info.url if webhook_info.url else None
            # ---------- 条件分支 ----------
            if webhook_url:
                recommendations.append("⚠️ 检测到 Webhook，这可能阻止 polling 工作；请在 Telegram 管理端确认并按需删除")
        except Exception as e:
            logger.warning("检查 webhook 时出错: error_type=%s", type(e).__name__)

        # 6. 检查消息处理器（PTB Application.handlers）
        handlers_count = count_application_handlers(bot_state_mod.application)
        if bot_state_mod.application is None:
            recommendations.append("⚠️ Application 未创建（轮询未启动），命令处理器尚未注册")
        elif handlers_count == 0:
            recommendations.append("⚠️ 没有注册任何消息处理器！命令无法工作")
        else:
            recommendations.append(f"✅ 已注册 {handlers_count} 个 handler（含命令/回调/调试）")

        # 7. 测试连接
        connection_test = "未测试"
        # ---------- 异常处理 ----------
        try:
            bot_info = run_on_send_loop(send_bot.get_me(), timeout=15.0)
            connection_test = f"成功: @{bot_info.username} (ID: {bot_info.id})"
        except Exception as e:
            connection_test = "失败：请检查 Bot 配置和网络连接"
            recommendations.append("❌ Bot 连接测试失败，请检查 Bot 配置和网络连接")

        # 8. 给出修复建议
        # ---------- 条件分支 ----------
        if not bot_thread_alive:
            recommendations.append("💡 如果轮询线程未运行，命令将无法响应。请检查应用日志或重启应用")

        # ---------- 条件分支 ----------
        if webhook_url:
            recommendations.append("💡 删除 webhook 后，轮询才能正常工作。可以使用 /api/v1/telegram/reset_webhook 删除")

        # ---------- 条件分支 ----------
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error("诊断 Telegram Bot 时发生错误: error_type=%s", type(e).__name__)
        raise_api_exception(
            error_code=ErrorCode.INTERNAL_ERROR,
            message="诊断失败，请稍后重试"
        )


@router.post("/reset_webhook", response_model=ResponseBaseSchema[SendMessageResponse], summary="强制删除 Webhook")
async def reset_webhook(
        http_request: Request,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    强制删除 Webhook 并重置 offset
    
    用于修复命令无响应问题
    
    需要管理员权限
    """
    # ---------- 入口：参数与依赖准备 ----------
   
    # ---------- 异常处理 ----------
    try:

        # ---------- 条件分支 ----------
        if not bot_initialized or not TELEBOT_AVAILABLE:
            raise_api_exception(
                error_code=ErrorCode.SERVICE_UNAVAILABLE,
                message="Bot 未初始化",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        token = getattr(settings, "TELEGRAM_TOKEN", None)
        if not token or not str(token).strip():
            raise_api_exception(
                error_code=ErrorCode.SERVICE_UNAVAILABLE,
                message="TELEGRAM_TOKEN 未配置",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        from app.core.telegram.ptb_runtime import get_send_bot, run_on_send_loop

        send_bot = get_send_bot(str(token).strip(), connect_timeout=3.0, read_timeout=15.0)

        # 删除 webhook
        run_on_send_loop(
            send_bot.delete_webhook(drop_pending_updates=True),
            timeout=20.0,
        )

        # 检查确认
        webhook_info = run_on_send_loop(send_bot.get_webhook_info(), timeout=15.0)

        # ---------- 条件分支 ----------
        if webhook_info.url:
            return ResponseBaseSchema.success(data=SendMessageResponse(
                success=False,
                message=f"Webhook 删除失败，仍然存在: {webhook_info.url}"
            ))
        else:
            await log_user_action(
                db=db,
                action_type="TASK_RUN",
                user=current_user,
                resource_type="TELEGRAM",
                resource_id=0,
                resource_name="重置Telegram Webhook",
                request=http_request,
            )
            await commit_audit_log(db)
            return ResponseBaseSchema.success(data=SendMessageResponse(
                success=True,
                message="Webhook 已成功删除。请重启应用以使轮询正常工作，或等待轮询线程自动重新连接"
            ))

    except HTTPException:
        raise
    except Exception as e:
        logger.error("删除 Webhook 时发生错误: error_type=%s", type(e).__name__)
        raise_api_exception(
            error_code=ErrorCode.INTERNAL_ERROR,
            message="删除 Webhook 失败，请稍后重试"
        )


# ====== 新的实用 API 端点 ======

class SendAlertRequest(BaseModel):
    """
    发送告警请求模型
    
    API 请求体，描述客户端提交的参数格式与约束。
    """
    alert_type: str = Field(..., description="告警类型", min_length=1, max_length=100)
    description: str = Field(..., description="告警描述", min_length=1, max_length=1000)
    module: Optional[str] = Field(None, description="模块名称", max_length=100)
    function: Optional[str] = Field(None, description="函数名称", max_length=100)
    line: Optional[int] = Field(None, description="行号")
    telegram_chat_id: Optional[str] = Field(None, description="目标聊天ID（可选，默认使用配置中的 TELEGRAM_ADMIN")


@router.post("/send_alert", response_model=ResponseBaseSchema[SendMessageResponse], summary="发送系统告警")
async def send_alert(
        http_request: Request,
        request: SendAlertRequest,
        current_user: User = Depends(require_admin),
        db: AsyncSession = Depends(get_db)
):
    """
    发送系统告警通知到指定 Telegram Chat。

    权限：仅管理员；写入审计日志；失败时返回明确错误码。
    """
    # ---------- 入口：参数与依赖准备 ----------
    # 检查是否启用 Telegram
    telegram_enabled = getattr(settings, 'TELEGRAM_ENABLE', True)
    # ---------- 条件分支 ----------
    if not telegram_enabled:
        raise_api_exception(
            error_code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Telegram Bot 功能已禁用（TELEGRAM_ENABLE=false）",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    # ---------- 异常处理 ----------
    try:
        # ---------- 条件分支 ----------
        if not bot_initialized:
            raise_api_exception(
                error_code=ErrorCode.SERVICE_UNAVAILABLE,
                message="Telegram Bot 未初始化，请检查 TELEGRAM_TOKEN 配置",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        # 构建位置信息
        location = {}
        # ---------- 条件分支 ----------
        if request.module:
            location['module'] = request.module
        # ---------- 条件分支 ----------
        if request.function:
            location['function'] = request.function
        # ---------- 条件分支 ----------
        if request.line:
            location['line'] = str(request.line)

        # 发送告警
        success = await TelegramNotificationService.send_system_alert(
            alert_type=request.alert_type,
            description=request.description,
            location=location if location else None,
            telegram_chat_id=request.telegram_chat_id,
            db=db
        )

        # ---------- 条件分支 ----------
        if success:
            logger.info(f"用户 {current_user.username} 通过 API 发送了系统告警")
            await log_user_action(
                db=db,
                action_type="API_ACCESS",
                user=current_user,
                resource_type="TELEGRAM",
                resource_id=0,
                resource_name="发送系统告警",
                request=http_request,
                details={"alert_type": request.alert_type},
            )
            await commit_audit_log(db)
            return ResponseBaseSchema.success(data=SendMessageResponse(
                success=True,
                message="系统告警发送成功"
            ))
        else:
            raise_api_exception(
                error_code=ErrorCode.INTERNAL_ERROR,
                message="系统告警发送失败"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("发送系统告警时发生错误: error_type=%s", type(e).__name__)
        raise_api_exception(
            error_code=ErrorCode.INTERNAL_ERROR,
            message="发送系统告警失败，请稍后重试"
        )


class SendBatchRequest(BaseModel):
    """
    发送批量通知请求模型
    
    API 请求体，描述客户端提交的参数格式与约束。
    """
    conversions: List[int] = Field(..., description="转化记录ID列表")
    telegram_chat_id: Optional[str] = Field(None, description="目标聊天ID（可选，默认使用配置中的 TELEGRAM_ADMIN")


@router.post("/send_batch", response_model=ResponseBaseSchema[SendMessageResponse], summary="发送批量转化通知")
async def send_batch_notifications(
        http_request: Request,
        request: SendBatchRequest,
        current_user: User = Depends(require_admin),
        db: AsyncSession = Depends(get_db)
):
    """
    批量发送转化通知到 Telegram（补发或测试场景）。

    权限：仅管理员；按请求中的转化 ID 列表逐条推送并汇总成功/失败数。
    """
    # ---------- 入口：参数与依赖准备 ----------
    # 检查是否启用 Telegram
    telegram_enabled = getattr(settings, 'TELEGRAM_ENABLE', True)
    # ---------- 条件分支 ----------
    if not telegram_enabled:
        raise_api_exception(
            error_code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Telegram Bot 功能已禁用（TELEGRAM_ENABLE=false）",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    # ---------- 异常处理 ----------
    try:
        # ---------- 条件分支 ----------
        if not bot_initialized:
            raise_api_exception(
                error_code=ErrorCode.SERVICE_UNAVAILABLE,
                message="Telegram Bot 未初始化，请检查 TELEGRAM_TOKEN 配置",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        # 查询转化记录
        result = await db.execute(
            select(PostbackConversion).where(
                PostbackConversion.id.in_(request.conversions)
            )
        )
        conversions = result.scalars().all()

        # ---------- 条件分支 ----------
        if not conversions:
            return ResponseBaseSchema.success(data=SendMessageResponse(
                success=False,
                message="未找到指定的转化记录"
            ))

        # 发送批量通知
        success = await TelegramNotificationService.send_batch_conversion_notifications(
            conversions=conversions,
            telegram_chat_id=request.telegram_chat_id,
            db=db
        )

        # ---------- 条件分支 ----------
        if success:
            logger.info(f"用户 {current_user.username} 通过 API 发送了批量转化通知")
            await log_user_action(
                db=db,
                action_type="API_ACCESS",
                user=current_user,
                resource_type="TELEGRAM",
                resource_id=0,
                resource_name="批量发送转化通知",
                request=http_request,
                details={"conversion_count": len(conversions)},
            )
            await commit_audit_log(db)
            return ResponseBaseSchema.success(data=SendMessageResponse(
                success=True,
                message=f"批量转化通知发送成功，共 {len(conversions)} 条"
            ))
        else:
            raise_api_exception(
                error_code=ErrorCode.INTERNAL_ERROR,
                message="批量转化通知发送失败"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("发送批量转化通知时发生错误: error_type=%s", type(e).__name__)
        raise_api_exception(
            error_code=ErrorCode.INTERNAL_ERROR,
            message="发送批量转化通知失败，请稍后重试"
        )
