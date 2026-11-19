"""批量通知补发参数校验必须先于数据库查询和下游 HTTP 请求。"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.models import UserRole
from app.services.notification.commands.resend_command import ResendNotificationCommand


class _DB:
    def __init__(self):
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        raise AssertionError("invalid batch input must be rejected before database access")


def _admin():
    return SimpleNamespace(id=1, role=UserRole.ADMIN)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "conversion_ids",
    [
        [505, 505],
        [0],
        [-1],
        [True],
        ["505"],
        [505, 506.0],
        tuple([505, 506]),
        list(range(1, 52)),
    ],
)
async def test_batch_resend_rejects_invalid_or_duplicate_ids_before_database(
    conversion_ids,
):
    db = _DB()

    with pytest.raises(HTTPException):
        await ResendNotificationCommand(db).batch_resend_conversions(
            conversion_ids,
            _admin(),
        )

    assert db.statements == []
