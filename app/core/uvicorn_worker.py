"""Gunicorn 使用的 Uvicorn Worker 安全配置。"""

from uvicorn.workers import UvicornWorker


class NoProxyHeadersUvicornWorker(UvicornWorker):
    """保留真实 TCP 对端，由应用仅在可信代理场景解析转发头。"""

    CONFIG_KWARGS = {
        **UvicornWorker.CONFIG_KWARGS,
        "proxy_headers": False,
    }
