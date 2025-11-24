"""
Excel导入处理模块
处理广告数据的Excel导入逻辑
"""
from fastapi import UploadFile, HTTPException, status, Query
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_, and_
from sqlalchemy.exc import IntegrityError
from typing import Any
import logging
import uuid
from io import BytesIO
from datetime import datetime

import pandas as pd
# 延迟导入 openpyxl，避免多进程环境下的导入问题

from app.core.database import get_db
from app.core.security import require_admin
from app.core.config import settings
from app.models.models import User, Client, Product, AdData
from app.core.country_code import find_country_code_by_any_format
from app.schemas.base import ResponseBaseSchema
from app.schemas.excel import ExcelImportResponse
from app.api.api_v1.endpoints.excel.utils import (
    allowed_file, ALLOWED_MIME_TYPES, parse_date_value, calculate_rates
)
from app.core.product_assignment import initialize_product_assignment
from datetime import date

logger = logging.getLogger(__name__)


async def validate_and_read_excel(file: UploadFile) -> tuple[pd.DataFrame, bytes]:
    """
    验证并读取Excel文件
    
    返回:
        (DataFrame, 文件内容bytes)
    """
    # 验证文件类型
    if file.content_type not in ALLOWED_MIME_TYPES or not allowed_file(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件类型。请上传Excel文件(.xlsx或.xls)"
        )

    # 读取文件内容
    max_size = settings.MAX_UPLOAD_SIZE
    contents = await file.read()

    # 检查文件大小
    if len(contents) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件大小超过限制（最大 {max_size / 1024 / 1024:.1f}MB）"
        )

    if not contents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
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
    if filename_lower.endswith('.xlsx'):
        engine = "openpyxl"
        if not is_xlsx:
            logger.warning(f"文件名是 .xlsx，但文件内容不是有效的 ZIP 格式（.xlsx 文件）")
    elif filename_lower.endswith('.xls'):
        engine = "xlrd"
        if not is_xls:
            logger.warning(f"文件名是 .xls，但文件内容不是有效的 OLE 格式（.xls 文件）")
    else:
        # 如果无法从文件名判断，尝试检测文件内容
        if is_xlsx:
            engine = "openpyxl"
            logger.info("通过文件内容检测到 .xlsx 格式")
        elif is_xls:
            engine = "xlrd"
            logger.info("通过文件内容检测到 .xls 格式")
        else:
            # 默认尝试 openpyxl，如果失败再尝试 xlrd
            engine = "openpyxl"
            logger.warning("无法确定文件格式，默认尝试 openpyxl 引擎")

    # 检查必要的库是否可用
    if engine == "xlrd":
        try:
            import xlrd
            logger.debug(f"xlrd 库已安装，版本: {xlrd.__version__ if hasattr(xlrd, '__version__') else 'unknown'}")
        except ImportError:
            logger.error("xlrd 库未安装，无法读取 .xls 格式文件")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="系统缺少 xlrd 库，无法读取 .xls 格式文件。请安装 xlrd 库或使用 .xlsx 格式文件。"
            )

    # 尝试解析Excel文件
    df = None
    last_error = None
    tried_engines = []

    # 首先尝试指定的引擎
    try:
        logger.debug(f"尝试使用 {engine} 引擎解析文件")
        df = pd.read_excel(BytesIO(contents), engine=engine)
        tried_engines.append(engine)
    except Exception as e:
        last_error = e
        error_msg = str(e)
        tried_engines.append(engine)
        logger.warning(f"使用 {engine} 引擎解析失败: {error_msg}")

        # 如果第一次尝试失败，尝试另一个引擎
        if engine == "openpyxl":
            # 尝试 xlrd
            try:
                import xlrd
                logger.info("尝试使用 xlrd 引擎解析文件（可能是 .xls 格式）")
                df = pd.read_excel(BytesIO(contents), engine="xlrd")
                engine = "xlrd"
                tried_engines.append("xlrd")
                logger.info("使用 xlrd 引擎解析成功")
            except ImportError:
                logger.error("xlrd 库未安装，无法尝试 .xls 格式")
            except Exception as e2:
                last_error = e2
                tried_engines.append("xlrd")
                logger.error(f"使用 xlrd 引擎也失败: {str(e2)}")
        elif engine == "xlrd":
            # 尝试 openpyxl
            try:
                logger.info("尝试使用 openpyxl 引擎解析文件（可能是 .xlsx 格式）")
                df = pd.read_excel(BytesIO(contents), engine="openpyxl")
                engine = "openpyxl"
                tried_engines.append("openpyxl")
                logger.info("使用 openpyxl 引擎解析成功")
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

        logger.error(f"Excel文件解析失败: {detail}。文件名: {file.filename}, 大小: {len(contents)}字节")

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )

    return df, contents


