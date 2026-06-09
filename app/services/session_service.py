"""
用户会话管理服务层。

功能说明：
- 查询当前用户或指定用户的活跃会话（未过期、is_active=True）
- 撤销单个/批量会话：JWT jti 写入 ``TokenBlacklist`` 且 ``UserSession.is_active=False``

撤销策略：
- 双写保证已签发 token 立即失效，即使用户未主动登出
- ``expires_at`` 比较统一使用 ``get_app_now_naive()``（北京时间）

在系统中的位置：
- 被管理端会话管理 API 与认证流程调用

注意事项：
1. 批量撤销管理员会话时须防止把自己踢下线（API 层通常排除当前 jti）
2. 过期会话清理由 ``cleanup_expired_sessions`` 定时任务物理删除
"""
import logging
from typing import Optional, List, Tuple

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.utils import get_app_now_naive
from app.models.models import User
from app.models.session import UserSession, TokenBlacklist

logger = logging.getLogger(__name__)


class SessionService:
    """
    用户会话服务。

    面向两类调用方：
    - 用户自助：查看/撤销自己的会话，批量撤销时可保留当前 token（current_jti）
    - 管理员：查看/强制撤销任意用户的会话
    """

    def __init__(self, db: AsyncSession):
        """注入异步数据库会话。"""
        self.db = db

    async def get_my_sessions(
            self,
            user_id: int,
            page: int = 1,
            page_size: int = 10
    ) -> Tuple[List[UserSession], int]:
        """
        获取当前用户的活跃会话列表（仅未过期）。

        Args:
            user_id: 用户 ID
            page: 页码（从 1 开始）
            page_size: 每页条数

        Returns:
            (会话列表, 总条数)；按 last_activity 降序
        """
        # 活跃会话：expires_at 存应用时区 naive 时间
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
        撤销当前用户的指定会话。

        校验会话归属后写入黑名单并标记为非活跃；提交失败时回滚并抛出 OPERATION_FAILED。

        Args:
            session_id: 会话主键
            user_id: 当前用户 ID（须与会话 user_id 一致）
            current_user: 当前用户实体（预留审计扩展）
        """
        # 归属校验：仅能撤销自己的会话
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

        # 撤销双写：黑名单使 JWT 失效，is_active 便于列表过滤
        blacklist_entry = TokenBlacklist(
            token_jti=session.token_jti,
            user_id=user_id,
            expires_at=session.expires_at,
            reason="用户主动撤销会话"
        )
        self.db.add(blacklist_entry)
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
        撤销当前用户除当前 token 外的全部活跃会话。

        通过 current_jti 排除本端会话，避免用户把自己踢下线。

        Args:
            user_id: 用户 ID
            current_jti: 当前 JWT 的 jti；为 None 时撤销该用户全部活跃会话
            current_user: 当前用户实体

        Returns:
            成功撤销的会话数量
        """
        # 筛选：活跃且未过期，可选排除 current_jti
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
        管理员查看指定用户的活跃会话列表。

        用户不存在时抛出 USER_NOT_FOUND；查询条件与 get_my_sessions 一致。

        Args:
            user_id: 目标用户 ID
            page: 页码
            page_size: 每页条数

        Returns:
            (会话列表, 总条数)
        """
        # 前置校验：避免对无效 user_id 做无意义分页查询
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
        管理员强制撤销指定用户的单个会话。

        黑名单 reason 记录操作管理员用户名，便于审计追溯。

        Args:
            user_id: 目标用户 ID
            session_id: 会话主键
            current_user: 执行操作的管理员
        """
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

        # 撤销双写（管理员强制下线）
        blacklist_entry = TokenBlacklist(
            token_jti=session.token_jti,
            user_id=user_id,
            expires_at=session.expires_at,
            reason=f"管理员 {current_user.username} 强制撤销"
        )
        self.db.add(blacklist_entry)
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
        管理员强制撤销指定用户的全部活跃会话。

        Args:
            user_id: 目标用户 ID
            current_user: 执行操作的管理员

        Returns:
            (撤销数量, 被操作用户名)
        """
        # 加载用户实体以返回 username，并确认用户存在
        user_result = await self.db.execute(select(User).where(User.id == user_id))
        user = user_result.scalars().first()

        if not user:
            raise_api_exception(
                ErrorCode.USER_NOT_FOUND,
                detail=f"用户ID {user_id} 不存在"
            )

        # 批量撤销该用户全部活跃会话
        query = select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.is_active == True,
            UserSession.expires_at > get_app_now_naive()  # 使用北京时间比较
        )

        result = await self.db.execute(query)
        sessions = result.scalars().all()

        revoked_count = 0
        for session in sessions:
            blacklist_entry = TokenBlacklist(
                token_jti=session.token_jti,
                user_id=user_id,
                expires_at=session.expires_at,
                reason=f"管理员 {current_user.username} 强制撤销所有会话"
            )
            self.db.add(blacklist_entry)
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
