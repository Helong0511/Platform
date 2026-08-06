"""
广告数据健康巡检 API（管理员）。

告警列表 / 标准快照 / 配置 / 手动冻结与巡检 / 重点关注产品。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_admin
from app.core.utils import get_app_now
from app.models.models import User
from app.schemas.base import ResponseBaseSchema
from app.services.ad_data import baseline_service as bs
from app.services.ad_data.health_runner import run_daily_health_scan
from app.services.ad_data.health_check import TODAY_GAP_ALERT_AFTER_HOUR
from app.services.ad_data.watch_products import (
    build_watch_products_report,
    format_watch_products_telegram,
    is_watch_window_active,
    parse_watch_products_text,
    send_watch_products_telegram,
    watch_window_status_label,
)

router = APIRouter()


class SettingsUpdate(BaseModel):
    drop_ratio: Optional[float] = Field(None, ge=0, le=1)
    request_floor: Optional[int] = Field(None, ge=0)
    revenue_floor: Optional[float] = Field(None, ge=0)
    enable_baseline_drop: Optional[bool] = None
    enable_missing: Optional[bool] = None
    enable_streak: Optional[bool] = None
    enable_today_gap: Optional[bool] = None
    enable_dod_drop: Optional[bool] = None
    enable_telegram: Optional[bool] = None
    cooldown_hours: Optional[int] = Field(None, ge=0, le=168)
    watch_products: Optional[str] = None
    # 空串表示清空；None 表示本次不改
    watch_effective_date: Optional[str] = None
    watch_expire_date: Optional[str] = None


class FreezeBody(BaseModel):
    stat_date: Optional[date] = None
    force: bool = False


class RunBody(BaseModel):
    today: Optional[date] = None
    send_telegram: Optional[bool] = None


class WatchCheckBody(BaseModel):
    today: Optional[date] = None
    send_telegram: bool = True


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    return date.fromisoformat(value[:10])


def _settings_payload(row) -> dict[str, Any]:
    today = get_app_now().date()
    eff = getattr(row, "watch_effective_date", None)
    exp = getattr(row, "watch_expire_date", None)
    if hasattr(eff, "isoformat"):
        pass
    else:
        eff = _parse_date(str(eff) if eff else None)
    if hasattr(exp, "isoformat"):
        pass
    else:
        exp = _parse_date(str(exp) if exp else None)
    window_ok, window_status = is_watch_window_active(
        today, effective_date=eff, expire_date=exp
    )
    return {
        "drop_ratio": float(row.drop_ratio or 0),
        "request_floor": int(row.request_floor or 0),
        "revenue_floor": float(row.revenue_floor or 0),
        "enable_baseline_drop": bool(row.enable_baseline_drop),
        "enable_missing": bool(row.enable_missing),
        "enable_streak": bool(row.enable_streak),
        "enable_today_gap": bool(row.enable_today_gap),
        "enable_dod_drop": bool(row.enable_dod_drop),
        "enable_telegram": bool(row.enable_telegram),
        "cooldown_hours": int(row.cooldown_hours or 0),
        "watch_products": str(getattr(row, "watch_products", None) or ""),
        "watch_effective_date": eff.isoformat() if eff else "",
        "watch_expire_date": exp.isoformat() if exp else "",
        "watch_window_active": window_ok,
        "watch_window_status": window_status,
        "watch_window_status_label": watch_window_status_label(window_status),
        "updated_at": row.updated_at.isoformat(sep=" ") if row.updated_at else None,
        "granularity": "stat_date + product_id + data_source",
        "freeze_cron_hint": "每天 00:30 冻结昨天",
        "watch_hint": (
            "支持回车/逗号/分号/空格等自动拆分；"
            "生效日期起（含）至失效日期止（含）自动盯数并发 Telegram；"
            "生效空=立即，失效空=长期"
        ),
        "today_gap_hint": (
            f"昨有今无：业务时 {TODAY_GAP_ALERT_AFTER_HOUR}:00 前不落库、不发 Telegram"
            "（避免 01:00 巡检刷屏）；开关关闭则全天不报"
        ),
        "today_gap_alert_after_hour": TODAY_GAP_ALERT_AFTER_HOUR,
    }


@router.get("/settings", response_model=ResponseBaseSchema[dict[str, Any]])
async def get_settings(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    row = await bs.get_or_create_settings(db)
    await db.commit()
    return ResponseBaseSchema.success(data=_settings_payload(row))


@router.put("/settings", response_model=ResponseBaseSchema[dict[str, Any]])
async def put_settings(
    body: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    try:
        row = await bs.update_settings(db, payload=body.model_dump(exclude_unset=True))
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResponseBaseSchema.success(
        data={
            "ok": True,
            "updated_at": row.updated_at.isoformat(sep=" ") if row.updated_at else None,
            "watch_count": len(parse_watch_products_text(row.watch_products)),
            "watch_effective_date": (
                row.watch_effective_date.isoformat()
                if getattr(row, "watch_effective_date", None)
                else ""
            ),
            "watch_expire_date": (
                row.watch_expire_date.isoformat()
                if getattr(row, "watch_expire_date", None)
                else ""
            ),
        }
    )


@router.get("/alerts", response_model=ResponseBaseSchema[dict[str, Any]])
async def get_alerts(
    stat_date: Optional[str] = None,
    alert_type: Optional[str] = None,
    product_id: Optional[int] = None,
    notified: Optional[bool] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    items, total = await bs.list_alerts(
        db,
        stat_date=_parse_date(stat_date),
        alert_type=alert_type,
        product_id=product_id,
        notified=notified,
        limit=limit,
        offset=offset,
    )
    return ResponseBaseSchema.success(
        data={"items": items, "total": total, "limit": limit, "offset": offset}
    )


@router.get("/baselines", response_model=ResponseBaseSchema[dict[str, Any]])
async def get_baselines(
    stat_date: Optional[str] = None,
    product_id: Optional[int] = None,
    data_source: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    items, total = await bs.list_baselines(
        db,
        stat_date=_parse_date(stat_date),
        product_id=product_id,
        data_source=data_source,
        limit=limit,
        offset=offset,
    )
    return ResponseBaseSchema.success(
        data={"items": items, "total": total, "limit": limit, "offset": offset}
    )


@router.post("/baselines/freeze", response_model=ResponseBaseSchema[dict[str, Any]])
async def post_freeze(
    body: FreezeBody,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    today = get_app_now().date()
    stat_date = body.stat_date or (today - timedelta(days=1))
    result = await bs.freeze_baseline_for_date(
        db, stat_date=stat_date, force=body.force
    )
    await db.commit()
    return ResponseBaseSchema.success(data=result)


@router.post("/run", response_model=ResponseBaseSchema[dict[str, Any]])
async def post_run(
    body: RunBody,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    result = await run_daily_health_scan(
        db,
        today=body.today,
        send_telegram=body.send_telegram,
    )
    await db.commit()
    return ResponseBaseSchema.success(data=result)


@router.post("/watch-check", response_model=ResponseBaseSchema[dict[str, Any]])
async def post_watch_check(
    body: WatchCheckBody,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """手动检查重点关注产品今日是否有数据，可选立即发 Telegram。"""
    row = await bs.get_or_create_settings(db)
    watch_text = str(getattr(row, "watch_products", None) or "")
    eff = bs._coerce_optional_date(getattr(row, "watch_effective_date", None))
    exp = bs._coerce_optional_date(getattr(row, "watch_expire_date", None))
    report = await build_watch_products_report(
        db,
        watch_text=watch_text,
        today=body.today,
        effective_date=eff,
        expire_date=exp,
    )
    if report is None:
        await db.commit()
        return ResponseBaseSchema.success(
            data={
                "sent": False,
                "reason": "empty_watch_list",
                "summary_text": "未配置重点关注产品",
            }
        )

    summary = format_watch_products_telegram(report)
    sent = False
    if body.send_telegram:
        result = await send_watch_products_telegram(
            db,
            watch_text=watch_text,
            today=body.today,
            force=True,
        )
        sent = bool(result.get("sent"))
        summary = str(result.get("summary_text") or summary)

    await db.commit()
    return ResponseBaseSchema.success(
        data={
            "sent": sent,
            "today": report.today.isoformat(),
            "wave_id": report.wave_id,
            "total": len(report.items),
            "with_data": len(report.with_data),
            "without_data": len(report.without_data),
            "window_status": report.window_status,
            "window_status_label": watch_window_status_label(report.window_status),
            "effective_date": (
                report.effective_date.isoformat() if report.effective_date else ""
            ),
            "expire_date": (
                report.expire_date.isoformat() if report.expire_date else ""
            ),
            "items": [
                {
                    "input_name": i.input_name,
                    "norm_key": i.norm_key,
                    "product_id": i.product_id,
                    "product_name": i.product_name,
                    "has_today_data": i.has_today_data,
                    "row_count": i.row_count,
                    "request_count": i.request_count,
                    "revenue_before": i.revenue_before,
                    "data_sources": i.data_sources,
                }
                for i in report.items
            ],
            "summary_text": summary,
        }
    )
