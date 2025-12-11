"""
数据库初始化模块
提供数据库创建和初始化功能
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy import text
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


async def create_database(engine: AsyncEngine | None = None):
    """
    创建数据库（如果不存在）
    
    参数:
        engine: 可选的数据库引擎（如果为None，会创建临时引擎）
    
    说明:
        - 连接到MySQL服务器但不指定数据库
        - 创建 platform 数据库（如果不存在）
        - 使用临时引擎，完成后自动释放
    """
    # 连接到MySQL服务器但不指定数据库
    db_url = settings.SQLALCHEMY_DATABASE_URI.replace('/platform', '')
    temp_engine = create_async_engine(db_url, echo=False)
    try:
        async with temp_engine.connect() as conn:
            await conn.execute(text("CREATE DATABASE IF NOT EXISTS `platform`"))
            await conn.commit()
        logger.info("数据库 platform 创建成功或已存在")
    except Exception as e:
        logger.error(f"创建数据库失败: {str(e)}")
        raise
    finally:
        await temp_engine.dispose()
