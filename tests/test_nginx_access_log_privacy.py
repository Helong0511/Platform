"""Nginx access log 不记录 URL 查询参数或客户端可伪造的请求头。"""
from pathlib import Path


def test_nginx_access_log_omits_query_string_referer_user_agent_and_forwarded_for():
    root = Path(__file__).resolve().parents[1]
    config = (
        root / "nginx" / "btfrx.online" / "nginx.conf"
    ).read_text(encoding="utf-8")

    log_format = config.split("log_format main", 1)[1].split(";", 1)[0]

    assert "$request_method $uri $server_protocol" in log_format
    assert '"$request"' not in log_format
    assert "$request_uri" not in log_format
    assert "$http_referer" not in log_format
    assert "$http_user_agent" not in log_format
    assert "$http_x_forwarded_for" not in log_format

    # 不得同时使用默认格式和 main 格式向同一文件重复写入。
    assert "access_log /var/log/nginx/access.log main;" in config
    assert config.count("access_log /var/log/nginx/access.log main;") == 1
    assert "access_log /var/log/nginx/access.log;" not in config
