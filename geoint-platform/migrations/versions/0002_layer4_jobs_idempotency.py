"""Source jobs + idempotency table for JetStream consumers.

Revision ID: 0002_layer4
Revises: 0001_initial
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_layer4"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("job_type", sa.String(64), nullable=False, server_default="poll"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("interval_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("locked_by", sa.String(128)),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column(
            "config",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("source_id", "name", name="uq_source_jobs_source_name"),
    )
    op.create_index(
        "ix_source_jobs_due",
        "source_jobs",
        ["enabled", "next_run_at", "status"],
    )
    op.create_index("ix_source_jobs_source_id", "source_jobs", ["source_id"])

    op.create_table(
        "processed_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("message_id", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("source_id", sa.String(128)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("message_id", name="uq_processed_messages_message_id"),
    )
    op.create_index(
        "ix_processed_messages_created",
        "processed_messages",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_table("processed_messages")
    op.drop_table("source_jobs")
