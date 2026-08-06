"""
广告数据健康巡检 — 重点关注产品。

- 配置：健康巡检 settings.watch_products（多行域名/URL）
- 匹配：去掉 http(s)://、路径后与 products.name 归一化比对
- 通知：一轮「*API获取数据」定时任务全部结束后，单独发 Telegram 汇报今日有无数据
"""
from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_redis_client
from app.core.telegram import send_telegram_notify_async
from app.core.telegram_utils import split_long_message
from app.core.utils import get_app_now, get_app_now_naive
from app.models.models import AdData, Product
from app.models.system import ScheduledTask
from app.scheduler_module.task_utils import task_supports_manual_date_range

logger = logging.getLogger(__name__)

# 回车/换行、中英文逗号/分号、竖线、顿号、空白 均可分隔多个产品
_WATCH_PRODUCT_SPLIT_RE = re.compile(r"[\s,，;；|、]+")

_WAVE_TTL_SECONDS = 2 * 60 * 60
_REDIS_DONE_PREFIX = "ad_data_watch:wave:"
_REDIS_NOTIFY_PREFIX = "ad_data_watch:notified:"

_memory_lock = threading.Lock()
_memory_done: dict[str, set[str]] = {}
_memory_notified: set[str] = set()


def normalize_product_key(raw: str) -> str:
    """将 URL / 域名归一为可比对的 host 键（小写、无协议、无路径）。"""
    s = (raw or "").strip()
    if not s:
        return ""
    lower = s.lower()
    for prefix in ("https://", "http://"):
        if lower.startswith(prefix):
            s = s[len(prefix) :]
            lower = s.lower()
            break
    s = s.split("/")[0].split("?")[0].split("#")[0]
    s = s.strip().strip(".")
    # 去掉可能的用户信息 user@host
    if "@" in s:
        s = s.rsplit("@", 1)[-1]
    return s.lower()


def parse_watch_products_text(text: Optional[str]) -> list[str]:
    """
    自动识别多种分隔方式，拆成产品列表：

    - 回车 / 换行
    - 英文逗号 ``,`` / 中文逗号 ``，`` / 顿号 ``、``
    - 英文分号 ``;`` / 中文分号 ``；``
    - 竖线 ``|``
    - 空格 / Tab 等空白

    去重按归一化键（忽略 https:// 差异），展示串保留用户输入片段。
    """
    if not text or not str(text).strip():
        return []
    seen: set[str] = set()
    out: list[str] = []
    for token in _WATCH_PRODUCT_SPLIT_RE.split(str(text).strip()):
        raw = (token or "").strip().strip("'\"“”‘’")
        if not raw:
            continue
        key = normalize_product_key(raw)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(raw)
    return out


def is_watch_window_active(
    today: date,
    *,
    effective_date: Optional[date] = None,
    expire_date: Optional[date] = None,
) -> tuple[bool, str]:
    """
    判断业务日是否落在重点关注生效窗口内。

    - 生效日期为空：立即生效
    - 失效日期为空：长期有效
    - 两端均含当天
    """
    if effective_date and today < effective_date:
        return False, "not_started"
    if expire_date and today > expire_date:
        return False, "expired"
    return True, "active"


def watch_window_status_label(status: str) -> str:
    return {
        "active": "生效中",
        "not_started": "未到生效日",
        "expired": "已过失效日",
        "empty": "未配置产品",
    }.get(status, status)


def watch_products_to_storage(lines: Sequence[str]) -> str:
    """保存前再归一一遍，统一为每行一个产品。"""
    return "\n".join(parse_watch_products_text("\n".join(lines)))


def current_upstream_wave_id(now=None) -> str:
    """与 */30 上游拉数 cron 对齐的半小时桶。"""
    now = now or get_app_now()
    minute_bucket = "00" if now.minute < 30 else "30"
    return f"{now.strftime('%Y%m%d%H')}{minute_bucket}"


@dataclass
class WatchProductStatus:
    input_name: str
    norm_key: str
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    has_today_data: bool = False
    row_count: int = 0
    request_count: int = 0
    revenue_before: float = 0.0
    data_sources: list[str] = field(default_factory=list)


