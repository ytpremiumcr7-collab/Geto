from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.outbox.repository import OutboxRepository


def _message(attempts: int):
    return SimpleNamespace(
        attempts=attempts,
        last_error=None,
        next_attempt_at=None,
        dead_lettered_at=None,
        lease_until=datetime.now(UTC),
        claimed_by="worker-1",
    )


def test_outbox_failure_schedules_exponential_retry_and_releases_lease():
    message = _message(0)

    OutboxRepository().mark_failed(message, "upstream down", max_attempts=5, base_backoff_seconds=10)

    assert message.attempts == 1
    assert message.next_attempt_at is not None
    assert message.dead_lettered_at is None
    assert message.lease_until is None
    assert message.claimed_by is None


def test_outbox_failure_dead_letters_after_max_attempts():
    message = _message(4)

    OutboxRepository().mark_failed(message, "still down", max_attempts=5, base_backoff_seconds=10)

    assert message.attempts == 5
    assert message.dead_lettered_at is not None
    assert message.next_attempt_at is None
    assert message.lease_until is None
    assert message.claimed_by is None
