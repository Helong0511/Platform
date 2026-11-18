"""生产环境 RSA JWT 密钥加载必须 fail-closed。"""
from pathlib import Path

import pytest

from app.core import security


def _set_security_root(monkeypatch, root: Path):
    module_file = root / "app" / "core" / "security.py"
    module_file.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(security, "__file__", str(module_file))


def test_production_rsa_paths_must_be_absolute_and_outside_repository(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    external = tmp_path / "runtime-keys"
    _set_security_root(monkeypatch, repo)
    monkeypatch.setattr(security.settings, "PRODUCTION_ENV", "production")

    with pytest.raises(RuntimeError, match="绝对路径"):
        security._resolve_rsa_key_path("keys/private_key.pem", "private")

    with pytest.raises(RuntimeError, match="代码仓库目录内"):
        security._resolve_rsa_key_path(
            str(repo / "keys" / "private_key.pem"), "private"
        )

    assert security._resolve_rsa_key_path(
        str(external / "private_key.pem"), "private"
    ) == str((external / "private_key.pem").resolve())


def test_production_missing_rsa_key_never_uses_ephemeral_pair(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _set_security_root(monkeypatch, repo)
    monkeypatch.setattr(security.settings, "PRODUCTION_ENV", "production")
    monkeypatch.setattr(
        security,
        "_generate_ephemeral_rsa_pair",
        lambda: pytest.fail("production must never generate ephemeral RSA keys"),
    )

    with pytest.raises(RuntimeError, match="拒绝使用仓库回退或临时密钥"):
        security.JWTUtils._load_rsa_key("", "", "private")


def test_production_private_rsa_file_requires_owner_only_permissions(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _set_security_root(monkeypatch, repo)
    monkeypatch.setattr(security.settings, "PRODUCTION_ENV", "production")

    key_dir = tmp_path / "runtime-keys"
    key_dir.mkdir(mode=0o700)
    key_file = key_dir / "private_key.pem"
    key_file.write_text("synthetic-private-key", encoding="utf-8")
    key_file.chmod(0o644)

    with pytest.raises(PermissionError, match="权限过宽"):
        security.JWTUtils._load_rsa_key("", str(key_file), "private")

    key_file.chmod(0o600)
    assert security.JWTUtils._load_rsa_key("", str(key_file), "private") == (
        "synthetic-private-key"
    )


def test_development_keeps_local_keys_directory_fallback(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    key_dir = repo / "keys"
    key_dir.mkdir(parents=True)
    local_key = key_dir / "private_key.pem"
    local_key.write_text("synthetic-development-key", encoding="utf-8")
    _set_security_root(monkeypatch, repo)
    monkeypatch.setattr(security.settings, "PRODUCTION_ENV", "development")

    assert security._resolve_rsa_key_path(
        "/missing/deployment/path/private_key.pem", "private"
    ) == str(local_key)


def test_development_keeps_ephemeral_rsa_fallback(monkeypatch):
    monkeypatch.setattr(security.settings, "PRODUCTION_ENV", "development")
    monkeypatch.setattr(
        security,
        "_generate_ephemeral_rsa_pair",
        lambda: ("synthetic-private", "synthetic-public"),
    )

    assert security.JWTUtils._load_rsa_key("", "", "private") == "synthetic-private"
    assert security.JWTUtils._load_rsa_key("", "", "public") == "synthetic-public"


def _write_rsa_pair(directory: Path, name: str):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    directory.mkdir(parents=True, exist_ok=True)
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_path = directory / f"{name}-private.pem"
    public_path = directory / f"{name}-public.pem"
    private_path.write_bytes(
        private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        private.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    private_path.chmod(0o600)
    public_path.chmod(0o644)
    return private_path, public_path


def _configure_production_rsa_paths(monkeypatch, private_path: Path, public_path: Path):
    monkeypatch.setattr(security.settings, "PRODUCTION_ENV", "production")
    monkeypatch.setattr(security.settings, "JWT_ALGORITHM", "RS256")
    monkeypatch.setattr(security.settings, "RSA_PRIVATE_KEY", "")
    monkeypatch.setattr(security.settings, "RSA_PUBLIC_KEY", "")
    monkeypatch.setattr(security.settings, "RSA_PRIVATE_KEY_PATH", str(private_path))
    monkeypatch.setattr(security.settings, "RSA_PUBLIC_KEY_PATH", str(public_path))


def test_production_startup_validates_matching_rsa_keypair(monkeypatch, tmp_path):
    private_path, public_path = _write_rsa_pair(tmp_path / "external", "jwt")
    _configure_production_rsa_paths(monkeypatch, private_path, public_path)

    security.validate_production_jwt_keypair()


def test_production_startup_rejects_mismatched_rsa_keypair(monkeypatch, tmp_path):
    private_path, _ = _write_rsa_pair(tmp_path / "private", "jwt")
    _, other_public_path = _write_rsa_pair(tmp_path / "public", "other")
    _configure_production_rsa_paths(monkeypatch, private_path, other_public_path)

    with pytest.raises(RuntimeError, match="公私钥无效或不匹配"):
        security.validate_production_jwt_keypair()


def test_production_startup_rejects_non_rs256_algorithm(monkeypatch):
    monkeypatch.setattr(security.settings, "PRODUCTION_ENV", "production")
    monkeypatch.setattr(security.settings, "JWT_ALGORITHM", "HS256")

    with pytest.raises(RuntimeError, match="必须为 RS256"):
        security.validate_production_jwt_keypair()
