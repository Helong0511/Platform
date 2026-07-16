"""
出站 URL SSRF 防护。

对 Postback 转发等「服务端按配置主动发起 HTTP 请求」的场景，在发请求前校验目标：
仅允许 http/https，拒绝回环、私网、链路本地、保留地址及常见云元数据主机名。
重定向链上的每个目标也应再次调用本模块校验。
"""
from __future__ import annotations

import ipaddress
import logging
import socket
from typing import Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# 明确禁止的主机名（大小写不敏感）；含云元数据常见别名
_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "metadata",
        "metadata.google.internal",
        "metadata.goog",
        "kubernetes.default",
        "kubernetes.default.svc",
    }
)

# 额外封锁的网段（部分环境 is_private 未覆盖或需显式拒绝）
_EXTRA_BLOCKED_NETWORKS = (
    ipaddress.ip_network("169.254.169.254/32"),  # 云元数据
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT / 部分 VPC
    ipaddress.ip_network("0.0.0.0/8"),
)


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """判断解析后的 IP 是否禁止作为出站目标。"""
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        return True
    for network in _EXTRA_BLOCKED_NETWORKS:
        try:
            if ip in network:
                return True
        except TypeError:
            # IPv4 / IPv6 与网段族不一致时跳过
            continue
    return False


def _hostname_blocked(hostname: str) -> bool:
    """主机名黑名单与可疑后缀检查。"""
    host = hostname.lower().rstrip(".")
    if host in _BLOCKED_HOSTNAMES:
        return True
    if host.endswith(".localhost") or host.endswith(".local") or host.endswith(".internal"):
        return True
    return False


def validate_outbound_url(url: str) -> Tuple[bool, str]:
    """
    校验出站 URL 是否允许发起服务端请求。

    Args:
        url: 完整 URL（可含查询串）

    Returns:
        (是否允许, 拒绝原因；允许时原因为空串)
    """
    if not url or not isinstance(url, str):
        return False, "url 为空"

    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False, "url 无法解析"

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return False, f"不允许的协议: {scheme or '(空)'}"

    hostname = parsed.hostname
    if not hostname:
        return False, "缺少主机名"

    if _hostname_blocked(hostname):
        return False, f"禁止的主机名: {hostname}"

    # 主机名本身是字面量 IP
    try:
        literal_ip = ipaddress.ip_address(hostname)
        if _is_blocked_ip(literal_ip):
            return False, f"禁止的目标 IP: {hostname}"
        return True, ""
    except ValueError:
        pass

    # DNS 解析后检查全部 A/AAAA，任一落在禁网段即拒绝
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        logger.warning("出站 URL DNS 解析失败: host=%s error=%s", hostname, exc)
        return False, "DNS 解析失败"
    except OSError as exc:
        logger.warning("出站 URL DNS 解析异常: host=%s error=%s", hostname, exc)
        return False, "DNS 解析异常"

    if not addr_infos:
        return False, "DNS 无解析结果"

    seen_ips: set[str] = set()
    for info in addr_infos:
        addr = info[4][0]
        if addr in seen_ips:
            continue
        seen_ips.add(addr)
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if _is_blocked_ip(ip):
            return False, f"解析结果落在禁网段: {addr}"

    return True, ""
