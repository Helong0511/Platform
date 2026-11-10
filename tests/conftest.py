"""每个测试完成后的异步资源清理。

应用使用模块级 SQLAlchemy AsyncEngine；pytest 默认逐测试关闭事件循环，
会令尚未释放的 aiosqlite worker thread 在后续 loop 关闭后回调。
每个测试结束时在当前测试 loop 中显式 dispose engine，避免连接池跨 loop 复用。
"""
import pytest_asyncio

from app.core.database import engine


@pytest_asyncio.fixture(scope="function", autouse=True)
async def dispose_shared_async_database_engine():
    yield
    await engine.dispose()
