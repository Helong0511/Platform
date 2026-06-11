"""国家信息维护 API

职责：管理员对国家/国家代码（countries 表）进行 CRUD 维护。

权限：所有端点均需管理员身份。
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.audit_log import commit_audit_log, log_create, log_delete, log_update
from app.core.constants import MAX_PAGE_SIZE
from app.core.database import get_db
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.security import require_admin
from app.models.models import CountryInfo, User
from app.schemas.base import ListResponseBaseSchema, PaginatedResponseBaseSchema, ResponseBaseSchema
from app.schemas.country import (
    CountryCreate,
    CountryResponse,
    CountryUpdate,
    UnrecognizedCountryCodeItem,
)
from app.services.country_service import collect_unrecognized_country_codes

router = APIRouter()
logger = logging.getLogger(__name__)


def _apply_keyword_filter(query, keyword: Optional[str]):
    """按关键字模糊匹配国家名称或代码。"""
    if not keyword or not keyword.strip():
        return query
    like_value = f"%{keyword.strip()}%"
    return query.where(
        or_(
            CountryInfo.alpha_2_code.like(like_value),
            CountryInfo.alpha_3_code.like(like_value),
            CountryInfo.country_name_zh.like(like_value),
            CountryInfo.country_name_en.like(like_value),
        )
    )


async def _get_country_or_404(db: AsyncSession, country_id: int) -> CountryInfo:
    result = await db.execute(select(CountryInfo).where(CountryInfo.id == country_id))
    country = result.scalars().first()
    if not country:
        raise_api_exception(ErrorCode.NOT_FOUND, detail=f"国家记录不存在：{country_id}")
    return country


async def _ensure_unique_codes(
    db: AsyncSession,
    *,
    alpha_2_code: Optional[str] = None,
    alpha_3_code: Optional[str] = None,
    numeric_code: Optional[str] = None,
    exclude_id: Optional[int] = None,
) -> None:
    """校验国家代码唯一性。"""
    checks = []
    if alpha_2_code:
        checks.append(("alpha_2_code", alpha_2_code, "国家二字代码"))
    if alpha_3_code:
        checks.append(("alpha_3_code", alpha_3_code, "国家三字代码"))
    if numeric_code:
        checks.append(("numeric_code", numeric_code, "国家数字代码"))

    for field_name, value, label in checks:
        query = select(CountryInfo).where(getattr(CountryInfo, field_name) == value)
        if exclude_id is not None:
            query = query.where(CountryInfo.id != exclude_id)
        result = await db.execute(query)
        if result.scalars().first():
            raise_api_exception(ErrorCode.VALIDATION_ERROR, detail=f"{label}已存在：{value}")


@router.get(
    "/",
    response_model=PaginatedResponseBaseSchema[list[CountryResponse]],
    summary="获取国家列表",
)
async def list_countries(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, description="每页数量"),
    keyword: Optional[str] = Query(None, description="关键字（名称或代码模糊搜索）"),
    continent: Optional[str] = Query(None, description="所属大洲"),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_admin),
):
    """分页查询国家列表，支持按名称/代码关键字及大洲筛选。"""
    query = select(CountryInfo)
    count_query = select(func.count(CountryInfo.id))

    query = _apply_keyword_filter(query, keyword)
    count_query = _apply_keyword_filter(count_query, keyword)

    if continent and continent.strip():
        continent_value = continent.strip()
        query = query.where(CountryInfo.continent == continent_value)
        count_query = count_query.where(CountryInfo.continent == continent_value)

    result = await db.execute(
        query.order_by(CountryInfo.alpha_2_code.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = result.scalars().all()
    total_result = await db.execute(count_query)
    total = total_result.scalar_one() or 0

    rows = [CountryResponse.model_validate(item) for item in items]
    return PaginatedResponseBaseSchema.success(
        data=rows,
        total=total,
        page=page,
        page_size=page_size,
        message="获取国家列表成功",
    )


@router.get(
    "/unrecognized",
    response_model=ListResponseBaseSchema[list[UnrecognizedCountryCodeItem]],
    summary="收集未识别的国家代码",
)
async def list_unrecognized_country_codes(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_admin),
):
    """
    扫描广告数据、TB 搜索数据及归档表，汇总未在 countries 表登记的国家代码。

    便于管理员快速补全国家信息；ZZ（全部区域）与已登记代码不在结果中。
    """
    items = await collect_unrecognized_country_codes(db)
    return ListResponseBaseSchema.success(
        data=items,
        count=len(items),
        message="获取未识别国家代码成功",
    )


@router.get(
    "/{country_id}",
    response_model=ResponseBaseSchema[CountryResponse],
    summary="获取国家详情",
)
async def get_country(
    country_id: int = Path(..., ge=1, description="国家ID"),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_admin),
):
    """按 ID 获取单条国家记录。"""
    country = await _get_country_or_404(db, country_id)
    return ResponseBaseSchema.success(
        data=CountryResponse.model_validate(country),
        message="获取国家详情成功",
    )


@router.post(
    "/",
    response_model=ResponseBaseSchema[CountryResponse],
    summary="创建国家",
)
async def create_country(
    request: Request,
    data: CountryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """新增国家记录，校验各代码唯一性。"""
    await _ensure_unique_codes(
        db,
        alpha_2_code=data.alpha_2_code,
        alpha_3_code=data.alpha_3_code,
        numeric_code=data.numeric_code,
    )

    country = CountryInfo(**data.model_dump())
    db.add(country)
    try:
        await db.commit()
        await db.refresh(country)
    except IntegrityError:
        await db.rollback()
        raise_api_exception(ErrorCode.VALIDATION_ERROR, detail="国家代码冲突，请检查二字/三字/数字代码是否重复")

    await log_create(
        db=db,
        user=current_user,
        resource_type="COUNTRY",
        resource_id=country.id,
        resource_name=f"{country.country_name_zh}({country.alpha_2_code})",
        request=request,
    )
    await commit_audit_log(db)
    return ResponseBaseSchema.success(
        data=CountryResponse.model_validate(country),
        message="创建国家成功",
    )


@router.put(
    "/{country_id}",
    response_model=ResponseBaseSchema[CountryResponse],
    summary="更新国家",
)
async def update_country(
    request: Request,
    country_id: int = Path(..., ge=1, description="国家ID"),
    data: CountryUpdate = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """更新国家记录，仅提交字段参与更新。"""
    country = await _get_country_or_404(db, country_id)
    update_fields = data.model_dump(exclude_unset=True)
    if not update_fields:
        return ResponseBaseSchema.success(
            data=CountryResponse.model_validate(country),
            message="无字段变更",
        )

    await _ensure_unique_codes(
        db,
        alpha_2_code=update_fields.get("alpha_2_code"),
        alpha_3_code=update_fields.get("alpha_3_code"),
        numeric_code=update_fields.get("numeric_code"),
        exclude_id=country_id,
    )

    for key, value in update_fields.items():
        setattr(country, key, value)

    try:
        await db.commit()
        await db.refresh(country)
    except IntegrityError:
        await db.rollback()
        raise_api_exception(ErrorCode.VALIDATION_ERROR, detail="国家代码冲突，请检查二字/三字/数字代码是否重复")

    await log_update(
        db=db,
        user=current_user,
        resource_type="COUNTRY",
        resource_id=country.id,
        resource_name=f"{country.country_name_zh}({country.alpha_2_code})",
        request=request,
        details={"updated_fields": list(update_fields.keys())},
    )
    await commit_audit_log(db)
    return ResponseBaseSchema.success(
        data=CountryResponse.model_validate(country),
        message="更新国家成功",
    )


@router.delete(
    "/{country_id}",
    response_model=ResponseBaseSchema[None],
    summary="删除国家",
)
async def delete_country(
    request: Request,
    country_id: int = Path(..., ge=1, description="国家ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """删除国家记录；关联归档表 country_code 将按外键规则置空。"""
    country = await _get_country_or_404(db, country_id)
    resource_name = f"{country.country_name_zh}({country.alpha_2_code})"

    await db.delete(country)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        logger.warning("删除国家失败 country_id=%s: %s", country_id, exc)
        raise_api_exception(ErrorCode.VALIDATION_ERROR, detail="删除失败，该国家代码仍被其他数据引用")

    await log_delete(
        db=db,
        user=current_user,
        resource_type="COUNTRY",
        resource_id=country_id,
        resource_name=resource_name,
        request=request,
    )
    await commit_audit_log(db)
    return ResponseBaseSchema.success(message="删除国家成功")
