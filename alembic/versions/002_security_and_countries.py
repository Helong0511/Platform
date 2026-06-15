"""security_and_countries: 敏感路径黑名单与国家字典表

Revision ID: 002_security_and_countries
Revises: 001_baseline
Create Date: 2026-06-15

增量迁移（幂等）：为已有生产库补齐 ORM 已定义但可能缺失的表。
新环境：先导入 sql/platform.sql，再 ``alembic stamp head``。
已有库：``alembic upgrade head``。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "002_security_and_countries"
down_revision: Union[str, None] = "001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return name in inspect(bind).get_table_names()


def upgrade() -> None:
    if not _has_table("countries"):
        op.create_table(
            "countries",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("alpha_2_code", sa.String(length=2), nullable=False),
            sa.Column("alpha_3_code", sa.String(length=3), nullable=False),
            sa.Column("numeric_code", sa.String(length=3), nullable=False),
            sa.Column("country_name_zh", sa.String(length=100), nullable=False),
            sa.Column("country_name_en", sa.String(length=100), nullable=False),
            sa.Column("official_name_zh", sa.String(length=150), nullable=True),
            sa.Column("official_name_en", sa.String(length=150), nullable=True),
            sa.Column("independent_status", sa.Boolean(), nullable=True, server_default=sa.text("1")),
            sa.Column("continent", sa.String(length=50), nullable=True),
            sa.Column("subregion", sa.String(length=50), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("alpha_2_code"),
            sa.UniqueConstraint("alpha_3_code"),
            sa.UniqueConstraint("numeric_code"),
            mysql_charset="utf8mb4",
        )
        op.create_index("idx_country_name_zh", "countries", ["country_name_zh"])
        op.create_index("idx_country_name_en", "countries", ["country_name_en"])
        op.create_index("idx_continent", "countries", ["continent"])
        op.create_index("idx_subregion", "countries", ["subregion"])

    if not _has_table("country_aliases"):
        op.create_table(
            "country_aliases",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("alias_name", sa.String(length=150), nullable=False),
            sa.Column("alias_normalized", sa.String(length=150), nullable=False),
            sa.Column("alpha_2_code", sa.String(length=2), nullable=False),
            sa.Column("remark", sa.String(length=255), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("alias_normalized", name="uq_country_alias_normalized"),
            mysql_charset="utf8mb4",
        )
        op.create_index("idx_country_alias_alpha2", "country_aliases", ["alpha_2_code"])

    if not _has_table("sensitive_path_probe_logs"):
        op.create_table(
            "sensitive_path_probe_logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("request_path", sa.String(length=1024), nullable=False),
            sa.Column("method", sa.String(length=16), nullable=True),
            sa.Column("client_ip", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.String(length=512), nullable=True),
            sa.Column("query_string", sa.String(length=2048), nullable=True),
            sa.Column("matched_rule", sa.String(length=255), nullable=True),
            sa.Column("severity_level", sa.Integer(), nullable=False, server_default=sa.text("2")),
            sa.Column("action_taken", sa.String(length=64), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.PrimaryKeyConstraint("id"),
            mysql_charset="utf8mb4",
        )
        op.create_index("idx_sensitive_probe_created_at", "sensitive_path_probe_logs", ["created_at"])
        op.create_index(
            "idx_sensitive_probe_ip_created",
            "sensitive_path_probe_logs",
            ["client_ip", "created_at"],
        )
        op.create_index(
            "idx_sensitive_probe_severity_created",
            "sensitive_path_probe_logs",
            ["severity_level", "created_at"],
        )

    if not _has_table("sensitive_blocked_ips"):
        op.create_table(
            "sensitive_blocked_ips",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("blocked_ip", sa.String(length=64), nullable=False),
            sa.Column("reason", sa.String(length=255), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("blocked_ip"),
            mysql_charset="utf8mb4",
        )
        op.create_index("idx_sensitive_blocked_ip_active", "sensitive_blocked_ips", ["is_active", "created_at"])


def downgrade() -> None:
    for table in (
        "sensitive_blocked_ips",
        "sensitive_path_probe_logs",
        "country_aliases",
        "countries",
    ):
        if _has_table(table):
            op.drop_table(table)
