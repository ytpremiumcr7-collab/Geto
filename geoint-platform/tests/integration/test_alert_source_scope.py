from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.alerts.models import GeofenceAlert
from app.alerts.service import AlertService
from app.db.tenant import tenant_session


@pytest.mark.asyncio
async def test_alert_source_scope_is_applied_before_limit():
    tenant_id = f"alert-authz-{uuid4()}"
    now = datetime.now(UTC)

    async with tenant_session(tenant_id) as session:
        # Restricted row is newer. A post-LIMIT Python filter would return no
        # result for limit=1 even though an authorized older alert exists.
        session.add_all(
            [
                GeofenceAlert(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    rule_id=None,
                    geofence_id=uuid4(),
                    entity_id="restricted-aircraft",
                    source_id="opensky",
                    event_type="enter",
                    severity="medium",
                    status="open",
                    payload={"source_id": "opensky"},
                    occurred_at=now,
                ),
                GeofenceAlert(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    rule_id=None,
                    geofence_id=uuid4(),
                    entity_id="allowed-earthquake",
                    source_id="usgs_earthquake",
                    event_type="enter",
                    severity="medium",
                    status="open",
                    payload={"source_id": "usgs_earthquake"},
                    occurred_at=now - timedelta(seconds=1),
                ),
            ]
        )
        await session.commit()

        rows = await AlertService().list_alerts(
            session,
            tenant_id,
            status="open",
            limit=1,
            allowed_source_ids={"usgs_earthquake"},
        )

    assert len(rows) == 1
    assert rows[0]["source_id"] == "usgs_earthquake"
    assert rows[0]["entity_id"] == "allowed-earthquake"
