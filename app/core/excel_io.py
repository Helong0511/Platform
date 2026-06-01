"""
Excel 读写工具：异步读取、同步导出流
"""
import asyncio
import logging
from io import BytesIO
from typing import Any, List, Optional, Union
from urllib.parse import quote

import pandas as pd
from fastapi.responses import StreamingResponse

from app.core.utils import get_app_now_naive

logger = logging.getLogger(__name__)

EXCEL_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

RowsInput = Union[List[dict[str, Any]], List[Any]]


def build_excel_bytes(
        rows: RowsInput,
        sheet_name: str,
        *,
        max_col_width: Optional[int] = 50,
) -> BytesIO:
    """
    将行数据写入 xlsx，返回可 seek(0) 的 BytesIO。
    max_col_width=None 时不限制列宽上限（仅 max_length+2）。
    """
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df = pd.DataFrame(rows)
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        worksheet = writer.sheets[sheet_name]
        for column_cells in worksheet.columns:
            max_length = max(
                len(str(cell.value)) for cell in column_cells
            ) if column_cells else 0
            width = max_length + 2
            if max_col_width is not None:
                width = min(width, max_col_width)
            worksheet.column_dimensions[column_cells[0].column_letter].width = width
    output.seek(0)
    return output


def excel_streaming_response(
        rows: RowsInput,
        sheet_name: str,
        filename_prefix: str,
        *,
        max_col_width: Optional[int] = 50,
) -> StreamingResponse:
    """生成带时间戳文件名的 Excel 下载响应。"""
    output = build_excel_bytes(rows, sheet_name, max_col_width=max_col_width)
    filename = f"{filename_prefix}_{get_app_now_naive().strftime('%Y%m%d_%H%M%S')}.xlsx"
    encoded_filename = quote(filename.encode("utf-8"))
    return StreamingResponse(
        output,
        media_type=EXCEL_MEDIA_TYPE,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )


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
