"""
国家代码查询工具模块

功能说明：
提供根据多种格式查找国家ISO 3166-1二字母代码的功能，支持：
- 多种输入格式：二字母代码、三字母代码、数字代码、中英文名称等
- 智能匹配：精确匹配、部分匹配、模糊匹配
- 特殊代码处理：未知区域（AA）、全部区域（ZZ）等

支持的输入格式（按优先级顺序）：
1. alpha_2_code（二字母代码）：如 "US", "CN", "GB"
2. alpha_3_code（三字母代码）：如 "USA", "CHN", "GBR"
3. numeric_code（数字代码）：如 "840", "156", "826"
4. country_name_en（英文名称）：如 "United States", "China"
5. country_name_zh（中文名称）：如 "美国", "中国"
6. official_name_en（官方英文名称）：如 "United States of America"
7. official_name_zh（官方中文名称）：如 "中华人民共和国"

匹配策略：
- 精确匹配优先：先尝试完全匹配
- 部分匹配：如果精确匹配失败，尝试包含关系匹配
- 中文智能匹配：
  - 支持输入值包含在数据库名称中（如 "孟加拉" 匹配 "孟加拉国"）
  - 支持数据库名称包含在输入值中（如 "多米尼加共和国" 匹配 "多米尼加"）
  - 优先匹配最长的匹配项（最完整的匹配）

特殊代码处理：
- "ZZ"：全部区域（用于统计查询；数据源未提供国家时也使用）
- "AA"：未知区域（历史数据或 countries 表登记项；新导入无法识别时保留原始代码）
- "unknown"：自动匹配为未知区域

使用场景：
- 广告数据导入时的国家代码解析
- 用户输入的国家名称转换为标准代码
- 数据查询和统计时的国家筛选
- API接口的国家参数验证

性能优化：
- 按优先级顺序查询，找到即返回
- 使用数据库索引优化查询性能
- 中文匹配使用LIKE查询，支持模糊匹配

注意事项：
1. 所有查询都返回ISO 3166-1二字母代码（alpha_2_code）
2. 如果找不到匹配的国家，返回None
3. 中文匹配可能较慢，建议优先使用代码格式输入
4. 部分匹配可能返回多个结果，优先返回最长的匹配项
"""
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.models import CountryInfo

# 获取当前模块的日志记录器
logger = logging.getLogger(__name__)

# 业务表 country_code 字段最大长度（与 ad_data / tb_search_data 表结构一致）
COUNTRY_CODE_STORAGE_MAX_LENGTH = 5


def preserve_unrecognized_country_code(
    country_input: str,
    max_length: int = COUNTRY_CODE_STORAGE_MAX_LENGTH,
) -> str:
    """
    无法识别国家时保留原始输入，截断至数据库字段长度上限。

    空值仍返回 ZZ（全部区域），表示数据源未提供国家信息。
    """
    if not country_input or not isinstance(country_input, str):
        return "ZZ"
    code = country_input.strip()
    if not code:
        return "ZZ"
    return code[:max_length]


def _pick_best_country_match(
    countries: list[CountryInfo],
    country_input: str,
) -> Optional[CountryInfo]:
    """多条命中时优先精确名称，否则取名称最长（更具体）的国家。"""
    if not countries:
        return None
    if len(countries) == 1:
        return countries[0]

    inp = country_input.strip().lower()
    for field in (
        "country_name_en",
        "official_name_en",
        "country_name_zh",
        "official_name_zh",
    ):
        exact = [
            c for c in countries
            if (getattr(c, field, None) or "").strip().lower() == inp
        ]
        if exact:
            return max(exact, key=lambda c: len((getattr(c, field, None) or "")))

    def _name_len(country: CountryInfo) -> int:
        return max(
            len(country.country_name_en or ""),
            len(country.official_name_en or ""),
            len(country.country_name_zh or ""),
            len(country.official_name_zh or ""),
        )

    return max(countries, key=_name_len)


async def _fetch_country_match(
    db: AsyncSession,
    query,
    country_input: str,
) -> Optional[CountryInfo]:
    """执行国家查询；多条时不抛异常，选取最精确的一条。"""
    result = await db.execute(query)
    countries = list(result.scalars().all())
    if not countries:
        return None
    if len(countries) > 1:
        logger.debug(
            "国家名称匹配到多条记录(%d)，输入=%r，将自动选取最精确项",
            len(countries),
            country_input,
        )
    return _pick_best_country_match(countries, country_input)


def resolve_country_name(
    country_info: Optional[any],
    country_code: Optional[str] = None,
    default_unknown: str = "未知区域",
    default_all: str = "全部区域"
) -> Optional[str]:
    """
    解析国家名称，处理特殊国家代码和缺失的国家信息
    
    Args:
        country_info: CountryInfo 对象（可能为 None）
        country_code: 国家代码（用于回退处理特殊代码）
        default_unknown: 未知区域的默认名称（默认为 "未知区域"）
        default_all: 全部区域的默认名称（默认为 "全部区域"）
    
    Returns:
        国家名称字符串；未在 countries 表登记时回退显示原始 country_code
    
    Example:
        # 有国家信息时
        country_name = resolve_country_name(country_info, ad_data.country_code)
        
        # 处理特殊代码
        country_name = resolve_country_name(None, "ZZ")  # -> "全部区域"
        country_name = resolve_country_name(None, "AA")  # -> "未知区域"
        country_name = resolve_country_name(None, "XX")  # -> "XX"（未识别，显示代码）
    """
    # 优先使用 CountryInfo 中的名称
    if country_info and hasattr(country_info, 'country_name_zh'):
        return country_info.country_name_zh
    
    # 如果没有 CountryInfo，根据 country_code 处理特殊代码或未识别代码
    if country_code:
        code = country_code.strip()
        if not code:
            return None
        if code == "ZZ":
            return default_all
        if code == "AA":
            return default_unknown
        # 未在 countries 表登记：显示原始国家代码，避免前端国家列为空
        return code
    
    return None


