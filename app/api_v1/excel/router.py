"""Excel 导入/导出 HTTP 路由

职责：暴露 /excel/import 与 /excel/export 端点，委托 import_handler / export_handler。

权限：需登录。

说明：Excel 批量导入/导出，支持广告数据等业务的表格批处理。"""
from datetime import date

from fastapi import APIRouter, Depends, UploadFile, File, Query, HTTPException
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log import log_user_action, commit_audit_log
from app.core.database import get_db
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.security import get_current_user, require_admin
from app.models.models import User
from app.schemas.base import ResponseBaseSchema
from app.schemas.excel import ExcelImportResponse
from .export_handler import export_ad_data_handler
from .import_handler import import_ad_data_handler

router = APIRouter()


@router.post(
    "/import/ad-data",
    response_model=ResponseBaseSchema[ExcelImportResponse],
    summary="导入广告数据"
)
async def import_ad_data(
        request: Request,
        file: UploadFile = File(...),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin),
        client_id: int | None = Query(
            None, description="指定客户ID，覆盖Excel中的客户信息"
        )
):
    """
    从Excel文件导入广告数据
    - 仅管理员可访问
    - 支持.xlsx和.xls格式
    - 验证数据格式和完整性
    - 批量导入广告数据
    - 返回导入结果和错误信息
    """
    # ---------- 入口：参数与依赖准备 ----------
    import_response = await import_ad_data_handler(
        file=file,
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
            "total_rows": import_response.imported_rows + import_response.failed_rows
        }
    )
    await commit_audit_log(db)

    # ---------- 构建响应 ----------
    return ResponseBaseSchema.success(data=import_response)


@router.get(
    "/export/ad-data",
    summary="导出广告数据"
)
async def export_ad_data(
        request: Request,
        start_date: date | None = Query(None, description="开始日期，格式YYYY-MM-DD"),
        end_date: date | None = Query(None, description="结束日期，格式YYYY-MM-DD"),
        product_id: int | None = Query(None, description="产品ID过滤"),
        client_id: int | None = Query(None, description="客户ID过滤"),
        country_code: str | None = Query(None, description="国家代码过滤"),
        ad_unit: str | None = Query(None, description="广告单元精确过滤"),
        dimension: str | None = Query(
            "country",
            description="统计维度：country=按国家，ad_unit=按广告单元，ad_unit_country=按广告单元+国家（country_ad_unit 为兼容别名）",
        ),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    导出广告数据到Excel文件
    - 客户只能导出自己的广告数据
    - 支持按日期范围和产品ID过滤
    - 成功时返回Excel文件流，失败时返回JSON错误响应
    """
    # ---------- 入口：参数与依赖准备 ----------
    # ---------- 异常处理 ----------
    try:
        response = await export_ad_data_handler(
            start_date=start_date,
            end_date=end_date,
            product_id=product_id,
            client_id=client_id,
            country_code=country_code,
            ad_unit=ad_unit,
            dimension=dimension,
            db=db,
            current_user=current_user
        )

        # 记录导出操作（仅在成功时记录）
        await log_user_action(
            db=db,
            action_type="EXPORT",
            user=current_user,
            resource_type="AD_DATA",
            request=request,
            success=True,
            details={
                "start_date": str(start_date) if start_date else None,
                "end_date": str(end_date) if end_date else None,
                "product_id": product_id,
                "client_id": client_id
            }
        )
        await commit_audit_log(db)

        return response
    except HTTPException:
        raise
    except Exception as e:
        # 如果已经是通过raise_api_exception抛出的异常，会由异常处理器处理
        # 这里捕获其他未预期的异常
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"导出数据失败：{str(e)}"
        )
