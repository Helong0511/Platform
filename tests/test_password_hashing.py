"""密码哈希迁移与历史 bcrypt 兼容回归测试。"""
from pathlib import Path
import re

import bcrypt
import pytest

from app.core.passwords import (
    hash_password,
    password_hash_needs_upgrade,
    verify_password,
)
from app.models.user import User
from app.services.password_service import upgrade_password_hash_after_login


def _legacy_hash(password: str) -> str:
    # 复现旧模型：UTF-8 编码后截断 72 字节，再忽略不完整尾部字符。
    normalized = password.encode("utf-8")[:72].decode("utf-8", errors="ignore").encode("utf-8")
    return bcrypt.hashpw(normalized, bcrypt.gensalt(rounds=4)).decode("ascii")


def test_new_passwords_use_argon2id_and_fit_database_column():
    encoded = hash_password("CorrectHorseBatteryStaple123!")
    assert encoded.startswith("$argon2id$")
    assert len(encoded) <= User.__table__.c.hashed_password.type.length
    assert verify_password("CorrectHorseBatteryStaple123!", encoded)
    assert not verify_password("CorrectHorseBatteryStaple123?", encoded)
    assert not password_hash_needs_upgrade("CorrectHorseBatteryStaple123!", encoded)


def test_argon2id_does_not_apply_legacy_bcrypt_72_byte_truncation():
    password = "A1" + "中" * 70
    encoded = hash_password(password)
    assert verify_password(password, encoded)
    assert not verify_password(password + "尾", encoded)


def test_legacy_bcrypt_hash_remains_verifiable_and_is_upgradeable():
    password = "LegacyPassword123!"
    encoded = _legacy_hash(password)
    assert verify_password(password, encoded)
    assert not verify_password("WrongPassword123!", encoded)
    assert password_hash_needs_upgrade(password, encoded)


def test_legacy_bcrypt_unicode_boundary_does_not_expand_old_verification_semantics():
    # 第 72 字节落在中文字符中间；旧写入与旧验证截断结果不同，原密码本来就无法通过旧验证。
    password = "A" * 71 + "中" + "suffix123"
    encoded = _legacy_hash(password)
    assert not verify_password(password, encoded)
    assert not verify_password("A" * 71 + "other-suffix", encoded)
    assert not password_hash_needs_upgrade(password, encoded)


def test_legacy_bcrypt_long_password_with_complete_utf8_boundary_remains_compatible():
    password = "A" * 72 + "suffix123"
    encoded = _legacy_hash(password)
    assert verify_password(password, encoded)
    assert verify_password("A" * 72 + "different-suffix", encoded)
    assert not password_hash_needs_upgrade(password, encoded)


def test_corrupt_or_unknown_hash_fails_closed():
    assert not verify_password("any-password", "not-a-password-hash")
    assert not verify_password("any-password", "$argon2id$broken")
    assert not verify_password("any-password", "$2b$broken")


def test_user_password_column_matches_authoritative_sql_baseline():
    assert User.__table__.c.hashed_password.type.length == 191

    root = Path(__file__).resolve().parents[1]
    source = (root / "sql" / "platform.sql").read_text(encoding="utf-8")
    users_start = source.index("CREATE TABLE IF NOT EXISTS `users`")
    users_end = source.index(") ENGINE=", users_start)
    users_sql = source[users_start:users_end]
    match = re.search(r"`hashed_password`\s+VARCHAR\((\d+)\)", users_sql, re.IGNORECASE)
    assert match is not None
    assert int(match.group(1)) == User.__table__.c.hashed_password.type.length


class _UpdateResult:
    rowcount = 1


class _ConflictResult:
    rowcount = 0


class _DB:
    def __init__(self, result=None):
        self.statement = None
        self.result = result or _UpdateResult()

    async def execute(self, statement):
        self.statement = statement
        return self.result


@pytest.mark.asyncio
async def test_successful_login_upgrade_uses_compare_and_swap_without_mutating_identity():
    legacy_hash = _legacy_hash("LegacyPassword123!")
    user = User(id=42, username="legacy-user", hashed_password=legacy_hash)
    db = _DB()

    upgraded = await upgrade_password_hash_after_login(
        db,
        user,
        "LegacyPassword123!",
    )

    assert upgraded is True
    assert user.hashed_password == legacy_hash
    assert "users" in str(db.statement).lower()
    assert "hashed_password" in str(db.statement).lower()
    from sqlalchemy.dialects import mysql
    compiled = db.statement.compile(dialect=mysql.dialect())
    assert "CAST(users.hashed_password AS BINARY)" in str(compiled)
    assert legacy_hash.encode("utf-8") in compiled.params.values()


@pytest.mark.asyncio
async def test_successful_login_does_not_upgrade_long_legacy_bcrypt_password():
    password = "A" * 71 + "中" + "suffix123"
    user = User(id=43, username="long-legacy-user", hashed_password=_legacy_hash(password))
    db = _DB()

    upgraded = await upgrade_password_hash_after_login(db, user, password)

    assert upgraded is False
    assert db.statement is None


@pytest.mark.asyncio
async def test_compare_and_swap_does_not_overwrite_a_concurrently_changed_password():
    legacy_hash = _legacy_hash("LegacyPassword123!")
    user = User(id=44, username="concurrent-user", hashed_password=legacy_hash)
    db = _DB(_ConflictResult())

    upgraded = await upgrade_password_hash_after_login(
        db,
        user,
        "LegacyPassword123!",
    )

    assert upgraded is False
    assert user.hashed_password == legacy_hash
    assert db.statement is not None
