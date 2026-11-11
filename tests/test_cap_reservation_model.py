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