@dataclass
class WatchProductsReport:
    today: date
    wave_id: str
    items: list[WatchProductStatus] = field(default_factory=list)
    effective_date: Optional[date] = None
    expire_date: Optional[date] = None
    window_status: str = "active"

    @property
    def with_data(self) -> list[WatchProductStatus]:
        return [i for i in self.items if i.has_today_data]

    @property
    def without_data(self) -> list[WatchProductStatus]:
        return [i for i in self.items if not i.has_today_data]


async def resolve_watch_product_ids(
    db: AsyncSession,
    *,
    watch_lines: Sequence[str],
) -> dict[str, list[tuple[int, str]]]:
    """
    归一化键 → [(product_id, product_name), ...]。
    同一域名可能对应多个客户下的同名/变体产品。
    """
    keys = [normalize_product_key(x) for x in watch_lines]
    keys = [k for k in keys if k]
    if not keys:
        return {}

    rows = (await db.execute(select(Product.id, Product.name))).all()
    by_key: dict[str, list[tuple[int, str]]] = {k: [] for k in keys}
    for pid, name in rows:
        nkey = normalize_product_key(str(name or ""))
        if nkey and nkey in by_key:
            by_key[nkey].append((int(pid), str(name or "")))
    return by_key


async def build_watch_products_report(
    db: AsyncSession,
    *,
    watch_text: Optional[str],
    today: Optional[date] = None,
    wave_id: Optional[str] = None,
    effective_date: Optional[date] = None,
    expire_date: Optional[date] = None,
) -> Optional[WatchProductsReport]:
    """按配置检查今日是否有广告数据；无关注列表时返回 None。"""
    lines = parse_watch_products_text(watch_text)
    if not lines:
        return None

    today = today or get_app_now().date()
    wave_id = wave_id or current_upstream_wave_id()
    _, window_status = is_watch_window_active(
        today, effective_date=effective_date, expire_date=expire_date
    )
    matched = await resolve_watch_product_ids(db, watch_lines=lines)

    all_pids: list[int] = []
    for pairs in matched.values():
        all_pids.extend(pid for pid, _ in pairs)

    agg_by_pid: dict[int, dict[str, Any]] = {}
    if all_pids:
        rows = (
            await db.execute(
                select(
                    AdData.product_id,
                    AdData.data_source,
                    func.count(AdData.id).label("row_count"),
                    func.coalesce(func.sum(AdData.request_count), 0).label("request_count"),
                    func.coalesce(func.sum(AdData.revenue_before_deduct), 0).label(
                        "revenue_before"
                    ),
                )
                .where(AdData.date == today, AdData.product_id.in_(all_pids))
                .group_by(AdData.product_id, AdData.data_source)
            )
        ).all()
        for pid, source, row_count, req, rev in rows:
            bucket = agg_by_pid.setdefault(
                int(pid),
                {
                    "row_count": 0,
                    "request_count": 0,
                    "revenue_before": 0.0,
                    "sources": set(),
                },
            )
            bucket["row_count"] += int(row_count or 0)
            bucket["request_count"] += int(req or 0)
            bucket["revenue_before"] += float(rev or 0)
            if source:
                bucket["sources"].add(str(source))

    items: list[WatchProductStatus] = []
    for raw in lines:
        key = normalize_product_key(raw)
        pairs = matched.get(key) or []
        if not pairs:
            items.append(
                WatchProductStatus(
                    input_name=raw,
                    norm_key=key,
                    has_today_data=False,
                )
            )
            continue
        # 合并同一关注项下匹配到的全部产品今日数据
        total_rows = 0
        total_req = 0
        total_rev = 0.0
        sources: set[str] = set()
        first_id, first_name = pairs[0]
        for pid, pname in pairs:
            bucket = agg_by_pid.get(pid)
            if not bucket:
                continue
            total_rows += int(bucket["row_count"])
            total_req += int(bucket["request_count"])
            total_rev += float(bucket["revenue_before"])
            sources |= set(bucket["sources"])
            first_id, first_name = pid, pname
        items.append(
            WatchProductStatus(
                input_name=raw,
                norm_key=key,
                product_id=first_id,
                product_name=first_name,
                has_today_data=total_rows > 0,
                row_count=total_rows,
                request_count=total_req,
                revenue_before=total_rev,
                data_sources=sorted(sources),
            )
        )

    return WatchProductsReport(
        today=today,
        wave_id=wave_id,
        items=items,
        effective_date=effective_date,
        expire_date=expire_date,
        window_status=window_status,
    )


