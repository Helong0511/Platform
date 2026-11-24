"""客户归属必须来自点击时快照，不能回退到当前 Publisher 配置。"""
import pytest

from app.core.postback.savers.conversion_saver import ConversionSaver


class _NoQuerySession:
    async def execute(self, statement):
        raise AssertionError("no product lookup expected without a product_id")


@pytest.mark.asyncio
async def test_missing_click_client_snapshot_does_not_fall_back_to_current_publisher():
    class _Publisher:
        client_id = 99

    trusted_client_id, trusted_product_id = (
        await ConversionSaver.resolve_trusted_attribution(
            normalized_data={"client_id": 99},
            click_association={
                "client_id": None,
                "publisher": _Publisher(),
                "product_id": None,
            },
            db=_NoQuerySession(),
        )
    )

    assert trusted_client_id is None
    assert trusted_product_id is None


@pytest.mark.asyncio
async def test_click_client_snapshot_wins_over_changed_publisher():
    class _Publisher:
        client_id = 99

    trusted_client_id, trusted_product_id = (
        await ConversionSaver.resolve_trusted_attribution(
            normalized_data={"client_id": 99},
            click_association={
                "client_id": 55,
                "publisher": _Publisher(),
                "product_id": None,
            },
            db=_NoQuerySession(),
        )
    )

    assert trusted_client_id == 55
    assert trusted_product_id is None
