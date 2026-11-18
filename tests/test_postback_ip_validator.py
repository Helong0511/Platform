"""Postback 来源 IP 白名单 fail-closed 回归测试。"""
from types import SimpleNamespace

import pytest

from app.core.postback.validators.ip_validator import IpValidator


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeDB:
    def __init__(self, addresses):
        self.addresses = addresses
        self.execute_calls = 0

    async def execute(self, statement):
        self.execute_calls += 1
        return FakeResult([
            SimpleNamespace(ip_address=address, id=index + 1)
            for index, address in enumerate(self.addresses)
        ])


@pytest.mark.asyncio
@pytest.mark.parametrize("request_ip", [None, "", "   ", "unknown", "UNKNOWN"])
async def test_missing_or_unknown_source_ip_is_rejected_without_whitelist_query(request_ip):
    db = FakeDB(["8.8.8.8"])

    valid, cleaned_ip = await IpValidator.validate(request_ip, db)

    assert valid is False
    assert cleaned_ip is None
    assert db.execute_calls == 0


@pytest.mark.asyncio
async def test_exact_whitelisted_source_ip_is_accepted():
    db = FakeDB(["8.8.8.8"])

    valid, cleaned_ip = await IpValidator.validate("8.8.8.8", db)

    assert valid is True
    assert cleaned_ip == "8.8.8.8"
    assert db.execute_calls == 1


@pytest.mark.asyncio
async def test_non_whitelisted_source_ip_is_rejected():
    db = FakeDB(["8.8.8.8"])

    valid, cleaned_ip = await IpValidator.validate("1.1.1.1", db)

    assert valid is False
    assert cleaned_ip == "1.1.1.1"


@pytest.mark.asyncio
async def test_empty_whitelist_rejects_all_source_ips():
    db = FakeDB([])

    valid, cleaned_ip = await IpValidator.validate("8.8.8.8", db)

    assert valid is False
    assert cleaned_ip == "8.8.8.8"
