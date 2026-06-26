"""Excel 导入辅助函数"""
import logging
from typing import Any, Optional

import pandas as pd

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception

logger = logging.getLogger(__name__)

# pandas 空值经 str() 后的占位文本，不能当作有效产品名
_INVALID_EXCEL_TEXT_VALUES = frozenset({"nan", "nat", "none", "<na>"})

# Excel 导入可识别的国家列名（映射后优先 country_code）
EXCEL_COUNTRY_COLUMN_NAMES = (
    "country_code",
    "国家代码",
    "国家",
    "country",
    "Country",
    "国家/地区",
)


def is_blank_excel_cell(value: Any) -> bool:
    """判断单元格是否为空（None / NaN / NaT / 空字符串）。"""
    if value is None:
        return True
    if pd.isna(value):
        return True
    return str(value).strip() == ""


def normalize_excel_product_name(value: Any) -> str:
    """规范化 Excel 产品名称；空值与 nan/NaT 占位符返回空字符串。"""
    if is_blank_excel_cell(value):
        return ""
    text = str(value).strip()
    if text.lower() in _INVALID_EXCEL_TEXT_VALUES:
        return ""
    return text


def is_valid_excel_import_row(row: pd.Series) -> bool:
    """行是否具备有效产品名与日期（用于过滤尾部空白行）。"""
    if "product_name" not in row.index or "date" not in row.index:
        return False
    if not normalize_excel_product_name(row.get("product_name")):
        return False
    return not is_blank_excel_cell(row.get("date"))


def drop_blank_excel_import_rows(df: pd.DataFrame) -> pd.DataFrame:
    """移除产品名或日期为空的行（Excel 尾部空白行常导致 NaT 导入错误）。"""
    if df.empty:
        return df
    if "product_name" not in df.columns or "date" not in df.columns:
        return df

    mask = df.apply(is_valid_excel_import_row, axis=1)
    dropped = int((~mask).sum())
    if dropped > 0:
        logger.info(f"已跳过 {dropped} 行空白或无效数据行（产品名/日期为空）")
    return df.loc[mask].copy()


def _parse_int_cell(value: Any, field_name: str) -> int:
    try:
        return int(float(value))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{field_name}格式无效: {value!r}") from exc


def require_int_from_cell(value: Any, field_name: str) -> int:
    """将必填 Excel 单元格转为整数；空值抛出 ValueError。"""
    if is_blank_excel_cell(value):
        raise ValueError(f"{field_name}不能为空")
    return _parse_int_cell(value, field_name)


def safe_int_from_cell(value: Any, field_name: str, *, default: int = 0) -> int:
    """将可选 Excel 单元格转为整数；空值返回 default。"""
    if is_blank_excel_cell(value):
        return default
    return _parse_int_cell(value, field_name)


def require_float_from_cell(value: Any, field_name: str) -> float:
    """将必填 Excel 单元格转为浮点数；空值抛出 ValueError。"""
    if is_blank_excel_cell(value):
        raise ValueError(f"{field_name}不能为空")
    try:
        return clean_numeric_value(value)
    except ValueError as exc:
        raise ValueError(f"{field_name}格式无效: {value!r}") from exc


def safe_float_from_cell(value: Any, field_name: str, *, default: float = 0.0) -> float:
    """将可选 Excel 单元格转为浮点数；空值返回 default。"""
    if is_blank_excel_cell(value):
        return default
    try:
        return clean_numeric_value(value)
    except ValueError as exc:
        raise ValueError(f"{field_name}格式无效: {value!r}") from exc


def excel_row_has_country_column(row: pd.Series) -> bool:
    """当前行是否包含国家相关列（仅限 Excel 列名检测）。"""
    return any(name in row.index for name in EXCEL_COUNTRY_COLUMN_NAMES)


def read_excel_country_cell_value(row: pd.Series) -> Optional[str]:
    """读取国家列单元格原始文本；列存在但为空时返回 None。"""
    for name in EXCEL_COUNTRY_COLUMN_NAMES:
        if name not in row.index:
            continue
        raw = row.get(name)
        if pd.notna(raw) and str(raw).strip():
            return str(raw).strip()
    return None


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

    if pd.isna(value):
        raise ValueError("值不能为空")

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

