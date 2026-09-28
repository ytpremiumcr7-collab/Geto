-- Reconcile durable PostgreSQL state after Redis/NATS are reset during DR.
-- Run only with application writers stopped.
BEGIN;

SELECT set_config('app.tenant_id', '__system__', false);
SELECT set_config('app.worker_mode', '1', false);

UPDATE source_jobs
SET status = 'retry',
    locked_until = NULL,
    locked_by = NULL,
    next_run_at = NOW(),
    last_error = CASE
        WHEN last_error IS NULL OR last_error = ''
            THEN 'requeued after disaster recovery transport reset'
        ELSE last_error
    END
WHERE status IN ('queued', 'running');

UPDATE processed_messages
SET status = 'failed',
    lease_until = NULL,
    worker_id = NULL,
    updated_at = NOW()
WHERE status = 'processing';

UPDATE outbox_messages
SET claimed_by = NULL,
    lease_until = NULL,
    next_attempt_at = COALESCE(next_attempt_at, NOW())
WHERE published_at IS NULL
  AND dead_lettered_at IS NULL;

UPDATE alert_deliveries
SET status = 'pending',
    claimed_by = NULL,
    lease_until = NULL,
    next_attempt_at = NOW(),
    last_error = CASE
        WHEN last_error IS NULL OR last_error = ''
            THEN 'requeued after disaster recovery transport reset'
        ELSE last_error
    END,
    updated_at = NOW()
WHERE status = 'sending'
  AND delivered_at IS NULL;

COMMIT;
