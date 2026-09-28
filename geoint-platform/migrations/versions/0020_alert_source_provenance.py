"""Make alert source provenance explicit and queryable.

Revision ID: 0020
Revises: 0019
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "geofence_alerts",
        sa.Column("source_id", sa.String(128), nullable=True),
    )
    op.execute(
        """
        UPDATE geofence_alerts
        SET source_id = COALESCE(
            NULLIF(payload ->> 'source_id', ''),
            'legacy_unknown'
        )
        WHERE source_id IS NULL
        """
    )
    op.alter_column("geofence_alerts", "source_id", nullable=False)
    op.create_index(
        "ix_geofence_alerts_tenant_source_time",
        "geofence_alerts",
        ["tenant_id", "source_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_geofence_alerts_tenant_source_time", table_name="geofence_alerts")
    op.drop_column("geofence_alerts", "source_id")
