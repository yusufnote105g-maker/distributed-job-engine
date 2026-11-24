"""Prometheus metrics.

Counters are incremented by the engine as work happens. Gauges that depend on
database state (queue depth, workers alive) are refreshed when the scrape
endpoint is called, because they are cheap to compute and always current.

The module is import-safe: it only defines collectors.
"""

from prometheus_client import Counter, Gauge, Histogram

JOBS_SUBMITTED = Counter(
    "jobs_submitted_total",
    "Job submissions accepted by the API (idempotent replays included)",
    ["priority"],
)

JOBS_COMPLETED = Counter(
    "jobs_completed_total", "Jobs that reached the completed state"
)

JOBS_FAILED = Counter(
    "jobs_failed_total", "Jobs that reached the failed state"
)

JOBS_DEAD_LETTER = Counter(
    "jobs_dead_letter_total", "Jobs that exhausted their retries"
)

JOBS_CANCELLED = Counter(
    "jobs_cancelled_total", "Jobs that were cancelled"
)

JOB_EXECUTION_SECONDS = Histogram(
    "job_execution_seconds",
    "Time spent executing a job payload",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300),
)

JOBS_BY_STATUS = Gauge(
    "jobs_by_status", "Jobs currently stored in each status", ["status"]
)

WORKERS_ACTIVE = Gauge(
    "workers_active", "Worker coroutines that are alive in this process"
)

OLDEST_PENDING_AGE_SECONDS = Gauge(
    "oldest_pending_job_age_seconds",
    "Age of the oldest pending job, 0 when the queue is empty",
)
