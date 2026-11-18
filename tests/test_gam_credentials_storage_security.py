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
