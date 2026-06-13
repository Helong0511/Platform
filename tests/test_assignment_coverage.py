"""产品分配覆盖与 Telegram 告警文案测试。"""
from app.core.product_assignment import format_assignment_gap_telegram_message


def test_format_assignment_gap_telegram_message():
    gaps = [
        {
            "product_name": "https://game2.ibobin.com/",
            "data_date": "2026-06-13",
            "row_count": 59,
        }
    ]
    msg = format_assignment_gap_telegram_message(
        notify_title="yangyangdeyi",
        gaps=gaps,
        total_orphan=59,
    )
    assert "产品分配覆盖异常" in msg
    assert "game2.ibobin.com" in msg
    assert "59 条" in msg
    assert "自动补全" not in msg


def test_format_assignment_gap_truncates_list():
    gaps = [{"product_name": "p1", "data_date": "2026-06-13", "row_count": 10}]
    msg = format_assignment_gap_telegram_message(
        notify_title="test",
        gaps=gaps,
        total_orphan=100,
    )
    assert "其余 90 条未列出" in msg
