"""Initial GEOINT schema."""

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():

    op.execute(
        "CREATE EXTENSION IF NOT EXISTS postgis"
    )

    op.create_table(
        "entities",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "entity_id",
            sa.String(255),
            nullable=False,
        ),
        sa.Column(
            "entity_type",
            sa.String(64),
            nullable=False,
        ),
        sa.Column(
            "first_seen",
            sa.DateTime(timezone=True),
        ),
        sa.Column(
            "last_seen",
            sa.DateTime(timezone=True),
        ),
        sa.Column(
            "properties",
            sa.JSON(),
        ),
        sa.UniqueConstraint(
            "entity_id",
            name="uq_entities_entity_id",
        ),
    )

    op.create_index(
        "ix_entities_entity_type",
        "entities",
        ["entity_type"],
    )

    op.create_table(
        "observations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "entity_id",
            sa.String(255),
            nullable=False,
        ),
        sa.Column(
            "entity_type",
            sa.String(64),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            sa.String(128),
            nullable=False,
        ),
        sa.Column(
            "source_record_id",
            sa.String(255),
        ),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "geometry",
            Geometry(
                geometry_type="POINTZ",
                srid=4326,
            ),
        ),
        sa.Column(
            "altitude_m",
            sa.Float,
        ),
        sa.Column(
            "speed_mps",
            sa.Float,
        ),
        sa.Column(
            "heading_deg",
            sa.Float,
        ),
        sa.Column(
            "accuracy_m",
            sa.Float,
        ),
        sa.Column(
            "confidence",
            sa.Float,
        ),
        sa.Column(
            "attributes",
            sa.JSON(),
        ),
        sa.Column(
            "provenance",
            sa.JSON(),
        ),
        sa.Column(
            "raw_payload_uri",
            sa.Text(),
        ),
        sa.UniqueConstraint(
            "source_id",
            "entity_id",
            "observed_at",
            name="uq_observations_source_entity_time",
        ),
    )

    op.create_index(
        "ix_observations_entity_time",
        "observations",
        ["entity_id", "observed_at"],
    )

    op.create_index(
        "ix_observations_source_time",
        "observations",
        ["source_id", "observed_at"],
    )

    op.create_table(
        "source_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "source_id",
            sa.String(128),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
        ),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
        ),
        sa.Column(
            "records_seen",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "records_normalized",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "error",
            sa.Text(),
        ),
    )

    op.create_index(
        "ix_source_runs_source_id",
        "source_runs",
        ["source_id"],
    )


def downgrade():

    op.drop_table("source_runs")
    op.drop_table("observations")
    op.drop_table("entities")

