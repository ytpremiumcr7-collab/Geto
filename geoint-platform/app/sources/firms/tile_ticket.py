"""Signed short-lived tickets for FIRMS WMS tile proxy (no NASA key in browser).

Ticket format (urlsafe base64 of utf-8):
  tenant_id|user_id|exp_unix|hex_hmac_sha256

HMAC key: settings.firms_tile_hmac_secret or settings.jwt_secret (dev fallback).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

from app.core.config import settings

DEFAULT_TTL_S = 15 * 60  # 15 minutes


def _secret() -> bytes:
    raw = (
        getattr(settings, "firms_tile_hmac_secret", None)
        or settings.jwt_secret
        or ""
    ).strip()
    if not raw:
        # Deterministic lab fallback only when auth_disabled / empty secret —
        # production bootstrap should already require jwt material.
        raw = "geoint-firms-tile-dev-only"
    return raw.encode("utf-8")


def issue_ticket(
    *,
    tenant_id: str,
    user_id: str,
    ttl_s: int = DEFAULT_TTL_S,
) -> tuple[str, int]:
    exp = int(time.time()) + max(60, ttl_s)
    body = f"{tenant_id}|{user_id}|{exp}"
    sig = hmac.new(_secret(), body.encode("utf-8"), hashlib.sha256).hexdigest()
    token = base64.urlsafe_b64encode(f"{body}|{sig}".encode()).decode("ascii")
    return token, exp


def verify_ticket(ticket: str) -> tuple[str, str] | None:
    """Return (tenant_id, user_id) if valid; else None."""
    if not ticket or not ticket.strip():
        return None
    try:
        raw = base64.urlsafe_b64decode(ticket.strip().encode("ascii")).decode("utf-8")
        parts = raw.split("|")
        if len(parts) != 4:
            return None
        tenant_id, user_id, exp_s, sig = parts
        exp = int(exp_s)
        if exp < int(time.time()):
            return None
        body = f"{tenant_id}|{user_id}|{exp_s}"
        expected = hmac.new(_secret(), body.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        if not tenant_id or not user_id:
            return None
        return tenant_id, user_id
    except Exception:
        return None
