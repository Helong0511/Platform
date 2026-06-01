"""短链接路径参数校验单元测试"""
import pytest
from fastapi import HTTPException

from app.routes.short_link.short_code_validate import validate_route_short_code


def test_validate_route_short_code_ok():
    assert validate_route_short_code("abc123") == "abc123"
    assert validate_route_short_code("  xyz  ") == "xyz"


@pytest.mark.parametrize("bad", ["", "null", "NULL", "undefined", "none", "  "])
def test_validate_route_short_code_rejects_invalid(bad):
    with pytest.raises(HTTPException) as exc:
        validate_route_short_code(bad)
    assert exc.value.status_code == 404
