"""
MySQL 全文搜索查询构建工具。

职责：在合法字段名约束下生成 FULLTEXT/LIKE 混合条件，供列表页关键词检索。

在系统中的位置：``app.core.fulltext_search``，由各 Service 层列表查询引用。
"""
import re
import logging
from typing import Optional
from sqlalchemy import text, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

logger = logging.getLogger(__name__)


def _validate_field_name(field_name: str) -> bool:
    """
    验证字段名是否安全
    只允许字母、数字、下划线
    """
    if not field_name:
        return False
    # 移除反引号后检查
    clean_name = field_name.strip('`')
    # 只允许字母、数字、下划线
    return bool(re.match(r'^[a-zA-Z0-9_]+$', clean_name))


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
            # 验证所有字段名
            validated_fields = []
            for field in search_fields:
                if not _validate_field_name(field):
                    logger.warning(f"无效的字段名，跳过: {field}")
                    continue
                # 清理字段名，移除可能的反引号并重新添加
                clean_field = field.strip('`')
                validated_fields.append(f"`{clean_field}`")
            
            if not validated_fields:
                logger.warning("没有有效的字段名，回退到LIKE查询")
                return None
            
            # 构建字段列表（已验证安全）
            fields_str = ", ".join(validated_fields)
            
            # 使用参数化查询，search_term通过bindparams绑定，安全
            # 注意：MATCH AGAINST的参数需要特殊处理，但我们已经通过bindparams绑定
            match_clause = text(
                f"MATCH({fields_str}) AGAINST(:search_term IN NATURAL LANGUAGE MODE WITH QUERY EXPANSION)"
            )
            # 转义特殊字符，防止SQL注入（虽然使用参数绑定，但MATCH AGAINST可能需要转义）
            escaped_term = search_term.replace("'", "''").replace("\\", "\\\\")
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
        base_query = base_query.where(or_(*like_conditions))
    
    return base_query

