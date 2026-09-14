"""Subjects JetStream estables."""

JOBS_PREFIX = "geoint.jobs"
OBSERVATIONS_PREFIX = "geoint.observation"
EVENTS_PREFIX = "geoint.event"
DLQ_PREFIX = "geoint.dlq"


def job_subject(source_id: str) -> str:
    return f"{JOBS_PREFIX}.{source_id}"


def dlq_subject(source_id: str | None = None) -> str:
    if source_id:
        return f"{DLQ_PREFIX}.{source_id}"
    return f"{DLQ_PREFIX}.>"
