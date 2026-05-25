"""
Excel 异步读取（避免在 async 路由中阻塞事件循环）
"""
import asyncio
import logging
from io import BytesIO
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


async def read_excel_from_bytes(
        contents: bytes,
        engine: str = "openpyxl",
) -> pd.DataFrame:
    """在线程池中执行 pd.read_excel"""
    return await asyncio.to_thread(
        pd.read_excel,
        BytesIO(contents),
        engine=engine,
    )


async def read_excel_with_fallback(
        contents: bytes,
        primary_engine: str,
        *,
        filename_lower: str = "",
) -> tuple[pd.DataFrame, str]:
    """
    尝试主引擎解析 Excel，失败时回退另一引擎。
    返回 (DataFrame, 实际使用的 engine)
    """
    try:
        df = await read_excel_from_bytes(contents, engine=primary_engine)
        return df, primary_engine
    except Exception as primary_error:
        logger.warning("使用 %s 引擎解析失败: %s", primary_engine, primary_error)
        fallback = "xlrd" if primary_engine == "openpyxl" else "openpyxl"
        if primary_engine == "xlrd" and filename_lower.endswith(".xls"):
            raise primary_error
        try:
            df = await read_excel_from_bytes(contents, engine=fallback)
            logger.info("使用 %s 引擎解析成功（回退）", fallback)
            return df, fallback
        except Exception:
            raise primary_error
