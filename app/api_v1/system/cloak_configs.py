"""
斗篷配置管理 API

本模块提供后台管理员对「斗篷（Cloak）」配置的 CRUD、桥页 HTML 上传，以及 Facebook Conversions API（CAPI）
测试上报能力。

业务背景简述：
- 斗篷：对外投放使用的桥页/跳转方案，通过 cloak_name 标识（如 master），与磁盘上的 {cloak_name}.html 桥页文件对应。
- 上报分三阶段：load（桥页加载完成）、click（用户点击跳转）、postback（下游转化回传）。
- 每个斗篷绑定主/备 Facebook Pixel 及 Access Token，用于向 Meta 发送 CAPI 事件。

权限：所有接口均需管理员身份（require_admin）。
"""
import logging
import socket
import time
import uuid
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
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.security import require_admin
from app.core.audit_log import (
    log_create,
    log_update,
    log_delete,
    commit_audit_log,
)
from app.models.models import CloakConfig, User
from app.schemas.base import PaginatedResponseBaseSchema, ResponseBaseSchema
from app.schemas.cloak import (
    CloakConfigCreate,
    CloakConfigResponse,
    CloakConfigUpdate,
    TestCloakReportRequest,
)
from app.services.cloak_pixel_mapping import invalidate_cloak_cache_for_dp

# FastAPI 子路由，挂载于系统管理相关前缀下
router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 内部辅助函数：桥页可用性、校验、测试上报
# ---------------------------------------------------------------------------


def _bridge_usability_fields(cloak_name: str) -> dict:
    """
    根据磁盘上是否存在桥页 HTML，计算响应中的可用性字段。

    桥页文件命名规则：{cloak_name}.html，读取路径与对外 /change 接口一致。
    无桥页文件时斗篷不可对外启用（is_enabled 保存时也会被拦截）。

    Args:
        cloak_name: 斗篷名称

    Returns:
        包含 bridge_html_present、is_usable 的字典，二者当前逻辑相同（有文件即可用）
    """
    present = bridge_html_exists(cloak_name)
    return {"bridge_html_present": present, "is_usable": present}


def _ensure_enabled_requires_bridge_html(cloak_name: str, is_enabled: bool) -> None:
    """
    启用斗篷前校验：必须已上传对应桥页 HTML。

    防止管理员在后台勾选「启用」但线上 /change 无法渲染桥页，导致投放链路断裂。

    Args:
        cloak_name: 斗篷名称
        is_enabled: 是否启用

    Raises:
        API 校验异常：启用且无桥页文件时
    """
    if is_enabled and not bridge_html_exists(cloak_name):
        raise_api_exception(
            ErrorCode.VALIDATION_ERROR,
            detail=f"启用斗篷前须先上传对应桥页 HTML（{cloak_name}.html）。无桥页文件时该斗篷不可用。",
        )


def _mask_token(token: str) -> str:
    """
    对 Facebook Access Token 做脱敏，用于测试上报接口返回体，避免完整 Token 泄露到前端日志。

    规则：长度 > 10 时保留前 6 位与后 4 位，中间以 ****** 替代；否则整段替换为 ******。

    Args:
        token: 原始 Access Token

    Returns:
        脱敏后的字符串
    """
    if not token:
        return ""
    if len(token) <= 10:
        return "******"
    return f"{token[:6]}******{token[-4:]}"


def _resolve_real_client_ip(request: Request) -> str:
    """
    从 HTTP 请求中解析「真实客户端 IP」，供 CAPI user_data.client_ip_address 使用。

    优先级（与常见反向代理部署一致）：
    1. X-Forwarded-For 第一个地址（多级代理时最左侧通常为原始客户端）
    2. X-Real-IP
    3. request.client.host（直连场景）
    4. 本机 hostname 解析
    5. 兜底 127.0.0.1

    Args:
        request: FastAPI 请求对象

    Returns:
        解析到的 IP 字符串
    """
    x_forwarded_for = request.headers.get("x-forwarded-for", "")
    if x_forwarded_for:
        # x-forwarded-for 可能是逗号分隔的多跳代理链，取第一个为来源地址
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
    """
    解析用于 CAPI 的 User-Agent。

    测试上报时尽量使用管理员浏览器真实 UA，以贴近线上 website 来源；缺失时用 server/{hostname} 占位。

    Args:
        request: FastAPI 请求对象

    Returns:
        User-Agent 字符串
    """
    user_agent = request.headers.get("user-agent", "").strip()
    return user_agent or f"server/{socket.gethostname()}"


