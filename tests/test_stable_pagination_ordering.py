"""OFFSET 列表的唯一排序键回归测试。"""
import pytest

from app.models.models import UserRole
from app.services.click_service import ClickService
from app.services.short_link_service import ShortLinkService
from app.services.cpl.postback_forward_log_service import PostbackForwardLogService


class _Result:
    def scalar(self):
        return 0

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return []


class _RecordingDB:
    def __init__(self):
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result()


def _admin():
    return type("Admin", (), {"id": 1, "role": UserRole.ADMIN})()


def _assert_unique_id_tiebreaker(statement, primary_key):
    sql = str(statement)
    primary_position = sql.index(primary_key)
    id_position = sql.rindex("id DESC")
    assert primary_position < id_position


@pytest.mark.asyncio
async def test_click_list_uses_click_time_then_unique_id():
    db = _RecordingDB()
    await ClickService(db).get_clicks(page=1, page_size=10)

    list_queries = [statement for statement in db.statements if "ORDER BY" in str(statement) and "click_time" in str(statement)]
    assert len(list_queries) == 1
    _assert_unique_id_tiebreaker(list_queries[0], "click_time DESC")


@pytest.mark.asyncio
async def test_short_link_list_uses_created_at_then_unique_id():
    db = _RecordingDB()
    await ShortLinkService(db).get_short_links(
        current_user=_admin(),
        page=1,
        page_size=10,
    )

    list_queries = [statement for statement in db.statements if "ORDER BY" in str(statement) and "short_links" in str(statement)]
    assert len(list_queries) == 1
    _assert_unique_id_tiebreaker(list_queries[0], "created_at DESC")


@pytest.mark.asyncio
async def test_postback_forward_logs_use_created_at_then_unique_id():
    db = _RecordingDB()
    await PostbackForwardLogService().list_forward_logs(
        conversion_id=None,
        product_id=None,
        publisher_id=None,
        success=None,
        start_date=None,
        end_date=None,
        page=1,
        page_size=10,
        db=db,
        current_user=_admin(),
    )

    list_queries = [statement for statement in db.statements if "ORDER BY" in str(statement) and "postback_forward_logs" in str(statement)]
    assert len(list_queries) == 1
    _assert_unique_id_tiebreaker(list_queries[0], "created_at DESC")
