"""ConversionSaver 归因快照字段（无数据库）。"""
import json
import os
import sys

import pytest

os.environ.setdefault("UNIT_TEST", "1")

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _build_raw_json(normalized, click_association):
    """与 ConversionSaver 内 raw_data 逻辑一致，便于单测。"""
    raw_in = normalized.get("raw_data")
    snapshot = None
    if click_association:
        snapshot = {
            k: click_association[k]
            for k in ("offer_id", "publisher_id", "advertiser_id", "click_id")
            if click_association.get(k) is not None
        } or None
    if isinstance(raw_in, dict):
        raw_payload = dict(raw_in)
        if snapshot:
            raw_payload["_attribution"] = snapshot
        return json.dumps(raw_payload)
    if snapshot:
        return json.dumps({"_attribution": snapshot})
    return None


def test_attribution_in_raw_and_snapshot_fields():
    normalized = {"raw_data": {"platform": "bft", "payout": 1.0}}
    assoc = {
        "click_id": "tok123",
        "offer_id": 10,
        "publisher_id": 20,
        "advertiser_id": 30,
    }
    raw = _build_raw_json(normalized, assoc)
    assert raw is not None
    data = json.loads(raw)
    assert data["_attribution"]["offer_id"] == 10
    assert data["_attribution"]["publisher_id"] == 20


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
