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


def test_template_cache_detects_atomic_replace_even_with_same_mtime(tmp_path):
    target = tmp_path / "master.html"
    target.write_text("<html>old cached template</html>", encoding="utf-8")
    cloak_scripts_paths.invalidate_bridge_template_cache()
    assert cloak_scripts_paths.read_bridge_html_template_cached(str(target)) == (
        "<html>old cached template</html>"
    )
    original_stat = target.stat()

    cloak_scripts_paths.atomic_write_bridge_html(
        str(target),
        "<html>new replacement template</html>",
    )
    # 模拟低精度文件系统/快速覆盖：即使 mtime 相同，也必须识别 inode 变化。
    os.utime(
        target,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
    )

    assert cloak_scripts_paths.read_bridge_html_template_cached(str(target)) == (
        "<html>new replacement template</html>"
    )
    cloak_scripts_paths.invalidate_bridge_template_cache()
