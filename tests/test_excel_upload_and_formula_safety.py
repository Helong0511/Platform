"""Excel 上传内存上限与导出公式注入回归测试。"""
from io import BytesIO

import pytest
from fastapi import HTTPException
from openpyxl import load_workbook

from app.api_v1.excel.ad_data_import.excel_reader import validate_and_read_excel
from app.api_v1.excel.utils import validate_excel_file
from app.core import excel_io
from app.core.config import settings


class _OversizedUpload:
    content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    filename = "payload.xlsx"

    def __init__(self):
        self.requested_size = None

    async def read(self, size=-1):
        self.requested_size = size
        return b"x" * size


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "validator",
    [validate_and_read_excel, validate_excel_file],
)
async def test_excel_upload_reads_only_limit_plus_one_byte(monkeypatch, validator):
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE", 10)
    upload = _OversizedUpload()

    with pytest.raises(HTTPException) as caught:
        await validator(upload)

    assert caught.value.status_code == 400
    assert upload.requested_size == 11


def test_excel_export_stores_user_controlled_formula_text_as_string():
    formula_text = "=HYPERLINK(\"https://attacker.invalid\",\"open\")"
    output = excel_io.build_excel_bytes(
        [{"产品名称": formula_text, "备注": "=1+1"}],
        "导出数据",
    )

    workbook = load_workbook(BytesIO(output.getvalue()), data_only=False)
    worksheet = workbook["导出数据"]

    assert worksheet["A2"].value == formula_text
    assert worksheet["A2"].data_type == "s"
    assert worksheet["B2"].value == "=1+1"
    assert worksheet["B2"].data_type == "s"
