"""
国家代码查询工具模块
提供根据多种格式查找国家代码的功能
"""
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.models import CountryInfo

# 获取当前模块的日志记录器
logger = logging.getLogger(__name__)


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
    
    # 按优先级顺序查询
    # 1. 首先尝试 alpha_2_code（二字母代码）
    query = select(CountryInfo).where(CountryInfo.alpha_2_code == country_input.upper())
    result = await db.execute(query)
    country = result.scalar_one_or_none()
    if country:
        return country.alpha_2_code
    
    # 2. 尝试 alpha_3_code（三字母代码）
    query = select(CountryInfo).where(CountryInfo.alpha_3_code == country_input.upper())
    result = await db.execute(query)
    country = result.scalar_one_or_none()
    if country:
        return country.alpha_2_code
    
    # 3. 尝试 numeric_code（数字代码）
    query = select(CountryInfo).where(CountryInfo.numeric_code == country_input)
    result = await db.execute(query)
    country = result.scalar_one_or_none()
    if country:
        return country.alpha_2_code
    
    # 4. 尝试 country_name_en（英文名称，不区分大小写，支持部分匹配）
    # 先尝试精确匹配
    query = select(CountryInfo).where(CountryInfo.country_name_en.ilike(country_input))
    result = await db.execute(query)
    country = result.scalar_one_or_none()
    if country:
        return country.alpha_2_code
    
    # 如果精确匹配失败，尝试部分匹配（包含关系）
    query = select(CountryInfo).where(CountryInfo.country_name_en.ilike(f"%{country_input}%"))
    result = await db.execute(query)
    country = result.scalar_one_or_none()
    if country:
        return country.alpha_2_code
    
    # 5. 尝试 official_name_en（官方英文名称）
    query = select(CountryInfo).where(CountryInfo.official_name_en.ilike(country_input))
    result = await db.execute(query)
    country = result.scalar_one_or_none()
    if country:
        return country.alpha_2_code
    
    # 官方英文名称部分匹配
    query = select(CountryInfo).where(CountryInfo.official_name_en.ilike(f"%{country_input}%"))
    result = await db.execute(query)
    country = result.scalar_one_or_none()
    if country:
        return country.alpha_2_code
    
    # 6. 尝试 country_name_zh（中文名称，先精确匹配，再模糊匹配）
    # 先尝试精确匹配
    query = select(CountryInfo).where(CountryInfo.country_name_zh == country_input)
    result = await db.execute(query)
    country = result.scalar_one_or_none()
    if country:
        return country.alpha_2_code
    
    # 如果精确匹配失败，尝试部分匹配（包含关系）
    # 支持两种情况：
    # 1. 输入值包含在数据库名称中：如 "孟加拉" 匹配 "孟加拉国"
    # 2. 数据库名称包含在输入值中：如 "多米尼加共和国" 匹配 "多米尼加"
    # 优先匹配最长的匹配项（按名称长度降序排序）
    
    # 情况1：输入值包含在数据库名称中（如 "孟加拉" 匹配 "孟加拉国"）
    query = select(CountryInfo).where(CountryInfo.country_name_zh.like(f"%{country_input}%")).order_by(
        func.length(CountryInfo.country_name_zh).desc()  # 按名称长度降序，优先匹配最长的
    )
    result = await db.execute(query)
    country = result.scalar_one_or_none()
    if country:
        return country.alpha_2_code
    
    # 情况2：数据库名称包含在输入值中（如 "多米尼加共和国" 匹配 "多米尼加"）
    query = select(CountryInfo).where(CountryInfo.country_name_zh.like(f"{country_input}%")).order_by(
        func.length(CountryInfo.country_name_zh).desc()  # 按名称长度降序，优先匹配最长的
    )
    result = await db.execute(query)
    country = result.scalar_one_or_none()
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
    result = await db.execute(query)
    country = result.scalar_one_or_none()
    if country:
        return country.alpha_2_code
    
    # 官方中文名称部分匹配
    query = select(CountryInfo).where(CountryInfo.official_name_zh.like(f"%{country_input}%")).order_by(
        func.length(CountryInfo.official_name_zh).desc()
    )
    result = await db.execute(query)
    country = result.scalar_one_or_none()
    if country:
        return country.alpha_2_code
    
    # 8. 特殊处理：unknown 匹配 "未知区域"
    if country_input.lower() == "unknown":
        query = select(CountryInfo).where(
            (CountryInfo.country_name_en.ilike("unknown")) | 
            (CountryInfo.country_name_zh == "未知区域") |
            (CountryInfo.alpha_2_code == "AA")
        )
        result = await db.execute(query)
        country = result.scalar_one_or_none()
        if country:
            return country.alpha_2_code
    
    # 如果所有格式都找不到，返回 None
    return None

