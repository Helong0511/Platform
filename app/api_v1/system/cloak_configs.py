"""
斗篷配置管理 API
"""
import logging
import socket
import time
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, File, Path, Query, Request, UploadFile
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import MAX_PAGE_SIZE
from app.core.cloak_scripts_paths import (
    MAX_BRIDGE_HTML_BYTES,
    bridge_html_exists,
    invalidate_bridge_template_cache,
    resolve_bridge_html_write_path,
    validate_bridge_html_bytes,
)
from app.core.database import get_db
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.security import require_admin
from app.models.models import CloakConfig, User
from app.schemas.base import PaginatedResponseBaseSchema, ResponseBaseSchema
from app.schemas.cloak import (
    CloakConfigCreate,
    CloakConfigResponse,
    CloakConfigUpdate,
    TestCloakReportRequest,
)
from app.services.cloak_pixel_mapping import invalidate_cloak_cache_for_dp

router = APIRouter()
logger = logging.getLogger(__name__)


def _bridge_usability_fields(cloak_name: str) -> dict:
    """磁盘上是否存在 {cloak_name}.html（与 /change 读取路径一致）。"""
    present = bridge_html_exists(cloak_name)
    return {"bridge_html_present": present, "is_usable": present}


def _ensure_enabled_requires_bridge_html(cloak_name: str, is_enabled: bool) -> None:
    if is_enabled and not bridge_html_exists(cloak_name):
        raise_api_exception(
            ErrorCode.VALIDATION_ERROR,
            detail=f"启用斗篷前须先上传对应桥页 HTML（{cloak_name}.html）。无桥页文件时该斗篷不可用。",
        )


def _mask_token(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 10:
        return "******"
    return f"{token[:6]}******{token[-4:]}"


def _resolve_real_client_ip(request: Request) -> str:
    x_forwarded_for = request.headers.get("x-forwarded-for", "")
    if x_forwarded_for:
        # x-forwarded-for 可能是逗号分隔，取第一个来源地址
        return x_forwarded_for.split(",")[0].strip()
    x_real_ip = request.headers.get("x-real-ip", "")
    if x_real_ip:
        return x_real_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"


def _resolve_real_user_agent(request: Request) -> str:
    user_agent = request.headers.get("user-agent", "").strip()
    return user_agent or f"server/{socket.gethostname()}"


def _build_facebook_payload(test_data: TestCloakReportRequest, client_ip: str, client_user_agent: str) -> dict:
    current_ts = int(time.time())
    user_data = {
        "client_ip_address": client_ip,
        "client_user_agent": client_user_agent,
        "fbc": f"fb.1.{current_ts}.{test_data.adsid}",
    }
    if test_data.use_hash:
        from app.core.third_party_report import sha256_hash
        user_data["em"] = sha256_hash(test_data.email)
        user_data["ph"] = sha256_hash(test_data.phone)
    else:
        user_data["em"] = test_data.email
        user_data["ph"] = test_data.phone

    return {
        "data": [
            {
                "event_name": test_data.event,
                "event_time": current_ts,
                "action_source": "website",
                "event_id": "cloak-test-event-id",
                "user_data": user_data,
            }
        ]
    }


async def _send_test_report(
    pixel_id: str,
    access_token: str,
    payload: dict,
    api_version: str = "v21.0",
) -> dict:
    request_url = f"https://graph.facebook.com/{api_version}/{pixel_id}/events"
    request_query = {"access_token": access_token}
    masked_request_query = {"access_token": _mask_token(access_token)}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(request_url, json=payload, params=request_query)
        return {
            "request_url": request_url,
            "request_query": masked_request_query,
            "request_body": payload,
            "response_status": response.status_code,
            "response_body": response.text,
            "success": 200 <= response.status_code < 300,
        }
    except Exception as exc:
        return {
            "request_url": request_url,
            "request_query": masked_request_query,
            "request_body": payload,
            "response_status": None,
            "response_body": None,
            "success": False,
            "error": str(exc),
        }


@router.get(
    "/",
    response_model=PaginatedResponseBaseSchema[list[CloakConfigResponse]],
    summary="获取斗篷配置列表",
)
async def list_cloak_configs(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, description="每页数量"),
    cloak_name: Optional[str] = Query(None, description="按斗篷名称搜索"),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_admin),
):
    query = select(CloakConfig)
    count_query = select(func.count(CloakConfig.id))
    if cloak_name:
        like_value = f"%{cloak_name.strip()}%"
        query = query.where(CloakConfig.cloak_name.like(like_value))
        count_query = count_query.where(CloakConfig.cloak_name.like(like_value))

    result = await db.execute(query.order_by(CloakConfig.id.desc()).offset((page - 1) * page_size).limit(page_size))
    items = result.scalars().all()
    total_result = await db.execute(count_query)
    total = total_result.scalar_one() or 0

    rows = []
    for item in items:
        row = CloakConfigResponse.model_validate(item)
        rows.append(row.model_copy(update=_bridge_usability_fields(item.cloak_name)))

    return PaginatedResponseBaseSchema.success(
        data=rows,
        total=total,
        page=page,
        page_size=page_size,
        message="获取斗篷配置成功",
    )


