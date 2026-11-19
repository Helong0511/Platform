"""密码哈希与历史 bcrypt 兼容层。

新密码使用 Argon2id；历史 bcrypt 哈希仅用于验证，并在安全条件满足时渐进升级。
所有哈希参数显式固定，避免依赖库默认值变化造成不可预期的资源消耗。
"""
from __future__ import annotations

import bcrypt
from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)

# OWASP 推荐的 Argon2id 最低配置：19 MiB、2 次迭代、1 个并行通道。
# 该配置兼顾服务端并发登录时的内存占用；后续应结合生产硬件压测再提高成本。
PASSWORD_HASHER = PasswordHasher(
    time_cost=2,
    memory_cost=19_456,
    parallelism=1,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    """生成新密码的 Argon2id 哈希，不截断 UTF-8 密码。"""
    if not isinstance(password, str):
        raise TypeError("password must be str")
    return PASSWORD_HASHER.hash(password)


def _legacy_bcrypt_password(password: str) -> bytes:
    """复现历史模型写入 bcrypt 前的 72 字节 UTF-8 截断规则。

    历史代码先截取 72 字节，再忽略被截断的 UTF-8 尾部残字节。
    这里必须保持相同规范化方式，才能验证所有历史哈希。
    """
    return password.encode("utf-8")[:72].decode("utf-8", errors="ignore").encode("utf-8")


def verify_password(password: str, encoded_hash: str) -> bool:
    """验证 Argon2id 新哈希或历史 bcrypt 哈希；未知/损坏格式一律拒绝。"""
    if not isinstance(password, str) or not isinstance(encoded_hash, str):
        return False

    try:
        if encoded_hash.startswith("$argon2id$"):
            return bool(PASSWORD_HASHER.verify(encoded_hash, password))

        if encoded_hash.startswith(("$2a$", "$2b$", "$2y$")):
            return bcrypt.checkpw(
                _legacy_bcrypt_password(password),
                encoded_hash.encode("ascii"),
            )
    except (
        UnicodeEncodeError,
        UnicodeDecodeError,
        ValueError,
        TypeError,
        VerifyMismatchError,
        VerificationError,
        InvalidHashError,
    ):
        return False

    return False


def password_hash_needs_upgrade(password: str, encoded_hash: str) -> bool:
    """判断已验证密码是否可以安全升级为当前 Argon2id 参数。

    历史 bcrypt 的语义是最多比较前 72 字节。若输入超过 72 字节，
    自动迁移会把原本可登录的一组密码收窄为单一完整字符串，因此暂不自动升级；
    用户主动修改密码时会使用完整密码生成新的 Argon2id 哈希。
    """
    if not isinstance(password, str) or not isinstance(encoded_hash, str):
        return False

    if encoded_hash.startswith("$argon2id$"):
        try:
            return PASSWORD_HASHER.check_needs_rehash(encoded_hash)
        except (ValueError, TypeError, InvalidHashError):
            return False

    if encoded_hash.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return len(password.encode("utf-8")) <= 72
        except UnicodeEncodeError:
            return False

    return False
