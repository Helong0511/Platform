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


class SSRFForbiddenError(Exception):
    """目标 URL 解析到私网/元数据等禁止地址时抛出。"""

    def __init__(self, reason: str, url: str = ""):
        self.reason = reason
        self.url = url
        super().__init__(reason)


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
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),  # IPv6 ULA
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
    ipaddress.ip_network("64:ff9b::/96"),  # NAT64 well-known prefix，防止映射到私网 IPv4
    ipaddress.ip_network("64:ff9b:1::/48"),  # 本地用途 NAT64 前缀
    ipaddress.ip_network("2002::/16"),  # 6to4 隧道地址，可能嵌入私网 IPv4
    ipaddress.ip_network("2001::/32"),  # Teredo 隧道地址
)


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """判断解析后的 IP 是否禁止作为出站目标；只允许全球单播地址。"""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        if _is_blocked_ip(ip.ipv4_mapped):
            return True

    if (
        not ip.is_global
        or ip.is_private
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


def resolve_public_ip(hostname: str) -> str:
    """
    解析并固定一个经过校验的公网 IP。

    调用方必须把返回 IP 用于实际 TCP 连接，不能只校验后再让 HTTP 客户端重新解析域名；
    否则 DNS rebinding 可在校验与连接之间切换到内网地址。
    """
    if not hostname or _hostname_blocked(hostname):
        raise SSRFForbiddenError(f"禁止的主机名: {hostname or '(空)'}")

    try:
        literal_ip = ipaddress.ip_address(hostname)
        if _is_blocked_ip(literal_ip):
            raise SSRFForbiddenError(f"禁止的目标 IP: {hostname}")
        return str(literal_ip)
    except ValueError:
        pass

    try:
        addr_infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        logger.warning("出站 URL DNS 解析失败: host=%s error=%s", hostname, exc)
        raise SSRFForbiddenError("DNS 解析失败") from exc
    except OSError as exc:
        logger.warning("出站 URL DNS 解析异常: host=%s error=%s", hostname, exc)
        raise SSRFForbiddenError("DNS 解析异常") from exc

    if not addr_infos:
        raise SSRFForbiddenError("DNS 无解析结果")

    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    seen_ips: set[str] = set()
    for info in addr_infos:
        addr = str(info[4][0]).split("%", 1)[0]
        if addr in seen_ips:
            continue
        seen_ips.add(addr)
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        # 任何 A/AAAA 记录指向非公网地址，都拒绝整个主机名。
        if _is_blocked_ip(ip):
            raise SSRFForbiddenError(f"解析结果落在禁网段: {addr}")
        addresses.append(ip)

    if not addresses:
        raise SSRFForbiddenError("DNS 无有效 IP 解析结果")

    # 优先 IPv4，降低不同运行环境对 IPv6 出站路由的差异。
    for ip in addresses:
        if isinstance(ip, ipaddress.IPv4Address):
            return str(ip)
    return str(addresses[0])


def validate_outbound_url(url: str) -> Tuple[bool, str]:
    """
    校验出站 URL 是否允许发起服务端请求。

    使用 getaddrinfo 检查全部 A/AAAA；任一结果落入禁网段即拒绝。
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

    try:
        resolve_public_ip(hostname)
    except SSRFForbiddenError as exc:
        return False, exc.reason

    return True, ""


def assert_outbound_url_safe(url: str) -> None:
    """校验失败时抛出 ``SSRFForbiddenError``。"""
    ok, reason = validate_outbound_url(url)
    if not ok:
        raise SSRFForbiddenError(reason, url=url)
