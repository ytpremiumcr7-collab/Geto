"""RLS on osm_features.

Revision ID: 0006_osm_rls
Revises: 0005_osm
"""

from alembic import op

revision = "0006_osm_rls"
down_revision = "0005_osm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE osm_features ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE osm_features FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY osm_features_tenant_isolation ON osm_features
        USING (tenant_id = current_setting('app.tenant_id', true))
        WITH CHECK (tenant_id = current_setting('app.tenant_id', true))
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS osm_features_tenant_isolation ON osm_features")
    op.execute("ALTER TABLE osm_features DISABLE ROW LEVEL SECURITY")
