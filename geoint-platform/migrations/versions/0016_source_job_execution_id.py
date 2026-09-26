"""Persist active execution identity for recurring source jobs.

Revision ID: 0016
Revises: 0015
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_jobs",
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    # Existing queued/retry/running rows may already have a JetStream message
    # whose legacy Nats-Msg-Id is the permanent job id. Preserve those in-flight
    # executions across the migration so the worker can finish them safely.
    op.execute(
        """
        UPDATE source_jobs
        SET execution_id = id
        WHERE execution_id IS NULL
          AND status IN ('queued', 'retry', 'running')
        """
    )
    op.create_index(
        "ix_source_jobs_execution_id",
        "source_jobs",
        ["tenant_id", "execution_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_source_jobs_execution_id", table_name="source_jobs")
    op.drop_column("source_jobs", "execution_id")
