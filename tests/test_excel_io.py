"""Excel 导出工具单元测试"""
from app.core.excel_io import build_excel_bytes, excel_streaming_response


def test_build_excel_bytes_creates_xlsx():
    output = build_excel_bytes(
        [{"列A": "值1", "列B": 2}, {"列A": "值2", "列B": 3}],
        "测试表",
    )
    content = output.getvalue()
    assert content[:2] == b"PK"
    assert len(content) > 100


def test_excel_streaming_response_headers():
    resp = excel_streaming_response(
        [{"名称": "测试"}],
        "Sheet1",
        "导出前缀",
    )
    assert resp.media_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "attachment" in resp.headers.get("Content-Disposition", "")
    assert "UTF-8" in resp.headers.get("Content-Disposition", "")


def test_build_excel_bytes_unlimited_column_width():
    long_text = "x" * 80
    output = build_excel_bytes(
        [{"宽列": long_text}],
        "宽表",
        max_col_width=None,
    )
    assert len(output.getvalue()) > 100
