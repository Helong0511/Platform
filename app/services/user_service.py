"""
用户服务层。

功能说明：
- 用户 CRUD、分页列表与统计（按角色过滤可见范围）
- 创建用户时可同事务创建关联 Client（company_name 等字段）
- 密码修改、用户名/邮箱唯一性校验；变更后失效权限缓存

权限模型：
- 管理员全量；普通用户仅可操作自身，且不可自行降级管理员角色

在系统中的位置：
- 被管理端用户 API 与认证模块调用；写操作记录审计日志

注意事项：
1. 密码经模型 ``set_password`` bcrypt 加密，服务层勿存明文
2. 禁用用户须同步撤销活跃会话，防止旧 token 继续使用
3. 写操作后失效 ``user_stats`` 缓存，保证管理端统计及时
"""
from typing import Optional, List, Dict, Any
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, or_, and_
from sqlalchemy.orm import selectinload

from app.models.models import User, Client, UserRole, Publisher
from app.services.base_service import BaseService
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.async_orm import get_first_loaded_collection_item
from app.core.audit_log import log_user_action, commit_audit_log
from app.core.utils import get_app_now_naive
from app.core.validation import validate_password_strength
from app.core.permission_cache import invalidate_user_permission_cache
from app.core.infrastructure.cache import get_cache_backend
from app.services.session_service import SessionService
import logging

logger = logging.getLogger(__name__)


