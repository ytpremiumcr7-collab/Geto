"""TimescaleDB opcional sobre Postgres.

La imagen postgis estándar no incluye Timescale. Si usas
`timescale/timescaledb-ha` o postgis+timescale:

  CREATE EXTENSION IF NOT EXISTS timescaledb;
  SELECT create_hypertable('observations', 'observed_at', if_not_exists => TRUE);

Este módulo solo expone helpers; no fuerza Timescale en el compose base.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def try_enable_hypertable(session: AsyncSession) -> bool:
    try:
        await session.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
        await session.execute(
            text(
                "SELECT create_hypertable('observations', 'observed_at', "
                "if_not_exists => TRUE, migrate_data => TRUE)"
            )
        )
        await session.commit()
        return True
    except Exception:
        await session.rollback()
        return False
