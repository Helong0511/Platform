"""测试进程级异步资源清理。

应用使用模块级 SQLAlchemy AsyncEngine；pytest 默认逐测试关闭事件循环，
会令尚未释放的 aiosqlite worker thread 在后续 loop 关闭后回调。
所有异步测试共用 session loop，并在整个测试会话结束时显式 dispose engine。
"""
import pytest_asyncio

from app.core.database import engine


@pytest_asyncio.fixture(scope="session", autouse=True)
async def dispose_shared_async_database_engine():
    yield
    await engine.dispose()