class UserService(BaseService[User]):
    """
    用户服务。

    基于 BaseService/仓储层分页查询；写操作后调用 invalidate_user_permission_cache
    保证权限缓存与库表一致。
    """

    def __init__(self, db: AsyncSession):
        """注入数据库会话并绑定 User 模型。"""
        super().__init__(db, User)

    @staticmethod
    async def invalidate_user_stats_cache() -> None:
        """写用户后失效管理端统计缓存。"""
        try:
            cache = await get_cache_backend()
            await cache.delete("user_stats")
        except Exception as e:
            logger.warning("清除 user_stats 缓存失败: error_type=%s", type(e).__name__)

    async def _revoke_sessions_on_disable(
            self,
            user_id: int,
            current_user: User,
    ) -> None:
        """禁用用户时撤销其全部活跃会话并拉黑 JWT。"""
        try:
            session_service = SessionService(self.db)
            revoked_count, username = await session_service.revoke_all_user_sessions(
                user_id, current_user
            )
            logger.info(
                "用户禁用同步撤会话: user_id=%s, username=%s, revoked=%s",
                user_id,
                username,
                revoked_count,
            )
        except Exception as e:
            logger.error(
                "禁用用户时撤销会话失败: user_id=%s error_type=%s",
                user_id,
                type(e).__name__,
            )

    async def get_user_by_id(
            self,
            user_id: int,
            current_user: User,
            include_client: bool = True
    ) -> User:
        """
        按 ID 获取用户详情。

        非管理员只能查询 user_id == current_user.id。

        Args:
            user_id: 用户主键
            current_user: 当前用户
            include_client: 是否预加载 clients 关联

        Returns:
            User 实体
        """
        # 读权限：本人或管理员
        self.require_owner_or_admin(current_user, user_id)

        # 通过仓储层获取数据
        load_relations = ["clients"] if include_client else None
        user = await self.repository.get_by_id(user_id, load_relations=load_relations)

        if not user:
            raise_api_exception(
                ErrorCode.USER_NOT_FOUND,
                detail=f"用户ID {user_id} 不存在"
            )

        return user

    async def get_users(
            self,
            current_user: User,
            page: int = 1,
            page_size: int = 10,
            username: Optional[str] = None,
            role: Optional[str] = None,
            is_active: Optional[bool] = None,
            search: Optional[str] = None
    ) -> tuple[List[User], int]:
        """
        分页获取用户列表（仅管理员）。

        支持 username/role/is_active 及 search 关键词（用户名、全名、邮箱）。

        Args:
            current_user: 当前用户（须为管理员）
            page: 页码
            page_size: 每页条数
            username: 用户名过滤（与 search 合并为搜索词）
            role: 角色字符串过滤
            is_active: 激活状态
            search: 通用搜索关键词

        Returns:
            (用户列表, 总条数)
        """
        # 权限检查：仅管理员可查看所有用户
        self.require_admin(current_user)

        # 构建过滤条件
        filters = {}
        if is_active is not None:
            filters["is_active"] = is_active

        if role:
            try:
                role_enum = UserRole(role)
                filters["role"] = role_enum
            except ValueError:
                pass  # 无效的角色值，忽略

        # 使用仓储层的分页查询（通过查询构建器）
        # 如果提供了username，使用search参数；否则使用search参数（如果提供）
        search_keyword = username or search

        return await self.repository.paginated(
            page=page,
            page_size=page_size,
            filters=filters,
            search_fields=["username", "full_name", "email"],
            search_keyword=search_keyword,
            order_by="created_at",
            desc_order=True,
            load_relations=["clients"]  # 预加载客户信息，避免N+1查询
        )

    async def create_user(
            self,
            user_data: Dict[str, Any],
            current_user: User
    ) -> User:
        """
        创建用户，可选同事务创建 Client。

        流程：唯一性校验 → 建 User → flush → 若有 company_name 则建 Client → commit → 清权限缓存。

        Args:
            user_data: 用户字段；可含 company_name/contact_person 等客户字段
            current_user: 当前管理员

        Returns:
            User（若创建了 Client 则含 clients 关联）
        """
        # --- 唯一性：用户名必填唯一，邮箱可选唯一 ---
        self.require_admin(current_user)

        conditions = [User.username == user_data['username']]
        if user_data.get('email'):
            conditions.append(User.email == user_data['email'])

        existing_users_result = await self.db.execute(
            select(User).where(or_(*conditions))
        )
        existing_users = existing_users_result.scalars().all()

        # 检查用户名是否已存在
        username_exists = any(u.username == user_data['username'] for u in existing_users)
        if username_exists:
            raise_api_exception(
                ErrorCode.USERNAME_TAKEN,
                detail=f"用户名 '{user_data['username']}' 已被使用，请选择其他用户名"
            )

        # 验证邮箱唯一性（如果提供）
        if user_data.get('email'):
            email_exists = any(u.email == user_data['email'] for u in existing_users)
            if email_exists:
                raise_api_exception(
                    ErrorCode.EMAIL_TAKEN,
                    detail=f"邮箱 '{user_data['email']}' 已被使用，请使用其他邮箱地址"
                )

        # --- 持久化 User ---
        user = User(
            username=user_data['username'],
            email=user_data.get('email'),
            full_name=user_data.get('full_name'),
            role=UserRole(user_data.get('role', 'client')) if isinstance(user_data.get('role'), str) else user_data.get(
                'role', UserRole.CLIENT),
            is_active=user_data.get('is_active', True),
            login_restricted=user_data.get('login_restricted', False),
            login_message=user_data.get('login_message')
        )

        # 设置密码
        if 'password' in user_data:
            user.set_password(user_data['password'])

        self.db.add(user)
        await self.db.flush()  # 先 flush 以获取 user.id

        # --- 可选：同一事务内创建 Client（一用户通常对应一个客户主体）---
        if user_data.get('company_name'):
            # 检查该用户是否已有客户关联
            client_count = await self.db.execute(
                select(func.count(Client.id)).where(Client.user_id == user.id)
            )
            if (client_count.scalar() or 0) > 0:
                logger.warning(f"User {user.username} already has a client associated")
            else:
                # 创建客户对象
                client = Client(
                    user_id=user.id,
                    key=str(uuid.uuid4()),
                    company_name=user_data['company_name'],
                    contact_person=user_data.get('contact_person'),
                    phone=user_data.get('phone'),
                    address=user_data.get('address'),
                    is_active=user_data.get('is_active', True)
                )
                self.db.add(client)
                await self.db.flush()

        await self.db.flush()

        # 若创建了客户，重新加载用户以包含客户信息（避免异步懒加载）
        if user_data.get('company_name'):
            user_query = select(User).options(selectinload(User.clients)).where(User.id == user.id)
            user_result = await self.db.execute(user_query)
            # selectinload不会产生重复行，但为了安全起见使用unique()
            user = user_result.unique().scalars().first()

        # 清除权限缓存（新用户创建）
        try:
            await invalidate_user_permission_cache(user.id)
        except Exception as e:
            logger.warning("清除权限缓存失败: error_type=%s", type(e).__name__)

        await self.invalidate_user_stats_cache()

        logger.info(f"用户已创建: {user.username} (ID: {user.id})")
        return user

    async def update_user(
            self,
            user_id: int,
            user_data: Dict[str, Any],
            current_user: User
    ) -> User:
        """
        更新用户信息。

        非管理员不可改 role；管理员不可将自己降为非 admin。
        修改 username/email/password 时分别做唯一性与强度校验。

        Args:
            user_id: 目标用户 ID
            user_data: 待更新字段
            current_user: 当前用户

        Returns:
            更新后的 User
        """
        # 获取用户
        user = await self.get_user_by_id(user_id, current_user, include_client=False)
        old_is_active = user.is_active

        # 非管理员：剥离 role，且只能改自己
        if current_user.role != UserRole.ADMIN:
            if current_user.id != user_id:
                raise_api_exception(
                    ErrorCode.FORBIDDEN,
                    detail="您只能修改自己的信息"
                )
            # 客户不能修改角色
            if 'role' in user_data:
                del user_data['role']

        # 验证用户名唯一性（如果修改）
        if 'username' in user_data and user_data['username'] != user.username:
            existing_user = await self.db.execute(
                select(User).where(User.username == user_data['username'])
            )
            if existing_user.scalar_one_or_none():
                raise_api_exception(
                    ErrorCode.USER_ALREADY_EXISTS,
                    detail=f"用户名 {user_data['username']} 已存在"
                )
            user.username = user_data['username']

        # 验证邮箱唯一性（如果修改）
        if 'email' in user_data and user_data['email'] != user.email:
            if user_data['email']:
                existing_email = await self.db.execute(
                    select(User).where(User.email == user_data['email'])
                )
                if existing_email.scalar_one_or_none():
                    raise_api_exception(
                        ErrorCode.EMAIL_TAKEN,
                        detail=f"邮箱 '{user_data['email']}' 已被使用，请使用其他邮箱地址"
                    )
            user.email = user_data.get('email')

        # 防止修改自己为非管理员
        if user.id == current_user.id and 'role' in user_data:
            role_value = user_data['role']
            if isinstance(role_value, str):
                role_value = UserRole(role_value)
            if role_value != UserRole.ADMIN:
                raise_api_exception(
                    ErrorCode.CANNOT_MODIFY_SELF_ROLE,
                    detail="不能将自己的角色修改为非管理员。如需修改角色，请联系其他管理员操作"
                )

        # 如果更新密码
        if 'password' in user_data and user_data['password']:
            user.set_password(user_data['password'])
            del user_data['password']

        # 处理 role 字段（如果是字符串，需要转换为枚举）
        if 'role' in user_data and user_data['role']:
            role_value = user_data['role']
            if isinstance(role_value, str):
                try:
                    user_data['role'] = UserRole(role_value)
                except ValueError:
                    raise_api_exception(
                        ErrorCode.VALIDATION_ERROR,
                        detail=f"无效的角色值：{role_value}。支持的角色：admin, client"
                    )

        # 更新其他字段
        for key, value in user_data.items():
            if hasattr(user, key):
                setattr(user, key, value)

        await self.db.flush()

        user = await self.get_user_by_id(user_id, current_user, include_client=False)

        # 禁用时同步撤销活跃会话（与模块注释约定一致）
        if old_is_active and not user.is_active:
            await self._revoke_sessions_on_disable(user_id, current_user)

        # 清除权限缓存（用户信息已更新）
        try:
            await invalidate_user_permission_cache(user_id)
        except Exception as e:
            logger.warning("清除权限缓存失败: error_type=%s", type(e).__name__)

        await self.invalidate_user_stats_cache()

        logger.info(f"用户已更新: {user.username} (ID: {user.id})")
        return user

    async def delete_user(
            self,
            user_id: int,
            current_user: User
    ) -> None:
        """
        删除用户（仅管理员）。

        若用户仍有关联 Client 则拒绝删除，避免孤儿业务数据。

        Args:
            user_id: 目标用户 ID
            current_user: 当前管理员
        """
        # 权限检查
        self.require_admin(current_user)

        # 获取用户
        user = await self.get_user_by_id(user_id, current_user, include_client=True)

        # 检查是否有关联的客户
        client = get_first_loaded_collection_item(user, "clients")
        if client:
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"用户 {user.username} 有关联的客户数据，无法删除"
            )

        # 删除用户
        await self.db.delete(user)
        await self.db.flush()

        # 清除权限缓存（用户已删除）
        try:
            await invalidate_user_permission_cache(user_id)
        except Exception as e:
            logger.warning("清除权限缓存失败: error_type=%s", type(e).__name__)

        await self.invalidate_user_stats_cache()

        logger.info(f"用户已删除: {user.username} (ID: {user_id})")

    async def change_password(
            self,
            user_id: int,
            old_password: str,
            new_password: str,
            current_user: User
    ) -> None:
        """
        修改密码。

        规则摘要：
        - 非管理员只能改自己的密码
        - CLIENT 角色需 client.password_change_enabled
        - 管理员改他人密码可跳过旧密码校验
        - 新密码须通过强度校验且不同于当前密码

        Args:
            user_id: 目标用户 ID
            old_password: 旧密码
            new_password: 新密码
            current_user: 当前用户
        """
        # 获取用户（包含客户信息，用于检查password_change_enabled）
        user = await self.get_user_by_id(user_id, current_user, include_client=True)

        # 权限检查：非管理员只能修改自己的密码
        if current_user.role != UserRole.ADMIN:
            if current_user.id != user_id:
                raise_api_exception(
                    ErrorCode.FORBIDDEN,
                    detail="您只能修改自己的密码"
                )

            # 如果是客户角色，检查是否允许修改密码
            if user.role == UserRole.CLIENT:
                client = get_first_loaded_collection_item(user, "clients")
                if client and not client.password_change_enabled:
                    raise_api_exception(
                        ErrorCode.FORBIDDEN,
                        detail="客户密码修改功能已被管理员禁用，请联系管理员修改密码"
                    )

        # 验证旧密码（管理员修改他人密码时不需要验证旧密码）
        if current_user.role != UserRole.ADMIN or current_user.id == user_id:
            if not user.verify_password(old_password):
                raise_api_exception(
                    ErrorCode.INVALID_CREDENTIALS,
                    detail="当前密码不正确，请重新输入"
                )

        # 验证新密码强度
        is_valid, error_msg = validate_password_strength(new_password)
        if not is_valid:
            raise_api_exception(
                ErrorCode.VALIDATION_ERROR,
                detail=f"新密码验证失败：{error_msg}"
            )

        # 检查新密码是否与当前密码相同
        if user.verify_password(new_password):
            raise_api_exception(
                ErrorCode.VALIDATION_ERROR,
                detail="新密码不能与当前密码相同"
            )

        # 设置新密码
        user.set_password(new_password)
        await self.db.flush()

        # 改密后吊销该用户全部活跃会话（含 Redis/MySQL jti 黑名单）
        try:
            from app.services.session_service import SessionService

            session_svc = SessionService(self.db)
            revoked, _ = await session_svc.revoke_all_user_sessions(user_id, current_user)
            logger.info(
                "用户改密后已吊销会话: user_id=%s revoked=%s",
                user_id,
                revoked,
            )
        except Exception as revoke_exc:
            logger.warning("改密后吊销会话失败（密码已更新）: error_type=%s", type(revoke_exc).__name__)

        # 记录审计日志
        await log_user_action(
            db=self.db,
            action_type="UPDATE",
            user=current_user,
            username=current_user.username,
            resource_type="USER",
            resource_id=user.id,
            resource_name=user.username,
            success=True,
            details={"action": "change_password"}
        )
        await commit_audit_log(self.db)

        logger.info(f"用户密码已修改: {user.username} (ID: {user_id})")

    async def get_user_stats(self) -> Dict[str, Any]:
        """
        汇总用户数量统计（Dashboard 等）。

        Returns:
            total_users、by_role、by_status、with_client_info 等聚合字段
        """
        # 总量与分角色/分状态计数
        total_result = await self.db.execute(select(func.count(User.id)))
        total_users = total_result.scalar() or 0

        # 按角色统计
        admin_result = await self.db.execute(
            select(func.count(User.id)).where(User.role == UserRole.ADMIN)
        )
        admin_count = admin_result.scalar() or 0

        client_result = await self.db.execute(
            select(func.count(User.id)).where(User.role == UserRole.CLIENT)
        )
        client_count = client_result.scalar() or 0

        # 按状态统计
        active_result = await self.db.execute(
            select(func.count(User.id)).where(User.is_active == True)
        )
        active_count = active_result.scalar() or 0

        inactive_result = await self.db.execute(
            select(func.count(User.id)).where(User.is_active == False)
        )
        inactive_count = inactive_result.scalar() or 0

        # 有客户信息的用户数
        client_users_result = await self.db.execute(
            select(func.count(func.distinct(Client.user_id)))
        )
        client_users_count = client_users_result.scalar() or 0

        return {
            "total_users": total_users,
            "by_role": {
                "admin": admin_count,
                "client": client_count
            },
            "by_status": {
                "active": active_count,
                "inactive": inactive_count
            },
            "with_client_info": client_users_count
        }

    async def check_client_has_publisher(self, client_id: int) -> bool:
        """
        判断客户是否至少有一个激活中的渠道（Publisher）。

        用于业务侧「客户是否已配置下游渠道」类校验。

        Args:
            client_id: 客户 ID

        Returns:
            True 表示存在 is_active 的 Publisher
        """
        publisher_result = await self.db.execute(
            select(func.count(Publisher.id)).where(
                and_(
                    Publisher.client_id == client_id,
                    Publisher.is_active == True
                )
            )
        )
        publisher_count = publisher_result.scalar() or 0
        return publisher_count > 0