def _resolve_test_report_params(config: CloakConfig, phase: str) -> tuple[str, Optional[float], Optional[str]]:
    """
    按测试阶段从斗篷配置中解析 CAPI 事件名、金额与货币。

    三阶段与配置字段对应关系：
    - load：load_report_event / load_report_value / load_report_currency
    - click：report_event / report_value / report_currency（桥页按钮点击跳转）
    - postback：postback_report_event / postback_report_value / postback_report_currency

    postback 阶段若事件为 Purchase 且未配置固定金额，测试时使用默认 9.99；
    线上真实 postback 由处理器按 payout 动态填值。

    Args:
        config: 数据库中的斗篷配置实体
        phase: 阶段标识，load | click | postback

    Returns:
        (event_name, value, currency) 三元组；非 Purchase 事件时 value/currency 可能为 None
    """
    if phase == "load":
        return (
            config.load_report_event or "PageView",
            config.load_report_value,
            config.load_report_currency,
        )
    if phase == "postback":
        value = config.postback_report_value
        if config.postback_report_event == "Purchase" and value is None:
            # 转化 Purchase 未配固定金额时，测试用默认金额（线上由 postback payout 决定）
            value = 9.99
        return (
            config.postback_report_event or "Purchase",
            value,
            config.postback_report_currency,
        )
    # 默认 click 阶段
    return (
        config.report_event or "ViewContent",
        config.report_value,
        config.report_currency,
    )


def _validate_test_report_phase(config: CloakConfig, phase: str) -> None:
    """
    测试上报前校验：若该阶段事件为 Purchase，须具备有效金额（postback 可留空走测试默认）。

    与 Schema 层创建/更新校验互补：测试接口在发送 HTTP 请求前再次拦截无效配置。

    Args:
        config: 斗篷配置
        phase: load | click | postback

    Raises:
        API 校验异常：Purchase 且金额缺失或 ≤ 0（postback 除外，允许 None 走默认）
    """
    event, value, _currency = _resolve_test_report_params(config, phase)
    if event != "Purchase":
        return
    if value is None or float(value) <= 0:
        phase_labels = {
            "load": "加载完成上报（载）",
            "click": "点击跳转上报（点）",
            "postback": "Postback 转化上报（转）",
        }
        raise_api_exception(
            ErrorCode.VALIDATION_ERROR,
            detail=(
                f"{phase_labels.get(phase, phase)} 事件为 Purchase 时须先在斗篷配置中保存大于 0 的金额"
                f"{'（转化可留空以使用测试默认金额）' if phase == 'postback' else ''}，再执行测上报"
            ),
        )


def _build_facebook_payload(
    test_data: TestCloakReportRequest,
    client_ip: str,
    client_user_agent: str,
    *,
    report_event: str,
    report_value: Optional[float],
    report_currency: Optional[str],
) -> dict:
    """
    构造 Meta Conversions API POST /{pixel_id}/events 的请求 JSON 体。

    结构遵循官方单事件数组格式：{"data": [event_obj]}。
    user_data 包含 IP、UA、fbc（由 adsid 模拟点击 ID）、邮箱与手机（可选 SHA256 哈希）。
    Purchase 事件附加 custom_data.currency 与 custom_data.value。

    Args:
        test_data: 测试请求体（含 adsid、email、phone、use_hash 等）
        client_ip: 客户端 IP（通常来自 _resolve_real_client_ip）
        client_user_agent: 客户端 UA
        report_event: 事件名
        report_value: Purchase 金额，非 Purchase 可 None
        report_currency: ISO 4217 货币代码，默认 USD

    Returns:
        可直接作为 httpx post json= 的 dict
    """
    current_ts = int(time.time())
    # user_data：CAPI 用于匹配与归因的字段
    user_data = {
        "client_ip_address": client_ip,
        "client_user_agent": client_user_agent,
        # fbc 格式 fb.1.{timestamp}.{fbclid}，测试用 adsid 占位
        "fbc": f"fb.1.{current_ts}.{test_data.adsid}",
    }
    if test_data.use_hash:
        # 生产环境通常对 PII 做 SHA256；测试可切换明文对比 Graph API 行为
        from app.core.third_party_report import sha256_hash
        user_data["em"] = sha256_hash(test_data.email)
        user_data["ph"] = sha256_hash(test_data.phone)
    else:
        user_data["em"] = test_data.email
        user_data["ph"] = test_data.phone

    event_obj: dict = {
        "event_name": report_event,
        "event_time": current_ts,
        "action_source": "website",  # 桥页为网站来源
        "event_id": f"cloak-sim-{uuid.uuid4()}",  # 去重 ID，每次测试唯一
        "user_data": user_data,
    }
    # Meta 要求 Purchase 必须带 value + currency
    if report_event == "Purchase" and report_value is not None:
        cur = (report_currency or "USD").strip().upper() or "USD"
        event_obj["custom_data"] = {"currency": cur, "value": float(report_value)}

    return {"data": [event_obj]}


