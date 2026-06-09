"""
Postback 重复转化检查服务。

功能说明：
- 检测正式转化表、待确认表内 platform+conversion_id+event_name 重复组
- 检测待确认与正式表之间的「跨表重复」，辅助排查重复回调或幂等失效
- 管理员运维工具，只读查询，不修改数据

在系统中的位置：
- 被管理端运维/诊断 API 调用

注意事项：
1. 仅管理员可访问，避免泄露转化明细给普通客户
2. 结果用于人工决策，不自动删除重复记录
"""
import logging
from typing import Optional, Dict, Any

from fastapi import HTTPException
from sqlalchemy import func, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.models.models import PostbackConversion, PendingPostbackConversion, User
from app.schemas.base import ResponseBaseSchema

logger = logging.getLogger(__name__)


class PostbackDuplicateService:
    """Postback 重复转化检测：表内重复与跨表重复。"""

    async def check_duplicate_conversions(
            self,
            platform: Optional[str],
            conversion_id: Optional[str],
            db: AsyncSession,
            current_user: User
    ):
        """
        检查重复的转化记录（仅管理员）。

        重复判定键：platform + conversion_id + event_name。

        检查范围：
        1. postback_conversions 表内 count>1 的分组及明细
        2. pending_postback_conversions（status=pending）表内重复
        3. pending 与 formal 之间相同三元组是否同时存在

        Args:
            platform: 可选，限定平台。
            conversion_id: 可选，限定转化 ID。
            db: 异步数据库会话。
            current_user: 操作管理员，写入 info 日志。

        Returns:
            ResponseBaseSchema，data 含 formal_duplicates、pending_duplicates、
            cross_duplicates 及 summary 计数。
        """
        try:
            duplicates_info: Dict[str, Any] = {
                "formal_duplicates": [],
                "pending_duplicates": [],
                "cross_duplicates": [],
                "summary": {
                    "formal_duplicate_count": 0,
                    "pending_duplicate_count": 0,
                    "cross_duplicate_count": 0
                }
            }

            # 1. 正式表：GROUP BY 后 HAVING count > 1
            formal_query = select(
                PostbackConversion.platform,
                PostbackConversion.conversion_id,
                PostbackConversion.event_name,
                func.count(PostbackConversion.id).label('count')
            ).group_by(
                PostbackConversion.platform,
                PostbackConversion.conversion_id,
                PostbackConversion.event_name
            ).having(func.count(PostbackConversion.id) > 1)

            if platform:
                formal_query = formal_query.where(PostbackConversion.platform == platform)
            if conversion_id:
                formal_query = formal_query.where(PostbackConversion.conversion_id == conversion_id)

            formal_result = await db.execute(formal_query)
            formal_duplicates = formal_result.all()

            for dup in formal_duplicates:
                detail_query = select(PostbackConversion).where(
                    PostbackConversion.platform == dup.platform,
                    PostbackConversion.conversion_id == dup.conversion_id,
                    PostbackConversion.event_name == dup.event_name
                ).order_by(PostbackConversion.created_at.desc())

                detail_result = await db.execute(detail_query)
                duplicate_records = detail_result.scalars().all()

                duplicates_info["formal_duplicates"].append({
                    "platform": dup.platform,
                    "conversion_id": dup.conversion_id,
                    "event_name": dup.event_name,
                    "count": dup.count,
                    "records": [
                        {
                            "id": r.id,
                            "created_at": r.created_at.isoformat() if r.created_at else None,
                            "original_payout": r.original_payout,
                            "payout": r.payout
                        }
                        for r in duplicate_records
                    ]
                })

            duplicates_info["summary"]["formal_duplicate_count"] = len(formal_duplicates)

            # 2. 待确认表：仅 status=pending 参与重复统计
            pending_query = select(
                PendingPostbackConversion.platform,
                PendingPostbackConversion.conversion_id,
                PendingPostbackConversion.event_name,
                func.count(PendingPostbackConversion.id).label('count')
            ).where(
                PendingPostbackConversion.status == 'pending'
            ).group_by(
                PendingPostbackConversion.platform,
                PendingPostbackConversion.conversion_id,
                PendingPostbackConversion.event_name
            ).having(func.count(PendingPostbackConversion.id) > 1)

            if platform:
                pending_query = pending_query.where(PendingPostbackConversion.platform == platform)
            if conversion_id:
                pending_query = pending_query.where(PendingPostbackConversion.conversion_id == conversion_id)

            pending_result = await db.execute(pending_query)
            pending_duplicates = pending_result.all()

            for dup in pending_duplicates:
                detail_query = select(PendingPostbackConversion).where(
                    PendingPostbackConversion.platform == dup.platform,
                    PendingPostbackConversion.conversion_id == dup.conversion_id,
                    PendingPostbackConversion.event_name == dup.event_name,
                    PendingPostbackConversion.status == 'pending'
                ).order_by(PendingPostbackConversion.created_at.desc())

                detail_result = await db.execute(detail_query)
                duplicate_records = detail_result.scalars().all()

                duplicates_info["pending_duplicates"].append({
                    "platform": dup.platform,
                    "conversion_id": dup.conversion_id,
                    "event_name": dup.event_name,
                    "count": dup.count,
                    "records": [
                        {
                            "id": r.id,
                            "created_at": r.created_at.isoformat() if r.created_at else None,
                            "request_ip": r.request_ip,
                            "original_payout": r.original_payout,
                            "payout": r.payout
                        }
                        for r in duplicate_records
                    ]
                })

            duplicates_info["summary"]["pending_duplicate_count"] = len(pending_duplicates)

            # 3. 跨表：批量加载 pending 对应的 formal 行，避免逐条查询
            all_pending_query = select(PendingPostbackConversion).where(
                PendingPostbackConversion.status == 'pending'
            )
            if platform:
                all_pending_query = all_pending_query.where(PendingPostbackConversion.platform == platform)
            if conversion_id:
                all_pending_query = all_pending_query.where(PendingPostbackConversion.conversion_id == conversion_id)

            all_pending_result = await db.execute(all_pending_query)
            all_pending = all_pending_result.scalars().all()

            formal_map = {}
            if all_pending:
                keys = [
                    (p.platform, p.conversion_id, p.event_name) for p in all_pending
                ]
                formal_rows = await db.execute(
                    select(PostbackConversion).where(
                        tuple_(
                            PostbackConversion.platform,
                            PostbackConversion.conversion_id,
                            PostbackConversion.event_name,
                        ).in_(keys)
                    )
                )
                for row in formal_rows.scalars().all():
                    formal_map[
                        (row.platform, row.conversion_id, row.event_name)
                    ] = row

            for pending in all_pending:
                formal_match = formal_map.get(
                    (pending.platform, pending.conversion_id, pending.event_name)
                )
                if formal_match:
                    duplicates_info["cross_duplicates"].append({
                        "platform": pending.platform,
                        "conversion_id": pending.conversion_id,
                        "event_name": pending.event_name,
                        "pending_record": {
                            "id": pending.id,
                            "created_at": pending.created_at.isoformat() if pending.created_at else None,
                            "request_ip": pending.request_ip,
                            "original_payout": pending.original_payout,
                            "payout": pending.payout
                        },
                        "formal_record": {
                            "id": formal_match.id,
                            "created_at": formal_match.created_at.isoformat() if formal_match.created_at else None,
                            "original_payout": formal_match.original_payout,
                            "payout": formal_match.payout
                        }
                    })

            duplicates_info["summary"]["cross_duplicate_count"] = len(duplicates_info["cross_duplicates"])

            logger.info(
                f"管理员 {current_user.username} 查询重复转化记录: "
                f"formal={duplicates_info['summary']['formal_duplicate_count']}, "
                f"pending={duplicates_info['summary']['pending_duplicate_count']}, "
                f"cross={duplicates_info['summary']['cross_duplicate_count']}"
            )

            return ResponseBaseSchema.success(
                data=duplicates_info,
                message=f"发现 {duplicates_info['summary']['formal_duplicate_count']} 组正式记录重复，"
                        f"{duplicates_info['summary']['pending_duplicate_count']} 组待确认记录重复，"
                        f"{duplicates_info['summary']['cross_duplicate_count']} 组跨表重复"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"查询重复转化记录失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"查询失败：{str(e)}"
            )


postback_duplicate_service = PostbackDuplicateService()
DuplicateHandler = PostbackDuplicateService
duplicate_handler = postback_duplicate_service
