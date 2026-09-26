"""Tenant and system-worker RLS for the transactional outbox.

Revision ID: 0015
Revises: 0014
"""

from __future__ import annotations

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE outbox_messages ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE outbox_messages FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS outbox_messages_tenant_isolation ON outbox_messages")
    op.execute(
        """
        CREATE POLICY outbox_messages_tenant_isolation ON outbox_messages
        USING (tenant_id = current_setting('app.tenant_id', true))
        WITH CHECK (tenant_id = current_setting('app.tenant_id', true))
        """
    )
    op.execute("DROP POLICY IF EXISTS outbox_messages_system_worker ON outbox_messages")
    op.execute(
        """
        CREATE POLICY outbox_messages_system_worker ON outbox_messages
        USING (
            current_setting('app.tenant_id', true) = '__system__'
            AND current_setting('app.worker_mode', true) = '1'
        )
        WITH CHECK (
            current_setting('app.tenant_id', true) = '__system__'
            AND current_setting('app.worker_mode', true) = '1'
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS outbox_messages_system_worker ON outbox_messages")
    op.execute("DROP POLICY IF EXISTS outbox_messages_tenant_isolation ON outbox_messages")
    op.execute("ALTER TABLE outbox_messages DISABLE ROW LEVEL SECURITY")