async def find_country_code_by_any_format(
    db: AsyncSession,
    country_input: str
) -> Optional[str]:
    """
    根据多种格式的输入查找国家代码（ISO 3166-1 二字母代码）
    
    支持的输入格式（按优先级顺序）：
    1. alpha_2_code（二字母代码，如 "US"）
    2. alpha_3_code（三字母代码，如 "USA"）
    3. numeric_code（数字代码，如 "840"）
    4. country_name_en（英文名称，如 "United States of America"）
    5. country_name_zh（中文名称，如 "美国"）
    6. official_name_en（官方英文名称）
    7. official_name_zh（官方中文名称）
    
    参数:
        db: 数据库会话
        country_input: 国家输入值（可以是上述任意格式）
    
    返回:
        str | None: 如果找到，返回 ISO 3166-1 二字母代码（如 "US"），否则返回 None
    """
    if not country_input or not isinstance(country_input, str):
        return None
    
    country_input = country_input.strip()
    if not country_input:
        return None
    
    # 按优先级顺序查询（模糊匹配可能命中多条，统一走 _fetch_country_match）
    # 1. 首先尝试 alpha_2_code（二字母代码）
    query = select(CountryInfo).where(CountryInfo.alpha_2_code == country_input.upper())
    country = await _fetch_country_match(db, query, country_input)
    if country:
        return country.alpha_2_code

    # 2. 尝试 alpha_3_code（三字母代码）
    query = select(CountryInfo).where(CountryInfo.alpha_3_code == country_input.upper())
    country = await _fetch_country_match(db, query, country_input)
    if country:
        return country.alpha_2_code

    # 3. 尝试 numeric_code（数字代码）
    query = select(CountryInfo).where(CountryInfo.numeric_code == country_input)
    country = await _fetch_country_match(db, query, country_input)
    if country:
        return country.alpha_2_code

    # 4. 尝试 country_name_en（英文名称，不区分大小写，支持部分匹配）
    query = select(CountryInfo).where(CountryInfo.country_name_en.ilike(country_input))
    country = await _fetch_country_match(db, query, country_input)
    if country:
        return country.alpha_2_code

    query = (
        select(CountryInfo)
        .where(CountryInfo.country_name_en.ilike(f"%{country_input}%"))
        .order_by(func.length(CountryInfo.country_name_en).desc())
    )
    country = await _fetch_country_match(db, query, country_input)
    if country:
        return country.alpha_2_code

    # 5. 尝试 official_name_en（官方英文名称）
    query = select(CountryInfo).where(CountryInfo.official_name_en.ilike(country_input))
    country = await _fetch_country_match(db, query, country_input)
    if country:
        return country.alpha_2_code

    query = (
        select(CountryInfo)
        .where(CountryInfo.official_name_en.ilike(f"%{country_input}%"))
        .order_by(func.length(CountryInfo.official_name_en).desc())
    )
    country = await _fetch_country_match(db, query, country_input)
    if country:
        return country.alpha_2_code

    # 6. 尝试 country_name_zh（中文名称，先精确匹配，再模糊匹配）
    query = select(CountryInfo).where(CountryInfo.country_name_zh == country_input)
    country = await _fetch_country_match(db, query, country_input)
    if country:
        return country.alpha_2_code

    query = (
        select(CountryInfo)
        .where(CountryInfo.country_name_zh.like(f"%{country_input}%"))
        .order_by(func.length(CountryInfo.country_name_zh).desc())
    )
    country = await _fetch_country_match(db, query, country_input)
    if country:
        return country.alpha_2_code

    query = (
        select(CountryInfo)
        .where(CountryInfo.country_name_zh.like(f"{country_input}%"))
        .order_by(func.length(CountryInfo.country_name_zh).desc())
    )
    country = await _fetch_country_match(db, query, country_input)
    if country:
        return country.alpha_2_code
    
    # 情况3：双向包含匹配（更宽松的匹配）
    # 获取所有国家，在 Python 中检查是否包含关系
    query = select(CountryInfo)
    result = await db.execute(query)
    all_countries = result.scalars().all()
    
    # 查找匹配的国家（输入值包含数据库名称，或数据库名称包含输入值）
    matches = []
    for country in all_countries:
        if country_input in country.country_name_zh or country.country_name_zh in country_input:
            matches.append(country)
    
    if matches:
        # 优先选择名称最长的匹配（最完整的匹配）
        best_match = max(matches, key=lambda c: len(c.country_name_zh))
        return best_match.alpha_2_code
    
    # 7. 尝试 official_name_zh（官方中文名称）
    query = select(CountryInfo).where(CountryInfo.official_name_zh == country_input)
    country = await _fetch_country_match(db, query, country_input)
    if country:
        return country.alpha_2_code

    query = (
        select(CountryInfo)
        .where(CountryInfo.official_name_zh.like(f"%{country_input}%"))
        .order_by(func.length(CountryInfo.official_name_zh).desc())
    )
    country = await _fetch_country_match(db, query, country_input)
    if country:
        return country.alpha_2_code

    # 8. 特殊处理：unknown / n/a 匹配「未知区域」
    if country_input.lower() in {"unknown", "n/a", "na"}:
        query = select(CountryInfo).where(
            (CountryInfo.country_name_en.ilike("unknown"))
            | (CountryInfo.country_name_zh == "未知区域")
            | (CountryInfo.alpha_2_code == "AA")
        )
        country = await _fetch_country_match(db, query, country_input)
        if country:
            return country.alpha_2_code
    
    # 如果所有格式都找不到，返回 None
    return None

