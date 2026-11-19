"""
FastAPI 应用 lifespan（启动 / 关闭）。
"""
import asyncio
import logging
import os
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import bindparam, inspect, text

from app.core.cache_manager import CacheManager
from app.core.config import settings
from app.core.security import validate_production_jwt_keypair
from app.core.database import AsyncSessionLocal, engine, init_db
from app.core.redis_client import close_redis_client, get_redis_client
from app.core.telegram.file_lock import is_lock_held as has_bot_lock
from app.core.telegram.file_lock import release_bot_lock
from app.core.telegram.polling_manager import start_bot_thread, stop_polling_application
from app.core.telegram.service_notify import (
    notify_service_started,
    notify_service_stopped,
    should_run_telegram_polling,
)
from app.core.telegram.shared_state import cleanup_stale_shared_state
from app.core.timezone_utils import check_and_validate_timezone, log_timezone_info
from app.db.migrations.gate import verify_schema_revision
from app.db.schema_contract import (
    BASELINE_MYSQL_TABLE_OPTIONS,
    MIGRATION_MYSQL_TABLE_OPTIONS,
)
from app.models import Base
from app.scheduler_module import init_scheduled_tasks, shutdown_scheduler, start_scheduler
from app.scheduler_module.task_init import init_scheduled_tasks_in_db

logger = logging.getLogger(__name__)


