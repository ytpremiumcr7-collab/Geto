"""Admin: source job status + enable/disable."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_roles
from app.auth.models import Principal
from app.db.session import get_db
from app.db.tenant import set_tenant
from app.jobs.models import SourceJob

router = APIRouter(prefix="/api/v1/admin/jobs", tags=["admin-jobs"])


@router.get("")
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_roles("admin")),
):
    await set_tenant(db, principal.tenant_id)
    result = await db.execute(
        select(SourceJob)
        .where(SourceJob.tenant_id == principal.tenant_id)
        .order_by(SourceJob.source_id, SourceJob.name)
    )
    jobs = []
    for j in result.scalars().all():
        jobs.append(
            {
                "id": str(j.id),
                "name": j.name,
                "source_id": j.source_id,
                "job_type": j.job_type,
                "status": j.status,
                "enabled": j.enabled,
                "interval_seconds": j.interval_seconds,
                "next_run_at": j.next_run_at.isoformat() if j.next_run_at else None,
                "last_run_at": j.last_run_at.isoformat() if j.last_run_at else None,
                "last_success_at": j.last_success_at.isoformat() if j.last_success_at else None,
                "last_error": j.last_error,
                "attempts": j.attempts,
            }
        )
    return {"jobs": jobs, "tenant_id": principal.tenant_id}


class JobPatch(BaseModel):
    enabled: bool | None = None
    interval_seconds: int | None = None


@router.patch("/{job_id}")
async def patch_job(
    job_id: UUID,
    body: JobPatch,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_roles("admin")),
):
    await set_tenant(db, principal.tenant_id)
    job = await db.get(SourceJob, job_id)
    if not job or job.tenant_id != principal.tenant_id:
        raise HTTPException(status_code=404, detail="Job not found")
    if body.enabled is not None:
        job.enabled = body.enabled
    if body.interval_seconds is not None:
        if body.interval_seconds < 1:
            raise HTTPException(status_code=400, detail="interval_seconds must be >= 1")
        job.interval_seconds = body.interval_seconds
    await db.commit()
    return {"id": str(job.id), "enabled": job.enabled, "interval_seconds": job.interval_seconds}
