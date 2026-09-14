"""Alert delivery attempts for notifier worker.

Revision ID: 0011_alert_deliveries
Revises: 0010_workspaces_alerts
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_alert_deliveries"
down_revision = "0010_workspaces_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False, index=True),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        # pending | sending | delivered | failed | skipped
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("response_meta", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(
        "ix_alert_deliveries_claim",
        "alert_deliveries",
        ["status", "next_attempt_at"],
    )
    op.execute("ALTER TABLE alert_deliveries ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE alert_deliveries FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY alert_deliveries_tenant_isolation ON alert_deliveries
        USING (tenant_id = current_setting('app.tenant_id', true))
        WITH CHECK (tenant_id = current_setting('app.tenant_id', true))
        """
    )
    op.execute(
        """
        CREATE POLICY alert_deliveries_system_worker ON alert_deliveries
        USING (current_setting('app.tenant_id', true) = '__system__')
        WITH CHECK (current_setting('app.tenant_id', true) = '__system__')
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS alert_deliveries CASCADE")
