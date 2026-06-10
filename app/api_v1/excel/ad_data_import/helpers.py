"""Excel 导入辅助函数"""
import logging
from typing import Any

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception

logger = logging.getLogger(__name__)


def _ensure_xlrd(strict: bool, error_message: str) -> bool:
    """_ensure_xlrd 处理函数。（详见字段 Field description）。"""
    try:
        import xlrd
        logger.debug(
            f"xlrd 库已安装，版本: {xlrd.__version__ if hasattr(xlrd, '__version__') else 'unknown'}"
        )
        return True
    except ImportError:
        logger.error(error_message)
        if strict:
            raise_api_exception(
                ErrorCode.IMPORT_FILE_INVALID,
                detail="系统缺少 xlrd 库，无法读取 .xls 格式文件。请安装 xlrd 库或使用 .xlsx 格式文件。"
            )
        return False


def clean_numeric_value(value: Any) -> float:
    """
    清理并转换数值字段，支持百分比格式（如 '100.00%'）
    
    参数:
        value: 要转换的值（可能是字符串、数字或包含百分号的字符串）
    
    返回:
        浮点数值
    
    异常:
        ValueError: 如果无法转换为数值
    """
    if value is None:
        raise ValueError("值不能为None")

    # 转换为字符串并去除首尾空格
    str_value = str(value).strip()

    if not str_value:
        raise ValueError("值不能为空")

    # 去除百分号（如果存在）
    if str_value.endswith('%'):
        str_value = str_value[:-1].strip()

    # 转换为浮点数
    try:
        return float(str_value)
    except ValueError as e:
        raise ValueError(f"无法转换为数值: '{value}'") from e

