"""Multi-tenant RLS binding.

Normal requests: set_tenant(session, principal.tenant_id)
Workers:         set_system_worker(session)  — requires GEOINT_SYSTEM_WORKER=1

RLS system policies require BOTH:
  app.tenant_id = '__system__'
  app.worker_mode = '1'
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal

SYSTEM_TENANT = "__system__"


class SystemTenantError(RuntimeError):
    pass


async def set_tenant(session: AsyncSession, tenant_id: str) -> None:
    """Bind RLS to a real tenant. Refuses the system sentinel."""
    if tenant_id == SYSTEM_TENANT:
        raise SystemTenantError(
            "Refusing to set tenant_id=__system__ via set_tenant(); "
            "workers must call set_system_worker()"
        )
    if not tenant_id or not str(tenant_id).strip():
        raise ValueError("tenant_id required")
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"),
        {"tid": str(tenant_id).strip()},
    )
    # Clear any leftover worker mode on this transaction
    await session.execute(text("SELECT set_config('app.worker_mode', '', true)"))


async def set_system_worker(session: AsyncSession) -> None:
    """Enable cross-tenant worker access (claim jobs, deliveries, etc.).

    Requires process env GEOINT_SYSTEM_WORKER=1 so a compromised API handler
    cannot enable system mode by only calling set_config.
    """
    if os.environ.get("GEOINT_SYSTEM_WORKER", "").strip() != "1":
        raise SystemTenantError(
            "GEOINT_SYSTEM_WORKER=1 is required to enable system worker RLS claim"
        )
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"),
        {"tid": SYSTEM_TENANT},
    )
    await session.execute(text("SELECT set_config('app.worker_mode', '1', true)"))


async def clear_tenant(session: AsyncSession) -> None:
    await session.execute(text("SELECT set_config('app.tenant_id', '', true)"))
    await session.execute(text("SELECT set_config('app.worker_mode', '', true)"))


async def get_tenant_session(session: AsyncSession, tenant_id: str) -> AsyncSession:
    await set_tenant(session, tenant_id)
    return session


@asynccontextmanager
async def tenant_session(tenant_id: str) -> AsyncIterator[AsyncSession]:
    """Open a session whose current transaction is tenant-bound for RLS."""
    async with SessionLocal() as session:
        await set_tenant(session, tenant_id)
        yield session


@asynccontextmanager
async def system_worker_session() -> AsyncIterator[AsyncSession]:
    """Open a cross-tenant worker session with the dual RLS claim applied."""
    async with SessionLocal() as session:
        await set_system_worker(session)
        yield session
