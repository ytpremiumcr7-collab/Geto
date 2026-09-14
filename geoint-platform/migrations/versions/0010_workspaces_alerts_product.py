"""Workspaces, saved layers, geofence alerts product tables + RLS.

Revision ID: 0010_workspaces_alerts
Revises: 0009_force_rls_system
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_workspaces_alerts"
down_revision = "0009_force_rls_system"
branch_labels = None
depends_on = None


def _rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
    op.execute(
        f"""
        CREATE POLICY {table}_tenant_isolation ON {table}
        USING (tenant_id = current_setting('app.tenant_id', true))
        WITH CHECK (tenant_id = current_setting('app.tenant_id', true))
        """
    )
    op.execute(f"DROP POLICY IF EXISTS {table}_system_worker ON {table}")
    op.execute(
        f"""
        CREATE POLICY {table}_system_worker ON {table}
        USING (current_setting('app.tenant_id', true) = '__system__')
        WITH CHECK (current_setting('app.tenant_id', true) = '__system__')
        """
    )


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("owner_user_id", sa.String(255), nullable=True),
        sa.Column("aoi_geojson", postgresql.JSONB(), nullable=True),
        sa.Column("map_center_lon", sa.Float(), nullable=True),
        sa.Column("map_center_lat", sa.Float(), nullable=True),
        sa.Column("map_zoom", sa.Float(), nullable=True),
        sa.Column("settings", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_workspaces_tenant_name"),
    )

    op.create_table(
        "saved_layers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False, index=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("layer_type", sa.String(64), nullable=False),  # source|observations|geofence|dem|wms|geojson
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("visible", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("style", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_saved_layers_workspace", "saved_layers", ["workspace_id"])

    op.create_table(
        "alert_channels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("channel_type", sa.String(32), nullable=False),  # webhook|email|websocket|log
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_alert_channels_tenant_name"),
    )

    op.create_table(
        "geofence_alert_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False, index=True),
        sa.Column("geofence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("on_enter", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("on_exit", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("channel_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("entity_type_filter", postgresql.JSONB(), nullable=True),  # list of types or null=all
        sa.Column("severity", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("silence_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_geofence_alert_rules_fence", "geofence_alert_rules", ["geofence_id"])

    op.create_table(
        "geofence_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False, index=True),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("geofence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),  # enter|exit
        sa.Column("severity", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),  # open|acked|resolved|silenced
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acked_by", sa.String(255), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_geofence_alerts_status", "geofence_alerts", ["tenant_id", "status"])
    op.create_index("ix_geofence_alerts_occurred", "geofence_alerts", ["occurred_at"])

    for t in (
        "workspaces",
        "saved_layers",
        "alert_channels",
        "geofence_alert_rules",
        "geofence_alerts",
    ):
        _rls(t)


def downgrade() -> None:
    for t in (
        "geofence_alerts",
        "geofence_alert_rules",
        "alert_channels",
        "saved_layers",
        "workspaces",
    ):
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
