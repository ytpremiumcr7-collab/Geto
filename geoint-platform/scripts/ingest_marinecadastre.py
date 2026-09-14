#!/usr/bin/env python3
"""Ingestión batch de export MarineCadastre / AccessAIS (CSV).

Uso:
  python -m scripts.ingest_marinecadastre /data/ais/export.csv
  python -m scripts.ingest_marinecadastre /data/ais/export.csv --dry-run

Valida columnas mínimas, reporta filas inválidas y lanza el adapter ais_file
contra el path (mismo camino de producción que el SourceJob).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path

# Columnas aceptadas (MarineCadastre usa variantes)
REQUIRED_ANY = {
    "mmsi": ("mmsi", "MMSI"),
    "lat": ("lat", "latitude", "LAT"),
    "lon": ("lon", "longitude", "lng", "LON"),
}
OPTIONAL = (
    "sog",
    "SOG",
    "cog",
    "COG",
    "basedatetime",
    "BaseDateTime",
    "vesselname",
    "VesselName",
)


def validate_csv(path: Path, max_errors: int = 20) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV sin cabecera")
        fields_lower = {(h or "").strip().lower(): h for h in reader.fieldnames}
        missing = []
        for key, aliases in REQUIRED_ANY.items():
            if not any(a.lower() in fields_lower for a in aliases):
                missing.append(key)
        if missing:
            raise ValueError(
                f"Columnas requeridas ausentes: {missing}. Cabecera: {list(reader.fieldnames)}"
            )

        total = 0
        bad = 0
        errors: list[str] = []
        for i, row in enumerate(reader, start=2):
            total += 1
            lower = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            mmsi = lower.get("mmsi") or row.get("MMSI")
            lat = lower.get("lat") or lower.get("latitude") or row.get("LAT")
            lon = lower.get("lon") or lower.get("longitude") or lower.get("lng") or row.get("LON")
            try:
                if not mmsi:
                    raise ValueError("MMSI vacío")
                float(lat)
                float(lon)
            except (TypeError, ValueError) as exc:
                bad += 1
                if len(errors) < max_errors:
                    errors.append(f"line {i}: {exc}")
        return {
            "path": str(path),
            "rows": total,
            "invalid": bad,
            "valid": total - bad,
            "sample_errors": errors,
            "headers": list(reader.fieldnames or []),
        }


async def run_ingest(path: Path, dry_run: bool) -> int:
    report = validate_csv(path)
    print("validation:", report)
    if dry_run:
        return 0 if report["valid"] > 0 else 1

    from app.db.session import SessionLocal
    from app.db.tenant import set_tenant
    from app.ingestion.dispatcher import SourceDispatcher

    # El adapter lee el path; forzamos config
    async with SessionLocal() as session:
        await set_tenant(session, "default")
        dispatcher = SourceDispatcher()
        n = await dispatcher.execute(
            session,
            source_id="ais_file",
            job_type="batch",
            config={"path": str(path)},
            tenant_id="default",
        )
    print(f"inserted_or_processed={n}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="MarineCadastre AIS CSV batch ingest")
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        if args.dry_run:
            report = validate_csv(args.csv_path)
            print(report)
            sys.exit(0 if report["valid"] >= 0 else 1)
        sys.exit(asyncio.run(run_ingest(args.csv_path, dry_run=False)))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
