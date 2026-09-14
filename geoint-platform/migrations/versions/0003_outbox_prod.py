"""Outbox messages for transactional publishing.

Revision ID: 0003_outbox
Revises: 0002_layer4
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_outbox"
down_revision = "0002_layer4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outbox_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False, server_default="default"),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_outbox_pending",
        "outbox_messages",
        ["published_at", "created_at"],
    )
    op.create_index("ix_outbox_subject", "outbox_messages", ["subject"])


def downgrade() -> None:
    op.drop_table("outbox_messages")
