"""国家信息相关业务逻辑：别名维护与未识别国家代码收集。"""
from __future__ import annotations

import logging
import re
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.country_code import (
    load_country_alias_map,
    normalize_country_alias_key,
)
from app.models.models import AdData, CountryAlias, CountryInfo, TBSearchData
from app.schemas.country import CountryAliasCreate, UnrecognizedCountryCodeItem

logger = logging.getLogger(__name__)

_ALPHA2_PATTERN = re.compile(r"^[A-Za-z]{2}$")
_SKIP_CODES = {"ZZ", "AA"}


def resolve_alpha2_via_alias(
    country_input: str,
    alias_map: dict[str, str],
) -> Optional[str]:
    """通过别名表（或内置）解析 ISO 二字代码。"""
    if not country_input or not str(country_input).strip():
        return None
    key = normalize_country_alias_key(country_input)
    return alias_map.get(key)


async def _count_by_country_code(db: AsyncSession, column) -> dict[str, int]:
    """按 country_code 分组统计指定表的记录数。"""
    query = (
        select(column, func.count())
        .where(column.isnot(None), column != "", column != "ZZ", column != "AA")
        .group_by(column)
    )
    result = await db.execute(query)
    counts: dict[str, int] = {}
    for code, cnt in result.all():
        if code:
            counts[str(code)] = int(cnt or 0)
    return counts


async def _archive_count_by_country_code(db: AsyncSession) -> dict[str, int]:
    """统计归档表中的国家代码；表不存在时返回空字典。"""
    try:
        result = await db.execute(
            text(
                """
                SELECT country_code, COUNT(*) AS cnt
                FROM ad_data_archive
                WHERE country_code IS NOT NULL
                  AND country_code != ''
                  AND country_code != 'ZZ'
                  AND country_code != 'AA'
                GROUP BY country_code
                """
            )
        )
        return {str(row[0]): int(row[1] or 0) for row in result.all() if row[0]}
    except Exception as exc:
        logger.debug("读取 ad_data_archive 未识别国家代码跳过: %s", exc)
        await db.rollback()
        return {}


def _merge_counts_by_bucket(
    ad_counts: dict[str, int],
    tb_counts: dict[str, int],
    archive_counts: dict[str, int],
    alias_map: dict[str, str],
    known_codes: set[str],
) -> dict[str, dict]:
    """
    将各表原始 country_code 按「未识别分组键」合并统计。

    分组键：已是未登记 alpha-2 时用原值；否则用 alias 目标或规范化原文。
    """
    buckets: dict[str, dict] = {}

    def _add(source: str, raw_code: str, count: int) -> None:
        code = (raw_code or "").strip()
        if not code or code.upper() in _SKIP_CODES:
            return
        upper = code.upper()
        if upper in known_codes:
            return

        suggested = resolve_alpha2_via_alias(code, alias_map)
        norm = normalize_country_alias_key(code)
        if suggested:
            bucket_key = f"alias-target:{suggested.upper()}"
            display = code
        elif _ALPHA2_PATTERN.match(code):
            bucket_key = f"alpha2:{upper}"
            display = upper
        else:
            bucket_key = f"name:{norm}"
            display = code

        if bucket_key not in buckets:
            buckets[bucket_key] = {
                "display": display,
                "variant_codes": set(),
                "suggested_alpha_2": suggested,
                "ad_data_count": 0,
                "tb_search_data_count": 0,
                "ad_data_archive_count": 0,
            }
        bucket = buckets[bucket_key]
        bucket["variant_codes"].add(code)
        if len(code) > len(bucket["display"]):
            bucket["display"] = code
        if suggested and not bucket["suggested_alpha_2"]:
            bucket["suggested_alpha_2"] = suggested
        if source == "ad_data":
            bucket["ad_data_count"] += count
        elif source == "tb_search_data":
            bucket["tb_search_data_count"] += count
        else:
            bucket["ad_data_archive_count"] += count

    for raw, cnt in ad_counts.items():
        _add("ad_data", raw, cnt)
    for raw, cnt in tb_counts.items():
        _add("tb_search_data", raw, cnt)
    for raw, cnt in archive_counts.items():
        _add("ad_data_archive", raw, cnt)

    return buckets


