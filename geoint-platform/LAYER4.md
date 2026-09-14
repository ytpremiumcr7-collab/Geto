# GEOINT — Capa 4 (cierre): Consumer JetStream + Idempotencia + DLQ + SourceJob↔Adapters

Código de producción listo para integrar sobre la **capa 1** (`app/`).

## Qué resuelve

- Durable consumers JetStream (queue group + durable name)
- `AckWait` + `MaxDeliver` → redelivery controlada
- Tras superar MaxDeliver → publicación automática a DLQ y ACK del mensaje original
- Tabla de idempotencia (`processed_messages`) por `Nats-Msg-Id` / job_id
- Scheduler con `FOR UPDATE SKIP LOCKED` + leases
- Dispatcher tipado por fuente (sin `**kwargs` genéricos a todos los adapters)
- Flujo: claim job → publish JetStream → worker → adapter → normalize → ON CONFLICT → mark success/failure

## Integración rápida

1. Copia `app/jobs`, `app/messaging`, `app/ingestion/dispatcher.py` y el modelo de idempotencia sobre tu proyecto generado por capa 1.
2. Aplica la migración `0002_layer4_jobs_idempotency.py`.
3. Añade al `Makefile` / compose el worker:

```bash
python -m app.workers.source_worker
python -m app.workers.job_scheduler
```

4. Variables (`.env`):

```
NATS_URL=nats://localhost:4222
NATS_STREAM=GEOINT
NATS_JOBS_SUBJECT=geoint.jobs.>
NATS_DURABLE=geoint-source-workers
NATS_QUEUE_GROUP=geoint-workers
NATS_ACK_WAIT_SECONDS=60
NATS_MAX_DELIVER=5
JOB_LEASE_SECONDS=120
JOB_POLL_INTERVAL_SECONDS=2
WORKER_ID=  # opcional; se auto-genera
```

## Orden de arranque

1. Infra (postgres, nats, minio…)
2. `alembic upgrade head`
3. `uvicorn app.main:app`
4. `python -m app.workers.job_scheduler`
5. `python -m app.workers.source_worker` (escalable horizontalmente)

## Flujo

```
PostgreSQL source_jobs (due)
        │
        ▼
  JobScheduler (SKIP LOCKED + lease)
        │
        ▼
  NATS JetStream  geoint.jobs.{source_id}
        │  (Nats-Msg-Id = job_id)
        ▼
  SourceWorker (durable + queue)
        │
        ├── already processed? → ACK
        ├── Dispatcher → adapter tipado
        ├── ON CONFLICT insert
        ├── mark job success
        └── ACK
              │
              └── failure / MaxDeliver → DLQ + mark failure
```
