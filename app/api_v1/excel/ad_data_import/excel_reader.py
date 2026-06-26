"""Excel 文件读取与列映射"""
import logging
from typing import Any

import pandas as pd
from fastapi import UploadFile

from app.api_v1.excel.utils import ALLOWED_MIME_TYPES, allowed_file, calculate_rates, parse_date_value
from app.api_v1.excel.ad_data_import.helpers import _ensure_xlrd, drop_blank_excel_import_rows
from app.api_v1.ml_model.ml_model import ColumnMappingService, REQUIRED_FIELDS
from app.core.config import settings
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.excel_io import read_excel_with_fallback

logger = logging.getLogger(__name__)


async def validate_and_read_excel(file: UploadFile) -> tuple[pd.DataFrame, bytes]:
    """
    验证并读取Excel文件
        
        返回:
            (DataFrame, 文件内容bytes)
    
    鉴权：由 Depends(get_current_user) 或 require_admin 控制；客户角色仅可操作自有数据。
    响应：统一 ResponseBaseSchema / PaginatedResponseBaseSchema 包装。
    """
    # ---------- 入口：参数与依赖准备 ----------
    # 验证文件类型
    # ---------- 条件分支 ----------
    if file.content_type not in ALLOWED_MIME_TYPES or not allowed_file(file.filename):
        raise_api_exception(
            ErrorCode.IMPORT_FILE_INVALID,
            detail="不支持的文件类型。请上传Excel文件(.xlsx或.xls)"
        )

    # 读取文件内容
    max_size = settings.MAX_UPLOAD_SIZE
    contents = await file.read()

    # 检查文件大小
    # ---------- 条件分支 ----------
    if len(contents) > max_size:
        raise_api_exception(
            ErrorCode.BAD_REQUEST,
            detail=f"文件大小超过限制（最大 {max_size / 1024 / 1024:.1f}MB）"
        )

    # ---------- 条件分支 ----------
    if not contents:
        raise_api_exception(
            ErrorCode.IMPORT_FILE_INVALID,
            detail="上传的文件为空"
        )

    # 检测文件格式（通过文件内容）
    file_signature = contents[:16] if len(contents) >= 16 else contents
    is_xlsx = contents[:4] == b'PK\x03\x04'  # .xlsx 文件（ZIP格式）
    is_xls = contents[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'  # .xls 文件（OLE格式）

    # 记录文件信息用于诊断
    filename_lower = file.filename.lower() if file.filename else ""
    logger.debug(f"文件信息: 文件名={file.filename}, 大小={len(contents)}字节, "
                 f"扩展名={filename_lower[-5:] if len(filename_lower) >= 5 else filename_lower}, "
                 f"文件头={file_signature.hex()[:32]}")

    # 根据文件扩展名和内容检测选择引擎
    # ---------- 条件分支 ----------
    if filename_lower.endswith('.xlsx'):
        engine = "openpyxl"
        # ---------- 条件分支 ----------
        if not is_xlsx:
            logger.warning(f"文件名是 .xlsx，但文件内容不是有效的 ZIP 格式（.xlsx 文件）")
    # ---------- 条件分支 ----------
    elif filename_lower.endswith('.xls'):
        engine = "xlrd"
        # ---------- 条件分支 ----------
        if not is_xls:
            logger.warning(f"文件名是 .xls，但文件内容不是有效的 OLE 格式（.xls 文件）")
    else:
        # 如果无法从文件名判断，尝试检测文件内容
        # ---------- 条件分支 ----------
        if is_xlsx:
            engine = "openpyxl"
            logger.info("通过文件内容检测到 .xlsx 格式")
        # ---------- 条件分支 ----------
        elif is_xls:
            engine = "xlrd"
            logger.info("通过文件内容检测到 .xls 格式")
        else:
            # 默认尝试 openpyxl，如果失败再尝试 xlrd
            engine = "openpyxl"
            logger.warning("无法确定文件格式，默认尝试 openpyxl 引擎")

    # 检查必要的库是否可用
    # ---------- 条件分支 ----------
    if engine == "xlrd":
        _ensure_xlrd(strict=True, error_message="xlrd 库未安装，无法读取 .xls 格式文件")

    # 尝试解析Excel文件
    df = None
    last_error = None
    tried_engines = []

    # 首先尝试指定的引擎
    # ---------- 异常处理 ----------
    try:
        logger.debug(f"尝试使用 {engine} 引擎解析文件")
        df, engine = await read_excel_with_fallback(
            contents,
            engine,
            filename_lower=filename_lower,
        )
        tried_engines.append(engine)
    except Exception as e:
        last_error = e
        tried_engines.append(engine)
        logger.warning(f"使用 {engine} 引擎解析失败: {str(e)}")

    # 如果所有尝试都失败，抛出友好的错误信息
    # ---------- 条件分支 ----------
    if df is None or df.empty:
        error_msg = str(last_error) if last_error else "无法解析Excel文件"

        # 构建详细的错误信息
        detail_parts = []

        # 检查文件格式
        # ---------- 条件分支 ----------
        if not is_xlsx and not is_xls:
            detail_parts.append("文件内容不是有效的 Excel 格式（.xlsx 或 .xls）")
            # 检查是否是其他常见格式
            # ---------- 条件分支 ----------
            if contents[:5] == b'<?xml' or contents[:5] == b'<html' or contents[:5] == b'<!DOC':
                detail_parts.append("文件可能是 HTML 或 XML 格式，不是 Excel 文件")
            # ---------- 条件分支 ----------
            elif b',' in contents[:100] and b'\n' in contents[:100]:
                detail_parts.append("文件可能是 CSV 格式，请使用 Excel 打开并另存为 .xlsx 格式")

        # 提供更友好的错误信息
        # ---------- 条件分支 ----------
        if "no valid workbook" in error_msg.lower() or "workbook" in error_msg.lower():
            detail_parts.append("Excel文件格式无效或文件已损坏")
            detail_parts.append("请确保文件是有效的 .xlsx 或 .xls 格式，且文件未损坏")
            detail_parts.append("建议：使用 Excel 打开文件，然后另存为 .xlsx 格式")
        # ---------- 条件分支 ----------
        elif "invalid" in error_msg.lower() or "InvalidFileException" in str(type(last_error).__name__):
            detail_parts.append("无效的Excel文件格式")
            detail_parts.append("请确保文件是 .xlsx 或 .xls 格式，且文件未损坏")
        # ---------- 条件分支 ----------
        elif "empty" in error_msg.lower() or "no columns" in error_msg.lower():
            detail_parts.append("Excel文件为空或没有数据")
            detail_parts.append("请确保文件包含至少一行数据")
        else:
            detail_parts.append(f"解析Excel文件失败: {error_msg}")
            detail_parts.append("请检查文件格式是否正确，或尝试重新保存文件")

        # 添加诊断信息
        # ---------- 条件分支 ----------
        if tried_engines:
            detail_parts.append(f"已尝试的解析引擎: {', '.join(tried_engines)}")

        detail = "。".join(detail_parts) if detail_parts else "无法解析Excel文件"

        logger.error(f"Excel文件解析失败: {detail}。文件名: {file.filename}, 大小: {len(contents)}字节")

        raise_api_exception(ErrorCode.IMPORT_DATA_VALIDATION_FAILED, detail=detail)

    # ---------- 构建响应 ----------
    return df, contents


async def process_column_mapping(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    处理列名映射和验证
        
        返回:
            (处理后的DataFrame, 映射结果)
    
    鉴权：由 Depends(get_current_user) 或 require_admin 控制；客户角色仅可操作自有数据。
    响应：统一 ResponseBaseSchema / PaginatedResponseBaseSchema 包装。
    """
    # 步骤1：规范化Excel列名
    excel_columns_normalized = ColumnMappingService.normalize_excel_columns(df.columns)
    df.columns = excel_columns_normalized

    # 步骤2：智能列名映射
    column_mapping_result = ColumnMappingService.smart_column_mapping(excel_columns_normalized)

    # 检查映射是否完整
    mapping_complete = column_mapping_result.get("mapping_complete", False)
    mapped_count = column_mapping_result.get("mapped_count", 0)
    required_count = column_mapping_result.get("required_count", 11)
    match_details = column_mapping_result.get("match_details", {})
    mapping = column_mapping_result.get("mapping", {})

    # 打印映射识别成功的详细信息
    if mapping:
        logger.info(
            f"✅ 列名映射识别成功: {mapped_count}/{required_count} 个字段已映射"
        )
        for excel_col, db_field in mapping.items():
            match_info = match_details.get(excel_col, ("未知", "", 0))
            match_type, rule_col, score = match_info
            field_name_cn = REQUIRED_FIELDS.get(db_field, db_field)
            if rule_col:
                logger.info(
                    f"  📌 '{excel_col}' -> '{field_name_cn}' ({db_field}) "
                    f"[{match_type}] 参考规则: '{rule_col}'"
                )
            else:
                logger.info(
                    f"  📌 '{excel_col}' -> '{field_name_cn}' ({db_field}) [{match_type}]"
                )
    else:
        logger.warning("⚠️ 列名映射识别失败：没有成功映射任何字段")

    if mapping_complete:
        logger.info("✅ Excel列名映射完整，能够匹配训练数据，将自动创建不存在的产品")
    else:
        logger.warning(
            f"⚠️ Excel列名映射不完整（{mapped_count}/{required_count}），"
            f"部分字段可能无法正确识别"
        )

    # 应用列名映射
    rename_dict = {
        excel_col: db_col
        for excel_col, db_col in mapping.items()
        if excel_col in df.columns and db_col not in df.columns
    }

    if rename_dict:
        df = df.rename(columns=rename_dict)
        logger.info(f"应用列名映射: {len(rename_dict)} 个列被重命名: {rename_dict}")

    # 验证必要的列
    # 注意：coverage_rate, display_rate, click_rate, ecpm_before_deduct 是可选的
    # 如果Excel中没有这些字段，会通过计算公式自动计算
    required_columns = [
        "date", "product_name", "request_count", "match_count",
        "display_count", "click_count", "revenue_before_deduct"
    ]
    # 可选字段（如果不存在会自动计算）
    optional_columns = ["coverage_rate", "display_rate", "click_rate", "viewability_rate", "ecpm_before_deduct", "cpc",
                        "pageviews"]
    missing_columns = [col for col in required_columns if col not in df.columns]

    # 规则2：字段映射不完整，报错不导入（完全基于训练数据，不能识别就不导入）
    if not mapping_complete:
        # 检查是否有错误信息（如：没有训练数据）
        error_msg = column_mapping_result.get("error")
        if error_msg:
            raise_api_exception(ErrorCode.IMPORT_DATA_VALIDATION_FAILED, detail=error_msg)

        if missing_columns:
            missing_cn = [REQUIRED_FIELDS.get(col, col) for col in missing_columns]
            unmatched_excel_cols = column_mapping_result.get("unmatched_excel_columns", [])

            # 构建详细的错误信息（强调基于训练数据）
            error_detail = (
                f"字段映射不完整，无法导入数据。"
                f"\n\n缺少必要的列: {', '.join(missing_cn)}。"
                f"\n\n系统完全基于训练数据进行智能识别，无法识别的列将不导入。"
            )

            # 显示训练数据统计
            training_rules_count = column_mapping_result.get("training_rules_count", 0)
            if training_rules_count > 0:
                error_detail += f"\n\n当前训练数据: {training_rules_count} 条映射规则"

            if unmatched_excel_cols:
                error_detail += f"\n\nExcel中未匹配的列: {', '.join(unmatched_excel_cols)}"
                error_detail += "\n\n可能的原因："
                error_detail += "\n1. 训练数据中没有这些列名的映射规则"
                error_detail += "\n2. 列名与训练数据中的列名相似度不够高（相似度阈值：60%）"
                error_detail += "\n3. 训练数据中可能存在错误的映射规则（例如：将'收益'映射到了'eCPM'）"
                error_detail += "\n\n解决建议："
                error_detail += "\n1. 检查训练数据中的映射规则是否正确"
                error_detail += "\n   - '收益'、'revenue' 相关列应映射到 'revenue_before_deduct'"
                error_detail += "\n   - 'eCPM'、'CPM'、'ecpm' 相关列应映射到 'ecpm_before_deduct'"
                error_detail += "\n2. 在'导入训练'功能中，将未匹配的Excel列名手动映射到缺失的数据库字段"
                error_detail += f"\n   例如：将 '{unmatched_excel_cols[0] if unmatched_excel_cols else 'Excel列名'}' 映射到 '{missing_cn[0] if missing_cn else '数据库字段'}'"
                error_detail += "\n3. 保存映射规则后，系统会自动识别相似的列名"

            error_detail += f"\n\n已映射的字段 ({column_mapping_result.get('mapped_count', 0)}/{column_mapping_result.get('required_count', 11)}): {', '.join([REQUIRED_FIELDS.get(v, v) for v in column_mapping_result.get('mapping', {}).values()])}"
            if column_mapping_result.get('mapping'):
                error_detail += f"\n映射详情: {column_mapping_result.get('mapping', {})}"

            raise_api_exception(
                ErrorCode.IMPORT_COLUMN_MAPPING_INCOMPLETE,
                detail=error_detail
            )
        else:
            missing_mapped = column_mapping_result.get("missing_columns", [])
            raise_api_exception(
                ErrorCode.IMPORT_COLUMN_MAPPING_INCOMPLETE,
                detail=(
                    f"字段映射不完整，无法导入数据。缺少映射的字段: {', '.join(missing_mapped)}。"
                    f"\n\n系统完全基于训练数据进行智能识别，无法识别的列将不导入。"
                    f"\n请先在'导入训练'功能中保存完整的映射规则。"
                )
            )

    # 字段映射完整时，继续验证
    if missing_columns:
        missing_cn = [REQUIRED_FIELDS.get(col, col) for col in missing_columns]
        raise_api_exception(
            ErrorCode.IMPORT_COLUMN_MAPPING_INCOMPLETE,
            detail=f"Excel文件缺少必要的列: {', '.join(missing_cn)}。映射结果: {column_mapping_result}"
        )

    # 计算缺失的比率字段
    df = calculate_rates(df)

    # 过滤尾部空白行，避免 NaT 被 int() 解析报错
    df = drop_blank_excel_import_rows(df)

    return df, column_mapping_result


def check_excel_duplicates(df: pd.DataFrame) -> dict[tuple[Any, str], list[int]]:
    """
    检查Excel内部重复数据（相同日期+产品名称）
    
    返回:
        重复数据映射 {(日期, 产品名称): [行号列表]}
    """
    excel_duplicate_map: dict[tuple[Any, str], list[int]] = {}

    for index, row in df.iterrows():
        try:
            date_value = row["date"]
            # 使用统一的日期解析函数，避免代码重复
            try:
                data_date = parse_date_value(date_value)
            except (ValueError, TypeError):
                continue

            product_name = (
                str(row["product_name"]).strip()
                if pd.notna(row.get("product_name")) else ""
            )
            if not product_name:
                continue

            key = (data_date, product_name)
            row_num = index + 2
            if key not in excel_duplicate_map:
                excel_duplicate_map[key] = []
            excel_duplicate_map[key].append(row_num)
        except Exception:
            continue

    return excel_duplicate_map
