"""一次性脚本：拆分 import_handler.py 为 import 子包"""
import pathlib

SRC = pathlib.Path("app/api_v1/excel/ad_data_import_handler.py")
lines = SRC.read_text(encoding="utf-8").splitlines(keepends=True)


def slice_lines(start: int, end: int) -> str:
    return "".join(lines[start - 1 : end])


base = pathlib.Path("app/api_v1/excel/ad_data_import")
base.mkdir(exist_ok=True)

helpers = (
    '"""Excel 导入辅助函数"""\n'
    "import logging\n"
    "from typing import Any\n\n"
    "from app.core.errors import ErrorCode\n"
    "from app.core.exceptions import raise_api_exception\n\n"
    "logger = logging.getLogger(__name__)\n\n\n"
    + slice_lines(48, 97)
)

excel_reader = (
    '"""Excel 文件读取与列映射"""\n'
    "import logging\n"
    "from typing import Any\n\n"
    "import pandas as pd\n"
    "from fastapi import UploadFile\n\n"
    "from app.api_v1.excel.utils import ALLOWED_MIME_TYPES, allowed_file, calculate_rates, parse_date_value\n"
    "from app.api_v1.excel.import.helpers import _ensure_xlrd\n"
    "from app.api_v1.ml_model.ml_model import ColumnMappingService, REQUIRED_FIELDS\n"
    "from app.core.config import settings\n"
    "from app.core.errors import ErrorCode\n"
    "from app.core.exceptions import raise_api_exception\n"
    "from app.core.excel_io import read_excel_with_fallback\n\n"
    "logger = logging.getLogger(__name__)\n\n\n"
    + slice_lines(99, 433)
)

product_resolver = (
    '"""产品查找与创建"""\n'
    "import logging\n"
    "from datetime import date\n"
    "from typing import Any\n\n"
    "from sqlalchemy.ext.asyncio import AsyncSession\n"
    "from sqlalchemy.future import select\n\n"
    "from app.core.product_assignment import initialize_product_assignment\n"
    "from app.core.utils import find_or_create_default_client\n"
    "from app.models.models import User, Client, Product\n\n"
    "logger = logging.getLogger(__name__)\n\n\n"
    + slice_lines(436, 641)
)

row_processor = (
    '"""单行广告数据导入处理"""\n'
    "import logging\n"
    "from datetime import datetime\n"
    "from typing import Any\n\n"
    "import pandas as pd\n"
    "from sqlalchemy import or_\n"
    "from sqlalchemy.ext.asyncio import AsyncSession\n"
    "from sqlalchemy.future import select\n\n"
    "from app.api_v1.excel.import.helpers import clean_numeric_value\n"
    "from app.api_v1.excel.import.product_resolver import find_or_create_product\n"
    "from app.api_v1.excel.utils import (\n"
    "    is_valid_numeric_value, normalize_date_key, parse_date_value, safe_get_value,\n"
    ")\n"
    "from app.core.ad_data_processor import check_and_notify_data_decrease\n"
    "from app.core.constants import ECPM_MULTIPLIER\n"
    "from app.core.country_code import find_country_code_by_any_format\n"
    "from app.core.utils import (\n"
    "    get_date_range, normalize_ad_unit, normalize_date_for_ad_data, truncate_to_2_decimal,\n"
    ")\n"
    "from app.models.models import User, AdData\n\n"
    "logger = logging.getLogger(__name__)\n\n\n"
    + slice_lines(643, 974)
)

handler = (
    '"""广告数据 Excel 导入主处理"""\n'
    "import asyncio\n"
    "import logging\n\n"
    "import pandas as pd\n"
    "from fastapi import HTTPException, UploadFile\n"
    "from sqlalchemy import or_, and_\n"
    "from sqlalchemy.exc import IntegrityError\n"
    "from sqlalchemy.ext.asyncio import AsyncSession\n"
    "from sqlalchemy.future import select\n\n"
    "from app.api_v1.excel.import.excel_reader import (\n"
    "    check_excel_duplicates, process_column_mapping, validate_and_read_excel,\n"
    ")\n"
    "from app.api_v1.excel.import.product_resolver import build_product_maps\n"
    "from app.api_v1.excel.import.row_processor import process_row_data\n"
    "from app.api_v1.excel.utils import parse_date_value\n"
    "from app.core.exceptions import handle_integrity_error, raise_api_exception\n"
    "from app.core.errors import ErrorCode\n"
    "from app.core.utils import format_error_details, build_import_message, get_date_range\n"
    "from app.models.models import User, AdData, AdminNotificationConfig\n"
    "from app.schemas.excel import ExcelImportResponse\n"
    "from app.services.telegram_notification_service import TelegramNotificationService\n\n"
    "logger = logging.getLogger(__name__)\n\n\n"
    + slice_lines(976, len(lines))
)

init_py = '''"""广告数据 Excel 导入子模块"""
from app.api_v1.excel.import.helpers import _ensure_xlrd, clean_numeric_value
from app.api_v1.excel.import.excel_reader import (
    validate_and_read_excel, process_column_mapping, check_excel_duplicates,
)
from app.api_v1.excel.import.product_resolver import build_product_maps, find_or_create_product
from app.api_v1.excel.import.row_processor import process_row_data
from app.api_v1.excel.import.handler import import_ad_data_handler

__all__ = [
    "_ensure_xlrd", "clean_numeric_value",
    "validate_and_read_excel", "process_column_mapping", "check_excel_duplicates",
    "build_product_maps", "find_or_create_product", "process_row_data",
    "import_ad_data_handler",
]
'''

shim = '''"""广告数据 Excel 导入处理（向后兼容垫片）

职责：解析上传 xlsx/xls，校验列映射与业务字段，批量 upsert AdData 并返回导入统计。
"""
from app.api_v1.excel.import import (  # noqa: F401
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
'''

(base / "helpers.py").write_text(helpers, encoding="utf-8")
(base / "excel_reader.py").write_text(excel_reader, encoding="utf-8")
(base / "product_resolver.py").write_text(product_resolver, encoding="utf-8")
(base / "row_processor.py").write_text(row_processor, encoding="utf-8")
(base / "handler.py").write_text(handler, encoding="utf-8")
(base / "__init__.py").write_text(init_py, encoding="utf-8")
SRC.write_text(shim, encoding="utf-8")
print("import split done")
