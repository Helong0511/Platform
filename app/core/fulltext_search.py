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
            
            # 普通自然语言模式；勿用 WITH QUERY EXPANSION（小表会近乎全表命中）
            match_clause = text(
                f"MATCH({fields_str}) AGAINST(:search_term IN NATURAL LANGUAGE MODE)"
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


def apply_like_search(base_query, model_class, search_fields: list[str], search_term: str):
    """对查询挂上 LIKE 条件；无有效字段时原样返回。"""
    like_conditions = build_like_query_conditions(
        model_class,
        search_fields,
        search_term,
    )
    if like_conditions:
        return base_query.where(or_(*like_conditions))
    return base_query


async def search_with_fulltext(
    db: AsyncSession,
    model_class,
    search_fields: list[str],
    search_term: str,
    base_query=None,
    use_fulltext: bool = True
):
    """
    构建带关键词条件的查询（优先 FULLTEXT，否则 LIKE）。

    注意：本函数只组装 SQL，不执行。无索引等执行期错误须由调用方捕获后
    以 ``use_fulltext=False`` 重试，或直接使用 ``apply_like_search``。
    小表（如 scheduled_tasks）建议 ``use_fulltext=False``。

    参数:
        db: 数据库会话（保留以兼容调用方；当前未使用）
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

    table_name = model_class.__tablename__

    if use_fulltext:
        fulltext_condition = build_fulltext_query(
            table_name,
            search_fields,
            search_term,
            use_fulltext=True
        )

        # SQLAlchemy ClauseElement 禁止用 if clause 做真值判断，须显式 is not None
        if fulltext_condition is not None:
            try:
                # 使用 MATCH AGAINST；调用方须保证表有对应全文索引
                return base_query.where(fulltext_condition)
            except Exception as e:
                logger.warning(f"全文搜索条件构建失败: {e}，回退到LIKE查询")

    return apply_like_search(base_query, model_class, search_fields, search_term)

