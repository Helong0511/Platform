"""广告数据 Excel 导入处理（向后兼容垫片）

职责：解析上传 xlsx/xls，校验列映射与业务字段，批量 upsert AdData 并返回导入统计。
"""
from app.api_v1.excel.ad_data_import import (  # noqa: F401
    _ensure_xlrd,
    clean_numeric_value,
    validate_and_read_excel,
    process_column_mapping,
    check_excel_duplicates,
    build_product_maps,
    find_or_create_product,
    process_row_data,
    import_ad_data_handler,
)

__all__ = [
    "_ensure_xlrd", "clean_numeric_value",
    "validate_and_read_excel", "process_column_mapping", "check_excel_duplicates",
    "build_product_maps", "find_or_create_product", "process_row_data",
    "import_ad_data_handler",
]