async def _send_test_report(
    pixel_id: str,
    access_token: str,
    payload: dict,
    api_version: Optional[str] = None,
) -> dict:
    """
    向 Facebook Graph API 发送单次测试上报，并封装请求/响应详情供管理端排查。

    超时 15 秒；异常时 success=False 并附带 error 字段，不向外抛出以免中断双像素测试流程。

    Args:
        pixel_id: Pixel ID
        access_token: 对应 Pixel 的 CAPI Access Token
        payload: _build_facebook_payload 产物
        api_version: Graph API 版本，默认读 settings.FACEBOOK_API_VERSION 或 v23.0

    Returns:
        含 request_url、脱敏 request_query、request_body、response_status、response_body、success 的字典
    """
    api_version = (api_version or settings.FACEBOOK_API_VERSION or "v23.0").strip()
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


# ---------------------------------------------------------------------------
# REST 接口：斗篷配置 CRUD、桥页上传、测试上报
# ---------------------------------------------------------------------------


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
    """
    分页列出所有斗篷配置，按 id 降序（新建在前）。

    支持 cloak_name 模糊搜索；每条记录合并磁盘桥页存在性（bridge_html_present / is_usable）。
    """
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

    # 将 ORM 转为响应 Schema，并附加桥页可用性（非数据库字段）
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
    request: Request,
    data: CloakConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    新建斗篷配置。

    校验：cloak_name 唯一；若 is_enabled=True 则须已存在桥页 HTML。
    写入审计日志（CLOAK_CONFIG / CREATE）。
    """
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
    await log_create(
        db=db,
        user=current_user,
        resource_type="CLOAK_CONFIG",
        resource_id=config.id,
        resource_name=config.cloak_name,
        request=request,
        details={"cloak_name": config.cloak_name, "is_enabled": config.is_enabled},
    )
    await commit_audit_log(db)
    resp = CloakConfigResponse.model_validate(config).model_copy(update=_bridge_usability_fields(config.cloak_name))
    return ResponseBaseSchema.success(data=resp, message="创建斗篷配置成功")


@router.put(
    "/{config_id}",
    response_model=ResponseBaseSchema[CloakConfigResponse],
    summary="更新斗篷配置",
)
async def update_cloak_config(
    request: Request,
    config_id: int = Path(..., ge=1, description="配置ID"),
    data: CloakConfigUpdate = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    部分更新斗篷配置（仅提交字段会写入）。

    额外服务端校验（补充 Schema）：
    - 改名时检查新名称唯一
    - 各阶段 Purchase 事件的金额规则
    - 启用时须有桥页 HTML

    更新后使 dp=斗篷名 相关的像素映射缓存失效；若改名则旧名、新名缓存均清理。
    """
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

    # 点击阶段 Purchase 须配置 report_value
    if config.report_event == "Purchase" and (
        config.report_value is None or float(config.report_value) <= 0
    ):
        raise_api_exception(
            ErrorCode.VALIDATION_ERROR,
            detail="点击上报事件为 Purchase 时必须配置大于 0 的金额（report_value）",
        )

    # 加载阶段：启用且 Purchase 须配置 load_report_value
    if config.load_report_enabled and config.load_report_event == "Purchase":
        if config.load_report_value is None or float(config.load_report_value) <= 0:
            raise_api_exception(
                ErrorCode.VALIDATION_ERROR,
                detail="启用加载上报且事件为 Purchase 时必须配置大于 0 的金额（load_report_value）",
            )

    # postback：固定金额若填写则须 > 0；留空表示线上用 postback payout
    if config.postback_report_enabled and config.postback_report_event == "Purchase":
        if config.postback_report_value is not None and float(config.postback_report_value) <= 0:
            raise_api_exception(
                ErrorCode.VALIDATION_ERROR,
                detail="postback Purchase 固定金额须大于 0，或留空以使用 postback 的 payout",
            )

    _ensure_enabled_requires_bridge_html(config.cloak_name, config.is_enabled)

    await db.commit()
    await db.refresh(config)
    # 斗篷名出现在投放链接 dp 参数中，配置变更需刷新运行时缓存
    invalidate_cloak_cache_for_dp(old_cloak_name)
    if config.cloak_name != old_cloak_name:
        invalidate_cloak_cache_for_dp(config.cloak_name)

    await log_update(
        db=db,
        user=current_user,
        resource_type="CLOAK_CONFIG",
        resource_id=config.id,
        resource_name=config.cloak_name,
        request=request,
        details=update_data,
    )
    await commit_audit_log(db)
    resp = CloakConfigResponse.model_validate(config).model_copy(update=_bridge_usability_fields(config.cloak_name))
    return ResponseBaseSchema.success(data=resp, message="更新斗篷配置成功")


