"""OSM features table for ETL + vector tiles.

Revision ID: 0005_osm
Revises: 0004_rls_geofence
"""

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision = "0005_osm"
down_revision = "0004_rls_geofence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "osm_features",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False, server_default="default"),
        sa.Column("osm_id", sa.String(64), nullable=False),
        sa.Column("feature_class", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255)),
        sa.Column(
            "geometry",
            Geometry(geometry_type="GEOMETRY", srid=4326),
            nullable=False,
        ),
        sa.Column(
            "tags",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("source", sa.String(64), server_default="overpass"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("tenant_id", "osm_id", name="uq_osm_features_tenant_osm_id"),
    )
    op.create_index(
        "ix_osm_features_geometry_gist",
        "osm_features",
        ["geometry"],
        postgresql_using="gist",
    )
    op.create_index(
        "ix_osm_features_tenant_class",
        "osm_features",
        ["tenant_id", "feature_class"],
    )


def downgrade() -> None:
    op.drop_table("osm_features")
