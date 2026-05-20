"""Postback IP 白名单服务。"""
import logging
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.constants import MAX_PAGE_SIZE
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.pagination import paginate_query
from app.models.models import PostbackIpWhitelist, User
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.schemas.postback_ip_whitelist import (
    PostbackIpWhitelistBatchCreate,
    PostbackIpWhitelistBatchCreateResponse,
    PostbackIpWhitelistCreate,
    PostbackIpWhitelistResponse,
    PostbackIpWhitelistUpdate,
)
from app.services.cpl.postback_pending_service import postback_pending_service

logger = logging.getLogger(__name__)


class PostbackIpWhitelistService:
    """Postback IP 白名单 CRUD 与批量操作。"""

    async def list_ip_whitelist(
            self,
            ip_address: Optional[str],
            is_active: Optional[bool],
            page: int,
            page_size: int,
            db: AsyncSession,
            current_user: User,
    ):
        try:
            query = select(PostbackIpWhitelist)
            conditions = []
            if ip_address:
                conditions.append(
                    PostbackIpWhitelist.ip_address.like(f"%{ip_address}%")
                )
            if is_active is not None:
                conditions.append(PostbackIpWhitelist.is_active == is_active)

            whitelist_items, total = await paginate_query(
                db=db,
                query=query,
                page=page,
                page_size=page_size,
                order_by=PostbackIpWhitelist.created_at.desc(),
                conditions=conditions if conditions else None,
                model_class=PostbackIpWhitelist,
            )

            logger.info(
                "管理员 %s 查询 IP 白名单: total=%s, page=%s",
                current_user.username,
                total,
                page,
            )

            return PaginatedResponseBaseSchema.success(
                data=[
                    PostbackIpWhitelistResponse.model_validate(item)
                    for item in whitelist_items
                ],
                total=total,
                page=page,
                page_size=page_size,
                message=f"成功获取 {len(whitelist_items)} 条记录，共 {total} 条",
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error("查询 IP 白名单失败: %s", e, exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"查询失败：{str(e)}",
            )

    async def create_ip_whitelist(
            self,
            data: PostbackIpWhitelistCreate,
            db: AsyncSession,
            current_user: User,
    ):
        try:
            existing = await db.execute(
                select(PostbackIpWhitelist).where(
                    PostbackIpWhitelist.ip_address == data.ip_address
                )
            )
            if existing.scalars().first():
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail=f"IP 地址 {data.ip_address} 已存在于白名单中",
                )

            whitelist_item = PostbackIpWhitelist(
                ip_address=data.ip_address,
                description=data.description,
                is_active=data.is_active,
            )
            db.add(whitelist_item)
            await db.commit()
            await db.refresh(whitelist_item)

            logger.info(
                "管理员 %s 创建 IP 白名单: ip=%s id=%s",
                current_user.username,
                data.ip_address,
                whitelist_item.id,
            )

            approval_result = await postback_pending_service.auto_approve_pending_by_ip(
                data.ip_address, db, current_user
            )
            message = "IP 白名单创建成功"
            if approval_result["approved_count"] > 0:
                message += (
                    f"，已自动批准 {approval_result['approved_count']} 条待确认转化记录"
                )
            if approval_result["skipped_count"] > 0:
                message += (
                    f"，跳过 {approval_result['skipped_count']} 条（已存在正式记录）"
                )

            return ResponseBaseSchema.success(
                data=PostbackIpWhitelistResponse.model_validate(whitelist_item),
                message=message,
            )
        except HTTPException:
            raise
        except Exception as e:
            await db.rollback()
            logger.error("创建 IP 白名单失败: %s", e, exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"创建失败：{str(e)}",
            )

    async def update_ip_whitelist(
            self,
            whitelist_id: int,
            data: PostbackIpWhitelistUpdate,
            db: AsyncSession,
            current_user: User,
    ):
        try:
            result = await db.execute(
                select(PostbackIpWhitelist).where(
                    PostbackIpWhitelist.id == whitelist_id
                )
            )
            whitelist_item = result.scalars().first()
            if not whitelist_item:
                raise_api_exception(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    detail=f"IP 白名单 ID {whitelist_id} 不存在",
                )

            if data.ip_address and data.ip_address != whitelist_item.ip_address:
                existing = await db.execute(
                    select(PostbackIpWhitelist).where(
                        PostbackIpWhitelist.ip_address == data.ip_address,
                        PostbackIpWhitelist.id != whitelist_id,
                    )
                )
                if existing.scalars().first():
                    raise_api_exception(
                        ErrorCode.VALIDATION_ERROR,
                        detail=f"IP 地址 {data.ip_address} 已存在于其他白名单记录中",
                    )

            if data.ip_address is not None:
                whitelist_item.ip_address = data.ip_address
            if data.description is not None:
                whitelist_item.description = data.description
            if data.is_active is not None:
                whitelist_item.is_active = data.is_active

            await db.commit()
            await db.refresh(whitelist_item)

            logger.info(
                "管理员 %s 更新 IP 白名单: id=%s ip=%s",
                current_user.username,
                whitelist_id,
                whitelist_item.ip_address,
            )

            return ResponseBaseSchema.success(
                data=PostbackIpWhitelistResponse.model_validate(whitelist_item),
                message="IP 白名单更新成功",
            )
        except HTTPException:
            raise
        except Exception as e:
            await db.rollback()
            logger.error("更新 IP 白名单失败: %s", e, exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"更新失败：{str(e)}",
            )

    async def batch_create_ip_whitelist(
            self,
            data: PostbackIpWhitelistBatchCreate,
            db: AsyncSession,
            current_user: User,
    ):
        try:
            created_items: List[PostbackIpWhitelist] = []
            failed_items = []

            existing_result = await db.execute(
                select(PostbackIpWhitelist.ip_address)
            )
            existing_ips = {
                row.strip() for row in existing_result.scalars().all() if row
            }

            for ip_address in data.ip_addresses:
                trimmed_ip = ip_address.strip()
                if trimmed_ip in existing_ips:
                    failed_items.append({
                        "ip_address": trimmed_ip,
                        "error": "IP地址已存在于白名单中",
                    })
                    continue
                try:
                    whitelist_item = PostbackIpWhitelist(
                        ip_address=trimmed_ip,
                        description=data.description,
                        is_active=data.is_active,
                    )
                    db.add(whitelist_item)
                    existing_ips.add(trimmed_ip)
                    created_items.append(whitelist_item)
                except Exception as e:
                    error_msg = str(e)
                    if (
                        "unique constraint" in error_msg.lower()
                        or "duplicate" in error_msg.lower()
                    ):
                        error_msg = "IP地址已存在于白名单中"
                        existing_ips.add(trimmed_ip)
                    failed_items.append({
                        "ip_address": trimmed_ip,
                        "error": error_msg,
                    })
                    logger.warning("创建IP白名单失败: %s, %s", trimmed_ip, error_msg)

            if created_items:
                try:
                    await db.commit()
                    for item in created_items:
                        await db.refresh(item)
                except Exception as commit_error:
                    await db.rollback()
                    error_msg = str(commit_error)
                    logger.error("批量提交IP白名单失败: %s", error_msg, exc_info=True)
                    for item in created_items:
                        failed_items.append({
                            "ip_address": item.ip_address,
                            "error": f"提交失败: {error_msg}",
                        })
                    created_items = []

            success_count = len(created_items)
            failed_count = len(failed_items)
            total_count = len(data.ip_addresses)

            total_approved = 0
            total_skipped = 0
            for item in created_items:
                approval_result = (
                    await postback_pending_service.auto_approve_pending_by_ip(
                        item.ip_address, db, current_user
                    )
                )
                total_approved += approval_result["approved_count"]
                total_skipped += approval_result["skipped_count"]

            if success_count == 0 and failed_count > 0:
                all_duplicates = all(
                    "已存在于白名单中" in item.get("error", "")
                    for item in failed_items
                )
                if all_duplicates:
                    message = (
                        f"所有 {total_count} 个IP地址都已存在于白名单中，无需重复添加"
                    )
                else:
                    message = f"批量创建失败：所有 {total_count} 个IP地址都无法添加"
            else:
                message = (
                    f"批量创建完成：成功 {success_count} 个，失败 {failed_count} 个，"
                    f"共 {total_count} 个"
                )
                if total_approved > 0:
                    message += f"，已自动批准 {total_approved} 条待确认转化记录"
                if total_skipped > 0:
                    message += f"，跳过 {total_skipped} 条（已存在正式记录）"

            logger.info(
                "管理员 %s 批量创建 IP 白名单: 总数=%s 成功=%s 失败=%s 自动批准=%s",
                current_user.username,
                total_count,
                success_count,
                failed_count,
                total_approved,
            )

            return ResponseBaseSchema.success(
                data=PostbackIpWhitelistBatchCreateResponse(
                    success_count=success_count,
                    failed_count=failed_count,
                    total_count=total_count,
                    created_items=[
                        PostbackIpWhitelistResponse.model_validate(item)
                        for item in created_items
                    ],
                    failed_items=failed_items,
                ),
                message=message,
            )
        except HTTPException:
            raise
        except Exception as e:
            await db.rollback()
            logger.error("批量创建 IP 白名单失败: %s", e, exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"批量创建失败：{str(e)}",
            )

    async def delete_ip_whitelist(
            self,
            whitelist_id: int,
            db: AsyncSession,
            current_user: User,
    ):
        try:
            result = await db.execute(
                select(PostbackIpWhitelist).where(
                    PostbackIpWhitelist.id == whitelist_id
                )
            )
            whitelist_item = result.scalars().first()
            if not whitelist_item:
                raise_api_exception(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    detail=f"IP 白名单 ID {whitelist_id} 不存在",
                )

            ip_address = whitelist_item.ip_address
            await db.delete(whitelist_item)
            await db.commit()

            logger.info(
                "管理员 %s 删除 IP 白名单: id=%s ip=%s",
                current_user.username,
                whitelist_id,
                ip_address,
            )

            return ResponseBaseSchema.success(
                data={"id": whitelist_id, "ip_address": ip_address},
                message="IP 白名单删除成功",
            )
        except HTTPException:
            raise
        except Exception as e:
            await db.rollback()
            logger.error("删除 IP 白名单失败: %s", e, exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"删除失败：{str(e)}",
            )


postback_ip_whitelist_service = PostbackIpWhitelistService()
