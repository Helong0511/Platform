"""
广告数据健康巡检 API（管理员）。

告警列表 / 标准快照 / 配置 / 手动冻结与巡检。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_admin
from app.core.utils import get_app_now
from app.models.models import User
from app.schemas.base import ResponseBaseSchema
from app.services.ad_data import baseline_service as bs
from app.services.ad_data.health_runner import run_daily_health_scan

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


class FreezeBody(BaseModel):
    stat_date: Optional[date] = None
    force: bool = False


class RunBody(BaseModel):
    today: Optional[date] = None
    send_telegram: Optional[bool] = None


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    return date.fromisoformat(value[:10])


@router.get("/settings", response_model=ResponseBaseSchema[dict[str, Any]])
async def get_settings(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    row = await bs.get_or_create_settings(db)
    await db.commit()
    return ResponseBaseSchema.success(
        data={
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
            "updated_at": row.updated_at.isoformat(sep=" ") if row.updated_at else None,
            "granularity": "stat_date + product_id + data_source",
            "freeze_cron_hint": "每天 00:30 冻结昨天",
        }
    )


@router.put("/settings", response_model=ResponseBaseSchema[dict[str, Any]])
async def put_settings(
    body: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    row = await bs.update_settings(db, payload=body.model_dump(exclude_unset=True))
    await db.commit()
    return ResponseBaseSchema.success(
        data={
            "ok": True,
            "updated_at": row.updated_at.isoformat(sep=" ") if row.updated_at else None,
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