def _schema_metadata_drift(sync_connection, metadata=None) -> dict:
    """只读核验 ORM 表、列、类型、NULL、主键、索引、外键及显式表字符集规则；绝不执行 DDL。"""
    from decimal import Decimal, InvalidOperation

    from sqlalchemy import Boolean, Integer, Numeric, String
    from sqlalchemy.schema import Computed, DefaultClause

    target_metadata = metadata or Base.metadata
    inspector = inspect(sync_connection)
    missing_tables = []
    missing_columns = {}
    column_type_mismatches = {}
    nullable_mismatches = {}
    column_attribute_mismatches = {}
    column_default_mismatches = {}
    column_default_unverifiable = {}
    column_onupdate_mismatches = {}
    column_generated_mismatches = {}
    column_generated_unverifiable = {}
    column_visibility_mismatches = {}
    column_collation_mismatches = {}
    primary_key_mismatches = {}
    index_mismatches = {}
    index_attribute_mismatches = {}
    unique_constraint_mismatches = {}
    foreign_key_mismatches = {}
    check_constraint_mismatches = {}
    table_option_mismatches = {}

    def type_mismatch(expected_type, actual_type, dialect_name: str) -> bool:
        expected_affinity = expected_type._type_affinity
        actual_affinity = actual_type._type_affinity
        if dialect_name == "mysql" and isinstance(expected_type, Boolean):
            is_mysql_boolean_storage = (
                actual_type.__class__.__name__.upper() == "TINYINT"
                and (
                    getattr(actual_type, "display_width", None) == 1
                    or getattr(actual_type, "length", None) == 1
                )
            )
            affinity_matches = actual_affinity is Boolean or is_mysql_boolean_storage
        else:
            affinity_matches = expected_affinity is actual_affinity
        if not affinity_matches:
            return True
        if isinstance(expected_type, String) and expected_type.length is not None:
            if getattr(actual_type, "length", None) != expected_type.length:
                return True
        if isinstance(expected_type, Numeric):
            for attribute in ("precision", "scale"):
                expected_value = getattr(expected_type, attribute, None)
                if expected_value is not None and getattr(actual_type, attribute, None) != expected_value:
                    return True
        expected_collation = getattr(expected_type, "collation", None)
        if expected_collation and getattr(actual_type, "collation", None) != expected_collation:
            return True
        return False

    def foreign_key_signature(item):
        options = item.get("options") or {}
        return (
            tuple(item.get("constrained_columns") or ()),
            item.get("referred_table"),
            tuple(item.get("referred_columns") or ()),
            (options.get("ondelete") or "").upper(),
            (options.get("onupdate") or "").upper(),
        )

    dialect_name = sync_connection.dialect.name
    sorted_tables = target_metadata.sorted_tables

    # MySQL 列属性和表级字符集规则按 schema 批量读取，避免逐列/逐表往返。
    mysql_column_extras_by_table = {}
    mysql_table_options_by_table = {}
    mysql_index_parts_by_table = {}
    default_schema = None
    if dialect_name == "mysql":
        default_schema = sync_connection.execute(text("SELECT DATABASE()")).scalar_one_or_none()
        tables_by_schema = {}
        for metadata_table in sorted_tables:
            schema_name = metadata_table.schema or default_schema
            if schema_name:
                tables_by_schema.setdefault(schema_name, []).append(metadata_table.name)
        # 正式 SQL 基线的表级规则与 ORM 显式选项共同构成可核验契约。
        expected_table_names = (
            set(BASELINE_MYSQL_TABLE_OPTIONS)
            | set(MIGRATION_MYSQL_TABLE_OPTIONS)
        )
        for metadata_table in sorted_tables:
            mysql_options = metadata_table.dialect_options["mysql"]
            if mysql_options.get("charset") or mysql_options.get("collate"):
                expected_table_names.add(metadata_table.name)
        table_options_statement = text(
            "SELECT t.TABLE_NAME, t.TABLE_COLLATION, c.CHARACTER_SET_NAME "
            "FROM information_schema.TABLES AS t "
            "LEFT JOIN information_schema.COLLATIONS AS c "
            "ON c.COLLATION_NAME = t.TABLE_COLLATION "
            "WHERE t.TABLE_SCHEMA = :schema_name AND t.TABLE_NAME IN :table_names"
        ).bindparams(bindparam("table_names", expanding=True))
        for schema_name, table_names in tables_by_schema.items():
            requested_tables = sorted(set(table_names) & expected_table_names)
            if not requested_tables:
                continue
            option_rows = sync_connection.execute(
                table_options_statement,
                {"schema_name": schema_name, "table_names": requested_tables},
            ).mappings().all()
            for row in option_rows:
                mysql_table_options_by_table[(schema_name, row["TABLE_NAME"])] = {
                    "mysql_charset": row.get("CHARACTER_SET_NAME"),
                    "mysql_collate": row.get("TABLE_COLLATION"),
                }

        column_extras_statement = text(
            "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_DEFAULT, EXTRA, GENERATION_EXPRESSION, "
            "CHARACTER_SET_NAME, COLLATION_NAME "
            "FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = :schema_name AND TABLE_NAME IN :table_names"
        ).bindparams(bindparam("table_names", expanding=True))
        # 索引结构同样按 schema 批量读取；Inspector 的列名列表不包含 MySQL 前缀、
        # 方向、索引方法、函数 key part 和可见性等完整属性。
        index_parts_statement = text(
            "SELECT TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX, COLUMN_NAME, EXPRESSION, "
            "COLLATION, SUB_PART, INDEX_TYPE, IS_VISIBLE "
            "FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA = :schema_name AND TABLE_NAME IN :table_names "
            "ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX"
        ).bindparams(bindparam("table_names", expanding=True))
        for schema_name, table_names in tables_by_schema.items():
            index_rows = sync_connection.execute(
                index_parts_statement,
                {"schema_name": schema_name, "table_names": sorted(set(table_names))},
            ).mappings().all()
            for row in index_rows:
                table_key = (schema_name, row["TABLE_NAME"])
                mysql_index_parts_by_table.setdefault(table_key, {}).setdefault(
                    row["INDEX_NAME"], []
                ).append(row)
        for schema_name, table_names in tables_by_schema.items():
            extra_rows = sync_connection.execute(
                column_extras_statement,
                {"schema_name": schema_name, "table_names": sorted(set(table_names))},
            ).mappings().all()
            for row in extra_rows:
                table_key = (schema_name, row["TABLE_NAME"])
                column_key = row["COLUMN_NAME"]
                mysql_column_extras_by_table.setdefault(table_key, {})[column_key] = {
                    "extra": (row.get("EXTRA") or "").casefold(),
                    "default": row.get("COLUMN_DEFAULT"),
                    "generation_expression": row.get("GENERATION_EXPRESSION"),
                    "character_set": row.get("CHARACTER_SET_NAME"),
                    "collation": row.get("COLLATION_NAME"),
                }

    for table in sorted_tables:
        if not inspector.has_table(table.name, schema=table.schema):
            missing_tables.append(table.fullname)
            continue

        actual_columns = {
            column["name"]: column
            for column in inspector.get_columns(table.name, schema=table.schema)
        }
        absent = sorted(
            column.name for column in table.columns
            if column.name not in actual_columns
        )
        if absent:
            missing_columns[table.fullname] = absent

        mysql_schema_name = (
            (table.schema or default_schema) if dialect_name == "mysql" else None
        )
        mysql_column_extras = mysql_column_extras_by_table.get(
            (mysql_schema_name, table.name), {}
        )

        def expected_server_default(column):
            # FetchedValue 只是“数据库会生成值”的标记；只有 DefaultClause 才代表 DDL DEFAULT。
            server_default = column.server_default
            if not isinstance(server_default, DefaultClause):
                return None
            argument = server_default.arg
            # SQLAlchemy 的普通字符串参数按列类型编译为字面量，不是 SQL 表达式。
            if isinstance(argument, str):
                return ("literal", argument)
            raw = str(argument).strip()
            # MySQL 可在同一 DEFAULT 子句中声明 ON UPDATE CURRENT_TIMESTAMP。
            timestamp_with_onupdate = re.fullmatch(
                r"(CURRENT_TIMESTAMP(?:\(\d+\))?)\s+ON\s+UPDATE\s+"
                r"CURRENT_TIMESTAMP(?:\(\d+\))?",
                raw,
                flags=re.IGNORECASE,
            )
            if timestamp_with_onupdate:
                return (
                    "expression",
                    re.sub(r"\s+", "", timestamp_with_onupdate.group(1)).casefold(),
                )
            # text("'literal'") 是显式 SQL 字符串常量；处理 SQL 单引号转义。
            quoted = re.fullmatch(r"'((?:''|[^'])*)'", raw)
            if quoted:
                return ("literal", quoted.group(1).replace("''", "'"))
            if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", raw):
                return ("literal", raw)
            if re.fullmatch(r"(?i)CURRENT_TIMESTAMP(?:\(\d+\))?", raw):
                return ("expression", re.sub(r"\s+", "", raw).casefold())
            # 不猜测函数、运算符或厂商扩展表达式的语义。
            return ("unverifiable", raw)

        def expected_mysql_onupdate(column):
            # server_onupdate/FetchedValue 是数据库生成值标记，不等于具体的 MySQL DDL。
            # 只有 server_default 明确写出 ON UPDATE 子句时才把它视为可核验要求。
            if column.server_onupdate is not None:
                return None
            server_default = column.server_default
            if not isinstance(server_default, DefaultClause):
                return False
            argument = server_default.arg
            if isinstance(argument, str):
                return False
            raw = str(argument).strip()
            return bool(
                re.fullmatch(
                    r"CURRENT_TIMESTAMP(?:\(\d+\))?\s+ON\s+UPDATE\s+"
                    r"CURRENT_TIMESTAMP(?:\(\d+\))?",
                    raw,
                    flags=re.IGNORECASE,
                )
            )

        def normalize_generated_expression(expression):
            # 只比较不含字符串/双引号字面量的简单表达式；复杂表达式宁可告警也不误报。
            raw = str(expression if expression is not None else "").strip()
            if not raw or chr(39) in raw or chr(34) in raw:
                return None
            raw = raw.replace(chr(96), "")
            # MySQL 元数据可能为表达式额外包裹括号；仅剥离完整包裹表达式的括号。
            while raw.startswith("(") and raw.endswith(")"):
                depth = 0
                wraps_expression = True
                for position, char in enumerate(raw):
                    if char == "(":
                        depth += 1
                    elif char == ")":
                        depth -= 1
                        if depth == 0 and position != len(raw) - 1:
                            wraps_expression = False
                            break
                if not wraps_expression or depth != 0:
                    break
                raw = raw[1:-1].strip()
            raw = re.sub(r"\s+", " ", raw)
            raw = re.sub(r"\s*([(),+\-*/%<>=!|&^])\s*", r"\1", raw)
            return raw.casefold()

        def expected_generated_expression(column):
            computed = column.computed
            if not isinstance(computed, Computed):
                return None
            return str(computed.sqltext).strip()

        def defaults_equal(column, expected, actual_value, actual_extra):
            expected_kind, expected_value = expected
            if actual_value is None:
                return False
            actual_text = str(actual_value).strip()
            is_generated_expression = "default_generated" in actual_extra
            if expected_kind == "expression":
                actual_expression = re.sub(r"\s+", "", actual_text).casefold()
                return is_generated_expression and actual_expression == expected_value
            if is_generated_expression:
                return False
            if isinstance(column.type, (Integer, Numeric, Boolean)):
                try:
                    return Decimal(actual_text) == Decimal(str(expected_value))
                except (InvalidOperation, ValueError):
                    return False
            return actual_text == str(expected_value)

        for column in table.columns:
            actual = actual_columns.get(column.name)
            if actual is None:
                continue
            if type_mismatch(column.type, actual["type"], dialect_name):
                column_type_mismatches.setdefault(table.fullname, {})[column.name] = {
                    "expected": str(column.type),
                    "actual": str(actual["type"]),
                }
            # 主键列的非空语义由 PK 约束保证；SQLite 反射可能报告 nullable=True。
            if (
                not column.primary_key
                and bool(actual["nullable"]) != bool(column.nullable)
            ):
                nullable_mismatches.setdefault(table.fullname, {})[column.name] = {
                    "expected": bool(column.nullable),
                    "actual": bool(actual["nullable"]),
                }

            if dialect_name == "mysql":
                # SQLAlchemy 的 auto 表示单列整数主键采用方言默认自增规则；
                # Python default/onupdate 不属于数据库列属性，不在此处推断。
                # 仅核验 ORM 显式声明的数据库自增要求。SQLAlchemy 的
                # autoincrement="auto" 是方言生成 DDL 的默认策略，不足以证明
                # 现有迁移/外部建表必须具备 AUTO_INCREMENT。
                expected_autoincrement = column.autoincrement is True
                column_extra = mysql_column_extras.get(column.name, {})
                actual_extra = column_extra.get("extra", "")
                # 仅核验 ORM 显式声明的列级 collation；未指定时遵循表/库默认值，不猜测。
                expected_collation = getattr(column.type, "collation", None)
                if expected_collation:
                    expected_collation = str(expected_collation)
                    # MySQL collation 名称以字符集名称作为前缀，例如 utf8mb4_bin / ascii_bin。
                    expected_charset = expected_collation.split("_", 1)[0]
                    actual_collation = column_extra.get("collation")
                    actual_charset = column_extra.get("character_set")
                    if (
                        (actual_collation or "").casefold() != expected_collation.casefold()
                        or (actual_charset or "").casefold() != expected_charset.casefold()
                    ):
                        column_collation_mismatches.setdefault(table.fullname, {})[column.name] = {
                            "expected": {
                                "character_set": expected_charset,
                                "collation": expected_collation,
                            },
                            "actual": {
                                "character_set": actual_charset,
                                "collation": actual_collation,
                            },
                        }
                # ORM 映射列默认可见；数据库意外设为 INVISIBLE 会改变 SELECT * 的结果。
                actual_invisible = "invisible" in actual_extra.split()
                if actual_invisible:
                    column_visibility_mismatches.setdefault(table.fullname, {})[column.name] = {
                        "expected": "visible",
                        "actual": "invisible",
                    }
                actual_autoincrement = "auto_increment" in actual_extra
                if expected_autoincrement != actual_autoincrement:
                    column_attribute_mismatches.setdefault(
                        table.fullname, {}
                    )[column.name] = {
                        "autoincrement": {
                            "expected": expected_autoincrement,
                            "actual": actual_autoincrement,
                        }
                    }

                actual_onupdate = bool(
                    re.search(
                        r"\bon\s+update\s+current_timestamp(?:\(\d+\))?",
                        actual_extra,
                    )
                )
                expected_onupdate = expected_mysql_onupdate(column)
                if (
                    expected_onupdate is not None
                    and actual_onupdate != expected_onupdate
                ):
                    column_onupdate_mismatches.setdefault(
                        table.fullname, {}
                    )[column.name] = {
                        "expected": expected_onupdate,
                        "actual": actual_onupdate,
                    }

                actual_generated_kind = (
                    "stored" if "stored generated" in actual_extra
                    else "virtual" if "virtual generated" in actual_extra
                    else None
                )
                expected_computed = column.computed
                actual_generation_expression = column_extra.get("generation_expression")
                if isinstance(expected_computed, Computed):
                    expected_expression = expected_generated_expression(column)
                    expected_normalized = normalize_generated_expression(expected_expression)
                    if actual_generated_kind is None:
                        column_generated_mismatches.setdefault(table.fullname, {})[column.name] = {
                            "expected": {"expression": expected_expression, "persisted": expected_computed.persisted},
                            "actual": None,
                        }
                    else:
                        actual_normalized = normalize_generated_expression(actual_generation_expression)
                        generated_difference = {}
                        if expected_normalized is None or actual_normalized is None:
                            column_generated_unverifiable.setdefault(table.fullname, {})[column.name] = {
                                "expected": expected_expression, "actual": actual_generation_expression
                            }
                        elif expected_normalized != actual_normalized:
                            generated_difference["expression"] = {"expected": expected_expression, "actual": actual_generation_expression}
                        # 存储模式不依赖表达式解析结果，可以独立安全核验。
                        if expected_computed.persisted is not None:
                            expected_kind = "stored" if expected_computed.persisted else "virtual"
                            if actual_generated_kind != expected_kind:
                                generated_difference["persisted"] = {"expected": expected_kind, "actual": actual_generated_kind}
                        if generated_difference:
                            column_generated_mismatches.setdefault(table.fullname, {})[column.name] = generated_difference
                elif actual_generated_kind is not None:
                    column_generated_mismatches.setdefault(table.fullname, {})[column.name] = {
                        "expected": None,
                        "actual": {"expression": actual_generation_expression, "persisted": actual_generated_kind},
                    }
                expected_default = expected_server_default(column)
                if expected_default:
                    if expected_default[0] == "unverifiable":
                        column_default_unverifiable.setdefault(
                            table.fullname, {}
                        )[column.name] = expected_default[1]
                    elif not defaults_equal(
                        column,
                        expected_default,
                        column_extra.get("default"),
                        actual_extra,
                    ):
                        column_default_mismatches.setdefault(
                            table.fullname, {}
                        )[column.name] = {
                            "expected": expected_default[1],
                            "actual": column_extra.get("default"),
                        }

        expected_pk = sorted(column.name for column in table.primary_key.columns)
        actual_pk = sorted(
            inspector.get_pk_constraint(table.name, schema=table.schema).get("constrained_columns") or []
        )
        if expected_pk != actual_pk:
            primary_key_mismatches[table.fullname] = {
                "expected": expected_pk,
                "actual": actual_pk,
            }

        expected_indexes = sorted(
            (index.name, tuple(column.name for column in index.columns))
            for index in table.indexes
            if not index.unique
        )
        actual_indexes = sorted(
            (item.get("name"), tuple(item.get("column_names") or ()))
            for item in inspector.get_indexes(table.name, schema=table.schema)
            if item.get("name") and not item.get("unique")
        )
        if expected_indexes != actual_indexes:
            index_mismatches[table.fullname] = {
                "expected": expected_indexes,
                "actual": actual_indexes,
            }

        if dialect_name == "mysql":
            actual_index_parts = mysql_index_parts_by_table.get(
                (mysql_schema_name, table.name), {}
            )
            attribute_mismatches = {}
            for expected_index in table.indexes:
                if not expected_index.name:
                    continue
                expected_columns = list(expected_index.expressions)
                expected_using = (
                    expected_index.dialect_options["mysql"].get("using") or "BTREE"
                ).upper()
                expected_length = expected_index.dialect_options["mysql"].get("length")
                actual_parts = actual_index_parts.get(expected_index.name, [])
                if not actual_parts:
                    # 名称/列集合缺失已由 index_mismatches 报告，不重复生成属性告警。
                    continue
                part_mismatches = []
                for position, expression in enumerate(expected_columns):
                    if position >= len(actual_parts):
                        part_mismatches.append({
                            "position": position + 1,
                            "expected": "index key part",
                            "actual": None,
                        })
                        continue
                    actual_part = actual_parts[position]
                    modifier = getattr(expression, "modifier", None)
                    direction = "D" if getattr(modifier, "__name__", "") == "desc_op" else "A"
                    base_expression = getattr(expression, "element", expression)
                    expected_column = getattr(base_expression, "name", None)
                    if isinstance(expected_length, dict):
                        prefix_length = expected_length.get(expected_column)
                    else:
                        prefix_length = expected_length
                    actual_expression = actual_part.get("EXPRESSION")
                    actual_column = actual_part.get("COLUMN_NAME")
                    actual_direction = actual_part.get("COLLATION")
                    actual_prefix = actual_part.get("SUB_PART")
                    actual_type = str(actual_part.get("INDEX_TYPE") or "").upper()
                    actual_visibility = str(actual_part.get("IS_VISIBLE") or "").upper()
                    differences = {}
                    if expected_column is not None and (
                        actual_column != expected_column or actual_expression is not None
                    ):
                        differences["column_or_expression"] = {
                            "expected_column": expected_column,
                            "actual_column": actual_column,
                            "actual_expression": actual_expression,
                        }
                    elif expected_column is None:
                        # 非简单列表达式目前不做文本等价推断，避免错误地宣称已核验。
                        differences["expression"] = {
                            "expected": str(expression),
                            "actual": actual_expression,
                            "verification": "unsupported_expression_metadata",
                        }
                    if (int(actual_prefix) if actual_prefix is not None else None) != (
                        int(prefix_length) if prefix_length is not None else None
                    ):
                        differences["prefix_length"] = {
                            "expected": prefix_length,
                            "actual": actual_prefix,
                        }
                    if actual_direction != direction:
                        differences["direction"] = {
                            "expected": direction,
                            "actual": actual_direction,
                        }
                    if actual_type != expected_using:
                        differences["index_type"] = {
                            "expected": expected_using,
                            "actual": actual_type,
                        }
                    if actual_visibility != "YES":
                        differences["visibility"] = {
                            "expected": "YES",
                            "actual": actual_visibility,
                        }
                    if differences:
                        part_mismatches.append({
                            "position": position + 1,
                            "differences": differences,
                        })
                if len(actual_parts) != len(expected_columns):
                    part_mismatches.append({
                        "key_part_count": {
                            "expected": len(expected_columns),
                            "actual": len(actual_parts),
                        }
                    })
                if part_mismatches:
                    attribute_mismatches[expected_index.name] = part_mismatches
            if attribute_mismatches:
                index_attribute_mismatches[table.fullname] = attribute_mismatches

        expected_unique = sorted({
            tuple(column.name for column in constraint.columns)
            for constraint in table.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        } | {
            tuple(column.name for column in index.columns)
            for index in table.indexes
            if index.unique
        })
        actual_unique = sorted({
            tuple(item.get("column_names") or ())
            for item in inspector.get_unique_constraints(table.name, schema=table.schema)
        } | {
            tuple(item.get("column_names") or ())
            for item in inspector.get_indexes(table.name, schema=table.schema)
            if item.get("unique")
        })
        if expected_unique != actual_unique:
            unique_constraint_mismatches[table.fullname] = {
                "expected": expected_unique,
                "actual": actual_unique,
            }

        expected_fks = sorted(
            (
                tuple(element.parent.name for element in fk.elements),
                fk.elements[0].column.table.name,
                tuple(element.column.name for element in fk.elements),
                (fk.ondelete or "").upper(),
                (fk.onupdate or "").upper(),
            )
            for fk in table.foreign_key_constraints
        )
        actual_fks = sorted(
            foreign_key_signature(item)
            for item in inspector.get_foreign_keys(table.name, schema=table.schema)
        )
        if expected_fks != actual_fks:
            foreign_key_mismatches[table.fullname] = {
                "expected": expected_fks,
                "actual": actual_fks,
            }

        # CHECK 约束不只核对名称：同名但表达式被放宽（例如 OR 1=1）同样属于 schema drift。
        def normalize_check_expression(expression) -> str:
            normalized = " ".join(str(expression if expression is not None else "").replace("`", "").split()).casefold()
            # MySQL Inspector 会为字符串字面量补充字符集 introducer（如 _utf8mb4''）；
            # 该标记不改变字面量值，比较 ORM 与数据库表达式前应移除。
            normalized = re.sub(r"(?<![a-z0-9_$])_[a-z0-9]+(?=\')", "", normalized)
            # MySQL Inspector 可能为表达式增加一层括号；仅剥离完整包裹表达式的括号。
            while normalized.startswith("(") and normalized.endswith(")"):
                depth = 0
                wraps_expression = True
                quote = None
                for position, char in enumerate(normalized):
                    if quote:
                        if char == quote:
                            quote = None
                        continue
                    if char in {"'", '"'}:
                        quote = char
                    elif char == "(":
                        depth += 1
                    elif char == ")":
                        depth -= 1
                        if depth == 0 and position != len(normalized) - 1:
                            wraps_expression = False
                            break
                if not wraps_expression or depth != 0:
                    break
                normalized = normalized[1:-1].strip()
            return normalized

        expected_checks = {
            constraint.name: normalize_check_expression(constraint.sqltext)
            for constraint in table.constraints
            if constraint.__class__.__name__ == "CheckConstraint" and constraint.name
        }
        actual_check_rows = [
            item
            for item in inspector.get_check_constraints(table.name, schema=table.schema)
            if item.get("name")
        ]
        actual_checks = {
            item["name"]: normalize_check_expression(item.get("sqltext"))
            for item in actual_check_rows
        }
        check_mismatches = {}
        if expected_checks != actual_checks:
            check_mismatches["expressions"] = {
                "expected": expected_checks,
                "actual": actual_checks,
            }

        if dialect_name == "mysql" and expected_checks:
            schema_name = table.schema or default_schema
            if schema_name:
                enforced_rows = sync_connection.execute(
                    text(
                        "SELECT CONSTRAINT_NAME, ENFORCED "
                        "FROM information_schema.TABLE_CONSTRAINTS "
                        "WHERE CONSTRAINT_SCHEMA = :schema_name "
                        "AND TABLE_NAME = :table_name AND CONSTRAINT_TYPE = 'CHECK'"
                    ),
                    {"schema_name": schema_name, "table_name": table.name},
                ).mappings().all()
                enforced = {row["CONSTRAINT_NAME"]: row["ENFORCED"] for row in enforced_rows}
                unenforced = sorted(
                    name for name in expected_checks
                    if enforced.get(name) != "YES"
                )
                if unenforced:
                    check_mismatches["unenforced"] = unenforced

        if check_mismatches:
            check_constraint_mismatches[table.fullname] = check_mismatches

        if dialect_name == "mysql":
            expected_options = dict(
                BASELINE_MYSQL_TABLE_OPTIONS.get(table.name)
                or MIGRATION_MYSQL_TABLE_OPTIONS.get(table.name, {})
            )
            mysql_options = table.dialect_options["mysql"]
            for option in ("charset", "collate"):
                expected_value = mysql_options.get(option)
                if expected_value:
                    expected_options[option] = expected_value
            if expected_options:
                schema_name = table.schema or default_schema
                actual_options = mysql_table_options_by_table.get(
                    (schema_name, table.name), {}
                )
                mismatches = {}
                for option, expected_value in expected_options.items():
                    actual_key = "mysql_charset" if option == "charset" else "mysql_collate"
                    actual_value = actual_options.get(actual_key)
                    if (actual_value or "").casefold() != expected_value.casefold():
                        mismatches[actual_key] = {"expected": expected_value, "actual": actual_value}
                if mismatches:
                    table_option_mismatches[table.fullname] = mismatches

    return {
        "missing_tables": sorted(missing_tables),
        "missing_columns": missing_columns,
        "column_type_mismatches": column_type_mismatches,
        "nullable_mismatches": nullable_mismatches,
        "column_attribute_mismatches": column_attribute_mismatches,
        "column_default_mismatches": column_default_mismatches,
        "column_default_unverifiable": column_default_unverifiable,
        "column_onupdate_mismatches": column_onupdate_mismatches,
        "column_generated_mismatches": column_generated_mismatches,
        "column_generated_unverifiable": column_generated_unverifiable,
        "column_visibility_mismatches": column_visibility_mismatches,
        "column_collation_mismatches": column_collation_mismatches,
        "primary_key_mismatches": primary_key_mismatches,
        "index_mismatches": index_mismatches,
        "index_attribute_mismatches": index_attribute_mismatches,
        "unique_constraint_mismatches": unique_constraint_mismatches,
        "foreign_key_mismatches": foreign_key_mismatches,
        "check_constraint_mismatches": check_constraint_mismatches,
        "table_option_mismatches": table_option_mismatches,
    }


