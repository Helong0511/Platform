"""Cap Reservation 账本 ORM 必须进入统一 metadata，供迁移与建表工具发现。"""
from sqlalchemy import create_engine, insert
from sqlalchemy.exc import IntegrityError

from app.models import Base, CapReservation


def test_cap_reservation_is_registered_in_shared_metadata():
    table = Base.metadata.tables.get("cap_reservations")

    assert table is CapReservation.__table__
    assert table is not None


def test_cap_reservation_has_stable_key_and_recovery_indexes():
    table = CapReservation.__table__

    unique_constraints = {
        constraint.name
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    index_names = {index.name for index in table.indexes}
    check_names = {constraint.name for constraint in table.constraints if constraint.__class__.__name__ == "CheckConstraint"}

    assert "uq_cap_reservation_key" in unique_constraints
    assert {
        "idx_cap_reservation_state_updated",
        "idx_cap_reservation_lease",
        "idx_cap_reservation_event",
        "idx_cap_reservation_scope",
    }.issubset(index_names)
    assert {
        "chk_cap_reservation_key_sha256",
        "chk_cap_reservation_offer_positive",
        "chk_cap_reservation_publisher_positive",
        "chk_cap_reservation_attempts_nonnegative",
        "chk_cap_reservation_kind_date",
        "chk_cap_reservation_state",
    }.issubset(check_names)


def test_cap_reservation_preserves_global_publisher_scope_and_total_date_semantics():
    table = CapReservation.__table__

    assert table.c.publisher_id.nullable is True
    assert table.c.business_date.nullable is True
    assert table.c.redis_reserved.nullable is False
    assert table.c.redis_token_cleaned.nullable is False
    assert table.c.reservation_key.type.length == 64
    assert table.c.redis_token_key.type.length == 512


def test_cap_reservation_check_constraints_are_portable_and_enforced_by_sqlite():
    """ORM CHECK 表达式应可在 SQLite 单测中执行，MySQL migration 再做独立验证。"""
    engine = create_engine("sqlite:///:memory:")
    try:
        CapReservation.__table__.create(engine)
        invalid_row = {
            "reservation_key": "too-short",
            "platform": "ci",
            "conversion_id": "conversion-1",
            "event_name": "purchase",
            "offer_id": 77,
            "publisher_id": None,
            "cap_kind": "daily",
            "business_date": None,
            "redis_counter_key": "counter:key",
            "redis_token_key": "counter:key:reservation:too-short",
            "redis_reserved": False,
            "redis_token_cleaned": False,
            "state": "PREPARED",
            "attempts": 0,
        }
        with engine.begin() as connection:
            import pytest
            with pytest.raises(IntegrityError):
                connection.execute(insert(CapReservation.__table__).values(**invalid_row))
    finally:
        engine.dispose()

def test_cap_reservation_updated_at_ddl_matches_orm_and_both_sql_entrypoints():
    """完整建库基线与增量迁移必须和 ORM 的更新时间语义一致。"""
    from pathlib import Path
    import re

    model_column = CapReservation.__table__.c.updated_at
    assert model_column.server_default is not None
    assert str(model_column.server_default.arg).upper() == "CURRENT_TIMESTAMP"
    assert model_column.onupdate is not None

    root = Path(__file__).resolve().parents[1]
    ddl_files = (
        root / "sql" / "platform.sql",
        root / "sql" / "migrations" / "20261111_cap_reservation_ledger.sql",
    )
    for ddl_file in ddl_files:
        sql = ddl_file.read_text(encoding="utf-8")
        match = re.search(
            r"CREATE TABLE IF NOT EXISTS cap_reservations\s*\((.*?)\)\s*ENGINE=InnoDB",
            sql,
            flags=re.IGNORECASE | re.DOTALL,
        )
        assert match is not None, f"cap_reservations DDL missing in {ddl_file}"
        table_ddl = match.group(1)
        assert re.search(
            r"updated_at\s+DATETIME\s+NOT NULL\s+DEFAULT\s+CURRENT_TIMESTAMP\s+COMMENT",
            table_ddl,
            flags=re.IGNORECASE,
        )
        assert not re.search(r"ON\s+UPDATE\s+CURRENT_TIMESTAMP", table_ddl, flags=re.IGNORECASE)

