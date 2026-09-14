# Paths de ingestión — qué usar

## Producción (sí usar)
SourceJob (Postgres)
  → job_scheduler (lease SKIP LOCKED)
  → NATS JetStream
  → source_worker
  → SourceDispatcher
  → PostGIS + outbox + (opcional) Redis rate-limit
  → API REST + WebSocket

Redis: rate limiting, no es el bus de jobs.
APIs: FastAPI; adapters hablan a NASA/USGS/etc.

## Legacy (no usar en prod)
| Módulo | Para qué era |
|--------|----------------|
| app/workers/ingestion.py | Poll directo sin NATS (dev rápido) |
| app/ingestion/pipeline.py | Pipeline viejo sin SourceJob |

Marcados DEPRECATED/LEGACY. Con Redis + APIs + scheduler/worker, no los necesitas.
