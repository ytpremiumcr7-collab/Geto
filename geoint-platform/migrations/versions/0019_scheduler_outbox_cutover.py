"""Cut over scheduler dispatch to the transactional outbox.

Revision ID: 0019
Revises: 0018

Old releases could leave SourceJob rows in queued/running while publication to
JetStream happened outside the database transaction. Deploy quiesces writers
before this migration. Those legacy active states are re-queued with the same
execution_id so the new scheduler can create a durable outbox dispatch.
"""

from __future__ import annotations

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE source_jobs
        SET status = 'retry',
            locked_until = NULL,
            locked_by = NULL,
            next_run_at = NOW(),
            last_error = CASE
                WHEN last_error IS NULL OR last_error = ''
                    THEN 'scheduler transactional-outbox cutover'
                ELSE last_error
            END
        WHERE status IN ('queued', 'running')
        """
    )


def downgrade() -> None:
    # Data-state cutovers are intentionally not reversed. Reintroducing the old
    # non-transactional dispatch semantics would be unsafe.
    pass
