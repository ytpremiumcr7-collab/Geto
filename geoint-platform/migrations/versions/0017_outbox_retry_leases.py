"""Lease, retry schedule, and dead-letter state for transactional outbox.

Revision ID: 0017
Revises: 0016
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "outbox_messages",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "outbox_messages",
        sa.Column("claimed_by", sa.String(128), nullable=True),
    )
    op.add_column(
        "outbox_messages",
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "outbox_messages",
        sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_outbox_dispatchable",
        "outbox_messages",
        ["published_at", "dead_lettered_at", "next_attempt_at", "lease_until", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_dispatchable", table_name="outbox_messages")
    op.drop_column("outbox_messages", "dead_lettered_at")
    op.drop_column("outbox_messages", "lease_until")
    op.drop_column("outbox_messages", "claimed_by")
    op.drop_column("outbox_messages", "next_attempt_at")
