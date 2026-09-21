"""Tenant-scoped idempotency and durable alert delivery leases.

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def _set_system_worker_context() -> None:
    # 0013 FORCEs RLS on both source_jobs and processed_messages. Alembic data
    # backfills must therefore establish the same dual system-worker claim used
    # by runtime workers before reading or mutating those tables.
    op.execute(
        "SELECT set_config('app.tenant_id', '__system__', true), "
        "set_config('app.worker_mode', '1', true)"
    )


def upgrade() -> None:
    _set_system_worker_context()

    # processed_messages: preserve tenant attribution where Nats-Msg-Id == source_job UUID.
    op.add_column(
        "processed_messages",
        sa.Column("tenant_id", sa.String(128), nullable=True),
    )
    op.execute(
        """
        UPDATE processed_messages AS pm
        SET tenant_id = sj.tenant_id
        FROM source_jobs AS sj
        WHERE pm.tenant_id IS NULL
          AND pm.message_id = sj.id::text
        """
    )
    # Historical messages that cannot be attributed must never collide with a real tenant.
    op.execute(
        """
        UPDATE processed_messages
        SET tenant_id = '__legacy__'
        WHERE tenant_id IS NULL
        """
    )
    op.alter_column("processed_messages", "tenant_id", nullable=False)
    op.drop_constraint(
        "uq_processed_messages_message_id",
        "processed_messages",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_processed_messages_tenant_message_id",
        "processed_messages",
        ["tenant_id", "message_id"],
    )
    op.create_index(
        "ix_processed_messages_tenant",
        "processed_messages",
        ["tenant_id"],
    )
    op.execute(
        """
        CREATE POLICY processed_messages_tenant_isolation ON processed_messages
        USING (tenant_id = current_setting('app.tenant_id', true))
        WITH CHECK (tenant_id = current_setting('app.tenant_id', true))
        """
    )

    # Alert delivery claims survive process crashes and can be reclaimed after lease expiry.
    op.add_column(
        "alert_deliveries",
        sa.Column("claimed_by", sa.String(128), nullable=True),
    )
    op.add_column(
        "alert_deliveries",
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_alert_deliveries_lease",
        "alert_deliveries",
        ["status", "lease_until"],
    )


def downgrade() -> None:
    _set_system_worker_context()

    op.drop_index("ix_alert_deliveries_lease", table_name="alert_deliveries")
    op.drop_column("alert_deliveries", "lease_until")
    op.drop_column("alert_deliveries", "claimed_by")

    op.execute(
        "DROP POLICY IF EXISTS processed_messages_tenant_isolation ON processed_messages"
    )
    op.drop_index("ix_processed_messages_tenant", table_name="processed_messages")
    op.drop_constraint(
        "uq_processed_messages_tenant_message_id",
        "processed_messages",
        type_="unique",
    )
    # Downgrade cannot represent duplicate message_ids across tenants. Keep one row.
    op.execute(
        """
        DELETE FROM processed_messages a
        USING processed_messages b
        WHERE a.message_id = b.message_id
          AND a.id::text > b.id::text
        """
    )
    op.create_unique_constraint(
        "uq_processed_messages_message_id",
        "processed_messages",
        ["message_id"],
    )
    op.drop_column("processed_messages", "tenant_id")
