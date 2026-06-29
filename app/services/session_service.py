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
from datetime import datetime, timedelta
import logging
from typing import Iterable, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.utils import get_app_now_naive
from app.models.models import User
from app.models.session import UserSession, TokenBlacklist

logger = logging.getLogger(__name__)


class TokenReuseError(Exception):
    """令牌已被轮换或撤销，不可重复使用。"""


def collect_tokens_from_request(
    request,
    extra_tokens: Optional[Iterable[str]] = None,
) -> list[str]:
    """从 Cookie、Authorization Bearer 及额外参数收集待撤销令牌（去重保序）。"""
    seen: set[str] = set()
    tokens: list[str] = []

    def _add(raw: Optional[str]) -> None:
        value = (raw or "").strip()
        if value and value not in seen:
            seen.add(value)
            tokens.append(value)

    for cookie_name in ("access_token", "refresh_token"):
        _add(request.cookies.get(cookie_name))

    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        _add(authorization[7:])

    if extra_tokens:
        for item in extra_tokens:
            _add(item)

    return tokens


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


async def _blacklist_single_token(
    db: AsyncSession,
    user_id: int,
    token: str,
    reason: str,
    *,
    require_fresh: bool = False,
    flush_immediately: bool = False,
) -> None:
    """将单个 JWT 写入黑名单并失效对应会话。"""
    from datetime import timezone

    from app.core.jwt_codec import decode_token_payload
    from app.core.utils import APP_TIMEZONE, get_app_now_naive

    payload = decode_token_payload(token, verify_exp=False)
    jti = payload.get("jti")
    if not jti:
        return

    jti_str = str(jti)
    existing = await db.execute(
        select(TokenBlacklist).where(TokenBlacklist.token_jti == jti_str)
    )
    if existing.scalars().first():
        if require_fresh:
            raise TokenReuseError("刷新令牌已被使用")
        return

    exp_ts = payload.get("exp")
    if exp_ts:
        expires_at = (
            datetime.fromtimestamp(exp_ts, tz=timezone.utc)
            .astimezone(APP_TIMEZONE)
            .replace(tzinfo=None)
        )
    else:
        expires_at = get_app_now_naive()

    db.add(
        TokenBlacklist(
            token_jti=jti_str,
            user_id=user_id,
            expires_at=expires_at,
            reason=reason,
        )
    )

    session_result = await db.execute(
        select(UserSession).where(UserSession.token_jti == jti_str)
    )
    session = session_result.scalars().first()
    if session:
        session.is_active = False

    if flush_immediately:
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            if require_fresh:
                raise TokenReuseError("刷新令牌已被使用") from exc
            logger.warning("令牌黑名单写入冲突（已撤销）: jti=%s", jti_str)


async def revoke_tokens_from_request(
    db: AsyncSession,
    request,
    user_id: int,
    reason: str,
    extra_tokens: Optional[Iterable[str]] = None,
    *,
    consume_refresh_token: Optional[str] = None,
) -> None:
    """
    将请求中的 access/refresh 令牌加入黑名单并失效对应会话。

    收集来源：HttpOnly Cookie、Authorization Bearer、extra_tokens。
    consume_refresh_token：刷新轮换时原子消费 refresh（并发重复刷新会抛 TokenReuseError）。
    """
    consumed = (consume_refresh_token or "").strip()
    if consumed:
        await _blacklist_single_token(
            db,
            user_id,
            consumed,
            reason,
            require_fresh=True,
            flush_immediately=True,
        )

    for token in collect_tokens_from_request(request, extra_tokens):
        if consumed and token == consumed:
            continue
        try:
            await _blacklist_single_token(db, user_id, token, reason)
        except TokenReuseError:
            raise
        except Exception as exc:
            logger.warning("撤销令牌失败: %s", exc)


async def record_access_token_session(
    db: AsyncSession,
    *,
    user_id: int,
    access_token: str,
    request,
    access_token_expires: timedelta,
) -> None:
    """登录或刷新成功后，将新 access_token 的 jti 写入活跃会话表。"""
    from datetime import timezone

    from app.core.jwt_codec import decode_token_payload
    from app.core.utils import APP_TIMEZONE, get_app_now_naive, get_client_ip, get_device_type

    try:
        payload = decode_token_payload(access_token, verify_exp=False)
        token_jti = payload.get("jti")
        if not token_jti:
            return

        expires_at_utc = datetime.now(timezone.utc) + access_token_expires
        expires_at = expires_at_utc.astimezone(APP_TIMEZONE).replace(tzinfo=None)

        db.add(
            UserSession(
                user_id=user_id,
                token_jti=str(token_jti),
                ip_address=get_client_ip(request),
                user_agent=(request.headers.get("User-Agent") or "")[:500],
                device_info=get_device_type(request),
                is_active=True,
                last_activity=get_app_now_naive(),
                expires_at=expires_at,
            )
        )
    except Exception as exc:
        logger.warning("记录会话信息失败: %s", exc)
