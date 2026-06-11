"""
Telegram Bot 同步数据库会话。

Bot 回调运行在独立线程，不可复用主进程 asyncio 引擎；
此处提供 pymysql 同步连接池，供统计查询、Postback 审批等场景使用。
"""
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


def _normalize_sync_db_url(db_url: str) -> str:
    """将异步 MySQL DSN 转为 pymysql 同步 DSN。"""
    if "+aiomysql" in db_url:
        return db_url.replace("+aiomysql", "+pymysql")
    if "+asyncmy" in db_url:
        return db_url.replace("+asyncmy", "+pymysql")
    if "mysql://" in db_url and "+" not in db_url:
        return db_url
    return db_url.replace("mysql://", "mysql+pymysql://")


@lru_cache(maxsize=1)
def get_sync_session_factory():
    """
    获取同步 Session 工厂（进程内单例，避免每次回调新建引擎）。

    Returns:
        sessionmaker 实例
    """
    sync_db_url = _normalize_sync_db_url(settings.SQLALCHEMY_DATABASE_URI)
    engine = create_engine(
        sync_db_url,
        pool_pre_ping=True,
        pool_recycle=settings.DB_POOL_RECYCLE,
        pool_size=5,
        max_overflow=3,
        echo=False,
    )
    return sessionmaker(bind=engine)
