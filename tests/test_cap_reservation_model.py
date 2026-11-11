"""Cap Reservation 账本 ORM 必须进入统一 metadata，供迁移与建表工具发现。"""
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

    assert "uq_cap_reservation_key" in unique_constraints
    assert {
        "idx_cap_reservation_state_updated",
        "idx_cap_reservation_lease",
        "idx_cap_reservation_event",
        "idx_cap_reservation_scope",
    }.issubset(index_names)


def test_cap_reservation_preserves_global_publisher_scope_and_total_date_semantics():
    table = CapReservation.__table__

    assert table.c.publisher_id.nullable is True
    assert table.c.business_date.nullable is True
    assert table.c.redis_reserved.nullable is False
    assert table.c.reservation_key.type.length == 64
    assert table.c.redis_token_key.type.length == 512
