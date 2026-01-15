"""
导入训练API端点
专注于Excel列名和字段的智能匹配
- 用户手动保存映射规则
- 智能列名映射（基于用户映射规则和标准映射表）
- 确保包含所有11个必要字段
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query, Body, Request
from typing import Optional
import logging
from datetime import datetime
from io import BytesIO
import json
import os
import re
from difflib import SequenceMatcher

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_admin
from app.core.database import get_db
from app.core.config import settings
from app.core.utils import get_app_now_naive, build_import_message
from app.core.audit_log import log_user_action
from app.models.models import User, AdData, Product
from app.schemas.base import ResponseBaseSchema
from app.api.api_v1.endpoints.excel.utils import validate_excel_file, parse_date_value
from app.core.constants import MAX_PAGE_SIZE
from sqlalchemy import and_, or_
from sqlalchemy.future import select
from starlette.datastructures import UploadFile as StarletteUploadFile
import traceback

router = APIRouter()
logger = logging.getLogger(__name__)

# 模型存储路径
MODEL_DIR = "models"
os.makedirs(MODEL_DIR, exist_ok=True)
MAPPING_RULES_FILE = os.path.join(MODEL_DIR, "column_mapping_rules.json")

# 11个必要字段的标准名称
REQUIRED_FIELDS = {
    "date": "数据日期",
    "product_name": "产品名称",
    "request_count": "请求数",
    "match_count": "匹配数",
    "coverage_rate": "覆盖率",
    "display_count": "展示数",
    "display_rate": "展示率",
    "click_count": "点击数",
    "click_rate": "点击率",
    "ecpm_before_deduct": "eCPM",
    "revenue_before_deduct": "收益"
}

# 可选字段（如果Excel中有这些字段，会被识别和导入，但不影响mapping_complete判断）
OPTIONAL_FIELDS = {
    "cpc": "CPC",
    "pageviews": "PageViews"
}

# 所有字段（包含必需字段和可选字段）
ALL_FIELDS = {**REQUIRED_FIELDS, **OPTIONAL_FIELDS}


def _ensure_xlrd(strict: bool, error_message: str) -> bool:
    try:
        import xlrd
        return True
    except ImportError:
        logger.error(error_message)
        if strict:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="系统缺少 xlrd 库，无法读取 .xls 格式文件。请安装 xlrd 库或使用 .xlsx 格式文件。"
            )
        return False


def _read_excel_file(contents: bytes, filename: Optional[str] = None) -> pd.DataFrame:
    """
    读取Excel文件，支持 .xlsx 和 .xls 格式
    
    参数:
        contents: 文件内容（bytes）
        filename: 文件名（可选，用于判断文件格式）
    
    返回:
        DataFrame对象
    
    异常:
        HTTPException: 如果文件无法解析
    """
    # 检测文件格式（通过文件内容）
    is_xlsx = contents[:4] == b'PK\x03\x04'  # .xlsx 文件（ZIP格式）
    is_xls = contents[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'  # .xls 文件（OLE格式）

    # 根据文件扩展名和内容检测选择引擎
    filename_lower = filename.lower() if filename else ""
    if filename_lower.endswith('.xlsx'):
        engine = "openpyxl"
        if not is_xlsx:
            logger.warning(f"文件名是 .xlsx，但文件内容不是有效的 ZIP 格式")
    elif filename_lower.endswith('.xls'):
        engine = "xlrd"
        if not is_xls:
            logger.warning(f"文件名是 .xls，但文件内容不是有效的 OLE 格式")
    else:
        # 如果无法从文件名判断，尝试检测文件内容
        if is_xlsx:
            engine = "openpyxl"
        elif is_xls:
            engine = "xlrd"
        else:
            engine = "openpyxl"  # 默认尝试 openpyxl

    # 检查必要的库是否可用
    if engine == "xlrd":
        _ensure_xlrd(strict=True, error_message="xlrd 库未安装，无法读取 .xls 格式文件")

    # 尝试解析Excel文件
    df = None
    last_error = None
    tried_engines = []

    # 首先尝试指定的引擎
    try:
        df = pd.read_excel(BytesIO(contents), engine=engine)
        tried_engines.append(engine)
    except Exception as e:
        last_error = e
        error_msg = str(e)
        tried_engines.append(engine)
        logger.warning(f"使用 {engine} 引擎解析失败: {error_msg}")

        # 如果第一次尝试失败，尝试另一个引擎
        if engine == "openpyxl":
            try:
                if _ensure_xlrd(strict=False, error_message="xlrd 库未安装，无法尝试 .xls 格式"):
                    logger.info("尝试使用 xlrd 引擎解析文件（可能是 .xls 格式）")
                    df = pd.read_excel(BytesIO(contents), engine="xlrd")
                    engine = "xlrd"
                    tried_engines.append("xlrd")
            except Exception as e2:
                last_error = e2
                tried_engines.append("xlrd")
                logger.error(f"使用 xlrd 引擎也失败: {str(e2)}")
        elif engine == "xlrd":
            try:
                logger.info("尝试使用 openpyxl 引擎解析文件（可能是 .xlsx 格式）")
                df = pd.read_excel(BytesIO(contents), engine="openpyxl")
                engine = "openpyxl"
                tried_engines.append("openpyxl")
            except Exception as e2:
                last_error = e2
                tried_engines.append("openpyxl")
                logger.error(f"使用 openpyxl 引擎也失败: {str(e2)}")

    # 如果所有尝试都失败，抛出友好的错误信息
    if df is None or df.empty:
        error_msg = str(last_error) if last_error else "无法解析Excel文件"

        # 构建详细的错误信息
        detail_parts = []

        # 检查文件格式
        if not is_xlsx and not is_xls:
            detail_parts.append("文件内容不是有效的 Excel 格式（.xlsx 或 .xls）")
            # 检查是否是其他常见格式
            if contents[:5] == b'<?xml' or contents[:5] == b'<html' or contents[:5] == b'<!DOC':
                detail_parts.append("文件可能是 HTML 或 XML 格式，不是 Excel 文件")
            elif b',' in contents[:100] and b'\n' in contents[:100]:
                detail_parts.append("文件可能是 CSV 格式，请使用 Excel 打开并另存为 .xlsx 格式")

        # 提供更友好的错误信息
        if "no valid workbook" in error_msg.lower() or "workbook" in error_msg.lower():
            detail_parts.append("Excel文件格式无效或文件已损坏")
            detail_parts.append("请确保文件是有效的 .xlsx 或 .xls 格式，且文件未损坏")
            detail_parts.append("建议：使用 Excel 打开文件，然后另存为 .xlsx 格式")
        elif "invalid" in error_msg.lower() or "InvalidFileException" in str(type(last_error).__name__):
            detail_parts.append("无效的Excel文件格式")
            detail_parts.append("请确保文件是 .xlsx 或 .xls 格式，且文件未损坏")
        elif "empty" in error_msg.lower() or "no columns" in error_msg.lower():
            detail_parts.append("Excel文件为空或没有数据")
            detail_parts.append("请确保文件包含至少一行数据")
        else:
            detail_parts.append(f"解析Excel文件失败: {error_msg}")
            detail_parts.append("请检查文件格式是否正确，或尝试重新保存文件")

        # 添加诊断信息
        if tried_engines:
            detail_parts.append(f"已尝试的解析引擎: {', '.join(tried_engines)}")

        detail = "。".join(detail_parts) if detail_parts else "无法解析Excel文件"

        logger.error(f"Excel文件解析失败: {detail}。文件名: {filename}, 大小: {len(contents)}字节")

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )

    return df


class ColumnMappingService:
    """列名映射服务"""

    @staticmethod
    def calculate_similarity(str1: str, str2: str) -> float:
        """
        计算两个字符串的相似度（0-1之间）
        使用SequenceMatcher算法
        """
        return SequenceMatcher(None, str1.lower().strip(), str2.lower().strip()).ratio()

    @staticmethod
    def extract_keywords(text: str) -> set[str]:
        """
        提取文本中的关键词（去除常见停用词）
        返回关键词集合
        """
        # 常见停用词
        stop_words = {'的', '了', '在', '是', '和', '与', '或', '及', '等', '等', '(', ')', '（', '）', '未', '减', '扣'}

        # 去除标点符号和空格，提取关键词
        keywords = set()
        text_lower = text.lower().strip()

        # 提取中文关键词（2个字符以上）
        chinese_chars = re.findall(r'[\u4e00-\u9fff]+', text)
        for char_seq in chinese_chars:
            if len(char_seq) >= 2 and char_seq not in stop_words:
                keywords.add(char_seq)
            # 也添加单个字符（如果是有意义的）
            if len(char_seq) == 1 and char_seq not in stop_words:
                keywords.add(char_seq)

        # 提取英文单词
        english_words = re.findall(r'[a-zA-Z]+', text_lower)
        for word in english_words:
            if len(word) >= 2 and word not in stop_words:
                keywords.add(word)

        return keywords

    @staticmethod
    def keyword_overlap_score(str1: str, str2: str) -> float:
        """
        计算两个字符串的关键词重叠度（0-1之间）
        基于关键词集合的交集和并集
        """
        keywords1 = ColumnMappingService.extract_keywords(str1)
        keywords2 = ColumnMappingService.extract_keywords(str2)

        if not keywords1 or not keywords2:
            return 0.0

        intersection = keywords1 & keywords2
        union = keywords1 | keywords2

        if not union:
            return 0.0

        return len(intersection) / len(union)

    @staticmethod
    def find_best_match_from_rules(
            excel_col: str,
            user_mapping_rules: dict[str, str],
            used_fields: set[str],
            similarity_threshold: float = 0.6
    ) -> tuple[Optional[str], float, str]:
        """
        从用户映射规则中找到最佳匹配
        
        返回: (匹配的数据库字段, 相似度分数, 匹配的规则列名)
        相似度分数 = 0.7 * 字符串相似度 + 0.3 * 关键词重叠度
        
        包含语义检查，确保 "收益" 相关列不会映射到 eCPM，反之亦然
        """
        best_match = None
        best_score = 0.0
        best_rule_col = None

        excel_col_normalized = excel_col.strip().lower()
        excel_keywords = ColumnMappingService.extract_keywords(excel_col)

        # 语义检查：判断 Excel 列的语义类型
        is_revenue_related = (
                                     '收益' in excel_col or 'revenue' in excel_col_normalized) and 'ecpm' not in excel_col_normalized and 'cpm' not in excel_col_normalized
        is_ecpm_related = (
                                  'ecpm' in excel_col_normalized or 'cpm' in excel_col_normalized) and '收益' not in excel_col and 'revenue' not in excel_col_normalized

        # 特殊处理：如果列名包含"千次"、"浏览"等词，且包含"收入"，可能是其他指标，不应该映射到"收益"
        is_other_metric = ('千次' in excel_col or '浏览' in excel_col or 'view' in excel_col_normalized) and (
                '收入' in excel_col or 'revenue' in excel_col_normalized)

        for rule_excel, rule_db in user_mapping_rules.items():
            # 跳过已使用的字段
            if rule_db in used_fields:
                continue

            # 语义一致性检查：避免错误映射
            # 如果 Excel 列是收益相关的，但规则映射到 eCPM，跳过
            if is_revenue_related and rule_db == 'ecpm_before_deduct':
                logger.debug(f"语义检查：'{excel_col}' 是收益相关，但规则 '{rule_excel}' 映射到 eCPM，跳过")
                continue

            # 如果 Excel 列是 eCPM 相关的，但规则映射到收益，跳过
            if is_ecpm_related and rule_db == 'revenue_before_deduct':
                logger.debug(f"语义检查：'{excel_col}' 是 eCPM 相关，但规则 '{rule_excel}' 映射到收益，跳过")
                continue

            # 特殊检查：如果列名是"千次浏览收入"等，且目标字段是"收益"，需要确保规则列名也包含相关关键词
            if is_other_metric and rule_db == 'revenue_before_deduct':
                rule_excel_lower_check = rule_excel.strip().lower()
                # 只有当规则列名也包含"千次"、"浏览"等词时，才允许匹配
                if not ('千次' in rule_excel or '浏览' in rule_excel or 'view' in rule_excel_lower_check):
                    logger.debug(
                        f"语义检查：'{excel_col}' 是其他指标（千次浏览收入），但规则 '{rule_excel}' 不包含相关关键词，跳过")
                    continue

            semantic_penalty = 0.0

            rule_excel_normalized = rule_excel.strip().lower()

            # 计算字符串相似度
            similarity = ColumnMappingService.calculate_similarity(excel_col, rule_excel)

            # 计算关键词重叠度
            keyword_overlap = ColumnMappingService.keyword_overlap_score(excel_col, rule_excel)

            # 综合分数（字符串相似度权重更高）
            combined_score = 0.7 * similarity + 0.3 * keyword_overlap

            # 应用语义惩罚
            if semantic_penalty > 0:
                combined_score = combined_score * (1 - semantic_penalty)

            # 如果精确匹配或高度相似，提高分数
            if excel_col_normalized == rule_excel_normalized:
                combined_score = 1.0
            elif excel_col_normalized in rule_excel_normalized or rule_excel_normalized in excel_col_normalized:
                combined_score = max(combined_score, 0.85)

            if combined_score > best_score and combined_score >= similarity_threshold:
                best_score = combined_score
                best_match = rule_db
                best_rule_col = rule_excel

        return best_match, best_score, best_rule_col if best_match else None

    @staticmethod
    def normalize_excel_column_name(col) -> str:
        """
        规范化Excel列名，确保编码正确
        
        参数:
            col: Excel列名（可能是str、bytes、数字、NaN等）
        
        返回:
            规范化的字符串（UTF-8编码）
        """
        # 处理NaN值
        if pd.isna(col):
            return "未命名列"

        # 转换为字符串
        if not isinstance(col, str):
            col = str(col)

        # 处理bytes类型
        if isinstance(col, bytes):
            try:
                col = col.decode('utf-8', errors='replace')
            except Exception:
                col = col.decode('utf-8', errors='replace')

        # 验证和修复UTF-8编码
        try:
            # 验证UTF-8编码
            col.encode('utf-8').decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            # 修复编码问题
            if isinstance(col, bytes):
                col = col.decode('utf-8', errors='replace')
            else:
                col = col.encode('utf-8', errors='replace').decode('utf-8', errors='replace')

        # 去除前后空格（但保留中间空格）
        return col.strip() if isinstance(col, str) else col

    @staticmethod
    def normalize_excel_columns(columns) -> list[str]:
        """
        批量规范化Excel列名列表
        
        参数:
            columns: Excel列名列表
        
        返回:
            规范化后的列名列表（去除前后空格）
        """
        return [ColumnMappingService.normalize_excel_column_name(col) for col in columns]

    @staticmethod
    def clean_string_for_json(s: str) -> str:
        """
        清理字符串以确保JSON序列化安全
        
        参数:
            s: 待清理的字符串
        
        返回:
            清理后的字符串
        """
        if not isinstance(s, str):
            s = str(s)

        try:
            # 验证UTF-8编码
            s.encode('utf-8').decode('utf-8')
            return s
        except (UnicodeEncodeError, UnicodeDecodeError):
            # 修复编码问题
            return s.encode('utf-8', errors='replace').decode('utf-8', errors='replace')

    @staticmethod
    def clean_mapping_for_json(mapping: dict) -> dict:
        """
        清理映射字典以确保JSON序列化安全
        
        参数:
            mapping: 映射字典 {excel_column: db_field}
        
        返回:
            清理后的映射字典
        """
        cleaned = {}
        for excel_col, db_field in mapping.items():
            clean_col = ColumnMappingService.clean_string_for_json(excel_col)
            cleaned[clean_col] = db_field
        return cleaned

    @staticmethod
    def load_user_mapping_rules(file_path: str = MAPPING_RULES_FILE) -> Optional[dict]:
        """
        加载用户保存的映射规则
        
        返回格式: {excel_column: db_field}
        例如: {"数据日期": "date", "产品名称": "product_name", ...}
        """
        try:
            if not os.path.exists(file_path):
                logger.debug(f"映射规则文件不存在: {file_path}")
                return None

            with open(file_path, 'r', encoding='utf-8') as f:
                mapping_data = json.load(f)

            # 验证文件格式
            if not isinstance(mapping_data, dict):
                logger.error(f"映射规则文件格式错误: 期望dict，实际{type(mapping_data)}")
                return None

            mapping = mapping_data.get("mapping", {})

            # 验证mapping格式
            if not isinstance(mapping, dict):
                logger.error(f"映射规则格式错误: mapping字段期望dict，实际{type(mapping)}")
                return None

            # 验证映射规则不为空
            if len(mapping) == 0:
                logger.warning("映射规则文件存在但为空")
                return None

            # 验证映射规则的字段值是否有效（包括必需字段和可选字段）
            all_valid_fields = list(ALL_FIELDS.keys())
            invalid_fields = []
            for excel_col, db_field in mapping.items():
                if db_field not in all_valid_fields:
                    invalid_fields.append(f"'{excel_col}' -> '{db_field}'")

            if invalid_fields:
                logger.error(
                    f"映射规则包含无效的字段名: {invalid_fields}, "
                    f"有效字段: {all_valid_fields}"
                )
                # 不返回None，而是过滤掉无效字段，继续使用有效的映射（包括必需字段和可选字段）
                valid_mapping = {
                    excel_col: db_field
                    for excel_col, db_field in mapping.items()
                    if db_field in all_valid_fields
                }
                if len(valid_mapping) == 0:
                    logger.error("映射规则中所有字段都无效，无法使用")
                    return None
                logger.warning(
                    f"映射规则包含无效字段，已过滤。有效映射数量: {len(valid_mapping)}/{len(mapping)}"
                )
                mapping = valid_mapping

            # 记录加载信息
            logger.info(
                f"成功加载用户映射规则: 文件={file_path}, "
                f"映射数量={len(mapping)}, 创建时间={mapping_data.get('created_at', '未知')}, "
                f"创建者={mapping_data.get('created_by', '未知')}, "
                f"版本={mapping_data.get('version', '未知')}"
            )

            return mapping
        except json.JSONDecodeError as e:
            logger.error(f"映射规则文件JSON解析失败: {file_path}, 错误: {str(e)}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"加载用户映射规则失败: {file_path}, 错误: {str(e)}", exc_info=True)
            return None

    @staticmethod
    def smart_column_mapping(excel_columns: list[str]) -> dict:
        """
        智能列名映射，完全基于用户保存的训练数据（映射规则）进行识别
        使用字符串相似度和关键词匹配算法，提高识别准确率
        如果训练数据无法识别所有必需字段，将拒绝导入
        """
        fuzzy_mapping = {}
        used_fields = set()  # 已使用的数据库字段（防止重复映射）
        used_excel_cols = set()  # 已使用的Excel列（防止重复使用）
        match_details = {}  # 记录每个映射的匹配方式：{excel_col: (match_type, rule_col, score)}

        # ====== 必须基于训练数据进行匹配 ======
        user_mapping_rules = ColumnMappingService.load_user_mapping_rules()
        if not user_mapping_rules:
            # 如果没有训练数据，无法进行映射
            logger.warning("没有找到用户保存的映射规则，无法进行智能识别。请先在'导入训练'功能中保存映射规则。")
            return {
                "mapping": {},
                "missing_columns": list(REQUIRED_FIELDS.values()),
                "mapped_count": 0,
                "required_count": len(REQUIRED_FIELDS),
                "mapping_complete": False,
                "unmatched_excel_columns": excel_columns,
                "error": "没有训练数据，无法进行列名映射。请先在'导入训练'功能中保存映射规则。"
            }

        # ====== 第一步：优先使用用户保存的所有映射规则 ======
        if user_mapping_rules:
            logger.info(f"使用用户保存的所有映射规则，共 {len(user_mapping_rules)} 条")

            # 规范化Excel列名（用于匹配）
            excel_cols_normalized = {col.strip(): col for col in excel_columns}
            excel_cols_lower = {col.strip().lower(): col for col in excel_columns}

            # 遍历所有保存的映射规则，尝试匹配Excel列名
            matched_rules = []

            # 第一轮：精确匹配和部分匹配
            for rule_excel, rule_db in user_mapping_rules.items():
                # 跳过已使用的字段
                if rule_db in used_fields:
                    continue

                rule_excel_normalized = rule_excel.strip()
                rule_excel_lower = rule_excel_normalized.lower()

                # 尝试匹配：精确匹配 -> 大小写不敏感匹配 -> 部分匹配
                matched = False
                for excel_col in excel_columns:
                    if excel_col in used_excel_cols:
                        continue

                    excel_col_normalized = excel_col.strip()
                    excel_col_lower = excel_col_normalized.lower()

                    # 精确匹配（去除空格后）
                    if rule_excel_normalized == excel_col_normalized:
                        fuzzy_mapping[excel_col] = rule_db
                        used_fields.add(rule_db)
                        used_excel_cols.add(excel_col)
                        match_details[excel_col] = ("精确匹配", rule_excel, 1.0)
                        matched_rules.append(f"精确匹配: '{excel_col}' -> '{rule_db}' (规则: '{rule_excel}')")
                        logger.debug(f"用户映射规则精确匹配: '{excel_col}' -> '{rule_db}' (规则: '{rule_excel}')")
                        matched = True
                        break

                    # 大小写不敏感匹配
                    if rule_excel_lower == excel_col_lower:
                        fuzzy_mapping[excel_col] = rule_db
                        used_fields.add(rule_db)
                        used_excel_cols.add(excel_col)
                        match_details[excel_col] = ("大小写不敏感匹配", rule_excel, 1.0)
                        matched_rules.append(f"大小写不敏感匹配: '{excel_col}' -> '{rule_db}' (规则: '{rule_excel}')")
                        logger.debug(
                            f"用户映射规则大小写不敏感匹配: '{excel_col}' -> '{rule_db}' (规则: '{rule_excel}')")
                        matched = True
                        break

                    # 部分字符串匹配（包含关系）
                    # 但需要检查语义一致性，避免错误映射
                    if (rule_excel_normalized in excel_col_normalized or
                            excel_col_normalized in rule_excel_normalized or
                            rule_excel_lower in excel_col_lower or
                            excel_col_lower in rule_excel_lower):
                        # 语义检查：确保 "收益"/"revenue" 相关列不会映射到 ecpm_before_deduct
                        # 确保 "eCPM"/"CPM"/"ecpm" 相关列不会映射到 revenue_before_deduct
                        is_revenue_related = (
                                                     '收益' in excel_col or 'revenue' in excel_col_lower) and 'ecpm' not in excel_col_lower and 'cpm' not in excel_col_lower
                        is_ecpm_related = (
                                                  'ecpm' in excel_col_lower or 'cpm' in excel_col_lower) and '收益' not in excel_col and 'revenue' not in excel_col_lower

                        # 特殊处理：如果列名包含"千次"、"浏览"等词，且包含"收入"，可能是其他指标，不应该映射到"收益"
                        is_other_metric = (
                                                  '千次' in excel_col or '浏览' in excel_col or 'view' in excel_col_lower) and (
                                                  '收入' in excel_col or 'revenue' in excel_col_lower)

                        # 如果 Excel 列是收益相关的，但规则映射到 eCPM，跳过（避免错误映射）
                        if is_revenue_related and rule_db == 'ecpm_before_deduct':
                            logger.debug(
                                f"跳过部分匹配：'{excel_col}' 是收益相关，但规则 '{rule_excel}' 映射到 eCPM，可能不正确")
                            continue

                        # 如果 Excel 列是 eCPM 相关的，但规则映射到收益，跳过（避免错误映射）
                        if is_ecpm_related and rule_db == 'revenue_before_deduct':
                            logger.debug(
                                f"跳过部分匹配：'{excel_col}' 是 eCPM 相关，但规则 '{rule_excel}' 映射到收益，可能不正确")
                            continue

                        # 特殊检查：如果列名是"千次浏览收入"等，且目标字段是"收益"，需要确保规则列名也包含相关关键词
                        if is_other_metric and rule_db == 'revenue_before_deduct':
                            rule_excel_lower_check = rule_excel.strip().lower()
                            # 只有当规则列名也包含"千次"、"浏览"等词时，才允许匹配
                            if not ('千次' in rule_excel or '浏览' in rule_excel or 'view' in rule_excel_lower_check):
                                logger.debug(
                                    f"跳过部分匹配：'{excel_col}' 是其他指标（千次浏览收入），但规则 '{rule_excel}' 不包含相关关键词，可能不正确")
                                continue

                        fuzzy_mapping[excel_col] = rule_db
                        used_fields.add(rule_db)
                        used_excel_cols.add(excel_col)
                        match_details[excel_col] = ("部分匹配", rule_excel, 0.85)
                        matched_rules.append(f"部分匹配: '{excel_col}' -> '{rule_db}' (规则: '{rule_excel}')")
                        logger.debug(f"用户映射规则部分匹配: '{excel_col}' -> '{rule_db}' (规则: '{rule_excel}')")
                        matched = True
                        break

            # 第二轮：对于未匹配的Excel列，使用相似度匹配
            unmatched_excel_cols = [col for col in excel_columns if col not in used_excel_cols]
            if unmatched_excel_cols and user_mapping_rules:
                # 为每个未匹配的列找到最佳匹配
                similarity_matches = []
                for excel_col in unmatched_excel_cols:
                    best_match, best_score, best_rule_col = ColumnMappingService.find_best_match_from_rules(
                        excel_col, user_mapping_rules, used_fields, similarity_threshold=0.6
                    )
                    if best_match:
                        similarity_matches.append((excel_col, best_match, best_score, best_rule_col))

                # 按相似度分数排序，优先匹配分数高的
                similarity_matches.sort(key=lambda x: x[2], reverse=True)

                # 应用相似度匹配（确保每个字段只匹配一次）
                for excel_col, rule_db, score, rule_col in similarity_matches:
                    if excel_col not in used_excel_cols and rule_db not in used_fields:
                        fuzzy_mapping[excel_col] = rule_db
                        used_fields.add(rule_db)
                        used_excel_cols.add(excel_col)
                        match_details[excel_col] = (f"相似度匹配(分数={score:.2f})", rule_col, score)
                        matched_rules.append(
                            f"相似度匹配({score:.2f}): '{excel_col}' -> '{rule_db}' (规则: '{rule_col}')"
                        )
                        logger.debug(
                            f"用户映射规则相似度匹配(分数={score:.2f}): '{excel_col}' -> '{rule_db}' (规则: '{rule_col}')"
                        )

            if matched_rules:
                logger.info(f"用户映射规则匹配成功 {len(matched_rules)} 条: {', '.join(matched_rules[:5])}")  # 只显示前5条
            else:
                logger.info(f"用户映射规则未找到匹配（共 {len(user_mapping_rules)} 条规则，Excel列: {excel_columns}）")

        # ====== 第二步：基于训练数据的智能推断（未匹配的列） ======
        # 注意：只有在用户映射规则无法完全匹配时，才进行智能推断
        # 如果某个字段已经被用户映射规则精确匹配，就不应该再为其他列推断这个字段
        unmatched_excel_cols = [col for col in excel_columns if col not in used_excel_cols]
        if not unmatched_excel_cols or not user_mapping_rules:
            pass  # 没有未匹配的列或没有训练数据，跳过
        else:
            # 对于每个未匹配的列，尝试从历史规则中推断
            for excel_col in unmatched_excel_cols:
                excel_keywords = ColumnMappingService.extract_keywords(excel_col)
                if not excel_keywords:
                    continue

                excel_col_normalized = excel_col.strip().lower()

                # 语义检查：判断 Excel 列的语义类型
                is_revenue_related = (
                                             '收益' in excel_col or 'revenue' in excel_col_normalized) and 'ecpm' not in excel_col_normalized and 'cpm' not in excel_col_normalized
                is_ecpm_related = (
                                          'ecpm' in excel_col_normalized or 'cpm' in excel_col_normalized) and '收益' not in excel_col and 'revenue' not in excel_col_normalized

                # 特殊处理：如果列名包含"千次"、"浏览"等词，且包含"收入"，可能是其他指标，不应该映射到"收益"
                is_other_metric = ('千次' in excel_col or '浏览' in excel_col or 'view' in excel_col_normalized) and (
                        '收入' in excel_col or 'revenue' in excel_col_normalized)

                # 在历史规则中查找包含相同关键词的规则
                best_inference = None
                best_inference_score = 0.0
                best_inference_rule = None

                for rule_excel, rule_db in user_mapping_rules.items():
                    # 跳过已使用的字段（已经被用户映射规则精确匹配的字段）
                    if rule_db in used_fields:
                        continue

                    # 语义一致性检查：避免错误映射
                    # 如果 Excel 列是收益相关的，但规则映射到 eCPM，跳过
                    if is_revenue_related and rule_db == 'ecpm_before_deduct':
                        logger.debug(
                            f"智能推断语义检查：'{excel_col}' 是收益相关，但规则 '{rule_excel}' 映射到 eCPM，跳过")
                        continue

                    # 如果 Excel 列是 eCPM 相关的，但规则映射到收益，跳过
                    if is_ecpm_related and rule_db == 'revenue_before_deduct':
                        logger.debug(
                            f"智能推断语义检查：'{excel_col}' 是 eCPM 相关，但规则 '{rule_excel}' 映射到收益，跳过")
                        continue

                    # 特殊检查：如果列名是"千次浏览收入"等，且目标字段是"收益"，需要更高的相似度阈值
                    if is_other_metric and rule_db == 'revenue_before_deduct':
                        # 只有当规则列名也包含"千次"、"浏览"等词时，才允许匹配
                        rule_excel_lower = rule_excel.strip().lower()
                        if not ('千次' in rule_excel or '浏览' in rule_excel or 'view' in rule_excel_lower):
                            logger.debug(
                                f"智能推断特殊检查：'{excel_col}' 是其他指标（千次浏览收入），但规则 '{rule_excel}' 不包含相关关键词，跳过")
                            continue

                    rule_keywords = ColumnMappingService.extract_keywords(rule_excel)
                    if not rule_keywords:
                        continue

                    # 计算关键词重叠度和字符串相似度
                    overlap = len(excel_keywords & rule_keywords) / len(
                        excel_keywords | rule_keywords) if excel_keywords | rule_keywords else 0
                    if overlap <= 0.3:  # 至少30%的关键词重叠
                        continue

                    similarity = ColumnMappingService.calculate_similarity(excel_col, rule_excel)
                    combined_score = 0.5 * overlap + 0.5 * similarity

                    # 对于"千次浏览收入"等特殊列，提高相似度阈值
                    if is_other_metric:
                        if combined_score < 0.7:  # 需要更高的相似度
                            logger.debug(
                                f"智能推断：'{excel_col}' 需要更高的相似度阈值（当前: {combined_score:.2f} < 0.7），跳过")
                            continue

                    if combined_score > best_inference_score and combined_score >= 0.6:  # 提高阈值到0.6
                        best_inference_score = combined_score
                        best_inference = rule_db
                        best_inference_rule = rule_excel

                # 如果找到合适的推断，应用映射
                if best_inference:
                    fuzzy_mapping[excel_col] = best_inference
                    used_fields.add(best_inference)
                    used_excel_cols.add(excel_col)
                    match_details[excel_col] = (f"智能推断(分数={best_inference_score:.2f})", best_inference_rule,
                                                best_inference_score)
                    logger.debug(
                        f"基于训练数据推断(分数={best_inference_score:.2f}): "
                        f"'{excel_col}' -> '{best_inference}' (参考规则: '{best_inference_rule}')"
                    )
                else:
                    logger.debug(f"未找到合适的推断匹配: '{excel_col}'")

        # 检查缺失的必需字段（不包括可选字段）
        required_fields = list(REQUIRED_FIELDS.keys())
        optional_fields = list(OPTIONAL_FIELDS.keys())
        mapped_fields = set(fuzzy_mapping.values())
        # 只检查必需字段是否缺失，可选字段不影响mapping_complete判断
        missing_required_fields = [col for col in required_fields if col not in mapped_fields]
        missing_columns = [REQUIRED_FIELDS[col] for col in missing_required_fields]

        # 记录未匹配的Excel列（用于调试）
        # 过滤掉未命名列（Unnamed: X）和空列
        unmatched_excel_cols = [
            col for col in excel_columns
            if col not in used_excel_cols
               and not (isinstance(col, str) and (col.startswith('Unnamed:') or col.strip() == '' or col == '未命名列'))
        ]
        if unmatched_excel_cols:
            logger.debug(f"未匹配的Excel列: {unmatched_excel_cols}")

        # 记录缺失的必需字段（用于调试）
        if missing_columns:
            logger.warning(
                f"缺失的必需字段: {missing_columns} (数据库字段: {missing_required_fields})。"
                f"未匹配的Excel列: {unmatched_excel_cols}"
            )

        return {
            "mapping": fuzzy_mapping,
            "missing_columns": missing_columns,
            "mapped_count": len(fuzzy_mapping),
            "required_count": len(required_fields),
            "mapping_complete": len(missing_columns) == 0,  # 只检查必需字段
            "unmatched_excel_columns": unmatched_excel_cols,  # 添加未匹配的Excel列信息
            "training_rules_count": len(user_mapping_rules) if user_mapping_rules else 0,  # 训练数据数量
            "match_details": match_details  # 匹配方式详情：{excel_col: (match_type, rule_col, score)}
        }


@router.post("/parse-excel", response_model=ResponseBaseSchema[dict], summary="解析Excel列名")
async def parse_excel_columns(
        file: UploadFile = File(...),
        current_user: User = Depends(get_current_user)
):
    """
    解析Excel文件的列名，返回所有列名供用户选择映射
    """
    try:
        # 验证文件并读取内容（使用公共验证函数）
        contents = await validate_excel_file(file)

        # 解析Excel（支持 .xlsx 和 .xls 格式）
        df = _read_excel_file(contents, file.filename)

        # 规范化Excel列名（确保编码正确）
        excel_columns = ColumnMappingService.normalize_excel_columns(df.columns)

        # 智能列名映射（作为推荐）
        column_mapping_result = ColumnMappingService.smart_column_mapping(excel_columns)

        # 清理返回数据，确保JSON序列化安全
        excel_columns_clean = [ColumnMappingService.clean_string_for_json(col) for col in excel_columns]
        recommended_mapping_clean = ColumnMappingService.clean_mapping_for_json(column_mapping_result["mapping"])

        # 返回Excel列名和推荐映射
        return ResponseBaseSchema.success(data={
            "excel_columns": excel_columns_clean,
            "recommended_mapping": recommended_mapping_clean,
            "required_fields": list(REQUIRED_FIELDS.keys()),
            "optional_fields": list(OPTIONAL_FIELDS.keys()),
            "all_fields": list(ALL_FIELDS.keys()),
            "field_names_cn": list(REQUIRED_FIELDS.values()),
            "optional_field_names_cn": list(OPTIONAL_FIELDS.values()),
            "all_field_names_cn": list(ALL_FIELDS.values())
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"解析Excel列名失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"解析Excel列名失败: {str(e)}"
        )


@router.post("/save-mapping", response_model=ResponseBaseSchema[dict], summary="保存用户映射规则")
async def save_user_mapping(
        mapping: dict = Body(..., description="用户选择的列名映射规则，格式：{excel_column: db_field}"),
        current_user: User = Depends(require_admin)
):
    """
    保存用户手动选择的列名映射规则
    """
    try:
        # 验证映射规则
        if not mapping or not isinstance(mapping, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="映射规则格式错误：必须是字典格式 {excel_column: db_field}"
            )

        required_fields = list(REQUIRED_FIELDS.keys())

        # ====== 检查1：验证映射规则格式 ======
        # 检查是否有空的Excel列名或字段名
        empty_excel_cols = [col for col in mapping.keys() if not col or not col.strip()]
        if empty_excel_cols:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"映射规则包含空的Excel列名: {empty_excel_cols}"
            )

        # ====== 检查2：检查重复的Excel列名（去除空格后） ======
        excel_cols_normalized = {}
        duplicate_excel_cols = []
        for excel_col in mapping.keys():
            normalized = excel_col.strip().lower()
            if normalized in excel_cols_normalized:
                duplicate_excel_cols.append(f"'{excel_col}' 和 '{excel_cols_normalized[normalized]}'")
            else:
                excel_cols_normalized[normalized] = excel_col

        if duplicate_excel_cols:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"发现重复的Excel列名（去除空格后相同）: {', '.join(duplicate_excel_cols)}。每个Excel列只能映射到一个字段。"
            )

        # ====== 检查3：检查多个Excel列映射到同一个数据库字段 ======
        mapped_fields = list(mapping.values())
        field_to_excel_cols = {}
        duplicate_field_mappings = []

        for excel_col, db_field in mapping.items():
            if db_field not in field_to_excel_cols:
                field_to_excel_cols[db_field] = []
            field_to_excel_cols[db_field].append(excel_col)

        # 找出被多个Excel列映射的字段
        for db_field, excel_cols in field_to_excel_cols.items():
            if len(excel_cols) > 1:
                duplicate_field_mappings.append(
                    f"字段 '{REQUIRED_FIELDS.get(db_field, db_field)}' ({db_field}) 被多个Excel列映射: {', '.join(excel_cols)}"
                )

        if duplicate_field_mappings:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"发现重复映射：一个数据库字段被多个Excel列映射。\n" + "\n".join(
                    duplicate_field_mappings) + "\n每个数据库字段只能被一个Excel列映射。"
            )

        # ====== 检查4：检查是否缺少必需字段 ======
        mapped_fields_set = set(mapped_fields)
        missing_fields = [field for field in required_fields if field not in mapped_fields_set]

        if missing_fields:
            missing_names = [REQUIRED_FIELDS[field] for field in missing_fields]
            logger.warning(
                f"用户 {current_user.username} 保存映射规则失败: "
                f"缺少必需字段映射 {missing_names}, "
                f"已映射字段: {list(mapped_fields_set)}, "
                f"映射规则: {mapping}"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"缺少必需字段映射: {', '.join(missing_names)}。请确保所有11个必需字段都已选择对应的Excel列。"
            )

        # ====== 检查5：验证映射值是否都是有效的字段名（包括必需字段和可选字段） ======
        all_valid_fields = list(ALL_FIELDS.keys())
        invalid_fields = [field for field in mapped_fields_set if field not in all_valid_fields]
        if invalid_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无效的字段名: {', '.join(invalid_fields)}。必须是以下字段之一: {', '.join(all_valid_fields)}"
            )

        # ====== 检查6：验证映射数量是否正确 ======
        if len(mapping) != len(required_fields):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"映射数量不正确：期望 {len(required_fields)} 个映射，实际 {len(mapping)} 个。可能存在重复或缺失的映射。"
            )

        # ====== 检查7：规范化Excel列名（去除前后空格） ======
        # 创建规范化的映射规则（去除Excel列名的前后空格）
        # 注意：检查2已经确保去除空格后不会重复，所以这里直接规范化即可
        normalized_mapping = {}
        for excel_col, db_field in mapping.items():
            normalized_excel_col = excel_col.strip()
            # 检查2已经确保规范化后不会重复，但如果出现（异常情况），记录错误
            if normalized_excel_col in normalized_mapping:
                logger.error(
                    f"规范化后出现重复的Excel列名: {normalized_excel_col}, "
                    f"原始列名: {excel_col}, 已存在映射: {normalized_mapping[normalized_excel_col]}"
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"规范化后出现重复的Excel列名: {normalized_excel_col}"
                )
            normalized_mapping[normalized_excel_col] = db_field

        # 使用规范化的映射规则
        mapping = normalized_mapping

        # ====== 合并已有映射规则 ======
        # 加载已有的映射规则（如果存在）
        existing_mapping = ColumnMappingService.load_user_mapping_rules()
        merged_mapping = {}

        if existing_mapping:
            # 先添加已有的映射规则
            merged_mapping.update(existing_mapping)
            logger.info(f"加载已有映射规则: {len(existing_mapping)} 条")

        # 合并新的映射规则（新规则会覆盖相同Excel列名的旧规则）
        new_mappings_count = 0
        updated_mappings_count = 0
        for excel_col, db_field in mapping.items():
            if excel_col in merged_mapping:
                # 如果Excel列名已存在，检查是否不同
                if merged_mapping[excel_col] != db_field:
                    logger.info(
                        f"更新映射规则: '{excel_col}' 从 '{merged_mapping[excel_col]}' 更新为 '{db_field}'"
                    )
                    updated_mappings_count += 1
                # 使用新的映射规则（覆盖旧规则）
                merged_mapping[excel_col] = db_field
            else:
                # 新的映射规则
                merged_mapping[excel_col] = db_field
                new_mappings_count += 1

        # 使用合并后的映射规则
        mapping = merged_mapping

        # 保存合并后的映射规则到文件
        mapping_data = {
            "created_at": get_app_now_naive().isoformat(),  # 使用北京时间
            "created_by": current_user.username,
            "mapping": mapping,
            "required_fields": required_fields,
            "mapping_count": len(mapping),
            "version": "1.0",  # 版本号，用于未来格式升级
            "update_info": {
                "new_mappings": new_mappings_count,
                "updated_mappings": updated_mappings_count,
                "total_mappings": len(mapping)
            }
        }

        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(MAPPING_RULES_FILE), exist_ok=True)

            # 使用临时文件写入，然后原子性重命名，避免文件损坏
            temp_file = MAPPING_RULES_FILE + ".tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(mapping_data, f, ensure_ascii=False, indent=2)

            # 原子性替换文件
            # 在Windows上，如果目标文件存在，os.rename会失败，所以先删除
            # 在Unix/Linux上，os.rename是原子的
            if os.path.exists(MAPPING_RULES_FILE):
                try:
                    os.remove(MAPPING_RULES_FILE)
                except OSError as e:
                    logger.warning(f"删除旧映射规则文件失败: {str(e)}")
                    # 如果删除失败，尝试重命名（Unix/Linux）
                    if os.name != 'nt':  # 非Windows系统
                        os.rename(MAPPING_RULES_FILE, MAPPING_RULES_FILE + ".old")

            # 原子性重命名临时文件
            try:
                os.rename(temp_file, MAPPING_RULES_FILE)
            except OSError as e:
                logger.error(f"重命名临时文件失败: {str(e)}")
                # 清理临时文件
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"保存映射规则文件失败: {str(e)}"
                )

            logger.info(
                f"用户 {current_user.username} 保存了列名映射规则: "
                f"文件={MAPPING_RULES_FILE}, 总映射数量={len(mapping)}, "
                f"新增={new_mappings_count}, 更新={updated_mappings_count}, "
                f"字段={list(set(mapping.values()))}"
            )
        except Exception as e:
            # 清理临时文件
            temp_file = MAPPING_RULES_FILE + ".tmp"
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
            raise

        return ResponseBaseSchema.success(data={
            "message": f"映射规则保存成功。总映射数量: {len(mapping)}，新增: {new_mappings_count}，更新: {updated_mappings_count}",
            "mapping": mapping,
            "mapped_count": len(mapping),
            "required_count": len(required_fields),
            "new_mappings": new_mappings_count,
            "updated_mappings": updated_mappings_count
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"保存映射规则失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"保存映射规则失败: {str(e)}"
        )


@router.post("/validate", response_model=ResponseBaseSchema[dict], summary="验证Excel列名映射")
async def validate_excel_columns(
        file: UploadFile = File(...),
        current_user: User = Depends(get_current_user)
):
    """
    验证Excel文件的列名映射
    - 优先使用用户保存的映射规则
    - 使用标准映射表和关键词匹配
    - 返回列名映射结果和缺失字段提示
    """
    try:
        # 验证文件并读取内容（使用公共验证函数）
        contents = await validate_excel_file(file)

        # 解析Excel（支持 .xlsx 和 .xls 格式）
        df = _read_excel_file(contents, file.filename)

        # 规范化Excel列名（确保编码正确）
        excel_columns_normalized = ColumnMappingService.normalize_excel_columns(df.columns)

        # 智能列名映射（会自动加载用户映射规则）
        column_mapping_result = ColumnMappingService.smart_column_mapping(excel_columns_normalized)

        # 生成建议
        recommendations = []
        if column_mapping_result["mapping_complete"]:
            recommendations.append("✅ 所有必需列都已成功映射")
        else:
            recommendations.append(f"⚠️ 缺失 {len(column_mapping_result['missing_columns'])} 个必需列")
            recommendations.append(f"缺失列: {', '.join(column_mapping_result['missing_columns'])}")

        recommendations.append(
            f"已映射 {column_mapping_result['mapped_count']}/{column_mapping_result['required_count']} 个字段")

        # 清理返回数据，确保JSON序列化安全
        excel_columns_clean = [ColumnMappingService.clean_string_for_json(col) for col in excel_columns_normalized]
        column_mapping_clean = column_mapping_result.copy()
        column_mapping_clean["mapping"] = ColumnMappingService.clean_mapping_for_json(column_mapping_result["mapping"])

        return ResponseBaseSchema.success(data={
            "column_mapping": column_mapping_clean,
            "excel_columns": excel_columns_clean,
            "recommendations": recommendations
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"验证Excel列名失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"验证Excel列名失败: {str(e)}"
        )


@router.get("/status", response_model=ResponseBaseSchema[dict], summary="获取映射规则状态")
async def get_mapping_status(
        current_user: User = Depends(get_current_user)
):
    """
    获取映射规则的状态信息
    - 用户映射规则文件是否存在
    - 必需字段列表
    """
    try:
        user_mapping_rules = ColumnMappingService.load_user_mapping_rules()

        status_info = {
            "mapping_rules_exists": os.path.exists(MAPPING_RULES_FILE),
            "has_user_mapping": user_mapping_rules is not None and len(user_mapping_rules) > 0,
            "required_fields": list(REQUIRED_FIELDS.keys()),
            "optional_fields": list(OPTIONAL_FIELDS.keys()),
            "all_fields": list(ALL_FIELDS.keys()),
            "field_names_cn": list(REQUIRED_FIELDS.values()),
            "optional_field_names_cn": list(OPTIONAL_FIELDS.values()),
            "total_fields": len(REQUIRED_FIELDS),
            "total_optional_fields": len(OPTIONAL_FIELDS)
        }

        if user_mapping_rules:
            status_info.update({
                "mapped_count": len(user_mapping_rules),
                "mapped_fields": list(user_mapping_rules.values())
            })

        return ResponseBaseSchema.success(data=status_info)

    except Exception as e:
        logger.error(f"获取映射规则状态失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取映射规则状态失败: {str(e)}"
        )


@router.get("/timezone", response_model=ResponseBaseSchema[dict], summary="获取应用时区配置")
async def get_timezone_config(
        current_user: User = Depends(get_current_user)
):
    """
    获取应用时区配置
    - 用于前端时间显示
    """
    try:
        return ResponseBaseSchema.success(data={
            "timezone": settings.TIMEZONE
        })
    except Exception as e:
        logger.error(f"获取时区配置失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取时区配置失败: {str(e)}"
        )


@router.post("/preview", response_model=ResponseBaseSchema[dict], summary="预览Excel数据")
async def preview_excel_data(
        file: UploadFile = File(...),
        rows: int = Query(10, ge=1, le=MAX_PAGE_SIZE, description="预览行数"),
        current_user: User = Depends(get_current_user)
):
    """
    预览Excel数据（映射后的数据）
    - 使用最新的映射规则进行数据映射
    - 返回前N行数据供预览
    """
    try:
        # 验证文件并读取内容（使用公共验证函数）
        contents = await validate_excel_file(file)

        # 解析Excel（支持 .xlsx 和 .xls 格式）
        df = _read_excel_file(contents, file.filename)

        # 规范化Excel列名
        excel_columns_normalized = ColumnMappingService.normalize_excel_columns(df.columns)

        # 智能列名映射（会自动加载用户映射规则）
        column_mapping_result = ColumnMappingService.smart_column_mapping(excel_columns_normalized)
        mapping = column_mapping_result["mapping"]

        # 如果映射不完整，仍然返回部分数据，但标记为不完整
        mapping_complete = column_mapping_result["mapping_complete"]

        # 重命名列
        df_mapped = df.copy()
        df_mapped.columns = excel_columns_normalized

        # 应用映射：将Excel列名映射到数据库字段名
        # mapping格式: {excel_column: db_field}
        # 需要创建 {excel_column: db_field} 的映射来重命名列
        column_rename_mapping = {}
        for excel_col, db_field in mapping.items():
            # excel_col 应该是规范化后的Excel列名
            # 确保excel_col在DataFrame的列中
            if excel_col in df_mapped.columns:
                column_rename_mapping[excel_col] = db_field

        if column_rename_mapping:
            df_mapped = df_mapped.rename(columns=column_rename_mapping)
            logger.debug(f"列名映射: {column_rename_mapping}")
        else:
            logger.warning(f"没有找到可映射的列，mapping: {mapping}, df_mapped.columns: {list(df_mapped.columns)}")

        # 只保留映射后的字段（包括必需字段和可选字段）
        all_fields = list(ALL_FIELDS.keys())
        available_fields = [f for f in all_fields if f in df_mapped.columns]

        # 如果没有可用字段，返回空数据
        if not available_fields:
            logger.warning(f"没有可用的映射字段，mapping: {mapping}, df_mapped.columns: {list(df_mapped.columns)}")
            return ResponseBaseSchema.success(data={
                "preview_data": [],
                "field_info": {},
                "total_rows": len(df),
                "preview_rows": 0,
                "mapping_complete": mapping_complete,
                "missing_columns": column_mapping_result.get("missing_columns", []) if not mapping_complete else []
            })

        df_preview = df_mapped[available_fields].head(rows)

        # 转换为字典列表
        preview_data = []
        for _, row in df_preview.iterrows():
            row_dict = {}
            for field in available_fields:
                value = row[field]
                # 处理NaN值
                if pd.isna(value):
                    row_dict[field] = None
                else:
                    # 清理值以确保JSON序列化安全
                    if isinstance(value, (int, float)):
                        row_dict[field] = value
                    elif isinstance(value, str):
                        row_dict[field] = ColumnMappingService.clean_string_for_json(value)
                    else:
                        row_dict[field] = str(value)
            preview_data.append(row_dict)

        # 构建字段信息（包含中文名称，支持必需字段和可选字段）
        field_info = {}
        for field in available_fields:
            field_info[field] = {
                "name": ALL_FIELDS.get(field, field),
                "key": field
            }

        logger.debug(
            f"预览数据: total_rows={len(df)}, preview_rows={len(preview_data)}, available_fields={available_fields}")

        return ResponseBaseSchema.success(data={
            "preview_data": preview_data,
            "field_info": field_info,
            "total_rows": len(df),
            "preview_rows": len(preview_data),
            "mapping_complete": mapping_complete,
            "missing_columns": column_mapping_result.get("missing_columns", []) if not mapping_complete else []
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"预览Excel数据失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"预览Excel数据失败: {str(e)}"
        )


@router.post("/import", response_model=ResponseBaseSchema[dict], summary="导入训练数据")
async def import_training_data(
        request: Request,
        file: UploadFile = File(...),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin),
        client_id: int | None = Query(
            None, description="指定客户ID，覆盖Excel中的客户信息"
        )
):
    """
    导入训练数据到数据库
    - 使用最新的映射规则进行数据映射
    - 验证数据完整性
    - 导入到ad_data表
    - 复用广告数据导入逻辑
    - 在导入前检查与已有数据的冲突
    """
    # 初始化冲突列表（在 try 块外定义，确保在所有情况下都可用）
    conflicts = []

    try:
        # 延迟导入，避免循环导入
        from app.api.api_v1.endpoints.excel.import_handler import (
            validate_and_read_excel, process_column_mapping, build_product_maps
        )

        # ====== 第一步：检查冲突 ======
        logger.info("开始检查训练数据冲突...")

        # 验证并读取Excel文件
        df, contents = await validate_and_read_excel(file)

        # 处理列名映射
        df, column_mapping_result = await process_column_mapping(df)

        # 构建产品映射（用于查找产品ID）
        product_map, product_name_map = await build_product_maps(db)

        # 收集本次要保存的数据（日期+产品ID）
        new_data_pairs = []
        new_data_details = []  # 保存详细信息用于打印

        for index, row in df.iterrows():
            try:
                date_value = row["date"]
                data_date = parse_date_value(date_value)
                product_name = str(row["product_name"]).strip()

                if not product_name:
                    continue

                # 查找产品ID
                matches = product_name_map.get(product_name, [])
                if matches:
                    product_id = matches[0]["product_id"] if len(matches) == 1 else (
                        next((m["product_id"] for m in matches if m["client_id"] == client_id), None)
                        if client_id else matches[0]["product_id"]
                    )
                    if product_id:
                        # 确保日期格式一致
                        if isinstance(data_date, datetime):
                            date_key = data_date.date()
                        else:
                            date_key = data_date

                        new_data_pairs.append((date_key, product_id))
                        new_data_details.append({
                            "row": index + 2,
                            "date": date_key,
                            "product_id": product_id,
                            "product_name": product_name,
                            "data": {
                                "request_count": row.get("request_count", 0),
                                "match_count": row.get("match_count", 0),
                                "display_count": row.get("display_count", 0),
                                "click_count": row.get("click_count", 0),
                                "cpc": row.get("cpc", 0.0),
                                "pageviews": row.get("pageviews", 0),
                                "ecpm_before_deduct": row.get("ecpm_before_deduct", 0),
                                "revenue_before_deduct": row.get("revenue_before_deduct", 0),
                            }
                        })
            except Exception as e:
                logger.warning(f"解析第 {index + 2} 行数据时出错: {str(e)}")
                continue

        # 查询数据库中已有的数据（conflicts 已在函数开始处初始化）
        if new_data_pairs:
            # 构建查询条件
            conditions = []
            for date, product_id in new_data_pairs:
                if isinstance(date, datetime):
                    date_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
                    date_end = date.replace(hour=23, minute=59, second=59, microsecond=999999)
                else:
                    date_start = datetime.combine(date, datetime.min.time())
                    date_end = datetime.combine(date, datetime.max.time())
                conditions.append(
                    and_(
                        AdData.date >= date_start,
                        AdData.date <= date_end,
                        AdData.product_id == product_id
                    )
                )

            if conditions:
                # 查询已存在的记录
                existing_query = select(AdData, Product).join(Product).where(or_(*conditions))
                existing_result = await db.execute(existing_query)

                # 构建已存在记录的映射
                existing_map = {}
                for ad_data, product in existing_result.all():
                    record_date = ad_data.date.date() if hasattr(ad_data.date, 'date') else ad_data.date
                    key = (record_date, ad_data.product_id)
                    existing_map[key] = {
                        "ad_data": ad_data,
                        "product": product
                    }

                # 检查冲突
                for new_data in new_data_details:
                    date_key = new_data["date"]
                    product_id = new_data["product_id"]
                    key = (date_key, product_id)

                    if key in existing_map:
                        existing = existing_map[key]
                        conflicts.append({
                            "new_data": new_data,
                            "existing_data": {
                                "id": existing["ad_data"].id,
                                "date": existing["ad_data"].date,
                                "product_id": existing["ad_data"].product_id,
                                "product_name": existing["product"].name,
                                "request_count": existing["ad_data"].request_count,
                                "match_count": existing["ad_data"].match_count,
                                "display_count": existing["ad_data"].display_count,
                                "click_count": existing["ad_data"].click_count,
                                "cpc": existing["ad_data"].cpc or 0.0,
                                "pageviews": existing["ad_data"].pageviews or 0,
                                "ecpm_before_deduct": existing["ad_data"].ecpm_before_deduct,
                                "revenue_before_deduct": existing["ad_data"].revenue_before_deduct,
                                "created_at": existing["ad_data"].created_at,
                                "updated_at": existing["ad_data"].updated_at,
                            }
                        })

        # 打印冲突信息
        if conflicts:
            logger.warning("=" * 80)
            logger.warning(f"⚠️ 发现 {len(conflicts)} 条训练数据冲突：")
            logger.warning("=" * 80)

            for i, conflict in enumerate(conflicts, 1):
                new = conflict["new_data"]
                existing = conflict["existing_data"]

                logger.warning(f"\n【冲突 {i}/{len(conflicts)}】")
                logger.warning(f"  日期: {new['date']}")
                logger.warning(f"  产品: {new['product_name']} (ID: {new['product_id']})")
                logger.warning(f"  Excel行号: 第 {new['row']} 行")
                logger.warning(f"\n  📥 本次要保存的数据：")
                logger.warning(f"    请求数: {new['data']['request_count']}")
                logger.warning(f"    匹配数: {new['data']['match_count']}")
                logger.warning(f"    展示数: {new['data']['display_count']}")
                logger.warning(f"    点击数: {new['data']['click_count']}")
                if 'cpc' in new['data'] and new['data']['cpc'] != 0.0:
                    logger.warning(f"    CPC: {new['data']['cpc']}")
                if 'pageviews' in new['data'] and new['data']['pageviews'] != 0:
                    logger.warning(f"    PageViews: {new['data']['pageviews']}")
                logger.warning(f"    eCPM: {new['data']['ecpm_before_deduct']}")
                logger.warning(f"    收益: {new['data']['revenue_before_deduct']}")
                logger.warning(f"\n  💾 数据库中已有的数据 (ID: {existing['id']})：")
                logger.warning(f"    请求数: {existing['request_count']}")
                logger.warning(f"    匹配数: {existing['match_count']}")
                logger.warning(f"    展示数: {existing['display_count']}")
                logger.warning(f"    点击数: {existing['click_count']}")
                if existing.get('cpc', 0.0) != 0.0:
                    logger.warning(f"    CPC: {existing['cpc']}")
                if existing.get('pageviews', 0) != 0:
                    logger.warning(f"    PageViews: {existing['pageviews']}")
                logger.warning(f"    eCPM: {existing['ecpm_before_deduct']}")
                logger.warning(f"    收益: {existing['revenue_before_deduct']}")
                logger.warning(f"    创建时间: {existing['created_at']}")
                logger.warning(f"    更新时间: {existing['updated_at']}")
                logger.warning(f"\n  ⚠️  注意: 导入时会更新已有记录，使用本次Excel中的数据覆盖数据库中的数据")
                logger.warning("-" * 80)

            logger.warning("=" * 80)
            logger.warning(f"总共发现 {len(conflicts)} 条冲突，导入时将更新这些记录")
            logger.warning("=" * 80)
        else:
            logger.info("✅ 未发现数据冲突，所有数据都是新数据")

        # ====== 第二步：执行导入 ======
        # 注意：UploadFile 对象可能不支持多次读取，需要重新创建文件对象
        # 使用之前读取的内容创建新的文件对象

        # 使用 BytesIO 创建新的文件对象
        file_like = BytesIO(contents)

        # 确保 content_type 正确设置
        content_type = getattr(file, 'content_type', None)
        if not content_type:
            # 根据文件扩展名推断 content_type
            filename_lower = (file.filename or "import.xlsx").lower()
            if filename_lower.endswith('.xlsx'):
                content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            elif filename_lower.endswith('.xls'):
                content_type = "application/vnd.ms-excel"
            else:
                content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        # 准备 headers（如果需要设置 content-type）
        headers = dict(file.headers) if hasattr(file, 'headers') and file.headers else {}
        if content_type:
            headers['content-type'] = content_type

        # 创建新的 UploadFile 对象
        new_file = StarletteUploadFile(
            filename=file.filename or "import.xlsx",
            file=file_like,
            headers=headers,
            size=len(contents)
        )

        # 延迟导入，避免循环导入
        from app.api.api_v1.endpoints.excel.import_handler import import_ad_data_handler
        
        # 调用实际的导入处理函数
        import_response = await import_ad_data_handler(
            file=new_file,
            db=db,
            current_user=current_user,
            client_id=client_id
        )

        # 记录导入操作
        await log_user_action(
            db=db,
            action_type="IMPORT",
            user=current_user,
            resource_type="AD_DATA",
            request=request,
            success=True,
            details={
                "filename": file.filename,
                "client_id": client_id,
                "imported_rows": import_response.imported_rows,
                "failed_rows": import_response.failed_rows,
                "total_rows": import_response.imported_rows + import_response.failed_rows,
                "source": "训练导入"
            }
        )

        # 构建返回消息：使用统一的导入消息构建函数
        message = build_import_message(
            imported_rows=import_response.imported_rows,
            failed_rows=import_response.failed_rows or 0,
            new_rows=import_response.new_rows or 0,
            updated_rows=import_response.updated_rows or 0,
            duplicate_rows=import_response.duplicate_rows or 0,
            separator="；",
            default_message="导入完成"
        )

        # 计算总行数（导入成功 + 失败）
        total_rows = import_response.imported_rows + (import_response.failed_rows or 0)

        # 准备冲突信息（简化版，用于返回给前端）
        conflicts_summary = []
        if conflicts:
            for conflict in conflicts:
                new = conflict["new_data"]
                existing = conflict["existing_data"]
                conflicts_summary.append({
                    "row": new["row"],
                    "date": str(new["date"]),
                    "product_name": new["product_name"],
                    "product_id": new["product_id"],
                    "existing_id": existing["id"],
                    "will_update": True  # 标记为将更新
                })

        return ResponseBaseSchema.success(data={
            "message": message,
            "status": import_response.status,
            "imported_rows": import_response.imported_rows,
            "failed_rows": import_response.failed_rows or 0,
            "new_rows": import_response.new_rows or 0,
            "updated_rows": import_response.updated_rows or 0,
            "duplicate_rows": import_response.duplicate_rows or 0,
            "total_rows": total_rows,
            "conflicts_count": len(conflicts),
            "conflicts": conflicts_summary,  # 冲突信息
            "error_details": import_response.error_details if import_response.error_details else []
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"导入训练数据失败: {str(e)}", exc_info=True)
        # 记录详细的错误信息，包括堆栈跟踪
        error_trace = traceback.format_exc()
        logger.error(f"错误堆栈跟踪:\n{error_trace}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"导入训练数据失败: {str(e)}。请查看服务器日志获取详细信息。"
        )
