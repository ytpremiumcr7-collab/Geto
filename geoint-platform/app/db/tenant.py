"""Aislamiento multi-tenant: SET LOCAL app.tenant_id para RLS."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def set_tenant(session: AsyncSession, tenant_id: str) -> None:
    """Debe llamarse al inicio de cada unidad de trabajo autenticada."""
    # true = local al transaction/session (no queda en la conexión de forma permanente)
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"),
        {"tid": tenant_id},
    )


async def clear_tenant(session: AsyncSession) -> None:
    await session.execute(text("SELECT set_config('app.tenant_id', '', true)"))


# --- Prefer these deps in new routes (reduces forgotten set_tenant) ---

async def get_tenant_session(session: AsyncSession, tenant_id: str) -> AsyncSession:
    """Bind RLS tenant on an existing session."""
    await set_tenant(session, tenant_id)
    return session
