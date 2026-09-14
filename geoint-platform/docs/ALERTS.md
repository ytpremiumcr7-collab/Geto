# Geofence alerts

Flow: **rule → alert → delivery queue → notifier worker**

## Channels

| Type | Notes |
|------|--------|
| `log` | Structured log (always available) |
| `webhook` | HTTP POST + optional HMAC |
| `smtp` | Email via `SMTP_*` settings |
| `nats` | JetStream subject |

## Worker

```bash
python -m app.workers.alert_notifier
# Health: :8081/health/live and /health/ready
```

Retries with exponential backoff; terminal `failed` after `max_attempts`.

## API

- Channels & rules under `/api/v1/alerts/...`
- Ack / resolve / silence
- `GET /api/v1/alerts/{id}/deliveries`
