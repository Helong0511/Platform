"""Postback pipeline 步骤测试。"""
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("UNIT_TEST", "1")
os.environ.setdefault("PRODUCTION_ENV", "development")

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.core.postback.pipeline import (
    PostbackPipelineContext,
    attribution_ids_from_association,
    step_check_duplicate,
)


def test_attribution_ids_from_token_association():
    assoc = {"offer_id": 1, "publisher_id": 2, "advertiser_id": 3}
    assert attribution_ids_from_association(assoc) == (1, 2, 3)


@pytest.mark.asyncio
async def test_step_check_duplicate_short_circuit():
    ctx = PostbackPipelineContext(
        platform="test",
        raw_data={},
        db=AsyncMock(),
        normalized_data={"conversion_id": "c1", "click_id": "k1"},
    )
    with patch(
        "app.core.postback.pipeline.DuplicateChecker.is_duplicate",
        new_callable=AsyncMock,
        return_value=True,
    ):
        assert await step_check_duplicate(ctx) is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
