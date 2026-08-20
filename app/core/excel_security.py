"""
Excel 上传安全校验：Zip Bomb / 解压体积 / 行数上限，并尽量禁用 XXE。

.xlsx 本质是 ZIP+XML；在交给 pandas/openpyxl 前做结构扫描。
"""
from __future__ import annotations

import logging
import zipfile
from io import BytesIO
from typing import Optional

logger = logging.getLogger(__name__)

# 默认限制（可被 settings 覆盖）
DEFAULT_MAX_UNCOMPRESSED_BYTES = 80 * 1024 * 1024  # 80MB 解压总大小
DEFAULT_MAX_COMPRESSION_RATIO = 100.0  # 压缩比上限
DEFAULT_MAX_ZIP_ENTRIES = 500
DEFAULT_MAX_EXCEL_ROWS = 100_000


def _try_enable_defusedxml() -> None:
    """注册 defusedxml，降低 XXE 风险（openpyxl/ElementTree 路径）。"""
    try:
        import defusedxml  # noqa: F401
        from defusedxml import ElementTree as _DefusedET  # noqa: F401
        import xml.etree.ElementTree as etree

        # 将标准库 ElementTree 的解析入口尽量导向 defusedxml
        etree.parse = _DefusedET.parse  # type: ignore[method-assign]
        etree.fromstring = _DefusedET.fromstring  # type: ignore[method-assign]
        logger.debug("已启用 defusedxml 加固 ElementTree")
    except ImportError:
        logger.warning(
            "未安装 defusedxml，xlsx XML 外部实体防护弱化；请 pip install defusedxml"
        )
    except Exception as exc:
        logger.warning("启用 defusedxml 失败: %s", exc)


_DEFUSED_READY = False


def ensure_defusedxml() -> None:
    """进程内只注册一次。"""
    global _DEFUSED_READY
    if _DEFUSED_READY:
        return
    _try_enable_defusedxml()
    _DEFUSED_READY = True


class ExcelSecurityError(ValueError):
    """Excel 安全校验失败。"""


def validate_xlsx_zip_bomb(
    contents: bytes,
    *,
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
    max_compression_ratio: float = DEFAULT_MAX_COMPRESSION_RATIO,
    max_entries: int = DEFAULT_MAX_ZIP_ENTRIES,
) -> None:
    """
    扫描 .xlsx（ZIP）成员，拒绝 Zip Bomb / 异常膨胀。

    非 ZIP（如旧 .xls）直接跳过。
    """
    if not contents or contents[:4] != b"PK\x03\x04":
        return

    ensure_defusedxml()

    try:
        with zipfile.ZipFile(BytesIO(contents)) as zf:
            infos = zf.infolist()
            if len(infos) > max_entries:
                raise ExcelSecurityError(
                    f"Excel 压缩包条目过多（{len(infos)} > {max_entries}）"
                )
            total_uncompressed = 0
            compressed_size = max(len(contents), 1)
            for info in infos:
                if info.file_size < 0 or info.compress_size < 0:
                    raise ExcelSecurityError("Excel 压缩包含非法大小字段")
                total_uncompressed += int(info.file_size)
                if total_uncompressed > max_uncompressed_bytes:
                    raise ExcelSecurityError(
                        f"Excel 解压后体积超过限制（>{max_uncompressed_bytes} 字节）"
                    )
                if info.compress_size > 0:
                    ratio = info.file_size / float(info.compress_size)
                    if ratio > max_compression_ratio and info.file_size > 1024 * 1024:
                        raise ExcelSecurityError(
                            f"Excel 压缩比异常（{ratio:.1f} > {max_compression_ratio}）"
                        )
            overall_ratio = total_uncompressed / float(compressed_size)
            if (
                overall_ratio > max_compression_ratio
                and total_uncompressed > 5 * 1024 * 1024
            ):
                raise ExcelSecurityError(
                    f"Excel 整体压缩比异常（{overall_ratio:.1f}）"
                )
    except zipfile.BadZipFile as exc:
        raise ExcelSecurityError("无效的 Excel/ZIP 文件") from exc


def enforce_max_rows(df_row_count: int, max_rows: int = DEFAULT_MAX_EXCEL_ROWS) -> None:
    """限制 DataFrame 行数，防止超大表拖垮内存/CPU。"""
    if df_row_count > max_rows:
        raise ExcelSecurityError(
            f"Excel 行数超过限制（{df_row_count} > {max_rows}）"
        )
