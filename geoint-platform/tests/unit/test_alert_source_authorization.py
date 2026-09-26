from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.alerts.service import AlertService


def _alert(source_id: str):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        tenant_id="tenant-a",
        rule_id=uuid4(),
        geofence_id=uuid4(),
        entity_id=f"entity:{source_id}",
        event_type="enter",
        severity="medium",
        status="open",
        payload={"source_id": source_id},
        occurred_at=now,
        acked_at=None,
        acked_by=None,
        resolved_at=None,
        created_at=now,
    )


class _Scalars:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return list(self.rows)


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return _Scalars(self.rows)


class _ListSession:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, _stmt):
        return _Result(self.rows)


class _GetSession:
    def __init__(self, row):
        self.row = row
        self.committed = False

    async def get(self, _model, _pk):
        return self.row

    async def commit(self):
        self.committed = True

    async def refresh(self, _row):
        return None


@pytest.mark.asyncio
async def test_alert_list_never_exposes_restricted_source():
    svc = AlertService()
    rows = [_alert("opensky"), _alert("usgs_earthquake")]

    out = await svc.list_alerts(
        _ListSession(rows),
        "tenant-a",
        status="open",
        limit=50,
        allowed_source_ids={"usgs_earthquake"},
    )

    assert {item["source_id"] for item in out} == {"usgs_earthquake"}


@pytest.mark.asyncio
async def test_restricted_alert_cannot_be_acked_by_id():
    svc = AlertService()
    session = _GetSession(_alert("opensky"))

    out = await svc.ack_alert(
        session,
        "tenant-a",
        session.row.id,
        "operator-1",
        allowed_source_ids={"usgs_earthquake"},
    )

    assert out is None
    assert session.committed is False
