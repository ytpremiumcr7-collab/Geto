"""Cut vendor-specific dropzone identity over to S3.

Revision ID: 0021
Revises: 0020

Object keys and raw provenance are intentionally not rewritten: they are
historical evidence. Operational identities and pending work move to the new
vendor-neutral source id.
"""

from __future__ import annotations

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def _system_context() -> None:
    op.execute(
        "SELECT set_config('app.tenant_id', '__system__', true), "
        "set_config('app.worker_mode', '1', true)"
    )


def upgrade() -> None:
    _system_context()

    op.execute(
        """
        UPDATE source_jobs
        SET source_id = 's3_dropzone',
            name = CASE
                WHEN name = 'minio-dropzone' THEN 's3-dropzone'
                ELSE name
            END
        WHERE source_id = 'minio_dropzone'
        """
    )
    op.execute(
        "UPDATE observations SET source_id = 's3_dropzone' "
        "WHERE source_id = 'minio_dropzone'"
    )
    op.execute(
        "UPDATE source_runs SET source_id = 's3_dropzone' "
        "WHERE source_id = 'minio_dropzone'"
    )
    op.execute(
        "UPDATE event_records SET source_id = 's3_dropzone' "
        "WHERE source_id = 'minio_dropzone'"
    )
    op.execute(
        "UPDATE geofence_alerts SET source_id = 's3_dropzone' "
        "WHERE source_id = 'minio_dropzone'"
    )
    op.execute(
        """
        UPDATE dlq_messages
        SET source_id = CASE
                WHEN source_id = 'minio_dropzone' THEN 's3_dropzone'
                ELSE source_id
            END,
            payload = CASE
                WHEN payload ->> 'source_id' = 'minio_dropzone'
                    THEN jsonb_set(payload, '{source_id}', '"s3_dropzone"'::jsonb)
                ELSE payload
            END,
            original_subject = replace(
                original_subject,
                'geoint.jobs.minio_dropzone',
                'geoint.jobs.s3_dropzone'
            )
        WHERE source_id = 'minio_dropzone'
           OR payload ->> 'source_id' = 'minio_dropzone'
           OR original_subject LIKE '%minio_dropzone%'
        """
    )
    op.execute(
        """
        UPDATE outbox_messages
        SET payload = CASE
                WHEN payload ->> 'source_id' = 'minio_dropzone'
                    THEN jsonb_set(payload, '{source_id}', '"s3_dropzone"'::jsonb)
                ELSE payload
            END,
            subject = replace(subject, 'minio_dropzone', 's3_dropzone')
        WHERE published_at IS NULL
          AND (
              payload ->> 'source_id' = 'minio_dropzone'
              OR subject LIKE '%minio_dropzone%'
          )
        """
    )


def downgrade() -> None:
    raise RuntimeError("0021 S3 storage cutover is intentionally irreversible")
