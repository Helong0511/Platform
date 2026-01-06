"""
用户会话管理服务层
封装会话查询和撤销的业务逻辑
"""
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_

from app.models.models import User
from app.models.session import UserSession, TokenBlacklist
from app.services.base_service import BaseService
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.utils import get_app_now_naive
import logging

logger = logging.getLogger(__name__)


class SessionService:
    """用户会话服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_my_sessions(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 10
    ) -> Tuple[List[UserSession], int]:
        """
        获取当前用户的活跃会话列表

        Args:
            user_id: 用户ID
            page: 页码
            page_size: 每页数量

        Returns:
            Tuple[List[UserSession], int]: (会话列表, 总数)
        """
        # 构建查询（expires_at 存储的是北京时间，使用北京时间比较）
        now = get_app_now_naive()
        query = select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.expires_at > now  # 只返回未过期的会话
        )
        count_query = select(func.count(UserSession.id)).where(
            UserSession.user_id == user_id,
            UserSession.expires_at > now
        )

        # 获取总数
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # 应用分页和排序
        query = query.order_by(UserSession.last_activity.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        # 执行查询
        result = await self.db.execute(query)
        sessions = result.scalars().all()

        return sessions, total

    async def revoke_my_session(
        self,
        session_id: int,
        user_id: int,
        current_user: User
    ) -> None:
        """
        撤销当前用户的指定会话

        Args:
            session_id: 会话ID
            user_id: 用户ID
            current_user: 当前用户
        """
        # 查询会话
        result = await self.db.execute(
            select(UserSession).where(
                UserSession.id == session_id,
                UserSession.user_id == user_id
            )
        )
        session = result.scalars().first()

        if not session:
            raise_api_exception(
                ErrorCode.NOT_FOUND,
                detail="会话不存在或不属于当前用户"
            )

        # 将token加入黑名单
        blacklist_entry = TokenBlacklist(
            token_jti=session.token_jti,
            user_id=user_id,
            expires_at=session.expires_at,
            reason="用户主动撤销会话"
        )
        self.db.add(blacklist_entry)

        # 标记会话为非活跃
        session.is_active = False

        try:
            await self.db.commit()
            logger.info(f"用户 {user_id} 撤销了会话 {session_id}")
        except Exception as e:
            await self.db.rollback()
            logger.error(f"撤销会话失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"撤销会话失败: {str(e)}"
            )

    async def revoke_all_my_sessions(
        self,
        user_id: int,
        current_jti: Optional[str],
        current_user: User
    ) -> int:
        """
        撤销当前用户的所有其他会话（保留当前会话）

        Args:
            user_id: 用户ID
            current_jti: 当前token的jti（用于排除当前会话）
            current_user: 当前用户

        Returns:
            int: 撤销的会话数量
        """
        # 查询所有其他活跃会话
        query = select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.is_active == True,
            UserSession.expires_at > get_app_now_naive()  # 使用北京时间比较
        )
        if current_jti:
            query = query.where(UserSession.token_jti != current_jti)

        result = await self.db.execute(query)
        sessions = result.scalars().all()

        revoked_count = 0
        for session in sessions:
            # 将token加入黑名单
            blacklist_entry = TokenBlacklist(
                token_jti=session.token_jti,
                user_id=user_id,
                expires_at=session.expires_at,
                reason="用户撤销所有其他会话"
            )
            self.db.add(blacklist_entry)

            # 标记会话为非活跃
            session.is_active = False
            revoked_count += 1

        try:
            await self.db.commit()
            logger.info(f"用户 {user_id} 撤销了 {revoked_count} 个其他会话")
        except Exception as e:
            await self.db.rollback()
            logger.error(f"撤销所有其他会话失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"撤销所有其他会话失败: {str(e)}"
            )

        return revoked_count

    async def get_user_sessions(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 10
    ) -> Tuple[List[UserSession], int]:
        """
        获取指定用户的活跃会话列表（仅管理员）

        Args:
            user_id: 用户ID
            page: 页码
            page_size: 每页数量

        Returns:
            Tuple[List[UserSession], int]: (会话列表, 总数)
        """
        # 先检查用户是否存在
        user_result = await self.db.execute(select(User.id).where(User.id == user_id))
        user_exists = user_result.scalar() is not None

        if not user_exists:
            raise_api_exception(
                ErrorCode.USER_NOT_FOUND,
                detail=f"用户ID {user_id} 不存在"
            )

        # 构建查询
        query = select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.expires_at > get_app_now_naive()  # 使用北京时间比较
        )
        count_query = select(func.count(UserSession.id)).where(
            UserSession.user_id == user_id,
            UserSession.expires_at > get_app_now_naive()  # 使用北京时间比较
        )

        # 获取总数
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # 应用分页和排序
        query = query.order_by(UserSession.last_activity.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        # 执行查询
        result = await self.db.execute(query)
        sessions = result.scalars().all()

        return sessions, total

    async def revoke_user_session(
        self,
        user_id: int,
        session_id: int,
        current_user: User
    ) -> None:
        """
        撤销指定用户的指定会话（仅管理员）

        Args:
            user_id: 用户ID
            session_id: 会话ID
            current_user: 当前用户（管理员）
        """
        # 查询会话
        result = await self.db.execute(
            select(UserSession).where(
                UserSession.id == session_id,
                UserSession.user_id == user_id
            )
        )
        session = result.scalars().first()

        if not session:
            raise_api_exception(
                ErrorCode.NOT_FOUND,
                detail="会话不存在"
            )

        # 将token加入黑名单
        blacklist_entry = TokenBlacklist(
            token_jti=session.token_jti,
            user_id=user_id,
            expires_at=session.expires_at,
            reason=f"管理员 {current_user.username} 强制撤销"
        )
        self.db.add(blacklist_entry)

        # 标记会话为非活跃
        session.is_active = False

        try:
            await self.db.commit()
            logger.info(f"管理员 {current_user.id} 撤销了用户 {user_id} 的会话 {session_id}")
        except Exception as e:
            await self.db.rollback()
            logger.error(f"撤销用户会话失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"撤销用户会话失败: {str(e)}"
            )

    async def revoke_all_user_sessions(
        self,
        user_id: int,
        current_user: User
    ) -> Tuple[int, str]:
        """
        撤销指定用户的所有会话（仅管理员）

        Args:
            user_id: 用户ID
            current_user: 当前用户（管理员）

        Returns:
            Tuple[int, str]: (撤销的会话数量, 用户名)
        """
        # 检查用户是否存在
        user_result = await self.db.execute(select(User).where(User.id == user_id))
        user = user_result.scalars().first()

        if not user:
            raise_api_exception(
                ErrorCode.USER_NOT_FOUND,
                detail=f"用户ID {user_id} 不存在"
            )

        # 查询所有活跃会话
        query = select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.is_active == True,
            UserSession.expires_at > get_app_now_naive()  # 使用北京时间比较
        )

        result = await self.db.execute(query)
        sessions = result.scalars().all()

        revoked_count = 0
        for session in sessions:
            # 将token加入黑名单
            blacklist_entry = TokenBlacklist(
                token_jti=session.token_jti,
                user_id=user_id,
                expires_at=session.expires_at,
                reason=f"管理员 {current_user.username} 强制撤销所有会话"
            )
            self.db.add(blacklist_entry)

            # 标记会话为非活跃
            session.is_active = False
            revoked_count += 1

        try:
            await self.db.commit()
            logger.info(f"管理员 {current_user.id} 撤销了用户 {user.username} 的 {revoked_count} 个会话")
        except Exception as e:
            await self.db.rollback()
            logger.error(f"撤销用户所有会话失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"撤销用户所有会话失败: {str(e)}"
            )

        return revoked_count, user.username

