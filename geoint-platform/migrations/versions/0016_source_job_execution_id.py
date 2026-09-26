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
    op.create_index(
        "ix_source_jobs_execution_id",
        "source_jobs",
        ["tenant_id", "execution_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_source_jobs_execution_id", table_name="source_jobs")
    op.drop_column("source_jobs", "execution_id")
