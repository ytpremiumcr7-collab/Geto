from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.auth.models import Principal
from app.api.routes import entities as entities_routes
from app.api.routes import observations as observations_routes


def _row(source_id: str, entity_id: str = "icao24:abc"):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=f"id-{source_id}",
        entity_id=entity_id,
        entity_type="aircraft",
        source_id=source_id,
        source_record_id=entity_id,
        observed_at=now,
        received_at=now,
        geometry=None,
        altitude_m=1000.0,
        speed_mps=120.0,
        heading_deg=90.0,
        accuracy_m=None,
        confidence=0.9,
        attributes={"callsign": "TEST"},
        provenance={"source_id": source_id},
        raw_payload_uri=None,
    )


class _LeakyObservationRepository:
    def __init__(self, _db):
        pass

    async def list(self, **_kwargs):
        # Deliberately simulate a repository regression that returns more than
        # the principal is authorized to read. Route-level defense must still
        # prevent restricted-source data from crossing the API boundary.
        return [_row("opensky"), _row("usgs_earthquake", "quake:1")]


@pytest.mark.asyncio
async def test_observations_all_never_leaks_restricted_source(monkeypatch):
    monkeypatch.setattr(observations_routes, "ObservationRepository", _LeakyObservationRepository)
    principal = Principal("operator-1", "tenant-a", frozenset({"operator"}))

    body = await observations_routes.list_observations(
        entity_id=None,
        source_id=None,
        since=None,
        until=None,
        limit=100,
        db=object(),
        principal=principal,
    )

    assert {row["source_id"] for row in body["observations"]} == {"usgs_earthquake"}


@pytest.mark.asyncio
async def test_entity_track_never_leaks_restricted_source(monkeypatch):
    monkeypatch.setattr(entities_routes, "ObservationRepository", _LeakyObservationRepository)
    principal = Principal("operator-1", "tenant-a", frozenset({"operator"}))

    body = await entities_routes.get_track(
        entity_id="icao24:abc",
        limit=100,
        db=object(),
        principal=principal,
    )

    assert len(body["track"]) == 1
    assert body["track"][0]["source_id"] == "usgs_earthquake"
