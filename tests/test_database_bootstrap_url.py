"""旧数据库引导入口的 fail-closed 回归测试。"""

import pytest

from app.db.database import create_database


@pytest.mark.asyncio
async def test_legacy_create_database_entrypoint_fails_closed():
    """旧 helper 必须 fail-closed，不得再使用应用 DSN 建库。"""
    with pytest.raises(RuntimeError, match="禁止通过应用数据库连接创建数据库"):
        await create_database()
