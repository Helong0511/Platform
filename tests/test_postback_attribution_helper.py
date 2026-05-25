"""归因收集：快照列齐全时不查 clicks。"""
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("UNIT_TEST", "1")
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def test_needs_click_lookup_false_when_snapshot_complete():
    from app.services.cpl.postback_attribution_helper import _needs_click_lookup

    conv = SimpleNamespace(
        click_id="abc",
        offer_id=1,
        publisher_id=2,
        advertiser_id=3,
        click_time="2026-01-01",
    )
    assert _needs_click_lookup(conv) is False


def test_needs_click_lookup_true_when_missing_offer():
    from app.services.cpl.postback_attribution_helper import _needs_click_lookup

    conv = SimpleNamespace(
        click_id="abc",
        offer_id=None,
        publisher_id=2,
        advertiser_id=3,
        click_time="2026-01-01",
    )
    assert _needs_click_lookup(conv) is True


@pytest.mark.asyncio
async def test_collect_skips_db_when_all_snapshots():
    from app.services.cpl.postback_attribution_helper import collect_attribution_ids

    conv = SimpleNamespace(
        click_id="tok1",
        offer_id=10,
        publisher_id=20,
        advertiser_id=30,
        click_time="2026-01-01",
        gid=None,
    )
    db = AsyncMock()
    offer_ids, pub_ids, adv_ids, gid_ids, clicks_map = await collect_attribution_ids(
        db, [conv]
    )
    assert offer_ids == {10}
    assert pub_ids == {20}
    assert adv_ids == {30}
    assert clicks_map == {}
    db.execute.assert_not_called()
