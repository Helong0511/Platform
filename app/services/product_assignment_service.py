"""
产品分配历史管理服务层。

功能说明：
- 产品与客户分配关系的创建、转移、历史查询与批量校验
- 维护 ProductAssignment 表，支撑广告数据权限隔离与报表过滤

在系统中的位置：
- 被产品管理、客户管理 API 调用；与 ``app.core.product_assignment`` 工具配合

注意事项：
1. 转移分配须在同一事务内更新历史记录与当前生效行
2. 清理无效分配（客户已删除等）应定期由校验接口触发
"""
import logging
from typing import List, Dict, Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.product_assignment import (
    lock_product_for_assignment,
    validate_product_assignments,
    cleanup_invalid_assignments,
)
from app.core.query_utils import invalidate_assignment_table_cache
from app.models.models import ProductAssignment, Product, Client, User, UserRole
from app.services.base_service import BaseService

logger = logging.getLogger(__name__)


class ProductAssignmentService(BaseService[ProductAssignment]):
    """
    产品分配历史服务。

    继承 BaseService 获得通用 CRUD；日期变更类操作均委托
    app.core.product_assignment 中的 validate / cleanup 工具函数。
    """

    def __init__(self, db: AsyncSession):
        """注入数据库会话并绑定 ProductAssignment 模型。"""
        super().__init__(db, ProductAssignment)

    async def get_product_assignments(
            self,
            product_id: int,
            current_user: User
    ) -> List[Dict[str, Any]]:
        """
        获取指定产品的分配历史（含客户、用户关联信息）。

        客户角色仅能查看归属自身的产品；无记录时会二次校验产品是否存在
        以区分「产品不存在」与「无权限」。

        Args:
            product_id: 产品 ID
            current_user: 当前用户

        Returns:
            分配记录字典列表（含 client_name、user_full_name 等展示字段）
        """
        # 优化查询：一次性查询产品、客户、用户和分配历史，减少数据库往返
        if current_user.role == UserRole.ADMIN:
            # 管理员：直接查询分配历史，同时关联产品、客户和用户信息
            query = select(ProductAssignment, Client, Product, User).join(
                Client, ProductAssignment.client_id == Client.id
            ).join(
                Product, ProductAssignment.product_id == Product.id
            ).join(
                User, Client.user_id == User.id
            ).where(
                ProductAssignment.product_id == product_id
            ).order_by(ProductAssignment.start_date.desc())
        else:
            # 客户：需要验证权限，只查询属于当前客户的产品分配历史
            query = select(ProductAssignment, Client, Product, User).join(
                Client, ProductAssignment.client_id == Client.id
            ).join(
                Product, ProductAssignment.product_id == Product.id
            ).join(
                User, Client.user_id == User.id
            ).where(
                ProductAssignment.product_id == product_id,
                Client.user_id == current_user.id
            ).order_by(ProductAssignment.start_date.desc())

        result = await self.db.execute(query)
        assignments_data = result.all()

        # 检查是否有数据
        if not assignments_data:
            # 如果没有分配历史，检查产品是否存在（使用JOIN优化，避免N+1查询）
            product_query = select(Product).options(selectinload(Product.client)).where(Product.id == product_id)

            # 如果是客户角色，在查询时直接过滤权限
            if current_user.role != UserRole.ADMIN:
                product_query = product_query.join(Client, Product.client_id == Client.id).where(
                    Client.user_id == current_user.id
                )

            product_result = await self.db.execute(product_query)
            product = product_result.scalars().first()

            if not product:
                # 如果是客户用户，可能是权限问题
                if current_user.role != UserRole.ADMIN:
                    raise_api_exception(
                        ErrorCode.PRODUCT_NO_PERMISSION,
                        detail=f"您没有权限查看产品ID {product_id} 的分配历史"
                    )
                else:
                    raise_api_exception(
                        ErrorCode.PRODUCT_NOT_FOUND,
                        detail=f"产品ID {product_id} 不存在"
                    )

        # 转换为响应格式
        assignments_list = []
        for row in assignments_data:
            # 解包查询结果（ProductAssignment, Client, Product, User）
            assignment, client, product, user = row
            assignment_dict = {
                "id": assignment.id,
                "product_id": assignment.product_id,
                "client_id": assignment.client_id,
                "start_date": assignment.start_date,
                "end_date": assignment.end_date,
                "created_at": assignment.created_at,
                "updated_at": assignment.updated_at,
                "client_name": client.company_name,
                "company_name": client.company_name,
                "contact_person": client.contact_person,
                "phone": client.phone,
                "user_full_name": user.full_name if user else None
            }
            assignments_list.append(assignment_dict)

        return assignments_list

    async def get_client_assignments(
            self,
            client_id: int,
            current_user: User
    ) -> List[Dict[str, Any]]:
        """
        获取指定客户名下所有产品的分配历史（仅管理员）。

        按产品 ID、开始日期降序排列；每条记录附带产品与客户展示字段。

        Args:
            client_id: 客户 ID
            current_user: 当前用户

        Returns:
            分配记录字典列表
        """
        # 检查客户是否存在 - 使用selectinload预加载用户信息
        client_query = select(Client).options(selectinload(Client.user)).where(Client.id == client_id)
        client_result = await self.db.execute(client_query)
        client = client_result.scalars().first()

        if not client:
            raise_api_exception(
                ErrorCode.CLIENT_NOT_FOUND,
                detail=f"客户ID {client_id} 不存在"
            )

        # 查询该客户的所有分配记录，按产品ID和开始日期排序，同时关联用户信息
        query = select(ProductAssignment, Product, User).join(
            Product, ProductAssignment.product_id == Product.id
        ).join(
            Client, ProductAssignment.client_id == Client.id
        ).join(
            User, Client.user_id == User.id
        ).where(
            ProductAssignment.client_id == client_id
        ).order_by(Product.id, ProductAssignment.start_date.desc())

        result = await self.db.execute(query)
        assignments_data = result.all()

        # 转换为响应格式
        assignments_list = []
        for assignment, product, user in assignments_data:
            assignment_dict = {
                "id": assignment.id,
                "product_id": assignment.product_id,
                "client_id": assignment.client_id,
                "start_date": assignment.start_date,
                "end_date": assignment.end_date,
                "created_at": assignment.created_at,
                "updated_at": assignment.updated_at,
                "client_name": client.company_name,
                "company_name": client.company_name,
                "contact_person": client.contact_person,
                "phone": client.phone,
                "user_full_name": user.full_name if user else None
            }
            assignments_list.append(assignment_dict)

        return assignments_list

    async def validate_product_assignments(
            self,
            product_id: int,
            current_user: User
    ) -> Dict[str, Any]:
        """
        校验产品分配时间线连贯性（仅管理员）。

        委托 validate_product_assignments，检查重叠、空窗等问题。

        Args:
            product_id: 产品 ID
            current_user: 当前用户

        Returns:
            含 is_valid、errors、warnings 及计数的验证结果
        """
        # 检查产品是否存在
        product_query = select(Product).where(Product.id == product_id)
        product_result = await self.db.execute(product_query)
        product = product_result.scalars().first()

        if not product:
            raise_api_exception(
                ErrorCode.PRODUCT_NOT_FOUND,
                detail=f"产品ID {product_id} 不存在"
            )

        # 执行验证
        validation_result = await validate_product_assignments(self.db, product_id)

        # 构建响应
        is_valid = len(validation_result["errors"]) == 0
        return {
            "product_id": product_id,
            "product_name": product.name,
            "is_valid": is_valid,
            "errors": validation_result["errors"],
            "warnings": validation_result["warnings"],
            "error_count": len(validation_result["errors"]),
            "warning_count": len(validation_result["warnings"])
        }

    async def cleanup_product_assignments(
            self,
            product_id: int,
            current_user: User
    ) -> Dict[str, Any]:
        """
        清理指定产品的无效分配记录（仅管理员）。

        委托 cleanup_invalid_assignments，删除逻辑上不应存在的记录。

        Args:
            product_id: 产品 ID
            current_user: 当前用户

        Returns:
            含 deleted_count、deleted_records、errors 的清理结果
        """
        # 检查产品是否存在
        product_query = select(Product).where(Product.id == product_id)
        product_result = await self.db.execute(product_query)
        product = product_result.scalars().first()

        if not product:
            raise_api_exception(
                ErrorCode.PRODUCT_NOT_FOUND,
                detail=f"产品ID {product_id} 不存在"
            )

        # 执行清理
        cleanup_result = await cleanup_invalid_assignments(self.db, product_id)

        # 构建响应
        return {
            "product_id": product_id,
            "product_name": product.name,
            "deleted_count": cleanup_result["deleted_count"],
            "deleted_records": cleanup_result["deleted_records"],
            "errors": cleanup_result["errors"],
            "has_errors": len(cleanup_result["errors"]) > 0,
            "message": cleanup_result["message"]
        }

    async def cleanup_all_product_assignments(
            self,
            current_user: User
    ) -> Dict[str, Any]:
        """
        清理所有产品的分配记录中的无效数据（仅管理员）

        Args:
            current_user: 当前用户

        Returns:
            Dict: 清理结果
        """
        # 执行清理（product_id为None表示清理所有产品）
        cleanup_result = await cleanup_invalid_assignments(self.db, product_id=None)

        # 构建响应
        return {
            "deleted_count": cleanup_result["deleted_count"],
            "deleted_records": cleanup_result["deleted_records"],
            "errors": cleanup_result["errors"],
            "has_errors": len(cleanup_result["errors"]) > 0,
            "message": cleanup_result["message"]
        }

    async def update_assignment_dates(
            self,
            assignment_id: int,
            date_update: Dict[str, Any],
            current_user: User
    ) -> Dict[str, Any]:
        """
        更新单条分配记录的起止日期（仅管理员）。

        流程：基本日期校验 → flush → 全产品时间线 validate →
        通过则 commit 并返回关联信息，失败则 rollback。

        Args:
            assignment_id: 分配记录 ID
            date_update: 含 start_date / end_date 的字典
            current_user: 当前用户

        Returns:
            更新后的分配记录字典
        """

        # 查询分配记录
        query = select(ProductAssignment).where(ProductAssignment.id == assignment_id)
        result = await self.db.execute(query)
        assignment = result.scalars().first()

        if not assignment:
            raise_api_exception(
                ErrorCode.NOT_FOUND,
                detail=f"分配记录ID {assignment_id} 不存在"
            )

        # 锁定产品行，避免与并发创建/转移写出重叠区间
        await lock_product_for_assignment(self.db, assignment.product_id)

        # 保存原始值用于回滚
        original_start_date = assignment.start_date
        original_end_date = assignment.end_date

        # 准备更新的值
        new_start_date = date_update.get('start_date', assignment.start_date)
        new_end_date = date_update.get('end_date', assignment.end_date)

        # 基本验证：如果end_date不为None，必须满足 start_date <= end_date
        if new_end_date is not None and new_start_date > new_end_date:
            raise_api_exception(
                ErrorCode.VALIDATION_ERROR,
                detail=f"日期逻辑错误：开始日期（{new_start_date}）不能大于结束日期（{new_end_date}）"
            )

        # 更新分配记录
        assignment.start_date = new_start_date
        assignment.end_date = new_end_date
        await self.db.flush()
        invalidate_assignment_table_cache()

        # 验证更新后的分配记录连贯性
        try:
            # 执行验证
            validation_result = await validate_product_assignments(self.db, assignment.product_id)

            if validation_result["errors"]:
                # 验证失败：回滚更改
                await self.db.rollback()

                error_msg = "; ".join(validation_result["errors"])
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail=f"日期更新后验证失败：{error_msg}。请确保日期不重叠且无空窗期。"
                )

            # 验证通过，在提交前先查询关联信息
            query_with_relations = select(ProductAssignment, Client, Product, User).join(
                Client, ProductAssignment.client_id == Client.id
            ).join(
                Product, ProductAssignment.product_id == Product.id
            ).outerjoin(
                User, Client.user_id == User.id
            ).where(
                ProductAssignment.id == assignment_id
            )
            result_with_relations = await self.db.execute(query_with_relations)
            row = result_with_relations.first()

            if not row:
                await self.db.rollback()
                logger.error(f"更新分配记录 {assignment_id} 后无法查询到记录")
                raise_api_exception(
                    ErrorCode.INTERNAL_ERROR,
                    detail="更新后无法查询到记录"
                )

            # 解包查询结果
            assignment_with_relations, client, product, user = row

            # 构建响应数据
            assignment_dict = {
                "id": assignment_with_relations.id,
                "product_id": assignment_with_relations.product_id,
                "client_id": assignment_with_relations.client_id,
                "start_date": assignment_with_relations.start_date,
                "end_date": assignment_with_relations.end_date,
                "created_at": assignment_with_relations.created_at,
                "updated_at": assignment_with_relations.updated_at,
                "client_name": client.company_name if client else None,
                "company_name": client.company_name if client else None,
                "contact_person": client.contact_person if client else None,
                "phone": client.phone if client else None,
                "user_full_name": user.full_name if user else None
            }

            # 提交更改
            await self.db.flush()

            logger.info(
                f"管理员 {current_user.id} 更新了产品分配记录 {assignment_id} 的日期："
                f"开始日期 {original_start_date} -> {new_start_date}, "
                f"结束日期 {original_end_date or 'NULL'} -> {new_end_date or 'NULL'}"
            )

            return assignment_dict

        except HTTPException:
            raise
        except Exception as e:
            # 回滚更改
            try:
                await self.db.rollback()
            except Exception as rollback_error:
                logger.error(f"回滚事务时出错: {str(rollback_error)}", exc_info=True)

            # 如果是我们自己的API异常，直接重新抛出
            if isinstance(e, HTTPException):
                raise e

            # 其他异常，记录并返回错误
            logger.error(
                f"更新分配记录 {assignment_id} 日期时出错: {str(e)}",
                exc_info=True
            )
            raise_api_exception(
                ErrorCode.INTERNAL_ERROR,
                detail=f"更新日期时出错: {str(e)}"
            )

    async def batch_update_assignment_dates(
            self,
            updates: List[Dict[str, Any]],
            current_user: User
    ) -> Dict[str, Any]:
        """
        批量更新同一产品下多条分配记录的日期（仅管理员）。

        约束：所有 assignment_id 必须属于同一 product_id；
        全部 flush 后做一次产品级 validate，任一错误则整体回滚。

        Args:
            updates: 更新列表，每项含 assignment_id、start_date、end_date
            current_user: 当前用户

        Returns:
            含 updated_count、product_id、message 的结果字典
        """
        if not updates or len(updates) == 0:
            raise_api_exception(
                ErrorCode.VALIDATION_ERROR,
                detail="更新列表不能为空"
            )

        # 获取所有要更新的分配记录ID
        assignment_ids = [update['assignment_id'] for update in updates]

        # 查询所有要更新的分配记录
        query = select(ProductAssignment).where(ProductAssignment.id.in_(assignment_ids))
        result = await self.db.execute(query)
        assignments = result.scalars().all()

        if len(assignments) != len(assignment_ids):
            found_ids = {a.id for a in assignments}
            missing_ids = set(assignment_ids) - found_ids
            raise_api_exception(
                ErrorCode.NOT_FOUND,
                detail=f"以下分配记录ID不存在: {', '.join(map(str, missing_ids))}"
            )

        # 创建ID到记录的映射
        assignment_map = {a.id: a for a in assignments}

        # 校验并锁定同一产品，串行化并发日期变更
        product_id = assignments[0].product_id
        for assignment in assignments:
            if assignment.product_id != product_id:
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail="批量更新只能更新同一产品的分配记录"
                )
        await lock_product_for_assignment(self.db, product_id)

        # 保存原始值用于日志
        original_values = {}
        for assignment in assignments:
            original_values[assignment.id] = {
                'start_date': assignment.start_date,
                'end_date': assignment.end_date
            }

        # 应用所有更新（不提交）
        for update_item in updates:
            assignment = assignment_map[update_item['assignment_id']]

            new_start_date = update_item.get('start_date', assignment.start_date)
            new_end_date = update_item.get('end_date', assignment.end_date)

            # 基本验证：如果end_date不为None，必须满足 start_date <= end_date
            if new_end_date is not None and new_start_date > new_end_date:
                await self.db.rollback()
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail=f"记录ID {assignment.id}: 日期逻辑错误：开始日期（{new_start_date}）不能大于结束日期（{new_end_date}）"
                )

            # 更新分配记录
            assignment.start_date = new_start_date
            assignment.end_date = new_end_date

        # 刷新到数据库（但不提交）
        await self.db.flush()
        invalidate_assignment_table_cache()

        # 验证所有更新后的分配记录连贯性
        try:
            # 执行验证（验证整个产品的所有记录）
            validation_result = await validate_product_assignments(self.db, product_id)

            if validation_result["errors"]:
                # 验证失败：回滚所有更改
                await self.db.rollback()

                error_msg = "; ".join(validation_result["errors"])
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail=f"批量更新后验证失败：{error_msg}。请确保日期不重叠且无空窗期。"
                )

            # 验证通过，提交所有更改
            await self.db.flush()

            # 记录日志
            update_summary = []
            for update_item in updates:
                assignment_id = update_item['assignment_id']
                original = original_values[assignment_id]
                assignment = assignment_map[assignment_id]
                update_summary.append(
                    f"记录ID {assignment_id}: "
                    f"开始日期 {original['start_date']} -> {assignment.start_date}, "
                    f"结束日期 {original['end_date'] or 'NULL'} -> {assignment.end_date or 'NULL'}"
                )

            logger.info(
                f"管理员 {current_user.id} 批量更新了产品 {product_id} 的 {len(updates)} 条分配记录：\n" +
                "\n".join(update_summary)
            )

            return {
                "updated_count": len(updates),
                "product_id": product_id,
                "message": f"成功批量更新 {len(updates)} 条记录，时间连贯性验证通过"
            }

        except HTTPException:
            raise
        except Exception as e:
            # 回滚所有更改
            try:
                await self.db.rollback()
            except Exception as rollback_error:
                logger.error(f"回滚事务时出错: {str(rollback_error)}", exc_info=True)

            # 如果是我们自己的API异常，直接重新抛出
            if isinstance(e, HTTPException):
                raise e

            # 其他异常，记录并返回错误
            logger.error(
                f"批量更新分配记录日期时出错: {str(e)}",
                exc_info=True
            )
            raise_api_exception(
                ErrorCode.INTERNAL_ERROR,
                detail=f"批量更新分配记录日期时出错: {str(e)}"
            )
