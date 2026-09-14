"""Webhook destination validation — block SSRF to private/link-local/metadata."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeWebhookURL(ValueError):
    pass


_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    for net in _BLOCKED_NETWORKS:
        if ip in net:
            return True
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
        return True
    return False


def validate_webhook_url(url: str, *, require_https: bool = False) -> str:
    """Validate URL for outbound webhook. Returns normalized URL or raises."""
    if not url or not isinstance(url, str):
        raise UnsafeWebhookURL("webhook url required")
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise UnsafeWebhookURL("webhook scheme must be http or https")
    if require_https and parsed.scheme != "https":
        raise UnsafeWebhookURL("webhook must use https")
    if not parsed.hostname:
        raise UnsafeWebhookURL("webhook host required")
    host = parsed.hostname
    # Block obvious local names
    if host.lower() in {"localhost", "metadata.google.internal"}:
        raise UnsafeWebhookURL(f"webhook host not allowed: {host}")
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as e:
        raise UnsafeWebhookURL(f"webhook host DNS failed: {e}") from e
    if not infos:
        raise UnsafeWebhookURL("webhook host DNS empty")
    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if _is_blocked(ip):
            raise UnsafeWebhookURL(f"webhook resolves to blocked address {ip}")
    return url.strip()
