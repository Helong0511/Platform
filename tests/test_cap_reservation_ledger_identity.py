"""Cap Reservation stable identity regression tests."""
from datetime import date

import pytest

from app.services.cap_reservation_ledger import build_reservation_identity


def _identity(**overrides):
    values = {
        "platform": "bft",
        "conversion_id": "conv-001",
        "event_name": "purchase",
        "offer_id": 88,
        "publisher_id": None,
        "cap_kind": "daily",
        "business_date": date(2026, 11, 11),
    }
    values.update(overrides)
    return build_reservation_identity(**values)


def test_same_postback_and_scope_produce_same_stable_reservation_key():
    first = _identity(event_name=" purchase ")
    second = _identity(event_name="purchase")

    assert first["reservation_key"] == second["reservation_key"]
    assert len(first["reservation_key"]) == 64


def test_global_publisher_scope_is_distinct_from_publisher_id():
    global_scope = _identity(publisher_id=None)
    publisher_scope = _identity(publisher_id=12)

    assert global_scope["reservation_key"] != publisher_scope["reservation_key"]
    assert global_scope["publisher_scope"] == "global"
    assert publisher_scope["publisher_scope"] == "publisher:12"


def test_daily_date_and_cap_kind_are_part_of_stable_key():
    next_day = _identity(business_date=date(2026, 11, 12))
    total = _identity(cap_kind="total", business_date=None)

    assert _identity()["reservation_key"] != next_day["reservation_key"]
    assert _identity()["reservation_key"] != total["reservation_key"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"cap_kind": "unknown"},
        {"cap_kind": "daily", "business_date": None},
        {"cap_kind": "total", "business_date": date(2026, 11, 11)},
        {"conversion_id": " "},
        {"offer_id": 0},
    ],
)
def test_invalid_reservation_identity_is_rejected(overrides):
    with pytest.raises(ValueError):
        _identity(**overrides)
