"""
广告数据处理工具模块
提供标准化的API数据后处理函数，供多个API调用
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.models.models import AdData, User
from app.api.api_v1.endpoints.excel.import_handler import (
    find_or_create_product,
    build_product_maps
)
from app.core.audit_log import log_user_action
from app.core.country_code import find_country_code_by_any_format
from app.core.utils import truncate_to_2_decimal

# 获取当前模块的日志记录器
logger = logging.getLogger(__name__)


async def check_and_notify_data_decrease(
    existing_data: Any,
    new_request_count: int,
    new_match_count: int,
    new_display_count: int,
    new_click_count: int,
    new_revenue_before: float,
    new_revenue_after: float,
    date_str: str,
    product_name: str,
    country_code: str,
    source: str = "API"
) -> None:
    """
    检查待更新数据是否比原有数据减少，如果减少则发送Telegram通知给管理员
    
    Args:
        existing_data: 数据库中现有的数据对象
        new_request_count: 新的请求数
        new_match_count: 新的匹配数
        new_display_count: 新的展示数
        new_click_count: 新的点击数
        new_revenue_before: 新的收益（减扣前）
        new_revenue_after: 新的收益（减扣后）
        date_str: 日期字符串
        product_name: 产品名称
        country_code: 国家代码
        source: 数据来源（默认"API"）
    """
    try:
        # 检查关键指标是否减少（减少量必须大于阈值才报告，避免浮点数精度问题导致的误报）
        decreased_fields = []
        # 浮点数类型的最小减少量阈值：至少减少0.01
        FLOAT_THRESHOLD = 0.01
        
        request_decrease = existing_data.request_count - new_request_count
        if request_decrease > 0:
            decreased_fields.append(f"请求数: 原有 {existing_data.request_count} → 新获取 {new_request_count} (减少 {request_decrease})")
        
        match_decrease = existing_data.match_count - new_match_count
        if match_decrease > 0:
            decreased_fields.append(f"匹配数: 原有 {existing_data.match_count} → 新获取 {new_match_count} (减少 {match_decrease})")
        
        display_decrease = existing_data.display_count - new_display_count
        if display_decrease > 0:
            decreased_fields.append(f"展示数: 原有 {existing_data.display_count} → 新获取 {new_display_count} (减少 {display_decrease})")
        
        click_decrease = existing_data.click_count - new_click_count
        if click_decrease > 0:
            decreased_fields.append(f"点击数: 原有 {existing_data.click_count} → 新获取 {new_click_count} (减少 {click_decrease})")
        
        revenue_before_decrease = existing_data.revenue_before_deduct - new_revenue_before
        if revenue_before_decrease > FLOAT_THRESHOLD:
            decreased_fields.append(f"收益(减扣前): 原有 {existing_data.revenue_before_deduct:.2f} → 新获取 {new_revenue_before:.2f} (减少 {revenue_before_decrease:.2f})")
        
        revenue_after_decrease = existing_data.revenue_after_deduct - new_revenue_after
        if revenue_after_decrease > FLOAT_THRESHOLD:
            decreased_fields.append(f"收益(减扣后): 原有 {existing_data.revenue_after_deduct:.2f} → 新获取 {new_revenue_after:.2f} (减少 {revenue_after_decrease:.2f})")
        
        # 如果有数据减少，发送通知
        if decreased_fields:
            from app.core.auto_bot import send_telegram_message
            import asyncio
            
            country_display = country_code if country_code else "未知"
            if country_code == "AA":
                country_display = "未知区域"
            elif country_code == "ZZ":
                country_display = "全部区域"
            
            telegram_msg = f"⚠️ 数据减少警告\n\n"
            telegram_msg += f"数据来源: {source}\n"
            telegram_msg += f"日期: {date_str}\n"
            telegram_msg += f"产品: {product_name}\n"
            telegram_msg += f"国家: {country_display}\n\n"
            telegram_msg += f"减少的字段:\n"
            for field in decreased_fields:
                telegram_msg += f"• {field}\n"
            
            # 发送通知（异步，不阻塞）
            try:
                await asyncio.wait_for(
                    send_telegram_message(telegram_msg),
                    timeout=5.0
                )
                logger.warning(
                    f"数据减少警告已发送: 日期={date_str}, 产品={product_name}, 国家={country_code}, "
                    f"减少字段数={len(decreased_fields)}"
                )
            except asyncio.TimeoutError:
                logger.warning(f"发送数据减少警告超时: 日期={date_str}, 产品={product_name}")
            except Exception as notify_err:
                logger.warning(f"发送数据减少警告失败: {notify_err}")
    except Exception as e:
        # 通知失败不应该影响数据更新流程
        logger.warning(f"检查数据减少时出错: {e}")


async def process_api_ad_data(
    data: List[Dict[str, Any]],
    db: AsyncSession,
    admin_user: User,
    source: str = "API",
    field_mapping: Optional[Dict[str, str]] = None
) -> Dict[str, int]:
    """
    标准化的API广告数据处理函数
    
    功能说明：
    1. 先按照日期、产品、国家检查是否有重复数据
    2. 识别不出来国家代码的数据，将数据累加后添加或更新到广告数据里
    3. 根据产品的减扣比例自动计算减扣后的eCPM和收益
    4. 如果数据已存在，会检查是否需要更新
    
    参数:
        data: API返回的数据列表，每条数据应包含以下字段（字段名通过field_mapping映射）：
            - date: 日期字符串 (YYYY-MM-DD格式)
            - product_name: 产品名称（通过field_mapping映射到API字段名，如"url"）
            - request_count: 请求次数 (通过field_mapping映射，如映射到"requests"，可选，默认0)
            - match_count: 匹配请求 (通过field_mapping映射，如映射到"matche_que"，可选，默认0)
            - display_count: 广告展示次数 (通过field_mapping映射，如映射到"adimpressions"，可选，默认0)
            - click_count: 点击数 (通过field_mapping映射，如映射到"clicks"，可选，默认0)
            - revenue_before_deduct: 预计收入 (通过field_mapping映射，如映射到"estirevenue"，可选，默认0)
            - ecpm_before_deduct: eCPM值 (通过field_mapping映射，如映射到"ecpm"，可选，会自动计算)
            - country_code: 国家代码（支持多种格式，如果无法识别则累加处理）
        db: 数据库会话
        admin_user: 管理员用户对象（用于产品查找/创建）
        source: 数据来源标识（用于日志记录，默认"API"）
        field_mapping: 字段映射字典，键为标准字段名，值为API返回的字段名
    
    返回:
        Dict[str, int]: 处理结果统计
            - inserted_count: 成功插入的数据条数
            - updated_count: 成功更新的数据条数
            - skipped_count: 跳过重复的数据条数
            - error_count: 处理出错的数据条数
    """
    # 字段映射函数
    def get_field(item: Dict[str, Any], field_name: str, default: Any = None) -> Any:
        """从数据项中获取字段值（严格按照传入的字段映射）"""
        if field_mapping and field_name in field_mapping:
            mapped_field = field_mapping[field_name]
        else:
            mapped_field = field_name
        return item.get(mapped_field, default)
    
    # ========== 构建产品映射（与Excel导入逻辑一致） ==========
    product_map, product_name_map = await build_product_maps(db)
    logger.debug(f"已构建产品映射: {len(product_map)} 个产品")
    
    # 初始化统计计数器
    inserted_count = 0
    updated_count = 0
    skipped_count = 0
    error_count = 0
    
    # ========== 第一步：预处理所有数据，识别国家代码并分组 ==========
    # 存储能识别国家代码的数据：不累加，每条单独存储
    recognized_data: List[Dict[str, Any]] = []
    
    # 存储无法识别国家代码的数据：key = (date_str, product_name), value = 累加的数据
    unrecognized_data: Dict[tuple, Dict[str, Any]] = {}
    
    # 遍历API返回的每条数据，进行预处理和分组
    for item in data:
        try:
            # 提取和验证基础字段
            item_date_str = get_field(item, "date", "")
            item_product_name = get_field(item, "product_name", "")
            
            # 验证日期
            if not item_date_str or not item_date_str.strip():
                logger.warning(f"日期为空，跳过该条数据")
                error_count += 1
                continue
            
            try:
                item_date = datetime.strptime(item_date_str.strip(), '%Y-%m-%d')
                item_date = item_date.replace(hour=0, minute=0, second=0, microsecond=0)
            except (ValueError, TypeError) as e:
                logger.warning(f"日期格式错误: {item_date_str}, 错误: {str(e)}, 跳过该条数据")
                error_count += 1
                continue
            
            # 验证产品名称
            if not item_product_name or not item_product_name.strip():
                logger.warning(f"产品名称为空，跳过该条数据")
                error_count += 1
                continue
            
            item_product_name = item_product_name.strip()
            
            # 解析数值字段
            try:
                item_request_count = int(get_field(item, "request_count", 0) or 0)
                item_match_count = int(get_field(item, "match_count", 0) or 0)
                item_display_count = int(get_field(item, "display_count", 0) or 0)
                item_click_count = int(get_field(item, "click_count", 0) or 0)
                item_revenue = float(get_field(item, "revenue_before_deduct", 0) or 0)
            except (ValueError, TypeError) as e:
                logger.warning(f"数值字段格式错误: {str(e)}, 跳过该条数据")
                error_count += 1
                continue
            
            # 计算eCPM
            item_ecpm_val = get_field(item, "ecpm_before_deduct")
            if item_ecpm_val is not None and item_ecpm_val != "":
                try:
                    item_ecpm = float(item_ecpm_val)
                except (ValueError, TypeError):
                    item_ecpm = (item_revenue / item_display_count * 1000) if item_display_count > 0 else 0.0
            else:
                item_ecpm = (item_revenue / item_display_count * 1000) if item_display_count > 0 else 0.0
            
            # 尝试识别国家代码
            item_country_input = get_field(item, "country_code", None)
            item_country_code = None
            
            if item_country_input and isinstance(item_country_input, str):
                item_country_input = item_country_input.strip()
                if item_country_input:
                    found_country_code = await find_country_code_by_any_format(db, item_country_input)
                    if found_country_code:
                        item_country_code = found_country_code
            
            # 根据是否能识别国家代码，分组数据
            if item_country_code:
                # 能识别国家代码，不累加，每条单独存储
                recognized_data.append({
                    "date_str": item_date_str,
                    "date": item_date,
                    "product_name": item_product_name,
                    "country_code": item_country_code,
                    "request_count": item_request_count,
                    "match_count": item_match_count,
                    "display_count": item_display_count,
                    "click_count": item_click_count,
                    "revenue": item_revenue,
                    "ecpm": item_ecpm
                })
            else:
                # 无法识别国家代码，按 (date_str, product_name) 分组累加
                key = (item_date_str, item_product_name)
                if key not in unrecognized_data:
                    unrecognized_data[key] = {
                        "date_str": item_date_str,
                        "date": item_date,
                        "product_name": item_product_name,
                        "request_count": 0,
                        "match_count": 0,
                        "display_count": 0,
                        "click_count": 0,
                        "revenue": 0.0,
                        "ecpm": 0.0,
                        "items": []  # 存储原始数据项，用于后续计算
                    }
                # 累加数据
                unrecognized_data[key]["request_count"] += item_request_count
                unrecognized_data[key]["match_count"] += item_match_count
                unrecognized_data[key]["display_count"] += item_display_count
                unrecognized_data[key]["click_count"] += item_click_count
                unrecognized_data[key]["revenue"] += item_revenue
                unrecognized_data[key]["items"].append({
                    "revenue": item_revenue,
                    "display_count": item_display_count,
                    "ecpm": item_ecpm
                })
                
                # 记录无法识别国家代码的警告
                logger.warning(
                    f"无法识别国家代码: [{item_country_input}], "
                    f"日期={item_date_str}, 产品={item_product_name}, "
                    f"将累加后使用'AA'（未知区域）作为国家代码"
                )
        
        except Exception as e:
            logger.error(f"预处理数据时出错: {str(e)}", exc_info=True)
            error_count += 1
            continue
    
    # ========== 第二步：处理能识别国家代码的数据（按日期、产品、国家检查重复，不累加，每条单独处理） ==========
    for item_data in recognized_data:
        async with db.begin_nested():
            try:
                date_str = item_data["date_str"]
                product_name = item_data["product_name"]
                country_code = item_data["country_code"]
                item_date = item_data["date"]
                
                # 查找或创建产品
                product_info = await find_or_create_product(
                    product_name=product_name,
                    target_client_id=None,
                    client_id=None,
                    mapping_complete=True,
                    product_map=product_map,
                    product_name_map=product_name_map,
                    db=db,
                    current_user=admin_user
                )
                
                product_id = product_info["product_id"]
                ecpm_deduct_ratio = product_info.get("ecpm_deduct_ratio", 0.0)
                revenue_deduct_ratio = product_info.get("revenue_deduct_ratio", 0.0)
                
                # 使用原始数据的eCPM（不累加）
                final_ecpm = item_data["ecpm"]
                total_revenue = item_data["revenue"]
                
                # 计算减扣后的值（截断到两位小数，不使用四舍五入）
                ecpm_after_deduct = truncate_to_2_decimal(final_ecpm * (1 - ecpm_deduct_ratio))
                revenue_after_deduct = truncate_to_2_decimal(total_revenue * (1 - revenue_deduct_ratio))
                
                # 检查数据是否重复（按日期、产品、国家）
                if isinstance(item_date, datetime):
                    date_start = item_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    date_end = item_date.replace(hour=23, minute=59, second=59, microsecond=999999)
                else:
                    date_start = datetime.combine(item_date, datetime.min.time())
                    date_end = datetime.combine(item_date, datetime.max.time())
                
                existing_query = select(AdData).where(
                    AdData.date >= date_start,
                    AdData.date <= date_end,
                    AdData.product_id == product_id,
                    AdData.country_code == country_code
                )
                existing_result = await db.execute(existing_query)
                existing_data = existing_result.scalars().first()
                
                # 处理数据（新建或更新）
                if existing_data:
                    # 检查数据是否减少（在更新之前）
                    await check_and_notify_data_decrease(
                        existing_data=existing_data,
                        new_request_count=item_data["request_count"],
                        new_match_count=item_data["match_count"],
                        new_display_count=item_data["display_count"],
                        new_click_count=item_data["click_count"],
                        new_revenue_before=total_revenue,
                        new_revenue_after=revenue_after_deduct,
                        date_str=date_str,
                        product_name=product_name,
                        country_code=country_code,
                        source=source
                    )
                    
                    # 检查是否需要更新
                    need_update = False
                    update_fields = []
                    
                    if existing_data.request_count != item_data["request_count"]:
                        need_update = True
                        update_fields.append(f"请求数: {existing_data.request_count} -> {item_data['request_count']}")
                        existing_data.request_count = item_data["request_count"]
                    
                    if existing_data.match_count != item_data["match_count"]:
                        need_update = True
                        update_fields.append(f"匹配数: {existing_data.match_count} -> {item_data['match_count']}")
                        existing_data.match_count = item_data["match_count"]
                    
                    if existing_data.display_count != item_data["display_count"]:
                        need_update = True
                        update_fields.append(f"展示数: {existing_data.display_count} -> {item_data['display_count']}")
                        existing_data.display_count = item_data["display_count"]
                    
                    if existing_data.click_count != item_data["click_count"]:
                        need_update = True
                        update_fields.append(f"点击数: {existing_data.click_count} -> {item_data['click_count']}")
                        existing_data.click_count = item_data["click_count"]
                    
                    # 如果基础数据有变化，重新计算比率字段
                    if need_update:
                        existing_data.calculate_rates()
                    
                    if abs(existing_data.ecpm_before_deduct - final_ecpm) > 0.01:
                        need_update = True
                        update_fields.append(f"eCPM(减扣前): {existing_data.ecpm_before_deduct:.2f} -> {final_ecpm:.2f}")
                        existing_data.ecpm_before_deduct = final_ecpm
                    
                    if abs(existing_data.revenue_before_deduct - total_revenue) > 0.01:
                        need_update = True
                        update_fields.append(f"收益(减扣前): {existing_data.revenue_before_deduct:.2f} -> {total_revenue:.2f}")
                        existing_data.revenue_before_deduct = total_revenue
                    
                    if abs(existing_data.ecpm_after_deduct - ecpm_after_deduct) > 0.01:
                        need_update = True
                        update_fields.append(f"eCPM(减扣后): {existing_data.ecpm_after_deduct:.2f} -> {ecpm_after_deduct:.2f}")
                        existing_data.ecpm_after_deduct = ecpm_after_deduct
                    
                    if abs(existing_data.revenue_after_deduct - revenue_after_deduct) > 0.01:
                        need_update = True
                        update_fields.append(f"收益(减扣后): {existing_data.revenue_after_deduct:.2f} -> {revenue_after_deduct:.2f}")
                        existing_data.revenue_after_deduct = revenue_after_deduct
                    
                    if need_update:
                        updated_count += 1
                        logger.info(
                            f"更新广告数据: 日期={date_str}, 产品={product_name}, 国家={country_code}, "
                            f"变化字段: {', '.join(update_fields)}"
                        )
                        
                        try:
                            await log_user_action(
                                db=db,
                                action_type="UPDATE",
                                username="SYSTEM",
                                resource_type="AD_DATA",
                                resource_id=existing_data.id,
                                resource_name=f"{product_name} - {date_str}",
                                ip_address=source,
                                success=True,
                                details={
                                    "date": date_str,
                                    "product_id": product_id,
                                    "product_name": product_name,
                                    "country_code": country_code,
                                    "update_fields": update_fields,
                                    "source": f"{source}自动更新"
                                }
                            )
                        except Exception as log_error:
                            logger.warning(f"记录广告数据更新操作日志失败: {log_error}")
                    else:
                        skipped_count += 1
                        logger.info(f"数据完全相同，跳过: 日期={date_str}, 产品={product_name}, 国家={country_code}")
                else:
                    # 创建新记录
                    if isinstance(item_date, datetime):
                        ad_data_date = item_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    else:
                        ad_data_date = datetime.combine(item_date, datetime.min.time())
                    
                    new_ad_data = AdData(
                        date=ad_data_date,
                        product_id=product_id,
                        country_code=country_code,
                        request_count=item_data["request_count"],
                        match_count=item_data["match_count"],
                        display_count=item_data["display_count"],
                        click_count=item_data["click_count"],
                        ecpm_before_deduct=final_ecpm,
                        ecpm_after_deduct=ecpm_after_deduct,
                        revenue_before_deduct=total_revenue,
                        revenue_after_deduct=revenue_after_deduct
                    )
                    # 计算并设置比率字段
                    new_ad_data.calculate_rates()
                    
                    db.add(new_ad_data)
                    await db.flush()
                    await db.refresh(new_ad_data)
                    inserted_count += 1
                    
                    logger.info(
                        f"添加广告数据: 日期={date_str}, 产品={product_name}, 国家={country_code}, "
                        f"请求数={item_data['request_count']}, 匹配数={item_data['match_count']}, "
                        f"展示数={item_data['display_count']}, 点击数={item_data['click_count']}, "
                        f"eCPM={final_ecpm:.2f}->{ecpm_after_deduct:.2f}, "
                        f"收益={total_revenue:.2f}->{revenue_after_deduct:.2f}"
                    )
                    
                    try:
                        await log_user_action(
                            db=db,
                            action_type="CREATE",
                            username="SYSTEM",
                            resource_type="AD_DATA",
                            resource_id=new_ad_data.id,
                            resource_name=f"{product_name} - {date_str}",
                            ip_address=source,
                            success=True,
                            details={
                                "date": date_str,
                                "product_id": product_id,
                                "product_name": product_name,
                                "country_code": country_code,
                                "request_count": item_data["request_count"],
                                "match_count": item_data["match_count"],
                                "display_count": item_data["display_count"],
                                "click_count": item_data["click_count"],
                                "ecpm_before_deduct": round(final_ecpm, 2),
                                "ecpm_after_deduct": round(ecpm_after_deduct, 2),
                                "revenue_before_deduct": round(total_revenue, 2),
                                "revenue_after_deduct": round(revenue_after_deduct, 2),
                                "source": f"{source}自动导入"
                            }
                        )
                    except Exception as log_error:
                        logger.warning(f"记录广告数据创建操作日志失败: {log_error}")
            
            except Exception as e:
                error_msg = str(e)
                if "IntegrityError" in str(type(e)) or "Duplicate entry" in error_msg or "uq_ad_data" in error_msg:
                    logger.warning(
                        f"数据重复冲突（唯一性约束）: 日期={date_str if 'date_str' in locals() else '未知'}, "
                        f"产品={product_name if 'product_name' in locals() else '未知'}, "
                        f"国家代码={country_code if 'country_code' in locals() else '未知'}, "
                        f"错误: {error_msg[:200]}"
                    )
                else:
                    logger.error(f"处理能识别国家代码的数据时出错: {error_msg}", exc_info=True)
                error_count += 1
    
    # ========== 第三步：处理无法识别国家代码的累加数据（按日期、产品检查重复，使用'AA'作为国家代码） ==========
    for key, grouped_data in unrecognized_data.items():
        async with db.begin_nested():
            try:
                date_str, product_name = key
                country_code = "AA"  # 使用'AA'（未知区域）作为无法识别国家代码的数据的国家代码
                
                # 查找或创建产品
                product_info = await find_or_create_product(
                    product_name=product_name,
                    target_client_id=None,
                    client_id=None,
                    mapping_complete=True,
                    product_map=product_map,
                    product_name_map=product_name_map,
                    db=db,
                    current_user=admin_user
                )
                
                product_id = product_info["product_id"]
                ecpm_deduct_ratio = product_info.get("ecpm_deduct_ratio", 0.0)
                revenue_deduct_ratio = product_info.get("revenue_deduct_ratio", 0.0)
                
                # 计算累加后的eCPM（加权平均）
                total_revenue = grouped_data["revenue"]
                total_display = grouped_data["display_count"]
                if total_display > 0:
                    calculated_ecpm = (total_revenue / total_display * 1000)
                else:
                    calculated_ecpm = 0.0
                
                final_ecpm = calculated_ecpm
                
                # 计算减扣后的值（截断到两位小数，不使用四舍五入）
                ecpm_after_deduct = truncate_to_2_decimal(final_ecpm * (1 - ecpm_deduct_ratio))
                revenue_after_deduct = truncate_to_2_decimal(total_revenue * (1 - revenue_deduct_ratio))
                
                # 检查数据是否重复（按日期、产品、国家代码'AA'）
                item_date = grouped_data["date"]
                if isinstance(item_date, datetime):
                    date_start = item_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    date_end = item_date.replace(hour=23, minute=59, second=59, microsecond=999999)
                else:
                    date_start = datetime.combine(item_date, datetime.min.time())
                    date_end = datetime.combine(item_date, datetime.max.time())
                
                existing_query = select(AdData).where(
                    AdData.date >= date_start,
                    AdData.date <= date_end,
                    AdData.product_id == product_id,
                    AdData.country_code == country_code
                )
                existing_result = await db.execute(existing_query)
                existing_data = existing_result.scalars().first()
                
                # 处理数据（新建或更新）
                if existing_data:
                    # 检查数据是否减少（在更新之前）
                    await check_and_notify_data_decrease(
                        existing_data=existing_data,
                        new_request_count=grouped_data["request_count"],
                        new_match_count=grouped_data["match_count"],
                        new_display_count=grouped_data["display_count"],
                        new_click_count=grouped_data["click_count"],
                        new_revenue_before=total_revenue,
                        new_revenue_after=revenue_after_deduct,
                        date_str=date_str,
                        product_name=product_name,
                        country_code=country_code,
                        source=f"{source}（无法识别国家代码，已累加）"
                    )
                    
                    # 检查是否需要更新
                    need_update = False
                    update_fields = []
                    
                    if existing_data.request_count != grouped_data["request_count"]:
                        need_update = True
                        update_fields.append(f"请求数: {existing_data.request_count} -> {grouped_data['request_count']}")
                        existing_data.request_count = grouped_data["request_count"]
                    
                    if existing_data.match_count != grouped_data["match_count"]:
                        need_update = True
                        update_fields.append(f"匹配数: {existing_data.match_count} -> {grouped_data['match_count']}")
                        existing_data.match_count = grouped_data["match_count"]
                    
                    if existing_data.display_count != grouped_data["display_count"]:
                        need_update = True
                        update_fields.append(f"展示数: {existing_data.display_count} -> {grouped_data['display_count']}")
                        existing_data.display_count = grouped_data["display_count"]
                    
                    if existing_data.click_count != grouped_data["click_count"]:
                        need_update = True
                        update_fields.append(f"点击数: {existing_data.click_count} -> {grouped_data['click_count']}")
                        existing_data.click_count = grouped_data["click_count"]
                    
                    # 如果基础数据有变化，重新计算比率字段
                    if need_update:
                        existing_data.calculate_rates()
                    
                    if abs(existing_data.ecpm_before_deduct - final_ecpm) > 0.01:
                        need_update = True
                        update_fields.append(f"eCPM(减扣前): {existing_data.ecpm_before_deduct:.2f} -> {final_ecpm:.2f}")
                        existing_data.ecpm_before_deduct = final_ecpm
                    
                    if abs(existing_data.revenue_before_deduct - total_revenue) > 0.01:
                        need_update = True
                        update_fields.append(f"收益(减扣前): {existing_data.revenue_before_deduct:.2f} -> {total_revenue:.2f}")
                        existing_data.revenue_before_deduct = total_revenue
                    
                    if abs(existing_data.ecpm_after_deduct - ecpm_after_deduct) > 0.01:
                        need_update = True
                        update_fields.append(f"eCPM(减扣后): {existing_data.ecpm_after_deduct:.2f} -> {ecpm_after_deduct:.2f}")
                        existing_data.ecpm_after_deduct = ecpm_after_deduct
                    
                    if abs(existing_data.revenue_after_deduct - revenue_after_deduct) > 0.01:
                        need_update = True
                        update_fields.append(f"收益(减扣后): {existing_data.revenue_after_deduct:.2f} -> {revenue_after_deduct:.2f}")
                        existing_data.revenue_after_deduct = revenue_after_deduct
                    
                    if need_update:
                        updated_count += 1
                        logger.info(
                            f"更新广告数据（无法识别国家代码，已累加）: 日期={date_str}, 产品={product_name}, 国家=AA, 变化字段: {', '.join(update_fields)}"
                        )
                        
                        try:
                            await log_user_action(
                                db=db,
                                action_type="UPDATE",
                                username="SYSTEM",
                                resource_type="AD_DATA",
                                resource_id=existing_data.id,
                                resource_name=f"{product_name} - {date_str}",
                                ip_address=source,
                                success=True,
                                details={
                                    "date": date_str,
                                    "product_id": product_id,
                                    "product_name": product_name,
                                    "country_code": country_code,
                                    "update_fields": update_fields,
                                    "source": f"{source}自动更新（无法识别国家代码，已累加）"
                                }
                            )
                        except Exception as log_error:
                            logger.warning(f"记录广告数据更新操作日志失败: {log_error}")
                    else:
                        skipped_count += 1
                        logger.info(f"数据完全相同，跳过: 日期={date_str}, 产品={product_name}, 国家=AA")
                else:
                    # 创建新记录
                    if isinstance(item_date, datetime):
                        ad_data_date = item_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    else:
                        ad_data_date = datetime.combine(item_date, datetime.min.time())
                    
                    new_ad_data = AdData(
                        date=ad_data_date,
                        product_id=product_id,
                        country_code=country_code,
                        request_count=grouped_data["request_count"],
                        match_count=grouped_data["match_count"],
                        display_count=grouped_data["display_count"],
                        click_count=grouped_data["click_count"],
                        ecpm_before_deduct=final_ecpm,
                        ecpm_after_deduct=ecpm_after_deduct,
                        revenue_before_deduct=total_revenue,
                        revenue_after_deduct=revenue_after_deduct
                    )
                    # 计算并设置比率字段
                    new_ad_data.calculate_rates()
                    
                    db.add(new_ad_data)
                    await db.flush()
                    await db.refresh(new_ad_data)
                    inserted_count += 1
                    
                    logger.info(
                        f"添加广告数据（无法识别国家代码，已累加）: 日期={date_str}, 产品={product_name}, 国家=AA, "
                        f"请求数={grouped_data['request_count']}, 匹配数={grouped_data['match_count']}, "
                        f"展示数={grouped_data['display_count']}, 点击数={grouped_data['click_count']}, "
                        f"eCPM={final_ecpm:.2f}->{ecpm_after_deduct:.2f}, "
                        f"收益={total_revenue:.2f}->{revenue_after_deduct:.2f}"
                    )
                    
                    try:
                        await log_user_action(
                            db=db,
                            action_type="CREATE",
                            username="SYSTEM",
                            resource_type="AD_DATA",
                            resource_id=new_ad_data.id,
                            resource_name=f"{product_name} - {date_str}",
                            ip_address=source,
                            success=True,
                            details={
                                "date": date_str,
                                "product_id": product_id,
                                "product_name": product_name,
                                "country_code": country_code,
                                "request_count": grouped_data["request_count"],
                                "match_count": grouped_data["match_count"],
                                "display_count": grouped_data["display_count"],
                                "click_count": grouped_data["click_count"],
                                "ecpm_before_deduct": round(final_ecpm, 2),
                                "ecpm_after_deduct": round(ecpm_after_deduct, 2),
                                "revenue_before_deduct": round(total_revenue, 2),
                                "revenue_after_deduct": round(revenue_after_deduct, 2),
                                "source": f"{source}自动导入（无法识别国家代码，已累加）"
                            }
                        )
                    except Exception as log_error:
                        logger.warning(f"记录广告数据创建操作日志失败: {log_error}")
            
            except Exception as e:
                error_msg = str(e)
                if "IntegrityError" in str(type(e)) or "Duplicate entry" in error_msg or "uq_ad_data" in error_msg:
                    logger.warning(
                        f"数据重复冲突（唯一性约束）: 日期={date_str if 'date_str' in locals() else '未知'}, "
                        f"产品={product_name if 'product_name' in locals() else '未知'}, "
                        f"国家代码=AA, 错误: {error_msg[:200]}"
                    )
                else:
                    logger.error(f"处理无法识别国家代码的数据时出错: {error_msg}", exc_info=True)
                error_count += 1
    
    # 返回处理结果统计
    return {
        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "error_count": error_count
    }
