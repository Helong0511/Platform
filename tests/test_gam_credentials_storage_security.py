"""GAM 服务账号私钥文件权限回归测试。"""
import os
import stat

import pytest

from app.scheduler_module import gam_credentials_storage as storage


@pytest.mark.skipif(os.name == "nt", reason="POSIX 文件权限位仅在 Linux/macOS 上验证")
def test_gam_credentials_directory_and_file_are_owner_only(tmp_path):
    target = tmp_path / "private-gam" / "gam-123.json"

    storage._write_credentials_file(target, '{"private_key":"synthetic"}')

    assert target.read_text(encoding="utf-8") == '{"private_key":"synthetic"}'
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert list(target.parent.glob("*.uploading")) == []
    assert list(target.parent.glob(".*.uploading")) == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX 文件权限位仅在 Linux/macOS 上验证")
def test_replacing_existing_world_readable_key_tightens_permissions(tmp_path):
    target = tmp_path / "secrets" / "gam-456.json"
    target.parent.mkdir()
    target.write_text('{"private_key":"old-synthetic"}', encoding="utf-8")
    target.chmod(0o644)

    storage._write_credentials_file(target, '{"private_key":"new-synthetic"}')

    assert target.read_text(encoding="utf-8") == '{"private_key":"new-synthetic"}'
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700


@pytest.mark.skipif(os.name == "nt", reason="POSIX 符号链接权限语义仅在 Linux/macOS 上验证")
def test_gam_credentials_writer_refuses_symlink_target(tmp_path):
    target = tmp_path / "secrets" / "gam-789.json"
    external = tmp_path / "outside.json"
    target.parent.mkdir()
    external.write_text('{"private_key":"outside-synthetic"}', encoding="utf-8")
    target.symlink_to(external)

    with pytest.raises(PermissionError, match="符号链接"):
        storage._write_credentials_file(target, '{"private_key":"replacement"}')

    assert target.is_symlink()
    assert external.read_text(encoding="utf-8") == '{"private_key":"outside-synthetic"}'


def test_production_requires_explicit_external_absolute_gam_directory(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(storage, "ROOT", repo)
    monkeypatch.setattr(storage, "DEFAULT_GAM_SECRETS_DIR", repo / "secrets")
    monkeypatch.setenv("PRODUCTION_ENV", "production")
    monkeypatch.delenv("GAM_SECRETS_DIR", raising=False)

    with pytest.raises(RuntimeError, match="必须显式配置"):
        storage.get_gam_secrets_dir()

    monkeypatch.setenv("GAM_SECRETS_DIR", "secrets")
    with pytest.raises(ValueError, match="绝对路径"):
        storage.get_gam_secrets_dir()

    monkeypatch.setenv("GAM_SECRETS_DIR", str(repo / "secrets"))
    with pytest.raises(ValueError, match="仓库目录内"):
        storage.get_gam_secrets_dir()

    external = tmp_path / "runtime-secrets"
    monkeypatch.setenv("GAM_SECRETS_DIR", str(external))
    assert storage.get_gam_secrets_dir() == external.resolve()


def test_development_keeps_local_gam_directory_compatibility(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(storage, "ROOT", repo)
    monkeypatch.setattr(storage, "DEFAULT_GAM_SECRETS_DIR", repo / "secrets")
    monkeypatch.setenv("PRODUCTION_ENV", "development")
    monkeypatch.delenv("GAM_SECRETS_DIR", raising=False)

    assert storage.get_gam_secrets_dir() == repo / "secrets"
    monkeypatch.setenv("GAM_SECRETS_DIR", "local-gam-secrets")
    assert storage.get_gam_secrets_dir() == repo / "local-gam-secrets"


def test_production_legacy_secrets_paths_resolve_to_external_directory(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    external = tmp_path / "secure-runtime" / "gam"
    monkeypatch.setattr(storage, "ROOT", repo)
    monkeypatch.setenv("PRODUCTION_ENV", "production")
    monkeypatch.setenv("GAM_SECRETS_DIR", str(external))

    assert storage.resolve_gam_credentials_path(
        "secrets/gam-123.json"
    ) == external.resolve() / "gam-123.json"
    assert storage.resolve_gam_credentials_path(
        str(external / "gam-456.json")
    ) == external.resolve() / "gam-456.json"

    with pytest.raises(ValueError, match="必须位于配置的 GAM_SECRETS_DIR"):
        storage.resolve_gam_credentials_path(
            str(repo / "secrets" / "gam-789.json")
        )

    with pytest.raises(ValueError, match="必须位于配置的 GAM_SECRETS_DIR"):
        storage.resolve_gam_credentials_path(
            str(tmp_path / "other-secure-dir" / "gam-999.json")
        )


def test_development_legacy_secrets_paths_keep_repository_default(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(storage, "ROOT", repo)
    monkeypatch.setattr(storage, "DEFAULT_GAM_SECRETS_DIR", repo / "secrets")
    monkeypatch.setenv("PRODUCTION_ENV", "development")
    monkeypatch.delenv("GAM_SECRETS_DIR", raising=False)

    assert storage.resolve_gam_credentials_path(
        "secrets/gam-123.json"
    ) == repo / "secrets" / "gam-123.json"


def test_production_absolute_credentials_still_require_gam_secrets_dir(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    external = tmp_path / "external"
    monkeypatch.setattr(storage, "ROOT", repo)
    monkeypatch.setenv("PRODUCTION_ENV", "production")
    monkeypatch.delenv("GAM_SECRETS_DIR", raising=False)

    with pytest.raises(RuntimeError, match="必须显式配置"):
        storage.resolve_gam_credentials_path(str(external / "gam-123.json"))
