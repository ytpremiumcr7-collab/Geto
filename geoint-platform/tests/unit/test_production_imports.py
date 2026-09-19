"""Regression tests for production-critical import seams.

These imports are intentionally kept as tiny smoke tests: if one fails,
workers cannot start even when API-only tests stay green.
"""


def test_source_worker_imports() -> None:
    from app.workers.source_worker import SourceWorker

    assert SourceWorker is not None


def test_outbox_dispatcher_imports() -> None:
    from app.outbox.dispatcher import OutboxDispatcher

    assert OutboxDispatcher is not None


def test_idempotency_repository_is_module_level() -> None:
    from app.jobs.repository import IdempotencyRepository

    assert IdempotencyRepository is not None


def test_clickhouse_sink_is_available() -> None:
    from app.analytics.clickhouse import ClickHouseSink

    assert ClickHouseSink is not None
