"""Idempotency claim state, source_runs RLS, source_jobs unique per tenant.

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- processed_messages: claim / lease ---
    op.add_column(
        "processed_messages",
        sa.Column("status", sa.String(32), nullable=False, server_default="completed"),
    )
    op.add_column(
        "processed_messages",
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "processed_messages",
        sa.Column("worker_id", sa.String(128), nullable=True),
    )
    op.add_column(
        "processed_messages",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_processed_messages_status", "processed_messages", ["status"])

    # --- source_runs RLS (table already has tenant_id since 0007) ---
    op.execute("ALTER TABLE IF EXISTS source_runs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE IF EXISTS source_runs FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS source_runs_tenant_isolation ON source_runs")
    op.execute(
        """
        CREATE POLICY source_runs_tenant_isolation ON source_runs
        USING (tenant_id = current_setting('app.tenant_id', true))
        WITH CHECK (tenant_id = current_setting('app.tenant_id', true))
        """
    )
    op.execute("DROP POLICY IF EXISTS source_runs_system_worker ON source_runs")
    op.execute(
        """
        CREATE POLICY source_runs_system_worker ON source_runs
        USING (current_setting('app.tenant_id', true) = '__system__')
        WITH CHECK (current_setting('app.tenant_id', true) = '__system__')
        """
    )

    # --- source_jobs unique (tenant_id, source_id, name) ---
    op.drop_constraint("uq_source_jobs_source_name", "source_jobs", type_="unique")
    op.create_unique_constraint(
        "uq_source_jobs_tenant_source_name",
        "source_jobs",
        ["tenant_id", "source_id", "name"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_source_jobs_tenant_source_name", "source_jobs", type_="unique")
    op.create_unique_constraint(
        "uq_source_jobs_source_name", "source_jobs", ["source_id", "name"]
    )
    op.execute("DROP POLICY IF EXISTS source_runs_system_worker ON source_runs")
    op.execute("DROP POLICY IF EXISTS source_runs_tenant_isolation ON source_runs")
    op.execute("ALTER TABLE IF EXISTS source_runs NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE IF EXISTS source_runs DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_processed_messages_status", table_name="processed_messages")
    op.drop_column("processed_messages", "updated_at")
    op.drop_column("processed_messages", "worker_id")
    op.drop_column("processed_messages", "lease_until")
    op.drop_column("processed_messages", "status")