def format_watch_products_telegram(report: WatchProductsReport) -> str:
    """生成单独的 Telegram 正文。"""
    eff = report.effective_date.isoformat() if report.effective_date else "立即"
    exp = report.expire_date.isoformat() if report.expire_date else "长期"
    lines = [
        "🔍 重点关注产品 · 今日数据检查",
        "",
        f"业务日: {report.today.isoformat()}",
        f"生效窗口: {eff} ~ {exp}（{watch_window_status_label(report.window_status)}）",
        f"轮次: {report.wave_id}（上游 API 拉数半小时轮）",
        f"关注数: {len(report.items)} · 有数据 {len(report.with_data)} · 无数据 {len(report.without_data)}",
        "",
    ]
    if report.with_data:
        lines.append("✅ 已有今日数据")
        for item in report.with_data:
            src = ",".join(item.data_sources) if item.data_sources else "-"
            name = item.product_name or item.input_name
            lines.append(
                f"  · {item.input_name}"
                f" → {name}"
                f" | 行={item.row_count}"
                f" 请求={item.request_count}"
                f" 收益扣前={item.revenue_before:.2f}"
                f" 来源={src}"
            )
        lines.append("")
    if report.without_data:
        lines.append("⚠️ 今日尚无数据")
        for item in report.without_data:
            if item.product_id is None:
                lines.append(f"  · {item.input_name}（库中暂无匹配产品）")
            else:
                name = item.product_name or item.input_name
                lines.append(f"  · {item.input_name} → {name}（已有产品但今日无行）")
        lines.append("")
    lines.append(f"生成时间: {get_app_now_naive().strftime('%Y-%m-%d %H:%M:%S')}")
    return "\n".join(lines).rstrip() + "\n"


async def load_watch_products_text(db: AsyncSession) -> str:
    from app.services.ad_data import baseline_service as bs

    row = await bs.get_or_create_settings(db)
    return str(getattr(row, "watch_products", None) or "")


async def list_active_upstream_api_task_names(db: AsyncSession) -> list[str]:
    """启用中的「*API获取数据」定时任务。"""
    rows = (
        await db.execute(
            select(ScheduledTask.task_name).where(
                ScheduledTask.is_active == True  # noqa: E712
            )
        )
    ).all()
    names = [str(r[0]) for r in rows if task_supports_manual_date_range(str(r[0]))]
    return sorted(set(names))


async def _try_claim_notify(wave_id: str) -> bool:
    """抢通知锁，避免多 worker 重复发送。"""
    redis = await get_redis_client()
    key = f"{_REDIS_NOTIFY_PREFIX}{wave_id}"
    if redis:
        try:
            ok = await redis.set(key, "1", nx=True, ex=_WAVE_TTL_SECONDS)
            return bool(ok)
        except Exception as exc:
            logger.warning("重点关注通知锁 Redis 失败，回退内存: %s", exc)

    with _memory_lock:
        if wave_id in _memory_notified:
            return False
        _memory_notified.add(wave_id)
        return True


async def _mark_task_done(wave_id: str, task_name: str) -> set[str]:
    redis = await get_redis_client()
    key = f"{_REDIS_DONE_PREFIX}{wave_id}"
    if redis:
        try:
            await redis.sadd(key, task_name)
            await redis.expire(key, _WAVE_TTL_SECONDS)
            members = await redis.smembers(key)
            done = {
                (m.decode() if isinstance(m, (bytes, bytearray)) else str(m))
                for m in (members or set())
            }
            return done
        except Exception as exc:
            logger.warning("重点关注完成集 Redis 失败，回退内存: %s", exc)

    with _memory_lock:
        bucket = _memory_done.setdefault(wave_id, set())
        bucket.add(task_name)
        return set(bucket)


