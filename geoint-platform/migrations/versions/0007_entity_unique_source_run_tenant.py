"""Entity unique per tenant + source_runs.tenant_id

Revision ID: 0007_tenant_hardening
Revises: 0006_osm_rls
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_tenant_hardening"
down_revision = "0006_osm_rls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE entities DROP CONSTRAINT IF EXISTS uq_entities_entity_id")
    op.create_unique_constraint(
        "uq_entities_tenant_entity_id",
        "entities",
        ["tenant_id", "entity_id"],
    )
    op.add_column(
        "source_runs",
        sa.Column("tenant_id", sa.String(128), server_default="default", nullable=False),
    )
    op.create_index("ix_source_runs_tenant", "source_runs", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_source_runs_tenant", table_name="source_runs")
    op.drop_column("source_runs", "tenant_id")
    op.drop_constraint("uq_entities_tenant_entity_id", "entities", type_="unique")
    op.create_unique_constraint("uq_entities_entity_id", "entities", ["entity_id"])