@router.post(
    "/",
    response_model=ResponseBaseSchema[CloakConfigResponse],
    summary="创建斗篷配置",
)
async def create_cloak_config(
    data: CloakConfigCreate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_admin),
):
    exists_result = await db.execute(
        select(CloakConfig).where(CloakConfig.cloak_name == data.cloak_name)
    )
    if exists_result.scalars().first():
        raise_api_exception(ErrorCode.VALIDATION_ERROR, detail=f"斗篷名称已存在：{data.cloak_name}")

    _ensure_enabled_requires_bridge_html(data.cloak_name, data.is_enabled)

    config = CloakConfig(**data.model_dump())
    db.add(config)
    await db.commit()
    await db.refresh(config)
    resp = CloakConfigResponse.model_validate(config).model_copy(update=_bridge_usability_fields(config.cloak_name))
    return ResponseBaseSchema.success(data=resp, message="创建斗篷配置成功")


@router.put(
    "/{config_id}",
    response_model=ResponseBaseSchema[CloakConfigResponse],
    summary="更新斗篷配置",
)
async def update_cloak_config(
    config_id: int = Path(..., ge=1, description="配置ID"),
    data: CloakConfigUpdate = ...,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_admin),
):
    result = await db.execute(select(CloakConfig).where(CloakConfig.id == config_id))
    config = result.scalars().first()
    if not config:
        raise_api_exception(ErrorCode.RESOURCE_NOT_FOUND, detail="斗篷配置不存在")

    old_cloak_name = config.cloak_name
    update_data = data.model_dump(exclude_unset=True)
    if "cloak_name" in update_data and update_data["cloak_name"] != config.cloak_name:
        duplicate_result = await db.execute(
            select(CloakConfig).where(CloakConfig.cloak_name == update_data["cloak_name"], CloakConfig.id != config_id)
        )
        if duplicate_result.scalars().first():
            raise_api_exception(ErrorCode.VALIDATION_ERROR, detail=f"斗篷名称已存在：{update_data['cloak_name']}")

    for key, value in update_data.items():
        setattr(config, key, value)

    _ensure_enabled_requires_bridge_html(config.cloak_name, config.is_enabled)

    await db.commit()
    await db.refresh(config)
    invalidate_cloak_cache_for_dp(old_cloak_name)
    if config.cloak_name != old_cloak_name:
        invalidate_cloak_cache_for_dp(config.cloak_name)

    resp = CloakConfigResponse.model_validate(config).model_copy(update=_bridge_usability_fields(config.cloak_name))
    return ResponseBaseSchema.success(data=resp, message="更新斗篷配置成功")


