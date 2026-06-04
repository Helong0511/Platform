"""baseline: 现有 schema 以 sql/platform.sql 为准

Revision ID: 001_baseline
Revises:
Create Date: 2026-06-04

首次 Alembic 基线：不对已有生产库执行 DDL。
新环境请先导入 sql/platform.sql，再 alembic stamp 001_baseline。
此后增量变更请 alembic revision --autogenerate。
"""
from typing import Sequence, Union

revision: str = "001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