async def send_watch_products_telegram(
    db: AsyncSession,
    *,
    watch_text: Optional[str] = None,
    today: Optional[date] = None,
    wave_id: Optional[str] = None,
    force: bool = False,
) -> dict[str, Any]:
    """检查并发送重点关注 Telegram；force 时忽略生效窗口与波次锁。"""
    from app.services.ad_data import baseline_service as bs

    cfg = await bs.load_settings_view(db)
    text = watch_text if watch_text is not None else cfg.watch_products
    check_day = today or get_app_now().date()
    window_ok, window_status = is_watch_window_active(
        check_day,
        effective_date=cfg.watch_effective_date,
        expire_date=cfg.watch_expire_date,
    )
    if not window_ok and not force:
        return {
            "sent": False,
            "reason": f"watch_window_{window_status}",
            "window_status": window_status,
            "effective_date": (
                cfg.watch_effective_date.isoformat() if cfg.watch_effective_date else None
            ),
            "expire_date": (
                cfg.watch_expire_date.isoformat() if cfg.watch_expire_date else None
            ),
        }

    report = await build_watch_products_report(
        db,
        watch_text=text,
        today=check_day,
        wave_id=wave_id,
        effective_date=cfg.watch_effective_date,
        expire_date=cfg.watch_expire_date,
    )
    if report is None:
        return {"sent": False, "reason": "empty_watch_list"}

    if not cfg.enable_telegram and not force:
        return {
            "sent": False,
            "reason": "telegram_disabled",
            "with_data": len(report.with_data),
            "without_data": len(report.without_data),
            "window_status": report.window_status,
        }

    msg = format_watch_products_telegram(report)
    for part in split_long_message(msg):
        await send_telegram_notify_async(part)
    return {
        "sent": True,
        "today": report.today.isoformat(),
        "wave_id": report.wave_id,
        "total": len(report.items),
        "with_data": len(report.with_data),
        "without_data": len(report.without_data),
        "window_status": report.window_status,
        "effective_date": (
            report.effective_date.isoformat() if report.effective_date else None
        ),
        "expire_date": report.expire_date.isoformat() if report.expire_date else None,
        "summary_text": msg,
    }


async def on_upstream_api_task_finished(task_name: str) -> None:
    """
    上游 API 拉数任务（成功/失败/软跳过）结束后调用。
    当本半小时轮内「全部启用的上游 API 任务」都完成后，单独发重点关注 Telegram。
    """
    if not task_supports_manual_date_range(task_name):
        return

    from app.core.database import AsyncSessionLocal
    from app.services.ad_data import baseline_service as bs

    wave_id = current_upstream_wave_id()
    try:
        async with AsyncSessionLocal() as db:
            settings_row = await bs.get_or_create_settings(db)
            watch_text = str(getattr(settings_row, "watch_products", None) or "")
            if not parse_watch_products_text(watch_text):
                await db.commit()
                return

            today = get_app_now().date()
            window_ok, window_status = is_watch_window_active(
                today,
                effective_date=getattr(settings_row, "watch_effective_date", None),
                expire_date=getattr(settings_row, "watch_expire_date", None),
            )
            if not window_ok:
                logger.info(
                    "重点关注：今日 %s 不在生效窗口（%s），跳过汇总通知",
                    today.isoformat(),
                    window_status,
                )
                await db.commit()
                return

            expected = await list_active_upstream_api_task_names(db)
            if not expected:
                await db.commit()
                return

            done = await _mark_task_done(wave_id, task_name)
            pending = [n for n in expected if n not in done]
            if pending:
                logger.info(
                    "重点关注：波次 %s 仍待 %d/%d 个上游任务（刚完成 %s）",
                    wave_id,
                    len(pending),
                    len(expected),
                    task_name,
                )
                await db.commit()
                return

            if not await _try_claim_notify(wave_id):
                logger.info("重点关注：波次 %s 通知已发送，跳过", wave_id)
                await db.commit()
                return

            result = await send_watch_products_telegram(
                db,
                watch_text=watch_text,
                wave_id=wave_id,
                force=False,
            )
            await db.commit()
            logger.info(
                "重点关注：波次 %s 全部上游 API 完成，通知结果=%s",
                wave_id,
                result,
            )
    except Exception as exc:
        logger.warning("重点关注波次收尾失败（不影响上游任务）: %s", exc, exc_info=True)