async def _verify_database_schema() -> str | None:
    """只读核验 migration revision 与 ORM 表/列/类型/NULL/主键/索引/外键/显式字符集；应用 Worker 不执行 schema DDL。"""
    async with engine.connect() as connection:
        current_revision = await verify_schema_revision(connection)
        drift = await connection.run_sync(_schema_metadata_drift)
        unverifiable_defaults = drift.get("column_default_unverifiable") or {}
        if unverifiable_defaults:
            # 无法安全解释的 DEFAULT 表达式只告警，不伪装成已确认的结构差异。
            logger.warning(
                "以下 MySQL server_default 表达式暂不支持自动比较：%s",
                unverifiable_defaults,
            )
        unverifiable_generated = drift.get("column_generated_unverifiable") or {}
        if unverifiable_generated:
            logger.warning("以下 MySQL generated column 表达式暂不支持安全自动比较：%s", unverifiable_generated)
        confirmed_drift = any(
            value
            for key, value in drift.items()
            if key not in {"column_default_unverifiable", "column_generated_unverifiable"}
        )
        if confirmed_drift:
            raise RuntimeError(
                "数据库 schema 与 ORM 不一致："
                f"missing_tables={drift['missing_tables']}; "
                f"missing_columns={drift['missing_columns']}; "
                f"column_type_mismatches={drift['column_type_mismatches']}; "
                f"nullable_mismatches={drift['nullable_mismatches']}; "
                f"column_attribute_mismatches={drift['column_attribute_mismatches']}; "
                f"column_default_mismatches={drift['column_default_mismatches']}; "
                f"column_default_unverifiable={drift['column_default_unverifiable']}; "
                f"column_onupdate_mismatches={drift['column_onupdate_mismatches']}; "
                f"column_generated_mismatches={drift['column_generated_mismatches']}; "
                f"column_generated_unverifiable={drift['column_generated_unverifiable']}; "
                f"column_visibility_mismatches={drift['column_visibility_mismatches']}; "
                f"column_collation_mismatches={drift['column_collation_mismatches']}; "
                f"primary_key_mismatches={drift['primary_key_mismatches']}; "
                f"index_mismatches={drift['index_mismatches']}; "
                f"unique_constraint_mismatches={drift['unique_constraint_mismatches']}; "
                f"foreign_key_mismatches={drift['foreign_key_mismatches']}; "
                f"check_constraint_mismatches={drift['check_constraint_mismatches']}; "
                f"table_option_mismatches={drift['table_option_mismatches']}"
            )
    return current_revision


