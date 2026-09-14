#!/usr/bin/env python3
"""CI product flow (ASGI + PostGIS).

auth/me → sources → analytics → topo → channel/rule → emit → delivery delivered.

Exit 0 only if critical path passes.
"""

from __future__ import annotations

import asyncio
import os
import sys
import traceback
from datetime import UTC, datetime
from uuid import uuid4

sys.path.insert(0, ".")


async def main() -> int:
    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("AUTH_DISABLED", "true")

    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import select

    from app.alerts.delivery import DeliveryService
    from app.alerts.models import AlertChannel, AlertDelivery, GeofenceAlertRule
    from app.alerts.service import AlertService
    from app.db.session import SessionLocal
    from app.db.tenant import set_tenant
    from app.main import app

    print("=== e2e_ci_product_flow ===")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/health/live")
        assert r.status_code == 200, r.text
        print("  PASS  health/live")

        r = await client.get("/api/v1/me")
        assert r.status_code == 200, r.text
        me = r.json()
        assert "permissions" in me
        tenant = me.get("tenant_id") or "default"
        print(f"  PASS  /me tenant={tenant} roles={me.get('roles')}")

        r = await client.get("/api/v1/sources")
        assert r.status_code == 200, r.text
        print("  PASS  sources")

        r = await client.get("/api/v1/analytics/templates")
        assert r.status_code == 200, r.text
        print(f"  PASS  analytics enabled={r.json().get('enabled')}")

        r = await client.get("/api/v1/topography/providers")
        assert r.status_code == 200, r.text
        print("  PASS  topography providers")

        r = await client.get("/api/v1/alerts?status=open")
        assert r.status_code == 200, r.text
        print("  PASS  alerts list")

    fence_id = uuid4()
    channel_id = uuid4()
    rule_id = uuid4()

    async with SessionLocal() as session:
        await set_tenant(session, tenant)
        ch = AlertChannel(
            id=channel_id,
            tenant_id=tenant,
            name="e2e-log",
            channel_type="log",
            config={},
            enabled=True,
        )
        session.add(ch)
        rule = GeofenceAlertRule(
            id=rule_id,
            tenant_id=tenant,
            geofence_id=fence_id,
            name="e2e-enter",
            on_enter=True,
            on_exit=False,
            channel_ids=[str(channel_id)],
            entity_type_filter=None,
            severity="high",
            enabled=True,
            silence_until=None,
        )
        session.add(rule)
        await session.commit()

        event = {
            "event_type": "geofence.enter",
            "geofence_id": str(fence_id),
            "entity_id": "E2E-ACFT-1",
            "occurred_at": datetime.now(UTC).isoformat(),
            "data": {"lat": 19.4, "lon": -99.1},
        }
        created = await AlertService().emit_from_geofence_event(
            session, tenant_id=tenant, event=event
        )
        await session.commit()
        assert created, "expected alert"
        print(f"  PASS  alert emit entity={created[0].get('entity_id')}")

        result = await session.execute(
            select(AlertDelivery).where(AlertDelivery.tenant_id == tenant)
        )
        deliveries = list(result.scalars().all())
        assert deliveries, "expected deliveries"
        d = deliveries[-1]
        d.status = "sending"
        out = await DeliveryService().process_one(session, d)
        await session.commit()
        status = out.get("status") if isinstance(out, dict) else out
        assert status == "delivered" or d.status == "delivered", (status, d.status)
        print(f"  PASS  delivery status={d.status}")

    print("=== E2E PRODUCT FLOW OK ===")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception:
        traceback.print_exc()
        raise SystemExit(1) from None
