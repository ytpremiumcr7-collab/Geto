"""ETL OSM vía Overpass → PostGIS.

No consultar Overpass por request de usuario: este job materializa AOI.
Límites públicos Overpass: usar con moderación; en prod preferir extract .osm.pbf + osm2pgsql.

Uso:
  python -m app.osm.etl --west -99.2 --south 19.3 --east -99.0 --north 19.5
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from datetime import UTC, datetime

import httpx
import structlog
from geoalchemy2.shape import from_shape
from shapely.geometry import LineString, Point, Polygon
from sqlalchemy.dialects.postgresql import insert

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.db.tenant import set_tenant
from app.osm.models import OsmFeature

log = structlog.get_logger()

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Query compacta: infra crítica en bbox
QUERY_TEMPLATE = """
[out:json][timeout:60];
(
  way["highway"]({s},{w},{n},{e});
  way["railway"]({s},{w},{n},{e});
  way["waterway"]({s},{w},{n},{e});
  way["aeroway"]({s},{w},{n},{e});
  node["aeroway"="aerodrome"]({s},{w},{n},{e});
  way["building"]({s},{w},{n},{e});
  node["amenity"~"hospital|school|police"]({s},{w},{n},{e});
  way["power"]({s},{w},{n},{e});
);
out body geom;
"""


def _feature_class(tags: dict) -> str:
    for key in (
        "highway",
        "railway",
        "waterway",
        "aeroway",
        "building",
        "power",
        "amenity",
    ):
        if key in tags:
            return key
    return "other"


def _geom_from_element(el: dict):
    t = el.get("type")
    if t == "node":
        return Point(float(el["lon"]), float(el["lat"]))
    geometry = el.get("geometry") or []
    coords = [(float(p["lon"]), float(p["lat"])) for p in geometry if "lon" in p]
    if len(coords) >= 4 and coords[0] == coords[-1]:
        return Polygon(coords)
    if len(coords) >= 2:
        return LineString(coords)
    if len(coords) == 1:
        return Point(coords[0])
    return None


async def fetch_overpass(west: float, south: float, east: float, north: float) -> dict:
    query = QUERY_TEMPLATE.format(s=south, w=west, n=north, e=east)
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(OVERPASS_URL, data={"data": query})
        response.raise_for_status()
        return response.json()


async def upsert_elements(
    session,
    tenant_id: str,
    elements: list[dict],
) -> int:
    rows = []
    for el in elements:
        tags = el.get("tags") or {}
        geom = _geom_from_element(el)
        if geom is None or geom.is_empty:
            continue
        osm_id = f"{el.get('type')}/{el.get('id')}"
        rows.append(
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "osm_id": osm_id,
                "feature_class": _feature_class(tags),
                "name": tags.get("name"),
                "geometry": from_shape(geom, srid=4326),
                "tags": tags,
                "source": "overpass",
                "updated_at": datetime.now(UTC),
            }
        )
    if not rows:
        return 0
    # insert en lotes
    stmt = insert(OsmFeature).values(rows)
    stmt = stmt.on_conflict_do_nothing(constraint="uq_osm_features_tenant_osm_id")
    # sin unique constraint osm_id aún — usamos delete+insert por bbox en versión lean:
    await session.execute(stmt)
    return len(rows)


async def run_etl(
    west: float,
    south: float,
    east: float,
    north: float,
    tenant_id: str = "default",
) -> int:
    data = await fetch_overpass(west, south, east, north)
    elements = data.get("elements") or []
    async with SessionLocal() as session:
        await set_tenant(session, tenant_id)
        # lean: borrar features del tenant en bbox aproximado no implementado;
        # producción completa usaría osm2pgsql + diff
        n = await upsert_elements(session, tenant_id, elements)
        await session.commit()
    log.info("osm_etl_done", elements=len(elements), upserted=n)
    return n


def main() -> None:
    parser = argparse.ArgumentParser(description="OSM Overpass → PostGIS ETL")
    parser.add_argument("--west", type=float, required=True)
    parser.add_argument("--south", type=float, required=True)
    parser.add_argument("--east", type=float, required=True)
    parser.add_argument("--north", type=float, required=True)
    parser.add_argument("--tenant", default="default")
    args = parser.parse_args()
    configure_logging(settings.log_level)
    asyncio.run(run_etl(args.west, args.south, args.east, args.north, args.tenant))


if __name__ == "__main__":
    main()