async def _sync_scheduled_tasks_for_worker(worker_pid: int) -> None:
    """仅调度 Worker 同步任务配置，避免每个 API Worker 重复写入 scheduled_tasks。"""
    if not settings.should_run_scheduler():
        logger.debug(
            "[Worker PID:%s] 纯 API Worker 跳过 scheduled_tasks 配置同步",
            worker_pid,
        )
        return

    try:
        await init_scheduled_tasks_in_db()
        logger.info("[Worker PID:%s] 定时任务配置已同步到数据库", worker_pid)
    except Exception as db_init_error:
        # 不输出数据库异常原文，避免日志泄露 SQL 参数。
        logger.error(
            "[Worker PID:%s] 定时任务配置同步失败：exception_type=%s",
            worker_pid,
            type(db_init_error).__name__,
        )
        # 调度 Worker 不能使用旧配置继续调度，必须拒绝启动。
        raise RuntimeError(
            "定时任务配置同步失败，调度 Worker 拒绝启动"
        ) from db_init_error


async def _start_scheduler_for_worker(worker_pid: int) -> None:
    """启动 APScheduler；任何初始化失败都必须阻止调度 Worker 就绪。"""
    try:
        logger.info("[Worker PID:%s] 开始初始化定时任务调度器...", worker_pid)
        await init_scheduled_tasks()
        logger.info("[Worker PID:%s] 定时任务初始化完成，正在启动调度器...", worker_pid)
        await start_scheduler()
        logger.info("[Worker PID:%s] 定时任务调度器已启动", worker_pid)
    except Exception as scheduler_error:
        # 调度器不可用时不能将 Worker 标记为健康；日志不输出异常原文。
        logger.error(
            "[Worker PID:%s] 定时任务调度器启动失败：exception_type=%s",
            worker_pid,
            type(scheduler_error).__name__,
        )
        raise RuntimeError("定时任务调度器启动失败，调度 Worker 拒绝就绪") from scheduler_error


