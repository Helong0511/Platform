"""密码哈希渐进升级服务。"""
from __future__ import annotations

from sqlalchemy import LargeBinary, cast, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def upgrade_password_hash_after_login(
    db: AsyncSession,
    user: User,
    password: str,
) -> bool:
    """登录验证成功后，以比较并交换方式升级旧哈希，避免覆盖并发密码修改。

    超过 bcrypt 72 字节的历史密码由模型策略决定暂不升级，以保留旧验证语义。
    UPDATE 条件同时约束 user_id 和原哈希；若期间密码已被修改，本次升级不生效。
    """
    if not user.needs_password_rehash(password):
        return False

    previous_hash = user.hashed_password
    replacement_hash = user.get_password_hash(password)
    result = await db.execute(
        update(User)
        .where(
            User.id == user.id,
            cast(User.hashed_password, LargeBinary) == previous_hash.encode("utf-8"),
        )
        .values(hashed_password=replacement_hash)
        .execution_options(synchronize_session=False)
    )
    return getattr(result, "rowcount", 0) == 1
