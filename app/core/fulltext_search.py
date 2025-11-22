"""
全文搜索工具模块
提供全文搜索查询构建功能，支持MySQL FULLTEXT索引
"""
import logging
from typing import Optional
from sqlalchemy import text, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

logger = logging.getLogger(__name__)


def build_fulltext_query(
    table_name: str,
    search_fields: list[str],
    search_term: str,
    use_fulltext: bool = True
) -> Optional[text]:
    """
    构建全文搜索查询条件
    
    参数:
        table_name: 表名（用于日志记录）
        search_fields: 要搜索的字段列表
        search_term: 搜索关键词
        use_fulltext: 是否使用FULLTEXT索引（默认True）
    
    返回:
        SQLAlchemy text对象或None
    """
    if not search_term or not search_term.strip():
        return None
    
    search_term = search_term.strip()
    
    # 如果使用全文搜索且字段数量合适
    if use_fulltext and len(search_fields) > 0:
        try:
            # 构建MATCH ... AGAINST查询
            # 使用ngram解析器支持中文搜索
            # 注意：字段名需要加表名前缀或使用反引号
            fields_str = ", ".join([f"`{field}`" for field in search_fields])
            # 转义特殊字符，防止SQL注入
            escaped_term = search_term.replace("'", "''")
            
            # 使用MATCH AGAINST进行全文搜索
            # 支持中文的ngram解析器
            match_clause = text(
                f"MATCH({fields_str}) AGAINST(:search_term IN NATURAL LANGUAGE MODE WITH QUERY EXPANSION)"
            )
            return match_clause.bindparams(search_term=escaped_term)
        except Exception as e:
            logger.warning(f"构建全文搜索查询失败: {e}，回退到LIKE查询")
            # 回退到LIKE查询
            return None
    
    return None


def build_like_query_conditions(
    model_class,
    search_fields: list[str],
    search_term: str
) -> list:
    """
    构建LIKE查询条件（回退方案）
    
    参数:
        model_class: SQLAlchemy模型类
        search_fields: 要搜索的字段列表
        search_term: 搜索关键词
    
    返回:
        查询条件列表
    """
    if not search_term or not search_term.strip():
        return []
    
    search_term = search_term.strip().lower()
    conditions = []
    
    for field_name in search_fields:
        field = getattr(model_class, field_name, None)
        if field is not None:
            # 使用func.lower()进行大小写不敏感搜索
            conditions.append(func.lower(field).like(f"%{search_term}%"))
    
    return conditions


async def search_with_fulltext(
    db: AsyncSession,
    model_class,
    search_fields: list[str],
    search_term: str,
    base_query=None,
    use_fulltext: bool = True
):
    """
    执行全文搜索查询
    
    参数:
        db: 数据库会话
        model_class: SQLAlchemy模型类
        search_fields: 要搜索的字段列表
        search_term: 搜索关键词
        base_query: 基础查询（可选）
        use_fulltext: 是否使用FULLTEXT索引（默认True）
    
    返回:
        查询对象
    """
    if base_query is None:
        base_query = select(model_class)
    
    # 获取表名（用于日志记录）
    table_name = model_class.__tablename__
    
    # 尝试使用全文搜索
    if use_fulltext:
        fulltext_condition = build_fulltext_query(
            table_name,
            search_fields,
            search_term,
            use_fulltext=True
        )
        
        if fulltext_condition:
            try:
                # 使用MATCH AGAINST查询
                # 注意：需要确保表有对应的全文索引
                base_query = base_query.where(fulltext_condition)
                return base_query
            except Exception as e:
                logger.warning(f"全文搜索查询失败: {e}，回退到LIKE查询")
                # 回退到LIKE查询
    
    # 使用LIKE查询（回退方案）
    like_conditions = build_like_query_conditions(
        model_class,
        search_fields,
        search_term
    )
    
    if like_conditions:
        from sqlalchemy import or_
        base_query = base_query.where(or_(*like_conditions))
    
    return base_query

