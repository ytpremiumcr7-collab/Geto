"""System worker claim + composite tenant FKs.

1. System RLS requires app.tenant_id=__system__ AND app.worker_mode=1
   (API cannot gain global access by only setting tenant_id).
2. Composite FKs: saved_layers → workspaces, geofence_alert_rules → geofences
   on (tenant_id, id).

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

_SYSTEM_TABLES = (
    "dem_assets",
    "source_jobs",
    "observations",
    "entities",
    "geofences",
    "geofence_state",
    "dlq_messages",
    "source_runs",
    "workspaces",
    "saved_layers",
    "alert_channels",
    "geofence_alert_rules",
    "geofence_alerts",
    "alert_deliveries",
    "processed_messages",
)


def _system_policy_sql(table: str) -> str:
    # Dual claim: magic tenant string alone is not enough
    return f"""
    CREATE POLICY {table}_system_worker ON {table}
    USING (
        current_setting('app.tenant_id', true) = '__system__'
        AND current_setting('app.worker_mode', true) = '1'
    )
    WITH CHECK (
        current_setting('app.tenant_id', true) = '__system__'
        AND current_setting('app.worker_mode', true) = '1'
    )
    """


def upgrade() -> None:
    for table in _SYSTEM_TABLES:
        op.execute(f"ALTER TABLE IF EXISTS {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE IF EXISTS {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {table}_system_worker ON {table}")
        op.execute(_system_policy_sql(table))

    # Composite uniqueness so FKs can reference (tenant_id, id)
    op.execute(
        """
        DO $$ BEGIN
          ALTER TABLE workspaces
            ADD CONSTRAINT uq_workspaces_tenant_id UNIQUE (tenant_id, id);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
          ALTER TABLE geofences
            ADD CONSTRAINT uq_geofences_tenant_id UNIQUE (tenant_id, id);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    # Drop weak FK saved_layers.workspace_id → workspaces.id only
    op.execute(
        """
        DO $$ BEGIN
          ALTER TABLE saved_layers DROP CONSTRAINT IF EXISTS saved_layers_workspace_id_fkey;
        EXCEPTION WHEN undefined_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
          ALTER TABLE saved_layers
            ADD CONSTRAINT fk_saved_layers_workspace_tenant
            FOREIGN KEY (tenant_id, workspace_id)
            REFERENCES workspaces (tenant_id, id)
            ON DELETE CASCADE;
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    # geofence_alert_rules → geofences (tenant, id)
    op.execute(
        """
        DO $$ BEGIN
          ALTER TABLE geofence_alert_rules
            ADD CONSTRAINT fk_alert_rules_geofence_tenant
            FOREIGN KEY (tenant_id, geofence_id)
            REFERENCES geofences (tenant_id, id)
            ON DELETE CASCADE;
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE geofence_alert_rules DROP CONSTRAINT IF EXISTS fk_alert_rules_geofence_tenant")
    op.execute("ALTER TABLE saved_layers DROP CONSTRAINT IF EXISTS fk_saved_layers_workspace_tenant")
    op.execute("ALTER TABLE geofences DROP CONSTRAINT IF EXISTS uq_geofences_tenant_id")
    op.execute("ALTER TABLE workspaces DROP CONSTRAINT IF EXISTS uq_workspaces_tenant_id")
    for table in _SYSTEM_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_system_worker ON {table}")
        # restore legacy single-claim policy
        op.execute(
            f"""
            CREATE POLICY {table}_system_worker ON {table}
            USING (current_setting('app.tenant_id', true) = '__system__')
            WITH CHECK (current_setting('app.tenant_id', true) = '__system__')
            """
        )
