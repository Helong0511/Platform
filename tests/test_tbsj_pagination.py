"""TBSJ 分页终止条件测试。"""
from app.scheduler_module.upstream_fetch import _should_break_tbsj_pagination


def test_break_when_items_is_dict_not_list():
    """items 为字典时不累积，且应立即终止分页（避免死循环）。"""
    assert _should_break_tbsj_pagination({"k": "v"}, total=100, collected=0) is True


def test_break_when_items_empty_list():
    assert _should_break_tbsj_pagination([], total=100, collected=0) is True


def test_break_when_collected_reaches_total():
    assert _should_break_tbsj_pagination([{"id": 1}], total=10, collected=10) is True


def test_continue_when_more_pages_expected():
    assert _should_break_tbsj_pagination([{"id": 1}], total=100, collected=50) is False


def test_continue_when_total_unknown_but_page_has_rows():
    """后续页缺少 total 时沿用先前 total；未凑齐则继续。"""
    assert _should_break_tbsj_pagination([{"id": 1}], total=200, collected=100) is False
