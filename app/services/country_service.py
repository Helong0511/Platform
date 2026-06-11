"""国家信息相关业务逻辑：收集业务数据中未登记的国家代码。"""
import logging
import re

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AdData, CountryInfo, TBSearchData
from app.schemas.country import UnrecognizedCountryCodeItem

logger = logging.getLogger(__name__)

_ALPHA2_PATTERN = re.compile(r"^[A-Za-z]{2}$")
_SKIP_CODES = {"ZZ", "AA"}


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


async def collect_unrecognized_country_codes(
    db: AsyncSession,
) -> list[UnrecognizedCountryCodeItem]:
    """
    汇总广告数据、TB 搜索数据及归档表中未在 countries 表登记的国家代码。

    排除空值、ZZ（全部区域）与 AA（历史未知区域占位）；按总出现次数降序排列。
    """
    known_result = await db.execute(select(CountryInfo.alpha_2_code))
    known_codes = {
        (row[0] or "").strip().upper()
        for row in known_result.all()
        if row[0]
    }

    ad_counts = await _count_by_country_code(db, AdData.country_code)
    tb_counts = await _count_by_country_code(db, TBSearchData.country_code)
    archive_counts = await _archive_count_by_country_code(db)

    all_codes = set(ad_counts) | set(tb_counts) | set(archive_counts)
    items: list[UnrecognizedCountryCodeItem] = []

    for raw_code in all_codes:
        code = (raw_code or "").strip()
        if not code or code.upper() in _SKIP_CODES:
            continue
        if code.upper() in known_codes:
            continue

        ad_data_count = ad_counts.get(raw_code, 0)
        tb_search_data_count = tb_counts.get(raw_code, 0)
        ad_data_archive_count = archive_counts.get(raw_code, 0)
        total_count = ad_data_count + tb_search_data_count + ad_data_archive_count
        if total_count <= 0:
            continue

        sources: list[str] = []
        if ad_data_count:
            sources.append("ad_data")
        if tb_search_data_count:
            sources.append("tb_search_data")
        if ad_data_archive_count:
            sources.append("ad_data_archive")

        items.append(
            UnrecognizedCountryCodeItem(
                country_code=code,
                ad_data_count=ad_data_count,
                tb_search_data_count=tb_search_data_count,
                ad_data_archive_count=ad_data_archive_count,
                total_count=total_count,
                sources=sources,
                is_valid_alpha2=bool(_ALPHA2_PATTERN.match(code)),
            )
        )

    items.sort(key=lambda item: (-item.total_count, item.country_code.upper()))
    return items