async def process_column_mapping(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    处理列名映射和验证
    
    返回:
        (处理后的DataFrame, 映射结果)
    """
    from app.api.api_v1.endpoints.ml_model import ColumnMappingService, REQUIRED_FIELDS

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
    optional_columns = ["coverage_rate", "display_rate", "click_rate", "ecpm_before_deduct"]
    missing_columns = [col for col in required_columns if col not in df.columns]

    # 规则2：字段映射不完整，报错不导入（完全基于训练数据，不能识别就不导入）
    if not mapping_complete:
        # 检查是否有错误信息（如：没有训练数据）
        error_msg = column_mapping_result.get("error")
        if error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )

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

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail
            )
        else:
            missing_mapped = column_mapping_result.get("missing_columns", [])
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"字段映射不完整，无法导入数据。缺少映射的字段: {', '.join(missing_mapped)}。"
                    f"\n\n系统完全基于训练数据进行智能识别，无法识别的列将不导入。"
                    f"\n请先在'导入训练'功能中保存完整的映射规则。"
                )
            )

    # 字段映射完整时，继续验证
    if missing_columns:
        missing_cn = [REQUIRED_FIELDS.get(col, col) for col in missing_columns]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Excel文件缺少必要的列: {', '.join(missing_cn)}。映射结果: {column_mapping_result}"
        )

    # 计算缺失的比率字段
    df = calculate_rates(df)

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


async def build_product_maps(
        db: AsyncSession
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """
    构建产品映射表
    
    返回:
        (product_map, product_name_map)
    """
    product_query = select(Product, Client)
    product_query = product_query.join(Client, Product.client_id == Client.id)
    product_result = await db.execute(product_query)
    products = product_result.unique().all()

    product_map: dict[str, dict[str, Any]] = {}
    product_name_map: dict[str, list[dict[str, Any]]] = {}

    for product, client in products:
        key = f"{client.id}_{product.name}"
        product_info = {
            "product_id": product.id,
            "client_id": client.id,
            "client_name": client.company_name,
            "product_name": product.name,
            "ecpm_deduct_ratio": product.ecpm_deduct_ratio,
            "revenue_deduct_ratio": product.revenue_deduct_ratio
        }
        product_map[key] = product_info

        if product.name not in product_name_map:
            product_name_map[product.name] = []
        product_name_map[product.name].append(product_info)

    return product_map, product_name_map


async def find_or_create_product(
        product_name: str,
        target_client_id: int | None,
        client_id: int | None,
        mapping_complete: bool,
        product_map: dict[str, dict[str, Any]],
        product_name_map: dict[str, list[dict[str, Any]]],
        db: AsyncSession,
        current_user: User
) -> dict[str, Any]:
    """
    查找或创建产品
    
    返回:
        产品信息字典
    """
    # 确定目标客户ID（查询参数优先）
    target_client_id = client_id or target_client_id

    # 首先尝试按产品名称查找
    matches = product_name_map.get(product_name, [])

    if len(matches) > 0:
        # 规则1.1：产品名称能找到客户
        if len(matches) == 1:
            product_info = matches[0]
            target_client_id = product_info["client_id"]
            logger.info(
                f"✅ 产品名称'{product_name}'找到客户，"
                f"使用产品ID: {product_info['product_id']}，客户ID: {target_client_id}"
            )
        else:
            # 多个匹配，优先使用指定客户ID的产品
            if target_client_id:
                matched_product = next(
                    (m for m in matches if m["client_id"] == target_client_id), None
                )
                if matched_product:
                    product_info = matched_product
                    logger.info(
                        f"✅ 产品名称'{product_name}'在客户ID {target_client_id} 中找到匹配"
                    )
                else:
                    product_info = matches[0]
                    target_client_id = product_info["client_id"]
                    client_list = [
                        f"客户ID {m['client_id']} ({m['client_name']})" for m in matches
                    ]
                    logger.warning(
                        f"产品名称'{product_name}'对应多个客户: {', '.join(client_list)}。"
                        f"使用第一个匹配的产品（客户ID: {target_client_id}）"
                    )
            else:
                product_info = matches[0]
                target_client_id = product_info["client_id"]
                client_list = [
                    f"客户ID {m['client_id']} ({m['client_name']})" for m in matches
                ]
                logger.warning(
                    f"产品名称'{product_name}'对应多个客户: {', '.join(client_list)}。"
                    f"使用第一个匹配的产品（客户ID: {target_client_id}）"
                )
        return product_info
    else:
        # 规则1.2：产品名称不能找到客户
        if mapping_complete:
            logger.info(
                f"✅ 映射完整，产品名称'{product_name}'找不到客户，"
                f"将创建新产品（默认客户为管理员）"
            )

            # 获取或创建默认客户
            create_client = None
            if not target_client_id:
                # 步骤1: 先查找"默认客户（导入数据）"
                # 不管是不是当前管理员的用户，只要有就直接使用，不用创建
                admin_client_query = select(Client).where(
                    Client.company_name == "默认客户（导入数据）"
                ).limit(1)
                admin_client_result = await db.execute(admin_client_query)
                create_client = admin_client_result.scalars().first()

                if create_client:
                    logger.info(
                        f"✅ 找到默认客户（导入数据）（ID: {create_client.id}，"
                        f"关联到用户ID: {create_client.user_id}），直接使用"
                    )
                else:
                    # 步骤2: 如果数据库中没有找到，检查会话中是否已经有待提交的默认客户对象
                    # 防止在同一个导入过程中重复创建
                    pending_default_client = None
                    try:
                        # 检查会话中的新对象（待提交的对象）
                        for obj in db.new:
                            if (isinstance(obj, Client) and 
                                obj.company_name == "默认客户（导入数据）"):
                                pending_default_client = obj
                                break
                    except AttributeError:
                        # 如果 db.new 不可用，尝试使用 identity_map
                        try:
                            for obj in db.identity_map.values():
                                if (isinstance(obj, Client) and 
                                    obj.company_name == "默认客户（导入数据）"):
                                    pending_default_client = obj
                                    break
                        except AttributeError:
                            pass
                    
                    if pending_default_client:
                        create_client = pending_default_client
                        logger.info(
                            f"✅ 在会话中找到待提交的默认客户（导入数据）（ID: {create_client.id if hasattr(create_client, 'id') else '待生成'}），直接使用"
                        )
                    else:
                        # 步骤3: 如果确实没有找到，才创建新的默认客户（关联到当前管理员用户）
                        logger.warning("没有找到默认客户（导入数据），将创建默认客户用于导入数据")
                        # 生成唯一的UUID作为客户密钥
                        client_key = str(uuid.uuid4())
                        create_client = Client(
                            user_id=current_user.id,
                            key=client_key,  # 必需字段：客户唯一标识UUID
                            company_name="默认客户（导入数据）",
                            is_active=True
                        )
                        db.add(create_client)
                        await db.flush()
                        await db.refresh(create_client)
                        logger.info(
                            f"✅ 已创建默认客户（导入数据）（ID: {create_client.id}，"
                            f"关联到用户: {current_user.username}）"
                        )

                target_client_id = create_client.id
                logger.info(
                    f"使用管理员的默认客户（ID: {target_client_id}，"
                    f"客户名称: {create_client.company_name}）创建产品"
                )
            else:
                # 验证指定的客户是否存在
                client_result = await db.execute(
                    select(Client).where(Client.id == target_client_id)
                )
                create_client = client_result.scalars().first()
                if not create_client:
                    raise ValueError(f"客户ID {target_client_id} 不存在")

            if not create_client:
                client_result = await db.execute(
                    select(Client).where(Client.id == target_client_id)
                )
                create_client = client_result.scalars().first()

            # 创建新产品（扣减比例设为0，不扣减）
            # 只有在产品已存在且有扣减比例时，才使用产品的扣减比例
            new_product = Product(
                client_id=target_client_id,
                name=product_name,
                ecpm_deduct_ratio=0.0,  # 新建产品默认不扣减
                revenue_deduct_ratio=0.0,  # 新建产品默认不扣减
                is_active=True
            )
            db.add(new_product)
            await db.flush()
            await db.refresh(new_product)

            # 初始化产品分配记录（确保新创建的产品有分配记录）
            try:
                product_start_date = date.today()
                await initialize_product_assignment(
                    db=db,
                    product_id=new_product.id,
                    client_id=target_client_id,
                    start_date=product_start_date
                )
                logger.info(
                    f"✅ 产品 {new_product.id} 的分配记录已初始化：客户 {target_client_id}，开始日期: {product_start_date}"
                )
            except Exception as e:
                logger.warning(
                    f"初始化产品分配记录失败: {str(e)}，但产品创建继续。"
                    f"产品ID: {new_product.id}，客户ID: {target_client_id}"
                )
                # 分配记录初始化失败不影响产品创建，继续执行

            product_info = {
                "product_id": new_product.id,
                "client_id": target_client_id,
                "client_name": create_client.company_name,
                "product_name": product_name,
                "ecpm_deduct_ratio": 0.0,  # 新建产品默认不扣减
                "revenue_deduct_ratio": 0.0  # 新建产品默认不扣减
            }

            # 添加到映射中
            key = f"{target_client_id}_{product_name}"
            product_map[key] = product_info
            product_name_map[product_name] = [product_info]

            logger.info(
                f"✅ 已创建新产品: {product_name} "
                f"(ID: {new_product.id}, 客户ID: {target_client_id}, "
                f"客户名称: {create_client.company_name})，扣减比例设为0（不扣减），"
                f"后续可手动修改客户和扣减比例"
            )

            return product_info
        else:
            raise ValueError(
                f"字段映射不完整，无法导入数据。产品 '{product_name}' 不存在且无法自动创建。"
            )


async def process_row_data(
        row: pd.Series,
        row_num: int,
        product_map: dict[str, dict[str, Any]],
        product_name_map: dict[str, list[dict[str, Any]]],
        mapping_complete: bool,
        client_id: int | None,
        db: AsyncSession,
        current_user: User,
        result: dict[str, Any],
        existing_records: dict[tuple[Any, int], AdData] | None = None
) -> None:
    """
    处理单行数据
    
    参数:
        row: DataFrame行
        row_num: Excel行号
        product_map: 产品映射
        product_name_map: 产品名称映射
        mapping_complete: 映射是否完整
        client_id: 客户ID（查询参数）
        db: 数据库会话
        current_user: 当前用户
        result: 结果字典（用于更新统计）
    """
    try:
        # 解析日期（Excel导入的日期默认是系统时区，不需要转换）
        date_value = row["date"]
        data_date = parse_date_value(date_value)

        # 获取产品名称
        product_name = str(row["product_name"]).strip()
        if not product_name:
            raise ValueError("产品名称不能为空")

        # 获取Excel中的client_id（如果存在）
        excel_client_id = None
        if "client_id" in row.index and pd.notna(row.get("client_id")):
            excel_client_id = int(row["client_id"])
        elif "客户ID" in row.index and pd.notna(row.get("客户ID")):
            excel_client_id = int(row["客户ID"])

        # 查找或创建产品
        product_info = await find_or_create_product(
            product_name=product_name,
            target_client_id=excel_client_id,
            client_id=client_id,
            mapping_complete=mapping_complete,
            product_map=product_map,
            product_name_map=product_name_map,
            db=db,
            current_user=current_user
        )

        # 确定扣减比例
        if product_info.get("product_name") != product_name:
            logger.info(
                f"产品名称不匹配（Excel: {product_name}, "
                f"数据库: {product_info.get('product_name')}），使用默认扣减比例（0）"
            )
            ecpm_deduct_ratio = 0.0
            revenue_deduct_ratio = 0.0
        else:
            ecpm_deduct_ratio = product_info["ecpm_deduct_ratio"]
            revenue_deduct_ratio = product_info["revenue_deduct_ratio"]

        # 解析数值字段
        try:
            request_count = int(row["request_count"])
            match_count = int(row["match_count"])
            display_count = int(row["display_count"])
            click_count = int(row["click_count"])
            revenue_before = float(row["revenue_before_deduct"])
            
            # 优先使用Excel表中的映射关系数据，如果不存在或为空/NaN，才按照计算公式计算
            # 覆盖率（匹配率）= 匹配数/请求数 * 100
            coverage_rate_val = row.get("coverage_rate")
            if coverage_rate_val is not None and pd.notna(coverage_rate_val) and str(coverage_rate_val).strip() != "":
                coverage_rate = float(coverage_rate_val)
            else:
                coverage_rate = (match_count / request_count * 100) if request_count > 0 else 0.0
            
            # 展示率 = 展示数/匹配数 * 100
            display_rate_val = row.get("display_rate")
            if display_rate_val is not None and pd.notna(display_rate_val) and str(display_rate_val).strip() != "":
                display_rate = float(display_rate_val)
            else:
                display_rate = (display_count / match_count * 100) if match_count > 0 else 0.0
            
            # 点击率 = 点击数/展示数 * 100
            click_rate_val = row.get("click_rate")
            if click_rate_val is not None and pd.notna(click_rate_val) and str(click_rate_val).strip() != "":
                click_rate = float(click_rate_val)
            else:
                click_rate = (click_count / display_count * 100) if display_count > 0 else 0.0
            
            # eCPM = 收益/展示数 * 1000
            ecpm_before_val = row.get("ecpm_before_deduct")
            if ecpm_before_val is not None and pd.notna(ecpm_before_val) and str(ecpm_before_val).strip() != "":
                ecpm_before = float(ecpm_before_val)
            else:
                ecpm_before = (revenue_before / display_count * 1000) if display_count > 0 else 0.0
                
        except (ValueError, TypeError) as e:
            raise ValueError(f"数值字段格式错误: {str(e)}")

        # 验证数值非负
        if request_count < 0 or match_count < 0 or display_count < 0 or click_count < 0:
            raise ValueError("请求数、匹配数、展示数和点击数不能为负数")
        if ecpm_before < 0 or revenue_before < 0:
            raise ValueError("eCPM和收益不能为负数")

        # 计算减扣后的值
        ecpm_after = ecpm_before * (1 - ecpm_deduct_ratio)
        revenue_after = revenue_before * (1 - revenue_deduct_ratio)

        logger.debug(
            f"产品: {product_name}, 客户ID: {product_info['client_id']}, "
            f"eCPM扣减比例: {ecpm_deduct_ratio}, 收益扣减比例: {revenue_deduct_ratio}, "
            f"eCPM: {ecpm_before} -> {ecpm_after}, 收益: {revenue_before} -> {revenue_after}"
        )

        # 检查是否已存在相同日期和产品的记录（使用预查询的结果或单独查询）
        existing_data = None
        if existing_records is not None:
            # 使用预查询的结果（优化性能）
            # 确保日期格式一致（使用date对象，不包含时间）
            if isinstance(data_date, datetime):
                date_key = data_date.date()
            else:
                date_key = data_date
            key = (date_key, product_info["product_id"])
            existing_data = existing_records.get(key)
        else:
            # 如果没有预查询结果，则单独查询（向后兼容）
            # 注意：AdData.date是DateTime类型，需要使用日期范围查询
            if isinstance(data_date, datetime):
                date_start = data_date.replace(hour=0, minute=0, second=0, microsecond=0)
                date_end = data_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            else:
                # data_date是date类型，转换为datetime范围
                date_start = datetime.combine(data_date, datetime.min.time())
                date_end = datetime.combine(data_date, datetime.max.time())

            # 获取国家代码（如果Excel中有，支持多种格式）
            # 支持的格式：alpha_2_code（二字母）、alpha_3_code（三字母）、numeric_code（数字）、country_name_en（英文名称）、country_name_zh（中文名称）、official_name_en（官方英文名称）、official_name_zh（官方中文名称）
            country_code = "ZZ"  # 默认值：全部区域
            country_input = None
            
            # 尝试从 "country_code" 或 "国家代码" 列获取
            if "country_code" in row.index and pd.notna(row.get("country_code")):
                country_input = str(row["country_code"]).strip()
            elif "国家代码" in row.index and pd.notna(row.get("国家代码")):
                country_input = str(row["国家代码"]).strip()
            
            if country_input:
                # 尝试根据多种格式查找国家代码
                found_country_code = await find_country_code_by_any_format(db, country_input)
                if found_country_code:
                    country_code = found_country_code
                else:
                    # 如果找不到，记录警告并使用默认值
                    logger.warning(
                        f"无法识别国家代码格式: {country_input}, "
                        f"日期={row.get('date', '未知')}, 产品={row.get('product_name', '未知')}, 使用默认值 'ZZ'"
                    )
                    country_code = "ZZ"
            
            # 构建国家代码匹配条件（与API数据处理逻辑一致）
            from sqlalchemy import or_
            if country_code == "ZZ":
                # 新数据是'ZZ'，匹配'ZZ'或NULL（向后兼容旧数据）
                country_condition = or_(
                    AdData.country_code == "ZZ",
                    AdData.country_code.is_(None)
                )
            else:
                # 新数据是具体国家代码，精确匹配
                country_condition = AdData.country_code == country_code
            
            existing_query = select(AdData).where(
                AdData.date >= date_start,
                AdData.date <= date_end,
                AdData.product_id == product_info["product_id"],
                country_condition  # 国家代码匹配条件
            )
            existing_result = await db.execute(existing_query)
            existing_data = existing_result.scalars().first()

        if existing_data:
            # 更新现有记录
            logger.info(
                f"⚠️ 数据库中存在重复记录: 日期={data_date}, "
                f"产品ID={product_info['product_id']}，将更新现有记录"
            )
            # 获取国家代码（如果Excel中有，支持多种格式）
            # 支持的格式：alpha_2_code（二字母）、alpha_3_code（三字母）、numeric_code（数字）、country_name_en（英文名称）、country_name_zh（中文名称）、official_name_en（官方英文名称）、official_name_zh（官方中文名称）
            country_code = "ZZ"  # 默认值：全部区域
            country_input = None
            
            # 尝试从 "country_code" 或 "国家代码" 列获取
            if "country_code" in row.index and pd.notna(row.get("country_code")):
                country_input = str(row["country_code"]).strip()
            elif "国家代码" in row.index and pd.notna(row.get("国家代码")):
                country_input = str(row["国家代码"]).strip()
            
            if country_input:
                # 尝试根据多种格式查找国家代码
                found_country_code = await find_country_code_by_any_format(db, country_input)
                if found_country_code:
                    country_code = found_country_code
                else:
                    # 如果找不到，记录警告并使用默认值
                    logger.warning(
                        f"无法识别国家代码格式: {country_input}, "
                        f"日期={row.get('date', '未知')}, 产品={row.get('product_name', '未知')}, 使用默认值 'ZZ'"
                    )
                    country_code = "ZZ"
            
            existing_data.country_code = country_code  # 更新国家代码
            existing_data.request_count = request_count
            existing_data.match_count = match_count
            existing_data.display_count = display_count
            existing_data.click_count = click_count
            existing_data.ecpm_before_deduct = ecpm_before
            existing_data.ecpm_after_deduct = ecpm_after
            existing_data.revenue_before_deduct = revenue_before
            existing_data.revenue_after_deduct = revenue_after
            # 如果Excel中提供了比率字段，使用Excel的值；否则使用计算值
            if coverage_rate_val is not None and pd.notna(coverage_rate_val) and str(coverage_rate_val).strip() != "":
                existing_data.coverage_rate = float(coverage_rate_val)
            else:
                existing_data.coverage_rate = coverage_rate
            if display_rate_val is not None and pd.notna(display_rate_val) and str(display_rate_val).strip() != "":
                existing_data.display_rate = float(display_rate_val)
            else:
                existing_data.display_rate = display_rate
            if click_rate_val is not None and pd.notna(click_rate_val) and str(click_rate_val).strip() != "":
                existing_data.click_rate = float(click_rate_val)
            else:
                existing_data.click_rate = click_rate
            # 如果基础数据有变化，重新计算比率字段（确保一致性）
            existing_data.calculate_rates()
            result["updated_rows"] += 1
            logger.debug(f"✅ 已更新记录: 日期={data_date}, 产品={product_name}")
        else:
            # 创建新记录
            # 注意：如果data_date是date类型，需要转换为datetime（使用当天的00:00:00）
            # Excel导入的日期默认是系统时区，不需要进行时区转换
            # 确保与数据库中的DateTime类型一致
            if isinstance(data_date, datetime):
                ad_data_date = data_date.replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                # data_date是date类型，转换为datetime（使用当天的00:00:00，系统时区）
                ad_data_date = datetime.combine(data_date, datetime.min.time())
            
            # 获取国家代码（如果Excel中有，支持多种格式）
            # 支持的格式：alpha_2_code（二字母）、alpha_3_code（三字母）、numeric_code（数字）、country_name_en（英文名称）、country_name_zh（中文名称）、official_name_en（官方英文名称）、official_name_zh（官方中文名称）
            country_code = "ZZ"  # 默认值：全部区域
            country_input = None
            
            # 尝试从 "country_code" 或 "国家代码" 列获取
            if "country_code" in row.index and pd.notna(row.get("country_code")):
                country_input = str(row["country_code"]).strip()
            elif "国家代码" in row.index and pd.notna(row.get("国家代码")):
                country_input = str(row["国家代码"]).strip()
            
            if country_input:
                # 尝试根据多种格式查找国家代码
                found_country_code = await find_country_code_by_any_format(db, country_input)
                if found_country_code:
                    country_code = found_country_code
                else:
                    # 如果找不到，记录警告并使用默认值
                    logger.warning(
                        f"无法识别国家代码格式: {country_input}, "
                        f"日期={row.get('date', '未知')}, 产品={row.get('product_name', '未知')}, 使用默认值 'ZZ'"
                    )
                    country_code = "ZZ"
            
            ad_data = AdData(
                date=ad_data_date,
                product_id=product_info["product_id"],
                country_code=country_code,  # 国家代码
                request_count=request_count,
                match_count=match_count,
                display_count=display_count,
                click_count=click_count,
                ecpm_before_deduct=ecpm_before,
                ecpm_after_deduct=ecpm_after,
                revenue_before_deduct=revenue_before,
                revenue_after_deduct=revenue_after
            )
            # 如果Excel中提供了比率字段，使用Excel的值；否则使用计算值
            if coverage_rate_val is not None and pd.notna(coverage_rate_val) and str(coverage_rate_val).strip() != "":
                ad_data.coverage_rate = float(coverage_rate_val)
            else:
                ad_data.coverage_rate = coverage_rate
            if display_rate_val is not None and pd.notna(display_rate_val) and str(display_rate_val).strip() != "":
                ad_data.display_rate = float(display_rate_val)
            else:
                ad_data.display_rate = display_rate
            if click_rate_val is not None and pd.notna(click_rate_val) and str(click_rate_val).strip() != "":
                ad_data.click_rate = float(click_rate_val)
            else:
                ad_data.click_rate = click_rate
            # 调用计算方法确保比率字段正确（如果基础数据有变化，会重新计算）
            ad_data.calculate_rates()
            db.add(ad_data)
            result["new_rows"] += 1
            logger.debug(f"✅ 已创建新记录: 日期={data_date}, 产品={product_name}")

            # 将新创建的记录添加到existing_records缓存中，以便后续行能检测到同一批数据中的重复
            # 这样可以避免同一批数据中的重复记录被插入（虽然数据库唯一性约束也会防止，但提前检测更好）
            if existing_records is not None:
                # 确保日期格式一致（使用date对象，不包含时间）
                if isinstance(data_date, datetime):
                    date_key = data_date.date()
                else:
                    date_key = data_date
                key = (date_key, product_info["product_id"])
                existing_records[key] = ad_data

        result["success_rows"] += 1

    except Exception as e:
        result["failed_rows"] += 1
        result["errors"].append({
            "row": row_num,
            "error": str(e)
        })


async def import_ad_data_handler(
        file: UploadFile,
        db: AsyncSession,
        current_user: User,
        client_id: int | None = None
) -> ExcelImportResponse:
    """
    导入广告数据的主处理函数
    
    返回:
        ExcelImportResponse对象
    """
    # 验证并读取Excel文件
    df, contents = await validate_and_read_excel(file)

    try:
        # 处理列名映射
        df, column_mapping_result = await process_column_mapping(df)
        mapping_complete = column_mapping_result.get("mapping_complete", False)

        # 准备导入结果
        result = {
            "total_rows": len(df),
            "success_rows": 0,
            "failed_rows": 0,
            "new_rows": 0,
            "updated_rows": 0,
            "duplicate_rows": 0,
            "errors": []
        }

        # 检查Excel内部重复数据
        excel_duplicate_map = check_excel_duplicates(df)
        excel_duplicates = {
            k: v for k, v in excel_duplicate_map.items() if len(v) > 1
        }

        # 构建需要跳过的行号集合（Excel内部重复时，只保留最后一行）
        rows_to_skip = set()
        if excel_duplicates:
            duplicate_count = sum(len(v) - 1 for v in excel_duplicates.values())
            result["duplicate_rows"] = duplicate_count
            for (dup_date, dup_product), dup_rows in excel_duplicates.items():
                # 只保留最后一行，跳过前面的重复行
                if len(dup_rows) > 1:
                    # 跳过除最后一行外的所有重复行
                    rows_to_skip.update(dup_rows[:-1])
                    logger.warning(
                        f"⚠️ Excel内部重复数据: 日期={dup_date}, 产品={dup_product}, "
                        f"行号={dup_rows}。将跳过前{len(dup_rows) - 1}行，只保留最后一行（第{dup_rows[-1]}行）。"
                    )
                    result["errors"].append({
                        "row": f"{', '.join(map(str, dup_rows[:-1]))}",
                        "error": (
                            f"Excel内部重复: 日期={dup_date}, 产品={dup_product}，"
                            f"已跳过前{len(dup_rows) - 1}行，只保留最后一行（第{dup_rows[-1]}行）"
                        )
                    })

        # 构建产品映射
        product_map, product_name_map = await build_product_maps(db)

        # 批量预查询数据库中可能重复的记录（优化性能）
        # 收集所有需要检查的日期和产品ID组合
        date_product_pairs = set()
        for index, row in df.iterrows():
            row_num = index + 2
            if row_num in rows_to_skip:
                continue
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
                        date_product_pairs.add((data_date, product_id))
            except Exception:
                continue

        # 批量查询数据库中已存在的记录（优化性能，减少数据库查询次数）
        existing_records = {}
        if date_product_pairs:
            conditions = []
            for date, product_id in date_product_pairs:
                # 确保日期格式正确（AdData.date是DateTime类型，需要转换为datetime进行比较）
                if isinstance(date, datetime):
                    # 如果已经是datetime，使用当天的开始时间
                    date_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
                    date_end = date.replace(hour=23, minute=59, second=59, microsecond=999999)
                else:
                    # 如果是date，转换为datetime（使用当天的00:00:00和23:59:59）
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
                existing_query = select(AdData).where(or_(*conditions))
                existing_result = await db.execute(existing_query)
                for record in existing_result.scalars().all():
                    # 使用日期（不包含时间）和产品ID作为key
                    record_date = record.date.date() if hasattr(record.date, 'date') else record.date
                    key = (record_date, record.product_id)
                    existing_records[key] = record
                logger.debug(f"批量查询到 {len(existing_records)} 条已存在的记录")

        # 处理每一行数据（跳过Excel内部重复的行）
        for index, row in df.iterrows():
            row_num = index + 2
            # 跳过Excel内部重复的行（只保留最后一行）
            if row_num in rows_to_skip:
                logger.debug(f"跳过Excel内部重复行: 第{row_num}行")
                continue

            await process_row_data(
                row=row,
                row_num=row_num,
                product_map=product_map,
                product_name_map=product_name_map,
                mapping_complete=mapping_complete,
                client_id=client_id,
                db=db,
                current_user=current_user,
                result=result,
                existing_records=existing_records  # 传入预查询的结果
            )

        # 提交事务
        try:
            await db.commit()
            logger.info(
                f"Ad data import completed. Success: {result['success_rows']}, "
                f"Failed: {result['failed_rows']}"
            )
        except IntegrityError as e:
            # 处理唯一性约束违反（数据库层面的重复检查）
            await db.rollback()
            error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
            logger.error(f"Ad data import commit failed: 唯一性约束违反 - {error_msg}")

            # 检查是否是唯一性约束错误
            if "uq_ad_data_date_product" in error_msg or "Duplicate entry" in error_msg or "UNIQUE constraint" in error_msg:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "导入失败：检测到重复数据。"
                        "可能是并发导入导致的，或者数据库中已存在相同日期和产品的记录。"
                        "请检查数据后重试。"
                    )
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"保存数据失败: {error_msg}"
                )
        except Exception as e:
            await db.rollback()
            logger.error(f"Ad data import commit failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"保存数据失败: {str(e)}"
            )

        # 构建响应
        error_details = []
        if result.get("errors"):
            for error in result["errors"]:
                if isinstance(error, dict):
                    error_details.append(
                        f"第{error.get('row', '?')}行: {error.get('error', '未知错误')}"
                    )
                else:
                    error_details.append(str(error))

        message_parts = [f"导入完成: 成功 {result['success_rows']} 条"]
        if result.get("new_rows", 0) > 0:
            message_parts.append(f"新增 {result['new_rows']} 条")
        if result.get("updated_rows", 0) > 0:
            message_parts.append(f"更新 {result['updated_rows']} 条")
        if result.get("duplicate_rows", 0) > 0:
            message_parts.append(f"Excel内部重复 {result['duplicate_rows']} 条")
        if result.get("failed_rows", 0) > 0:
            message_parts.append(f"失败 {result['failed_rows']} 条")

        import_response = ExcelImportResponse(
            message="，".join(message_parts),
            status=200,
            imported_rows=result["success_rows"],
            failed_rows=result.get("failed_rows", 0),
            new_rows=result.get("new_rows", 0),
            updated_rows=result.get("updated_rows", 0),
            duplicate_rows=result.get("duplicate_rows", 0),
            error_details=error_details if error_details else None
        )

        logger.info(
            f"导入统计: 总计 {result['total_rows']} 行，"
            f"成功 {result['success_rows']} 行（新增 {result.get('new_rows', 0)} 行，"
            f"更新 {result.get('updated_rows', 0)} 行），"
            f"Excel内部重复 {result.get('duplicate_rows', 0)} 行，"
            f"失败 {result.get('failed_rows', 0)} 行"
        )

        # 发送 Telegram 通知（仅在成功导入时）
        if result['success_rows'] > 0:
            try:
                from app.core.auto_bot import send_telegram_message
                import asyncio
                
                # 构建通知消息
                telegram_msg = f"📊 Excel 导入成功\n\n"
                telegram_msg += f"用户: {current_user.username}\n"
                telegram_msg += f"文件: {file.filename}\n"
                telegram_msg += f"总计: {result['total_rows']} 行\n"
                telegram_msg += f"✅ 成功: {result['success_rows']} 条"
                
                if result.get('new_rows', 0) > 0:
                    telegram_msg += f"（新增 {result['new_rows']} 条"
                if result.get('updated_rows', 0) > 0:
                    if result.get('new_rows', 0) > 0:
                        telegram_msg += f"，更新 {result['updated_rows']} 条）"
                    else:
                        telegram_msg += f"（更新 {result['updated_rows']} 条）"
                else:
                    if result.get('new_rows', 0) > 0:
                        telegram_msg += "）"
                
                if result.get('failed_rows', 0) > 0:
                    telegram_msg += f"\n❌ 失败: {result['failed_rows']} 条"
                
                # 异步发送消息（不阻塞响应）
                asyncio.create_task(send_telegram_message(telegram_msg))
            except Exception as telegram_err:
                # Telegram 通知失败不影响导入结果
                logger.warning(f"发送 Telegram 通知失败: {telegram_err}")

        return import_response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ad data import failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"导入广告数据失败: {str(e)}"
        )
    finally:
        await file.close()
