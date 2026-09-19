from starlette.requests import Request

from app.core import config as cfg
from app.middleware.rate_limit_mw import _client_ip


def _request(peer: str, xff: str | None = None) -> Request:
    headers = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
            "query_string": b"",
            "scheme": "https",
            "server": ("testserver", 443),
            "client": (peer, 12345),
        }
    )


def test_untrusted_peer_cannot_spoof_x_forwarded_for(monkeypatch):
    monkeypatch.setattr(cfg.settings, "trusted_proxy_cidrs", "")
    assert _client_ip(_request("203.0.113.10", "1.1.1.1")) == "203.0.113.10"


def test_trusted_proxy_can_supply_original_client(monkeypatch):
    monkeypatch.setattr(cfg.settings, "trusted_proxy_cidrs", "10.0.0.0/8,2001:db8::/32")
    assert _client_ip(_request("10.20.30.40", "198.51.100.25, 10.20.30.40")) == "198.51.100.25"


def test_malformed_forwarded_ip_falls_back_to_peer(monkeypatch):
    monkeypatch.setattr(cfg.settings, "trusted_proxy_cidrs", "10.0.0.0/8")
    assert _client_ip(_request("10.20.30.40", "not-an-ip")) == "10.20.30.40"
