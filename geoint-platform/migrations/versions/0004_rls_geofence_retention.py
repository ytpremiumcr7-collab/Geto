"""tenant_id, RLS, geofences, geofence_state, dlq_messages.

Revision ID: 0004_rls_geofence
Revises: 0003_outbox
"""

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision = "0004_rls_geofence"
down_revision = "0003_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- tenant columns ---
    op.add_column(
        "observations",
        sa.Column("tenant_id", sa.String(128), server_default="default", nullable=False),
    )
    op.add_column(
        "entities",
        sa.Column("tenant_id", sa.String(128), server_default="default", nullable=False),
    )
    op.add_column(
        "source_jobs",
        sa.Column("tenant_id", sa.String(128), server_default="default", nullable=False),
    )

    op.create_index("ix_observations_tenant", "observations", ["tenant_id"])
    op.create_index("ix_entities_tenant", "entities", ["tenant_id"])
    op.create_index("ix_source_jobs_tenant", "source_jobs", ["tenant_id"])

    # Unique dedup per tenant
    op.execute(
        "ALTER TABLE observations DROP CONSTRAINT IF EXISTS uq_observations_source_entity_time"
    )
    op.create_unique_constraint(
        "uq_observations_tenant_source_entity_time",
        "observations",
        ["tenant_id", "source_id", "entity_id", "observed_at"],
    )

    # --- geofences ---
    op.create_table(
        "geofences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column(
            "geometry",
            Geometry(geometry_type="MULTIPOLYGON", srid=4326),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("min_altitude", sa.Float()),
        sa.Column("max_altitude", sa.Float()),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "name", name="uq_geofences_tenant_name"),
    )
    op.create_index(
        "ix_geofences_geometry_gist",
        "geofences",
        ["geometry"],
        postgresql_using="gist",
    )
    op.create_index("ix_geofences_tenant_enabled", "geofences", ["tenant_id", "enabled"])

    # --- geofence membership state (enter/exit) ---
    op.create_table(
        "geofence_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("geofence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", sa.String(255), nullable=False),
        sa.Column("inside", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("since", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "geofence_id",
            "entity_id",
            name="uq_geofence_state_tenant_fence_entity",
        ),
    )

    # --- DLQ operable ---
    op.create_table(
        "dlq_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False, server_default="default"),
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("original_subject", sa.String(255), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("delivery_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_dlq_status_created", "dlq_messages", ["status", "created_at"])

    # --- RLS ---
    op.execute("ALTER TABLE observations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE entities ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE geofences ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE geofence_state ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE source_jobs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE dlq_messages ENABLE ROW LEVEL SECURITY")

    # Policies: app sets SET LOCAL app.tenant_id = '...'
    for table in (
        "observations",
        "entities",
        "geofences",
        "geofence_state",
        "source_jobs",
        "dlq_messages",
    ):
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            USING (tenant_id = current_setting('app.tenant_id', true))
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true))
            """
        )
        # Bypass for migrations / superuser roles is default for table owner
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in (
        "dlq_messages",
        "geofence_state",
        "geofences",
        "source_jobs",
        "entities",
        "observations",
    ):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_table("dlq_messages")
    op.drop_table("geofence_state")
    op.drop_table("geofences")

    op.drop_constraint(
        "uq_observations_tenant_source_entity_time",
        "observations",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_observations_source_entity_time",
        "observations",
        ["source_id", "entity_id", "observed_at"],
    )
    op.drop_column("source_jobs", "tenant_id")
    op.drop_column("entities", "tenant_id")
    op.drop_column("observations", "tenant_id")
