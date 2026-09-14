"""FORCE RLS + system worker policies for dem_assets and source_jobs.

Revision ID: 0009_force_rls_system
Revises: 0008_dem_assets
"""

from __future__ import annotations

from alembic import op

revision = "0009_force_rls_system"
down_revision = "0008_dem_assets"
branch_labels = None
depends_on = None

# Tables that must enforce RLS even for table owner
_TABLES = (
    "dem_assets",
    "source_jobs",
    "observations",
    "entities",
    "geofences",
    "geofence_state",
    "dlq_messages",
)


def upgrade() -> None:
    for table in _TABLES:
        # FORCE so table owner / superuser habits cannot silently bypass
        op.execute(f"ALTER TABLE IF EXISTS {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE IF EXISTS {table} FORCE ROW LEVEL SECURITY")
        # Allow background workers that set app.tenant_id = '__system__'
        op.execute(f"DROP POLICY IF EXISTS {table}_system_worker ON {table}")
        op.execute(
            f"""
            CREATE POLICY {table}_system_worker ON {table}
            USING (current_setting('app.tenant_id', true) = '__system__')
            WITH CHECK (current_setting('app.tenant_id', true) = '__system__')
            """
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_system_worker ON {table}")
        op.execute(f"ALTER TABLE IF EXISTS {table} NO FORCE ROW LEVEL SECURITY")
