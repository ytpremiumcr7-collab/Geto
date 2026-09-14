# Alert notifiers

Flow: **geofence enter/exit → rule match → `geofence_alerts` → `alert_deliveries` → worker → channel**

## Worker

```bash
python -m app.workers.alert_notifier
# or compose service geoint-alert-notifier
```

Claims `alert_deliveries` with `app.tenant_id=__system__`, delivers per channel, retries with exponential backoff (30s × 2^n, max 1h, 5 attempts).

## Channel types

| type | config |
|------|--------|
| `webhook` | `{ "url": "https://…", "secret": "optional-hmac", "headers": {} }` |
| `email` | `{ "to": "ops@example.com", "subject": "optional" }` + env `SMTP_*` |
| `log` | `{}` — structured log only |
| `websocket` | `{ "subject": "geoint.alert.default" }` — NATS publish |

Webhook signature header: `X-Geoint-Signature: sha256=<hmac_hex>` over raw JSON body.

## API

- `GET /api/v1/alerts/{id}/deliveries` — status per channel
- Create channels/rules as before under `/api/v1/alerts/channels` and `/rules`

Silence on a rule prevents **new** alerts (and thus new deliveries). Ack/resolve does not retract already-sent webhooks; new deliveries skip if alert is `resolved`.
