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
