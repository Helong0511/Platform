"""桥页上传原子替换测试：并发读取方不能看到半写入文件。"""
import os
import stat

import pytest

from app.core import cloak_scripts_paths


def test_atomic_write_bridge_html_replaces_complete_file_and_preserves_mode(tmp_path):
    target = tmp_path / "master.html"
    target.write_text("<html>old complete content</html>", encoding="utf-8")
    target.chmod(0o640)

    cloak_scripts_paths.atomic_write_bridge_html(
        str(target),
        "<html>new complete content with 中文</html>",
    )

    assert target.read_text(encoding="utf-8") == "<html>new complete content with 中文</html>"
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    assert sorted(path.name for path in tmp_path.iterdir()) == ["master.html"]


def test_atomic_write_bridge_html_keeps_old_file_when_replace_fails(tmp_path, monkeypatch):
    target = tmp_path / "master.html"
    old_content = "<html>old content remains</html>"
    target.write_text(old_content, encoding="utf-8")

    def fail_replace(source, destination):
        raise OSError("simulated atomic replace failure")

    monkeypatch.setattr(cloak_scripts_paths.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated atomic replace failure"):
        cloak_scripts_paths.atomic_write_bridge_html(
            str(target),
            "<html>new content must not partially appear</html>",
        )

    assert target.read_text(encoding="utf-8") == old_content
    assert sorted(path.name for path in tmp_path.iterdir()) == ["master.html"]
