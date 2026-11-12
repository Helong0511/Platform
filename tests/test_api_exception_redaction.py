"""关键 API/服务异常出口不得将原始异常消息写入响应或日志。"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_tracking_endpoints_do_not_log_or_return_raw_exception_text():
    source = _source("app/api_v1/tracking/tracking.py")
    assert 'logger.error(f"点击追踪失败: {str(e)}"' not in source
    assert 'detail=f"点击追踪失败: {str(e)}"' not in source
    assert "异步保存点击记录最终失败: click_id=%s error=%s" not in source
    assert "exc_info=True" not in source


def test_short_link_diagnostics_do_not_expose_exception_text():
    source = _source("app/api_v1/tracking/short_links.py")
    assert 'str(e)' not in source
    assert "exc_info=True" not in source
    assert "Redis SCAN失败，降级使用KEYS: {scan_error}" not in source


def test_user_api_and_service_logs_do_not_include_raw_exception_objects():
    api_source = _source("app/api_v1/users/users.py")
    service_source = _source("app/services/user_service.py")
    assert "获取用户统计信息失败: {str(e)}" not in api_source
    assert "exc_info=True" not in api_source
    assert "exc_info=True" not in service_source
    assert "清除 user_stats 缓存失败: {e}" not in service_source
    assert "改密后吊销会话失败（密码已更新）: %s" not in service_source


def test_short_link_service_does_not_log_raw_database_exceptions():
    source = _source("app/services/short_link_service.py")
    assert "创建短链接失败: {str(e)}" not in source
    assert "创建短链接代码重复: {str(e)}" not in source
    assert "exc_info=True" not in source
