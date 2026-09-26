"""Durable tenant/source-scoped product event store.

Revision ID: 0018
Revises: 0017
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("entity_id", sa.String(255), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_event_records_tenant_time",
        "event_records",
        ["tenant_id", "occurred_at"],
    )
    op.create_index(
        "ix_event_records_tenant_source_time",
        "event_records",
        ["tenant_id", "source_id", "occurred_at"],
    )

    op.execute("ALTER TABLE event_records ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE event_records FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY event_records_tenant_isolation ON event_records
        USING (tenant_id = current_setting('app.tenant_id', true))
        WITH CHECK (tenant_id = current_setting('app.tenant_id', true))
        """
    )
    op.execute(
        """
        CREATE POLICY event_records_system_worker ON event_records
        USING (
            current_setting('app.tenant_id', true) = '__system__'
            AND current_setting('app.worker_mode', true) = '1'
        )
        WITH CHECK (
            current_setting('app.tenant_id', true) = '__system__'
            AND current_setting('app.worker_mode', true) = '1'
        )
        """
    )


def downgrade() -> None:
    op.drop_table("event_records")