async def collect_unrecognized_country_codes(
    db: AsyncSession,
) -> list[UnrecognizedCountryCodeItem]:
    """
    汇总业务数据中未在 countries 表登记的国家代码。

    - 合并写法变体（如 U.S. Virgin Islands / US Virgin Islands）的出现次数
    - 标注别名可映射的 suggested_alpha_2
    """
    known_result = await db.execute(select(CountryInfo.alpha_2_code))
    known_codes = {
        (row[0] or "").strip().upper()
        for row in known_result.all()
        if row[0]
    }

    alias_map = await load_country_alias_map(db)
    db_alias_keys = set()
    try:
        result = await db.execute(select(CountryAlias.alias_normalized))
        db_alias_keys = {str(r[0]) for r in result.all() if r[0]}
    except Exception:
        await db.rollback()

    ad_counts = await _count_by_country_code(db, AdData.country_code)
    tb_counts = await _count_by_country_code(db, TBSearchData.country_code)
    archive_counts = await _archive_count_by_country_code(db)

    buckets = _merge_counts_by_bucket(
        ad_counts, tb_counts, archive_counts, alias_map, known_codes
    )

    items: list[UnrecognizedCountryCodeItem] = []
    for bucket in buckets.values():
        total = (
            bucket["ad_data_count"]
            + bucket["tb_search_data_count"]
            + bucket["ad_data_archive_count"]
        )
        if total <= 0:
            continue

        display = bucket["display"]
        suggested = bucket.get("suggested_alpha_2")
        norm = normalize_country_alias_key(display)
        alias_registered = norm in db_alias_keys or norm in alias_map

        sources: list[str] = []
        if bucket["ad_data_count"]:
            sources.append("ad_data")
        if bucket["tb_search_data_count"]:
            sources.append("tb_search_data")
        if bucket["ad_data_archive_count"]:
            sources.append("ad_data_archive")

        items.append(
            UnrecognizedCountryCodeItem(
                country_code=display,
                ad_data_count=bucket["ad_data_count"],
                tb_search_data_count=bucket["tb_search_data_count"],
                ad_data_archive_count=bucket["ad_data_archive_count"],
                total_count=total,
                sources=sources,
                is_valid_alpha2=bool(_ALPHA2_PATTERN.match(display)),
                suggested_alpha_2=suggested,
                alias_registered=alias_registered,
                variant_codes=sorted(bucket["variant_codes"]),
            )
        )

    items.sort(key=lambda item: (-item.total_count, item.country_code.upper()))
    return items


async def list_country_aliases(
    db: AsyncSession,
    *,
    keyword: Optional[str] = None,
) -> list[CountryAlias]:
    query = select(CountryAlias).order_by(CountryAlias.alpha_2_code, CountryAlias.alias_name)
    if keyword and keyword.strip():
        like = f"%{keyword.strip()}%"
        query = query.where(
            CountryAlias.alias_name.ilike(like)
            | CountryAlias.alias_normalized.ilike(like)
            | CountryAlias.alpha_2_code.ilike(like)
        )
    result = await db.execute(query)
    return list(result.scalars().all())


async def create_country_alias(
    db: AsyncSession,
    data: CountryAliasCreate,
) -> CountryAlias:
    normalized = normalize_country_alias_key(data.alias_name)
    existing = await db.execute(
        select(CountryAlias).where(CountryAlias.alias_normalized == normalized)
    )
    if existing.scalars().first():
        raise ValueError(f"别名已存在：{data.alias_name}")

    row = CountryAlias(
        alias_name=data.alias_name.strip(),
        alias_normalized=normalized,
        alpha_2_code=data.alpha_2_code.strip().upper(),
        remark=data.remark.strip() if data.remark else None,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


async def delete_country_alias(db: AsyncSession, alias_id: int) -> None:
    result = await db.execute(select(CountryAlias).where(CountryAlias.id == alias_id))
    row = result.scalars().first()
    if not row:
        raise LookupError(f"别名不存在：{alias_id}")
    await db.delete(row)