@router.post(
    "/{config_id}/bridge-html",
    response_model=ResponseBaseSchema[dict],
    summary="上传斗篷桥页 HTML",
)
async def upload_cloak_bridge_html(
    config_id: int = Path(..., ge=1, description="配置ID"),
    file: UploadFile = File(..., description="桥页 HTML 文件（UTF-8）"),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_admin),
):
    result = await db.execute(select(CloakConfig).where(CloakConfig.id == config_id))
    config = result.scalars().first()
    if not config:
        raise_api_exception(ErrorCode.RESOURCE_NOT_FOUND, detail="斗篷配置不存在")

    raw = await file.read(MAX_BRIDGE_HTML_BYTES + 1)
    if len(raw) > MAX_BRIDGE_HTML_BYTES:
        raise_api_exception(
            ErrorCode.VALIDATION_ERROR,
            detail=f"HTML 文件过大，最大允许 {MAX_BRIDGE_HTML_BYTES // (1024 * 1024)}MB",
        )

    filename = (file.filename or "").strip().lower()
    if filename and not filename.endswith(".html"):
        raise_api_exception(ErrorCode.VALIDATION_ERROR, detail="请上传 .html 文件")

    try:
        text = validate_bridge_html_bytes(raw)
    except ValueError as exc:
        raise_api_exception(ErrorCode.VALIDATION_ERROR, detail=str(exc))

    try:
        target_path = resolve_bridge_html_write_path(config.cloak_name)
    except (FileNotFoundError, PermissionError) as exc:
        raise_api_exception(ErrorCode.VALIDATION_ERROR, detail=str(exc))

    try:
        with open(target_path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    except OSError as exc:
        logger.exception("写入桥页 HTML 失败: %s", target_path)
        raise_api_exception(ErrorCode.VALIDATION_ERROR, detail=f"写入文件失败：{exc}")

    logger.warning("[斗篷管理] 已上传桥页 HTML：cloak_name=%s path=%s", config.cloak_name, target_path)
    invalidate_bridge_template_cache(target_path)
    invalidate_cloak_cache_for_dp(config.cloak_name)

    saved_filename = f"{config.cloak_name}.html"
    return ResponseBaseSchema.success(
        data={
            "cloak_name": config.cloak_name,
            "saved_as": saved_filename,
            "bytes_written": len(text.encode("utf-8")),
        },
        message="桥页 HTML 上传成功",
    )


@router.delete(
    "/{config_id}",
    response_model=ResponseBaseSchema[dict],
    summary="删除斗篷配置",
)
async def delete_cloak_config(
    config_id: int = Path(..., ge=1, description="配置ID"),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_admin),
):
    result = await db.execute(select(CloakConfig).where(CloakConfig.id == config_id))
    config = result.scalars().first()
    if not config:
        raise_api_exception(ErrorCode.RESOURCE_NOT_FOUND, detail="斗篷配置不存在")

    deleted_cloak_name = config.cloak_name
    await db.delete(config)
    await db.commit()
    invalidate_cloak_cache_for_dp(deleted_cloak_name)
    return ResponseBaseSchema.success(data={"id": config_id}, message="删除斗篷配置成功")


@router.post(
    "/{config_id}/test-report",
    response_model=ResponseBaseSchema[dict],
    summary="测试斗篷上报",
)
async def test_cloak_report(
    config_id: int = Path(..., ge=1, description="配置ID"),
    test_data: TestCloakReportRequest = ...,
    request: Request = ...,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_admin),
):
    result = await db.execute(select(CloakConfig).where(CloakConfig.id == config_id))
    config = result.scalars().first()
    if not config:
        raise_api_exception(ErrorCode.RESOURCE_NOT_FOUND, detail="斗篷配置不存在")

    client_ip = _resolve_real_client_ip(request)
    client_user_agent = _resolve_real_user_agent(request)
    payload = _build_facebook_payload(test_data, client_ip, client_user_agent)
    primary_result = await _send_test_report(config.pixel_id, config.access_token, payload)

    backup_result = None
    if config.backup_pixel_id and config.backup_access_token:
        backup_result = await _send_test_report(config.backup_pixel_id, config.backup_access_token, payload)

    return ResponseBaseSchema.success(
        data={
            "cloak_name": config.cloak_name,
            "is_enabled": config.is_enabled,
            "primary": primary_result,
            "backup": backup_result,
            "backup_skipped": backup_result is None,
        },
        message="测试上报完成",
    )
