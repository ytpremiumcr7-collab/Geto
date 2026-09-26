"""Real ingestion E2E: scheduler -> JetStream -> worker -> dispatcher -> DB/MinIO."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select

from app.core.config import settings
from app.db.models import Observation, SourceRun
from app.db.session import engine
from app.db.tenant import system_worker_session, tenant_session
from app.infrastructure.object_store import ObjectStore
from app.jobs.models import ProcessedMessage, SourceJob
from app.outbox.models import OutboxMessage
from app.workers.job_scheduler import JobScheduler
from app.workers.source_worker import SourceWorker

TENANT_ID = "e2e-ingestion"
HEX_ID = "abc123"


async def _wait_worker_ready(worker: SourceWorker, timeout: float = 15.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if worker.js is not None:
            try:
                await worker.js.consumer_info(settings.nats_stream, worker.durable)
                return
            except Exception:
                pass
        await asyncio.sleep(0.1)
    raise TimeoutError("source worker durable consumer did not become ready")


async def _seed_job(path: str) -> UUID:
    job = SourceJob(
        tenant_id=TENANT_ID,
        name=f"e2e-readsb-{uuid4().hex[:8]}",
        source_id="readsb_local",
        job_type="poll",
        status="pending",
        interval_seconds=3600,
        next_run_at=datetime.now(UTC) - timedelta(seconds=1),
        attempts=0,
        max_attempts=3,
        config={"path": path},
        enabled=True,
    )
    async with tenant_session(TENANT_ID) as session:
        session.add(job)
        await session.commit()
    return job.id


async def _wait_pipeline(job_id: UUID, timeout: float = 30.0):
    deadline = asyncio.get_running_loop().time() + timeout
    last_state: tuple[str | None, bool, int] | None = None
    while asyncio.get_running_loop().time() < deadline:
        async with tenant_session(TENANT_ID) as session:
            job = await session.get(SourceJob, job_id)
            observation = (
                await session.execute(
                    select(Observation).where(
                        Observation.tenant_id == TENANT_ID,
                        Observation.source_id == "readsb_local",
                        Observation.entity_id == f"icao24:{HEX_ID}",
                    )
                )
            ).scalar_one_or_none()
            runs = list(
                (
                    await session.execute(
                        select(SourceRun).where(
                            SourceRun.tenant_id == TENANT_ID,
                            SourceRun.source_id == "readsb_local",
                        )
                    )
                )
                .scalars()
                .all()
            )
            outbox = (
                await session.execute(
                    select(OutboxMessage).where(
                        OutboxMessage.tenant_id == TENANT_ID,
                        OutboxMessage.subject == "geoint.ingestion.readsb_local.completed",
                    )
                )
            ).scalar_one_or_none()

        last_state = (
            job.status if job else None,
            observation is not None,
            len(runs),
        )
        if (
            job is not None
            and job.status == "pending"
            and job.last_success_at is not None
            and observation is not None
            and runs
            and runs[-1].status == "ok"
            and outbox is not None
        ):
            return job, observation, runs[-1], outbox
        await asyncio.sleep(0.2)
    raise AssertionError(f"ingestion pipeline did not complete; last_state={last_state!r}")


async def main() -> int:
    os.environ.setdefault("GEOINT_SYSTEM_WORKER", "1")
    os.environ["NATS_DURABLE"] = f"geoint-e2e-{uuid4().hex[:10]}"

    fixture = {
        "now": 1_790_000_000,
        "aircraft": [
            {
                "hex": HEX_ID,
                "lat": 19.4326,
                "lon": -99.1332,
                "alt_baro": 12000,
                "gs": 220.0,
                "track": 87.0,
                "flight": "E2E123",
                "seen": 0.1,
            }
        ],
    }
    fixture_path = Path(tempfile.gettempdir()) / f"geoint-readsb-{uuid4().hex}.json"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

    scheduler = JobScheduler(poll_interval=0.1)
    worker = SourceWorker()
    worker_task: asyncio.Task[None] | None = None
    try:
        # Scheduler connection creates/updates the JetStream streams.
        await scheduler.js.connect()
        worker_task = asyncio.create_task(worker.start())
        await _wait_worker_ready(worker)

        job_id = await _seed_job(str(fixture_path))
        await scheduler.tick()

        job, observation, run, outbox = await _wait_pipeline(job_id)

        assert observation.raw_payload_uri is not None
        prefix = f"s3://{settings.minio_bucket_raw}/raw/{TENANT_ID}/readsb_local/"
        assert observation.raw_payload_uri.startswith(prefix), observation.raw_payload_uri

        bucket_and_key = observation.raw_payload_uri.removeprefix("s3://")
        bucket, key = bucket_and_key.split("/", 1)
        raw = json.loads((await ObjectStore().get_bytes(key, bucket=bucket)).decode("utf-8"))
        assert raw["aircraft"][0]["hex"] == HEX_ID

        async with system_worker_session() as session:
            processed = (
                await session.execute(
                    select(ProcessedMessage).where(
                        ProcessedMessage.tenant_id == TENANT_ID,
                        ProcessedMessage.message_id == str(job_id),
                    )
                )
            ).scalar_one_or_none()
        assert processed is not None
        assert processed.status == "completed"

        assert job.attempts == 0
        assert job.locked_until is None
        assert job.locked_by is None
        assert run.records_seen == 1
        assert run.records_normalized == 1
        assert outbox.payload["inserted"] == 1

        print(
            "INGESTION_E2E_OK",
            {
                "tenant": TENANT_ID,
                "job_id": str(job_id),
                "entity_id": observation.entity_id,
                "raw_uri": observation.raw_payload_uri,
                "processed": processed.status,
            },
        )
        return 0
    finally:
        worker.stop()
        if worker_task is not None:
            try:
                await asyncio.wait_for(worker_task, timeout=7)
            except TimeoutError:
                worker_task.cancel()
                await asyncio.gather(worker_task, return_exceptions=True)
        await scheduler.js.close()
        fixture_path.unlink(missing_ok=True)
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