def _should_run_cache_warmup() -> bool:
    """仅在单进程或 Gunicorn 的首个 API worker 中执行预热。"""
    if os.getenv("GUNICORN_ROLE", "api").strip().lower() == "scheduler":
        return False
    worker_marker = os.getenv("SCHEDULER_WORKER", "").strip()
    if worker_marker:
        return worker_marker == "1"
    return True


# ====== 应用生命周期管理 ======
# 使用 lifespan 上下文管理器替代已弃用的 @app.on_event()
# 这是 FastAPI 0.95.0+ 推荐的方式，提供更好的资源管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理（启动 / 关闭）。

    启动：时区校验 → 只读 schema revision/drift gate → init_db → 缓存预热 → 调度器与 Telegram Bot → Redis
    关闭：停止调度器、释放 Bot 锁、关闭 Redis、通知服务下线
    """
    # ====== 启动时执行 ======
    worker_pid = os.getpid()
    redis_client = None
    cache_warmup_task = None
    logger.info(f"[Worker PID:{worker_pid}] 应用启动中...")

    # 生产 JWT RS256 密钥必须在开始监听请求前完成路径、权限和公私钥匹配校验。
    try:
        validate_production_jwt_keypair()
    except Exception as exc:
        logger.error(
            "[Worker PID:%s] JWT 密钥配置不安全或不可用，拒绝启动：exception_type=%s",
            worker_pid,
            type(exc).__name__,
        )
        raise RuntimeError("JWT 密钥配置未达到生产启动要求，拒绝启动") from exc

    # 检查并验证时区配置（启动时首先检查）
    try:
        timezone_consistent = check_and_validate_timezone()
        if not timezone_consistent:
            logger.warning(
                f"[Worker PID:{worker_pid}] 系统时区与配置时区不一致，"
                "应用将使用配置的时区处理所有时间操作"
            )
        # 记录详细的时区信息
        log_timezone_info()
    except Exception as e:
        logger.warning(f"时区检查时出错: {e}，继续启动...")

    try:
        from app.core.tracking.click_persist import log_click_persist_mode_at_startup

        log_click_persist_mode_at_startup()
    except Exception as e:
        logger.debug("点击落库策略日志跳过: %s", e)

    # 只读核验数据库 migration revision 与 ORM 结构；API/Scheduler Worker 不创建数据库或执行 DDL。
    # 新库必须先由 provisioning 导入基线并运行独立 Migration Runner。
    try:
        current_revision = await _verify_database_schema()
        logger.info(
            "[Worker PID:%s] 数据库 schema revision 与 ORM 结构核验通过：revision=%s",
            worker_pid,
            current_revision,
        )
    except Exception as exc:
        logger.error(
            "[Worker PID:%s] 数据库 schema 初始化/核验失败，拒绝启动：exception_type=%s",
            worker_pid,
            type(exc).__name__,
        )
        raise RuntimeError("数据库 schema 未达到应用启动要求，拒绝启动") from exc

    # 初始化数据库，创建默认管理员账户；核心 DB 初始化失败时不得继续对外提供服务。
    try:
        await init_db()
        logger.info(f"[Worker PID:{worker_pid}] 数据库初始化完成（包括默认管理员账户）")
    except Exception as exc:
        logger.error(
            "[Worker PID:%s] 数据库初始化失败，拒绝启动：exception_type=%s",
            worker_pid,
            type(exc).__name__,
        )
        raise RuntimeError("数据库初始化失败，拒绝启动") from exc

    # 加载标准维度配置（scheduled_tasks.standard_report_type → 内存）
    try:
        from app.core.ad_data_metadata import refresh_standard_report_types
        await refresh_standard_report_types()
        logger.info(f"[Worker PID:{worker_pid}] 标准维度配置加载完成")
    except Exception as e:
        logger.warning(f"[Worker PID:{worker_pid}] 标准维度配置加载失败: {e}，使用内置默认值")

    # 初始化Redis连接（如果配置了）
    try:
        redis_client = await get_redis_client()
        if redis_client:
            logger.info(f"[Worker PID:{worker_pid}] Redis连接已初始化")
        else:
            logger.info(
                f"[Worker PID:{worker_pid}] Redis不可用；支持降级的组件使用内存存储，"
                "短链接/Offer缓存与预热已禁用"
            )
    except Exception as e:
        logger.warning(
            f"[Worker PID:{worker_pid}] Redis初始化失败: {e}；"
            "支持降级的组件使用内存存储，短链接/Offer缓存与预热已禁用"
        )

    # 同步 task_config.py → scheduled_tasks 表；调度 Worker 必须依赖完整配置。
    await _sync_scheduled_tasks_for_worker(worker_pid)

    # 定时任务调度器：仅调度 worker 启动（Gunicorn 多 worker 时由 SCHEDULER_WORKER=1 标识）
    if settings.should_run_scheduler():
        await _start_scheduler_for_worker(worker_pid)
    else:
        logger.info(
            f"[Worker PID:{worker_pid}] 跳过定时任务调度器"
            f"（ENABLE_SCHEDULER/SCHEDULER_WORKER 未启用本 worker；任务记录已同步到数据库）"
        )

    # Telegram：调度进程只发启停通知；API 进程才启动 Bot 轮询（单实例文件锁）
    try:
        cleanup_stale_shared_state()
        telegram_enabled = getattr(settings, 'TELEGRAM_ENABLE', True)
        logger.info(
            f"[Worker PID:{worker_pid}] Telegram 启用={telegram_enabled}, "
            f"轮询={should_run_telegram_polling()}"
        )
        if not telegram_enabled:
            logger.info(f"[Worker PID:{worker_pid}] Telegram 已禁用，跳过")
        elif should_run_telegram_polling():
            from app.core.telegram.bot_initializer import initialize_bot
            from app.core.telegram import bot_state

            logger.info(f"[Worker PID:{worker_pid}] 初始化 Telegram Bot（API 进程）...")
            bot_instance, initialized, available = initialize_bot()
            logger.info(
                f"[Worker PID:{worker_pid}] Bot 初始化: initialized={initialized}, available={available}"
            )
            bot_initialized = bot_state.bot_initialized

            if initialized and bot_initialized:
                start_success = start_bot_thread()
                if not start_success:
                    logger.info(
                        f"[Worker PID:{worker_pid}] Bot 轮询未启动（其他进程已占用或未取得锁）"
                    )
            else:
                logger.info(f"[Worker PID:{worker_pid}] Bot 未配置或初始化失败，跳过轮询")
        else:
            logger.info(
                f"[Worker PID:{worker_pid}] 调度进程不启动 Bot 轮询，仅发送服务启停通知"
            )
    except Exception as e:
        logger.error(f"[Worker PID:{worker_pid}] Telegram 初始化失败: {e}", exc_info=True)
        logger.warning(f"[Worker PID:{worker_pid}] 应用将继续启动，Telegram 可能不可用")

    # 缓存预热：Redis 可用时，仅由首个 API worker 后台执行
    if redis_client and _should_run_cache_warmup():
        # 在后台任务中执行缓存预热，不阻塞应用启动
        async def warmup_cache_background():
            """启动后后台预热字典/配置类缓存，失败仅打警告不阻塞服务。"""
            try:
                async with AsyncSessionLocal() as db:
                    await CacheManager.warmup_all(db)
            except Exception as e:
                logger.warning(f"缓存预热失败: {e}，不影响应用启动")

        # 延迟执行缓存预热，确保数据库和Redis都已初始化
        cache_warmup_task = asyncio.create_task(warmup_cache_background())
        logger.info(f"[Worker PID:{worker_pid}] 缓存预热任务已启动（后台执行）")
    elif not redis_client:
        logger.info(f"[Worker PID:{worker_pid}] 跳过缓存预热：Redis 不可用")
    else:
        logger.info(f"[Worker PID:{worker_pid}] 跳过缓存预热：由首个 API worker 执行")

    # 启动系统监控与性能优化后台任务
    try:
        from app.core.monitoring import start_monitoring_tasks
        from app.core.performance_optimization import (
            optimization_manager,
            start_bottleneck_detection,
        )

        await optimization_manager.ensure_hydrated_from_redis()
        asyncio.create_task(start_monitoring_tasks())
        asyncio.create_task(start_bottleneck_detection())
        logger.info(f"[Worker PID:{worker_pid}] 系统监控与瓶颈检测任务已启动")
    except Exception as e:
        logger.error(f"[Worker PID:{worker_pid}] 系统监控/瓶颈检测任务启动失败: {e}", exc_info=True)
        logger.warning(f"[Worker PID:{worker_pid}] 应用将继续启动，监控功能可能不可用")

    logger.info("应用启动完成")

    # 启动通知放到后台，避免 Telegram 不可达时在 yield 前阻塞、延迟 API 监听
    if getattr(settings, "TELEGRAM_ENABLE", True):

        async def _send_startup_notify_background() -> None:
            try:
                sent = await asyncio.to_thread(notify_service_started)
                if sent:
                    logger.info(f"[Worker PID:{worker_pid}] 已发送服务启动 Telegram 通知")
                else:
                    logger.debug(
                        f"[Worker PID:{worker_pid}] 未发送服务启动通知（非通知 worker 或已禁用）"
                    )
            except Exception as e:
                logger.warning(f"发送服务启动通知失败: {e}", exc_info=True)

        asyncio.create_task(_send_startup_notify_background())
    else:
        logger.info(f"[Worker PID:{worker_pid}] TELEGRAM_ENABLE=false，跳过服务启动通知")

    # ====== 应用运行期间 ======
    yield

    # ====== 关闭时执行 ======
    logger.info("应用关闭中...")
    if cache_warmup_task and not cache_warmup_task.done():
        cache_warmup_task.cancel()
        try:
            await cache_warmup_task
        except asyncio.CancelledError:
            logger.debug("缓存预热任务已取消")
    try:
        from app.core.monitoring import system_monitor

        await system_monitor.stop_resource_monitor()
    except asyncio.CancelledError:
        logger.debug("资源监控关闭时任务被取消（正常关闭流程）")
    except Exception as e:
        logger.warning(f"关闭资源监控时出现错误: {e}")
    try:
        from app.scheduler_module.scheduler import mark_scheduler_shutting_down

        mark_scheduler_shutting_down()
    except Exception:
        pass
    try:
        if settings.should_run_scheduler():
            await shutdown_scheduler()
    except asyncio.CancelledError:
        # 应用关闭时任务被取消是正常的，不需要记录错误
        logger.debug("定时任务调度器关闭时任务被取消（正常关闭流程）")
    except Exception as e:
        logger.warning(f"关闭定时任务调度器时出现错误: {e}")

    try:
        # 关闭Redis连接
        await close_redis_client()
    except asyncio.CancelledError:
        # 应用关闭时任务被取消是正常的，不需要记录错误
        logger.debug("Redis连接关闭时任务被取消（正常关闭流程）")
    except Exception as e:
        logger.warning(f"关闭Redis连接时出现错误: {e}")

    try:
        telegram_enabled = getattr(settings, 'TELEGRAM_ENABLE', True)
        if telegram_enabled:
            try:
                notify_service_stopped()
            except asyncio.CancelledError:
                logger.debug("发送服务关闭通知时任务被取消（正常关闭流程）")
            except asyncio.TimeoutError:
                logger.debug("发送服务关闭通知超时（可能连接已断开）")
            from app.core.telegram import bot_state as _bot_state_mod
            if (
                should_run_telegram_polling()
                and _bot_state_mod.bot_initialized
                and has_bot_lock()
            ):
                try:
                    stop_polling_application(timeout=8.0)
                except Exception as stop_err:
                    logger.warning(f"停止 Telegram Application 时出错: {stop_err}")
                try:
                    release_bot_lock()
                except Exception as stop_err:
                    logger.warning(f"释放 Telegram Bot 锁时出错: {stop_err}")
            elif should_run_telegram_polling() and _bot_state_mod.bot_initialized:
                logger.debug(f"[PID:{os.getpid()}] 未持有 Bot 锁，跳过 stop_bot")
    except asyncio.CancelledError:
        # 应用关闭时任务被取消是正常的，不需要记录错误
        logger.debug("关闭 Telegram 机器人时任务被取消（正常关闭流程）")
    except Exception as e:
        logger.warning(f"关闭 Telegram 机器人时出现错误: {e}")

    try:
        # 清理数据库连接池
        await engine.dispose()
        logger.info("数据库连接池已关闭")
    except asyncio.CancelledError:
        # 应用关闭时任务被取消是正常的，不需要记录错误
        logger.debug("关闭数据库连接池时任务被取消（正常关闭流程）")
    except Exception as e:
        # 关闭时的错误不应该影响应用关闭流程
        logger.warning(f"关闭数据库连接池时出现错误: {e}")
    finally:
        logger.info("应用已关闭")
        # 排空异步日志队列，减少优雅关闭时尾部日志丢失
        try:
            from app.core.log_queue import shutdown_log_queue

            shutdown_log_queue(timeout_sec=2.0)
        except Exception:
            pass