@router.post(
    "/{config_id}/bridge-html",
    response_model=ResponseBaseSchema[dict],
    summary="上传斗篷桥页 HTML",
)
async def upload_cloak_bridge_html(
    request: Request,
    config_id: int = Path(..., ge=1, description="配置ID"),
    file: UploadFile = File(..., description="桥页 HTML 文件（UTF-8）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    上传并覆盖保存斗篷桥页 HTML 文件。

    流程：读文件 → 大小/扩展名校验 → UTF-8 与内容校验 → 写入 {cloak_name}.html
    → 失效模板缓存与 dp 斗篷缓存 → 记审计（action=upload_bridge_html）。

    文件最终以配置中的 cloak_name 命名，与上传时的原始文件名无关。
    """
    result = await db.execute(select(CloakConfig).where(CloakConfig.id == config_id))
    config = result.scalars().first()
    if not config:
        raise_api_exception(ErrorCode.RESOURCE_NOT_FOUND, detail="斗篷配置不存在")

    # 多读 1 字节用于判断是否超限，避免大文件占满内存
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
    await log_update(
        db=db,
        user=current_user,
        resource_type="CLOAK_CONFIG",
        resource_id=config.id,
        resource_name=config.cloak_name,
        request=request,
        details={
            "action": "upload_bridge_html",
            "saved_as": saved_filename,
            "bytes_written": len(text.encode("utf-8")),
        },
    )
    await commit_audit_log(db)
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
    request: Request,
    config_id: int = Path(..., ge=1, description="配置ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    删除斗篷配置记录。

    注意：不自动删除磁盘上的 {cloak_name}.html，仅删数据库行并清理 dp 缓存。
    审计日志在物理删除前写入。
    """
    result = await db.execute(select(CloakConfig).where(CloakConfig.id == config_id))
    config = result.scalars().first()
    if not config:
        raise_api_exception(ErrorCode.RESOURCE_NOT_FOUND, detail="斗篷配置不存在")

    deleted_cloak_name = config.cloak_name
    await log_delete(
        db=db,
        user=current_user,
        resource_type="CLOAK_CONFIG",
        resource_id=config.id,
        resource_name=deleted_cloak_name,
        request=request,
    )
    await commit_audit_log(db)
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
    """
    模拟向 Facebook CAPI 发送一次事件，用于验证 Pixel、Token 与事件配置是否正确。

    根据 test_data.report_phase 选择 load/click/postback 对应的事件与金额；
    客户端 IP/UA 取自当前管理端请求（非 test_data 中的 ip/ua 字段，后者保留兼容）。

    若配置了备份像素与 Token，会并行逻辑先后各发一次，返回 primary 与 backup 详情；
    无备份时 backup 为 null，backup_skipped 为 true。
    """
    result = await db.execute(select(CloakConfig).where(CloakConfig.id == config_id))
    config = result.scalars().first()
    if not config:
        raise_api_exception(ErrorCode.RESOURCE_NOT_FOUND, detail="斗篷配置不存在")

    phase = test_data.report_phase
    _validate_test_report_phase(config, phase)
    report_event, report_value, report_currency = _resolve_test_report_params(config, phase)

    client_ip = _resolve_real_client_ip(request)
    client_user_agent = _resolve_real_user_agent(request)
    payload = _build_facebook_payload(
        test_data,
        client_ip,
        client_user_agent,
        report_event=report_event,
        report_value=report_value,
        report_currency=report_currency,
    )
    primary_result = await _send_test_report(config.pixel_id, config.access_token, payload)

    backup_result = None
    if config.backup_pixel_id and config.backup_access_token:
        backup_result = await _send_test_report(config.backup_pixel_id, config.backup_access_token, payload)

    return ResponseBaseSchema.success(
        data={
            "cloak_name": config.cloak_name,
            "is_enabled": config.is_enabled,
            "report_phase": phase,
            "report_event": report_event,
            "report_value": report_value,
            "report_currency": report_currency,
            "primary": primary_result,
            "backup": backup_result,
            "backup_skipped": backup_result is None,
        },
        message="测试上报完成",
    )
