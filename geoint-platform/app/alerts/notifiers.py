"""Channel notifiers: webhook (HTTP), SMTP, log, websocket (NATS fan-out)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any, Protocol

import httpx

log = logging.getLogger(__name__)


class NotifierResult:
    def __init__(self, ok: bool, meta: dict[str, Any] | None = None, error: str | None = None):
        self.ok = ok
        self.meta = meta or {}
        self.error = error


class Notifier(Protocol):
    async def send(self, *, alert: dict[str, Any], channel_config: dict[str, Any]) -> NotifierResult: ...


def build_alert_body(alert: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": alert.get("id"),
        "tenant_id": alert.get("tenant_id"),
        "geofence_id": alert.get("geofence_id"),
        "entity_id": alert.get("entity_id"),
        "event_type": alert.get("event_type"),
        "severity": alert.get("severity"),
        "status": alert.get("status"),
        "occurred_at": alert.get("occurred_at"),
        "payload": alert.get("payload") or {},
        "product": "geoint",
        "version": "2.3.0",
    }


class LogNotifier:
    async def send(self, *, alert: dict[str, Any], channel_config: dict[str, Any]) -> NotifierResult:
        body = build_alert_body(alert)
        log.info(
            "alert_notify_log entity=%s event=%s severity=%s alert_id=%s",
            body.get("entity_id"),
            body.get("event_type"),
            body.get("severity"),
            body.get("id"),
        )
        return NotifierResult(ok=True, meta={"sink": "log"})


class WebhookNotifier:
    """POST JSON to config.url. Optional HMAC-SHA256 with config.secret → X-Geoint-Signature."""

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    async def send(self, *, alert: dict[str, Any], channel_config: dict[str, Any]) -> NotifierResult:
        url = (channel_config.get("url") or "").strip()
        if not url:
            return NotifierResult(ok=False, error="webhook config missing url")
        if not (url.startswith("https://") or url.startswith("http://")):
            return NotifierResult(ok=False, error="webhook url must be http(s)")

        body = build_alert_body(alert)
        raw = json.dumps(body, separators=(",", ":"), default=str).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": "geoint-alert-notifier/2.3"}
        extra = channel_config.get("headers") or {}
        if isinstance(extra, dict):
            headers.update({str(k): str(v) for k, v in extra.items()})

        secret = channel_config.get("secret") or ""
        if secret:
            sig = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
            headers["X-Geoint-Signature"] = f"sha256={sig}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
                resp = await client.post(url, content=raw, headers=headers)
            meta = {"status_code": resp.status_code, "url": url.split("?")[0]}
            if 200 <= resp.status_code < 300:
                return NotifierResult(ok=True, meta=meta)
            return NotifierResult(
                ok=False,
                meta=meta,
                error=f"webhook HTTP {resp.status_code}: {resp.text[:300]}",
            )
        except Exception as e:
            return NotifierResult(ok=False, error=f"webhook error: {e}")


class SmtpNotifier:
    """Send email via SMTP. Channel config: {to, cc?, subject?}. Server from settings."""

    async def send(self, *, alert: dict[str, Any], channel_config: dict[str, Any]) -> NotifierResult:
        from app.core.config import settings

        to_addr = (channel_config.get("to") or "").strip()
        if not to_addr:
            return NotifierResult(ok=False, error="smtp config missing to")

        host = getattr(settings, "smtp_host", None) or ""
        if not host:
            return NotifierResult(ok=False, error="SMTP_HOST not configured")

        port = int(getattr(settings, "smtp_port", 587) or 587)
        user = getattr(settings, "smtp_user", None) or ""
        password = getattr(settings, "smtp_password", None) or ""
        from_addr = (
            channel_config.get("from")
            or getattr(settings, "smtp_from", None)
            or user
            or "geoint@localhost"
        )
        use_tls = bool(getattr(settings, "smtp_use_tls", True))

        body = build_alert_body(alert)
        subject = channel_config.get("subject") or (
            f"[GEOINT {body.get('severity', '').upper()}] "
            f"geofence {body.get('event_type')} · {body.get('entity_id')}"
        )
        text = (
            f"GEOINT geofence alert\n"
            f"event: {body.get('event_type')}\n"
            f"entity: {body.get('entity_id')}\n"
            f"geofence: {body.get('geofence_id')}\n"
            f"severity: {body.get('severity')}\n"
            f"occurred_at: {body.get('occurred_at')}\n"
            f"alert_id: {body.get('id')}\n"
            f"payload: {json.dumps(body.get('payload') or {}, default=str)}\n"
        )

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_addr
        if channel_config.get("cc"):
            msg["Cc"] = channel_config["cc"]
        msg.set_content(text)

        try:
            # stdlib SMTP is sync; run in thread via asyncio if needed — keep simple
            import asyncio

            def _send() -> None:
                if use_tls and port == 465:
                    context = ssl.create_default_context()
                    with smtplib.SMTP_SSL(host, port, context=context, timeout=20) as smtp:
                        if user:
                            smtp.login(user, password)
                        smtp.send_message(msg)
                else:
                    with smtplib.SMTP(host, port, timeout=20) as smtp:
                        smtp.ehlo()
                        if use_tls:
                            context = ssl.create_default_context()
                            smtp.starttls(context=context)
                            smtp.ehlo()
                        if user:
                            smtp.login(user, password)
                        smtp.send_message(msg)

            await asyncio.to_thread(_send)
            return NotifierResult(ok=True, meta={"to": to_addr, "host": host})
        except Exception as e:
            return NotifierResult(ok=False, error=f"smtp error: {e}")


class WebsocketNotifier:
    """Publish alert to NATS for realtime UI fan-out (subject geoint.alert.<tenant>)."""

    async def send(self, *, alert: dict[str, Any], channel_config: dict[str, Any]) -> NotifierResult:
        try:
            from app.messaging.jetstream import JetStreamClient

            body = build_alert_body(alert)
            tenant = body.get("tenant_id") or "default"
            subject = channel_config.get("subject") or f"geoint.alert.{tenant}"
            js = JetStreamClient()
            await js.connect()
            try:
                assert js.js is not None
                await js.js.publish(subject, json.dumps(body, default=str).encode())
            finally:
                await js.close()
            return NotifierResult(ok=True, meta={"subject": subject})
        except Exception as e:
            return NotifierResult(ok=False, error=f"websocket/nats error: {e}")


def get_notifier(channel_type: str) -> Notifier:
    t = (channel_type or "").lower().strip()
    if t == "webhook":
        return WebhookNotifier()
    if t == "email" or t == "smtp":
        return SmtpNotifier()
    if t == "websocket":
        return WebsocketNotifier()
    if t == "log":
        return LogNotifier()
    return LogNotifier()  # unknown → log fallback
