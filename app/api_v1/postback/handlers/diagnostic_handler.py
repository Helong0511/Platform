"""诊断工具处理模块"""
import logging
from typing import Dict, Any

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.models.models import (
    PostbackConversion, ConversionDeductionLog, PostbackNotification, User
)
from app.schemas.base import ResponseBaseSchema

logger = logging.getLogger(__name__)


class DiagnosticHandler:
    """诊断工具处理器"""

    async def diagnose_postback_record(
            self,
            conversion_or_click_id: str,
            db: AsyncSession,
            current_user: User
    ):
        """
        诊断 PostBack 记录问题
        
        当收到通知但找不到记录时，使用此接口进行诊断
        会检查：
        1. 主表（postback_conversions）中是否存在
        2. 扣减日志表（conversion_deduction_logs）中是否存在
        3. 通知记录表（postback_notifications）中是否存在
        4. 可能的平台名称变化
        
        仅管理员可访问
        """
        try:
            diagnosis_result: Dict[str, Any] = {
                "conversion_or_click_id": conversion_or_click_id,
                "found_in_main_table": False,
                "found_in_deduction_logs": False,
                "found_in_notifications": False,
                "platform_name_changes": [],
                "suggestions": []
            }

            # 1. 检查主表（postback_conversions）
            main_table_query = select(PostbackConversion).where(
                or_(
                    PostbackConversion.conversion_id == conversion_or_click_id,
                    PostbackConversion.click_id == conversion_or_click_id
                )
            )
            main_result = await db.execute(main_table_query)
            main_records = main_result.scalars().all()

            if main_records:
                diagnosis_result["found_in_main_table"] = True
                diagnosis_result["main_table_records"] = [
                    {
                        "id": record.id,
                        "platform": record.platform,
                        "conversion_id": record.conversion_id,
                        "click_id": record.click_id,
                        "created_at": record.created_at.isoformat() if record.created_at else None,
                        "conversion_status": getattr(record, 'conversion_status', None),
                        "is_deducted": getattr(record, 'is_deducted', False)
                    }
                    for record in main_records
                ]
                # 收集所有平台名称（使用集合推导式去重）
                platforms = list({r.platform for r in main_records})
                if len(platforms) > 1 or (len(platforms) == 1 and platforms[0] != "bft"):
                    diagnosis_result["platform_name_changes"] = platforms
                    diagnosis_result["suggestions"].append(
                        f"记录已找到，但平台名称可能已从 'bft' 变为 '{platforms[0]}'（根据广告主自动更新）。"
                        f"请在查询时选择平台为 '{platforms[0]}' 或使用'全部'。"
                    )
            else:
                diagnosis_result["suggestions"].append(
                    "在主表中未找到记录。可能原因：1) 数据验证失败 2) 被扣量 3) 重复检测跳过 4) 平台名称变化"
                )

            # 2. 检查扣减日志表（conversion_deduction_logs）
            deduction_query = select(ConversionDeductionLog).where(
                ConversionDeductionLog.click_id == conversion_or_click_id
            ).order_by(ConversionDeductionLog.created_at.desc())
            deduction_result = await db.execute(deduction_query)
            deduction_logs = deduction_result.scalars().all()

            if deduction_logs:
                diagnosis_result["found_in_deduction_logs"] = True
                diagnosis_result["deduction_logs"] = [
                    {
                        "id": log.id,
                        "conversion_id": log.conversion_id,
                        "click_id": log.click_id,
                        "deducted_volume": log.deducted_volume,
                        "deducted_amount": float(log.deducted_amount) if log.deducted_amount else 0.0,
                        "original_amount": float(log.original_amount) if log.original_amount else 0.0,
                        "final_amount": float(log.final_amount) if log.final_amount else 0.0,
                        "created_at": log.created_at.isoformat() if log.created_at else None,
                        "deduction_reason": log.deduction_reason
                    }
                    for log in deduction_logs
                ]
                # 检查是否有被扣量的记录
                deducted_logs = [log for log in deduction_logs if log.deducted_volume > 0]
                if deducted_logs:
                    diagnosis_result["suggestions"].append(
                        f"在扣减日志表中找到 {len(deducted_logs)} 条被扣量的记录。"
                        f"这些转化因扣量而未保存到主表，但会记录在扣减日志表中。"
                        f"可以在'扣减管理'页面查看这些记录。"
                    )

            # 3. 检查通知记录表（postback_notifications）
            # 通过 click_id 或 conversion_id 查找通知记录
            notification_query = select(PostbackNotification).join(
                PostbackConversion,
                PostbackNotification.conversion_id == PostbackConversion.id
            ).where(
                or_(
                    PostbackConversion.conversion_id == conversion_or_click_id,
                    PostbackConversion.click_id == conversion_or_click_id
                )
            ).order_by(PostbackNotification.created_at.desc())
            notification_result = await db.execute(notification_query)
            notifications = notification_result.scalars().all()

            if notifications:
                diagnosis_result["found_in_notifications"] = True
                diagnosis_result["notifications"] = [
                    {
                        "id": notif.id,
                        "conversion_id": notif.conversion_id,
                        "notification_type": notif.notification_type,
                        "notification_channel": notif.notification_channel,
                        "notification_status": notif.notification_status,
                        "created_at": notif.created_at.isoformat() if notif.created_at else None
                    }
                    for notif in notifications
                ]
                diagnosis_result["suggestions"].append(
                    f"找到 {len(notifications)} 条通知记录，说明系统已收到并处理了该转化。"
                )

            # 4. 提供建议
            if not diagnosis_result["found_in_main_table"] and not diagnosis_result["found_in_deduction_logs"]:
                diagnosis_result["suggestions"].append(
                    "未在任何表中找到记录。可能原因："
                    "1) 数据验证失败，未保存到数据库"
                    "2) 重复检测跳过（相同的转化已处理过）"
                    "3) 点击ID或转化ID不正确"
                    "建议：检查后端日志，搜索该 click_id 或 conversion_id"
                )
            elif not diagnosis_result["found_in_main_table"] and diagnosis_result["found_in_deduction_logs"]:
                diagnosis_result["suggestions"].append(
                    "记录在扣减日志表中，但不在主表中。这是正常的，因为被扣量的转化不会保存到主表。"
                    "可以在'扣减管理'页面查看这些记录。"
                )

            logger.info(
                f"管理员 {current_user.username} 诊断 PostBack 记录: "
                f"conversion_or_click_id={conversion_or_click_id}, "
                f"found_in_main={diagnosis_result['found_in_main_table']}, "
                f"found_in_deduction={diagnosis_result['found_in_deduction_logs']}, "
                f"found_in_notifications={diagnosis_result['found_in_notifications']}"
            )

            return ResponseBaseSchema.success(
                data=diagnosis_result,
                message="诊断完成"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"诊断 PostBack 记录失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"诊断失败: {str(e)}"
            )


diagnostic_handler = DiagnosticHandler()
