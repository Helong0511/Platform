"""广告数据 Excel 导入主处理"""
import asyncio
import logging

import pandas as pd
from fastapi import HTTPException, UploadFile
from sqlalchemy import or_, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api_v1.excel.ad_data_import.excel_reader import (
    check_excel_duplicates, process_column_mapping, validate_and_read_excel,
)
from app.api_v1.excel.ad_data_import.product_resolver import build_product_maps
from app.api_v1.excel.ad_data_import.row_processor import process_row_data
from app.api_v1.excel.utils import parse_date_value
from app.core.exceptions import handle_integrity_error, raise_api_exception
from app.core.errors import ErrorCode
from app.core.utils import format_error_details, build_import_message, normalize_date_for_ad_data
from app.core.ad_data_metadata import normalize_upstream_account
from app.core.country_code import normalize_ad_data_country_cache_key
from app.models.models import User, AdData, AdminNotificationConfig
from app.schemas.excel import ExcelImportResponse
from app.core.ad_data_processor import send_pending_data_decrease_warnings
from app.services.telegram_notification_service import TelegramNotificationService

logger = logging.getLogger(__name__)


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
    
    鉴权：由 Depends(get_current_user) 或 require_admin 控制；客户角色仅可操作自有数据。
    响应：统一 ResponseBaseSchema / PaginatedResponseBaseSchema 包装。
    """
    # ---------- 入口：参数与依赖准备 ----------
    # 验证并读取Excel文件
    df, contents = await validate_and_read_excel(file)

    # ---------- 异常处理 ----------
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
        # ---------- 条件分支 ----------
        if excel_duplicates:
            duplicate_count = sum(len(v) - 1 for v in excel_duplicates.values())
            result["duplicate_rows"] = duplicate_count
            # ---------- 循环处理 ----------
            for (dup_date, dup_product), dup_rows in excel_duplicates.items():
                # 只保留最后一行，跳过前面的重复行
                # ---------- 条件分支 ----------
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
        # ---------- 循环处理 ----------
        for index, row in df.iterrows():
            row_num = index + 2
            # ---------- 条件分支 ----------
            if row_num in rows_to_skip:
                continue
            # ---------- 异常处理 ----------
            try:
                date_value = row["date"]
                data_date = parse_date_value(date_value)
                product_name = str(row["product_name"]).strip()
                # ---------- 条件分支 ----------
                if not product_name:
                    continue
                # 查找产品ID
                matches = product_name_map.get(product_name, [])
                # ---------- 条件分支 ----------
                if matches:
                    product_id = matches[0]["product_id"] if len(matches) == 1 else (
                        next((m["product_id"] for m in matches if m["client_id"] == client_id), None)
                        if client_id else matches[0]["product_id"]
                    )
                    # ---------- 条件分支 ----------
                    if product_id:
                        date_product_pairs.add((data_date, product_id))
            except Exception:
                continue

        # 批量查询数据库中已存在的记录（优化性能，减少数据库查询次数）
        existing_records = {}
        # ---------- 条件分支 ----------
        if date_product_pairs:
            conditions = []
            # ---------- 循环处理 ----------
            for date, product_id in date_product_pairs:
                conditions.append(
                    and_(
                        AdData.date == normalize_date_for_ad_data(date),
                        AdData.product_id == product_id
                    )
                )
            # ---------- 条件分支 ----------
            if conditions:
                existing_query = select(AdData).where(or_(*conditions))
                existing_result = await db.execute(existing_query)
                # ---------- 循环处理 ----------
                for record in existing_result.scalars().all():
                    record_date = record.date
                    record_country = normalize_ad_data_country_cache_key(record.country_code)
                    key = (
                        record_date,
                        record.product_id,
                        record_country,
                        record.ad_unit or '',
                        record.data_source or 'legacy',
                        record.report_type or 'legacy',
                        normalize_upstream_account(record.upstream_account),
                    )
                    existing_records[key] = record
                logger.debug(f"批量查询到 {len(existing_records)} 条已存在的记录")

        # 处理每一行数据（跳过Excel内部重复的行）
        # ---------- 循环处理 ----------
        for index, row in df.iterrows():
            row_num = index + 2
            # 跳过Excel内部重复的行（只保留最后一行）
            # ---------- 条件分支 ----------
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

        # 注意：不需要手动提交事务，get_db 依赖会自动处理
        # 但如果需要捕获 IntegrityError 并给出特定错误消息，可以在提交前检查
        # 由于 get_db 会在函数正常返回时自动提交，我们只需要在提交前捕获可能的错误
        logger.info(
            f"Ad data import completed. Success: {result['success_rows']}, "
            f"Failed: {result['failed_rows']}"
        )

        # 提前刷新以触发可能的 IntegrityError（在 get_db 自动提交之前）
        # 这样可以在提交前捕获错误并给出更友好的错误消息
        # ---------- 异常处理 ----------
        try:
            await db.flush()  # 刷新到数据库但不提交，触发约束检查
        except IntegrityError as e:
            # 使用统一的 IntegrityError 处理函数
            handle_integrity_error(
                error=e,
                constraint_name="uq_ad_data_identity",
                custom_message=(
                    "导入失败：检测到重复数据。"
                    "可能是并发导入导致的，或者数据库中已存在相同日期和产品的记录。"
                    "请检查数据后重试。"
                ),
                log_context="Ad data import"
            )

        await send_pending_data_decrease_warnings(
            traffic_decreases=result.get("traffic_decreases") or [],
            metric_decreases=result.get("metric_decreases") or [],
        )

        if int(result.get("success_rows") or 0) > 0:
            try:
                from app.services.ad_data.query_cache import invalidate_ad_data_query_caches

                await invalidate_ad_data_query_caches(reason="excel_import")
            except Exception as cache_exc:
                logger.warning("Excel 导入后清理广告数据查询缓存失败: %s", cache_exc)

        # 构建响应：使用统一的错误详情格式化函数
        error_details = format_error_details(result.get("errors", []))

        # 使用统一的导入消息构建函数
        import_message = build_import_message(
            imported_rows=result['success_rows'],
            failed_rows=result.get("failed_rows", 0),
            new_rows=result.get("new_rows", 0),
            updated_rows=result.get("updated_rows", 0),
            duplicate_rows=result.get("duplicate_rows", 0),
            separator="，",
            default_message="导入完成"
        )

        import_response = ExcelImportResponse(
            message=import_message,
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
        # ---------- 条件分支 ----------
        if result['success_rows'] > 0:
            # 构建通知消息
            telegram_msg = f"📊 Excel 导入成功\n\n"
            telegram_msg += f"用户: {current_user.username}\n"
            telegram_msg += f"文件: {file.filename}\n"
            telegram_msg += f"总计: {result['total_rows']} 行\n"
            telegram_msg += f"✅ 成功: {result['success_rows']} 条"

            # ---------- 条件分支 ----------
            if result.get('new_rows', 0) > 0:
                telegram_msg += f"（新增 {result['new_rows']} 条"
            # ---------- 条件分支 ----------
            if result.get('updated_rows', 0) > 0:
                # ---------- 条件分支 ----------
                if result.get('new_rows', 0) > 0:
                    telegram_msg += f"，更新 {result['updated_rows']} 条）"
                else:
                    telegram_msg += f"（更新 {result['updated_rows']} 条）"
            else:
                # ---------- 条件分支 ----------
                if result.get('new_rows', 0) > 0:
                    telegram_msg += "）"

            # ---------- 条件分支 ----------
            if result.get('failed_rows', 0) > 0:
                telegram_msg += f"\n❌ 失败: {result['failed_rows']} 条"

            # 获取管理员配置并发送通知
            # ---------- 异常处理 ----------
            try:
                admin_config_result = await db.execute(
                    select(AdminNotificationConfig).where(AdminNotificationConfig.id == 1)
                )
                admin_config = admin_config_result.scalars().first()

                # ---------- 条件分支 ----------
                if (
                        admin_config
                        and admin_config.telegram_enabled
                        and admin_config.telegram_chat_id
                ):
                    await asyncio.wait_for(
                        TelegramNotificationService.send_admin_notification(
                            message=telegram_msg,
                            telegram_chat_id=admin_config.telegram_chat_id,
                            notification_type='statistics',
                            db=db
                        ),
                        timeout=120.0,
                    )
                    logger.info(
                        f"Telegram 通知发送成功，用户: {current_user.username}, 文件: {file.filename}, 成功: {result['success_rows']} 条")
            except asyncio.TimeoutError:
                logger.warning(f"发送 Telegram 通知超时，用户: {current_user.username}, 文件: {file.filename}")
            except Exception as e:
                logger.warning(f"发送 Telegram 通知失败: {str(e)}")

        return import_response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ad data import failed: {str(e)}")
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"导入广告数据失败: {str(e)}"
        )
    finally:
        await file.close()
