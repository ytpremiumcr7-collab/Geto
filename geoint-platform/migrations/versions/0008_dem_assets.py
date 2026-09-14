"""dem_assets catalog for topography engine.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008_dem_assets"
down_revision = "0007_tenant_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dem_assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False, server_default="default"),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("product_name", sa.String(256), nullable=False),
        sa.Column("product_type", sa.String(32), nullable=False, server_default="dtm"),
        sa.Column("resolution_m", sa.Float, nullable=False),
        sa.Column("crs", sa.String(64), nullable=False, server_default="EPSG:4326"),
        sa.Column("vertical_datum", sa.String(64), nullable=True),
        sa.Column("bbox_west", sa.Float, nullable=False),
        sa.Column("bbox_south", sa.Float, nullable=False),
        sa.Column("bbox_east", sa.Float, nullable=False),
        sa.Column("bbox_north", sa.Float, nullable=False),
        sa.Column("file_uri", sa.Text, nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=True),
        sa.Column("source_version", sa.String(128), nullable=True),
        sa.Column("acquisition_date", sa.String(32), nullable=True),
        sa.Column("byte_size", sa.BigInteger, nullable=True),
        sa.Column("extra", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_dem_assets_tenant", "dem_assets", ["tenant_id"])
    op.create_index(
        "ix_dem_assets_bbox",
        "dem_assets",
        ["bbox_west", "bbox_south", "bbox_east", "bbox_north"],
    )
    op.create_index("ix_dem_assets_provider", "dem_assets", ["provider"])

    # RLS
    op.execute("ALTER TABLE dem_assets ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY dem_assets_tenant_isolation ON dem_assets
        USING (tenant_id = current_setting('app.tenant_id', true))
        WITH CHECK (tenant_id = current_setting('app.tenant_id', true))
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS dem_assets_tenant_isolation ON dem_assets")
    op.drop_table("dem_assets")
