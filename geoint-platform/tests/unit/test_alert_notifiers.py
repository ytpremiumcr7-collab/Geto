"""Notifier unit tests — log + webhook signature + missing config."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.alerts.notifiers import LogNotifier, WebhookNotifier, build_alert_body, get_notifier


def test_build_alert_body():
    body = build_alert_body(
        {
            "id": "a1",
            "entity_id": "x",
            "event_type": "enter",
            "severity": "high",
            "payload": {"lat": 1},
        }
    )
    assert body["entity_id"] == "x"
    assert body["product"] == "geoint"


def test_log_notifier_ok():
    r = asyncio.run(LogNotifier().send(alert={"id": "1", "entity_id": "e"}, channel_config={}))
    assert r.ok


def test_webhook_missing_url():
    r = asyncio.run(WebhookNotifier().send(alert={"id": "1"}, channel_config={}))
    assert not r.ok
    assert "url" in (r.error or "")


def test_webhook_success_and_signature():
    alert = {"id": "aid", "entity_id": "acft-1", "event_type": "enter", "severity": "medium"}
    secret = "s3cr3t"

    mock_resp = MagicMock()
    mock_resp.status_code = 204
    mock_resp.text = ""

    async def fake_post(url, content=None, headers=None):
        assert url == "https://hooks.example.com/geoint"
        assert headers["Content-Type"] == "application/json"
        expected = hmac.new(secret.encode(), content, hashlib.sha256).hexdigest()
        assert headers["X-Geoint-Signature"] == f"sha256={expected}"
        json.loads(content.decode())
        return mock_resp

    mock_client = MagicMock()
    mock_client.post = fake_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.alerts.notifiers.httpx.AsyncClient", return_value=mock_client):
        r = asyncio.run(
            WebhookNotifier().send(
                alert=alert,
                channel_config={"url": "https://hooks.example.com/geoint", "secret": secret},
            )
        )
    assert r.ok
    assert r.meta.get("status_code") == 204


def test_get_notifier_types():
    assert isinstance(get_notifier("log"), LogNotifier)
    assert isinstance(get_notifier("webhook"), WebhookNotifier)
