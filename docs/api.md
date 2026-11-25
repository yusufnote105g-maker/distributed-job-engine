# API reference

Base path: `/api/v1`. Interactive docs: `/docs`, schema: `/openapi.json`.

## Authentication

Authentication is **off by default**. It turns on when `API_KEYS` or the legacy
`SECRET_KEY` is set. The header is named by `API_KEY_HEADER` (default
`X-API-Key`).

`API_KEYS` is a semicolon-separated list of `name:scopes:secret` entries; scopes
are joined by `+`:

```bash
API_KEYS="ci:read+write:long-secret; dashboard:read:other-secret; ops:admin:third"
```

| Scope | Grants |
| --- | --- |
| `read` | `GET /jobs`, `GET /jobs/{id}`, `GET /stats`, `GET /metrics`, `GET /metrics/prometheus` |
| `write` | `POST /jobs`, `POST /jobs/{id}/cancel`, `DELETE /jobs/{id}` |
| `admin` | everything above |

`GET /health` is always public so probes need no credentials.

Responses:

| Status | Meaning |
| --- | --- |
| `401` | key missing or wrong (`WWW-Authenticate: X-API-Key`) |
| `403` | key is valid but lacks the required scope |
| `429` | rate limit exceeded, `Retry-After: 60` (`RATE_LIMIT_PER_MINUTE`) |

`SECRET_KEY` keeps working as a single key named `default` with all scopes, so
existing deployments do not break. When both are set, both are accepted — which
is how keys are rotated without downtime: add the new key, deploy, switch
clients, remove the old key, deploy again.

> **Behaviour change in 1.4.0:** when authentication is enabled, read endpoints
> are protected too. They expose payloads, results and error messages, so they
> were previously an unauthenticated data leak.

## Request id

Every response carries the header named by `REQUEST_ID_HEADER` (default
`X-Request-ID`). If the client sends one it is reused, otherwise a random id is
generated. The same id appears in every log line for that request, in both
`LOG_FORMAT=text` and `LOG_FORMAT=json`.

## POST /jobs

Submit a job. Returns `201`.

```json
{
  "payload": "{\"task\":\"sleep\",\"seconds\":1}",
  "priority": "high",
  "idempotency_key": "order-1234",
  "timeout": 60,
  "max_retries": 5
}
```

| Field | Type | Rules |
| --- | --- | --- |
| `payload` | string | required, 1–100000 chars |
| `priority` | enum | `low` \| `normal` \| `high` \| `critical`, default `normal` |
| `idempotency_key` | string | optional, ≤64 chars, unique |
| `timeout` | int | optional, 1–86400 s, default from `WORKER_TIMEOUT` |
| `max_retries` | int | optional, 0–100, default from `MAX_RETRIES` |

Submitting again with the same `idempotency_key` returns the **existing** job
with `201` — it does not create a duplicate and does not reset its state. The
guarantee is enforced by a unique index, so it also holds when requests race.

Validation failures return `422`.

## GET /jobs

Query parameters:

| Parameter | Type | Meaning |
| --- | --- | --- |
| `status` | enum | filter by status |
| `limit` | int | 1–100, default 50 |
| `offset` | int | ≥0, classic pagination |
| `before` | string | cursor: return jobs older than this `job_id` |

```json
{
  "jobs": [ ... ],
  "total": 42,
  "limit": 2,
  "offset": 0,
  "next_cursor": "0f1c2a3e-..."
}
```

Ordered by `created_at DESC, id DESC`.

`next_cursor` is the `job_id` of the last job on a full page, or `null` when
there is nothing left. Pass it back as `before` to get the next page. This is
keyset pagination: pages do not shift when new jobs are submitted, and deep
pages stay as fast as the first one. `offset` remains available for simple
cases. An unknown `before` returns `404`.

```bash
curl -s "localhost:8000/api/v1/jobs?limit=50"
curl -s "localhost:8000/api/v1/jobs?limit=50&before=$CURSOR"
```

## GET /jobs/{job_id}

Returns the job, or `404` if unknown. `job_id` is a UUID string.

## POST /jobs/{job_id}/cancel

Cancels a job that is `pending`, `claimed`, `running` or `retrying`. Returns
`{"message": "Job cancelled successfully"}`.

* `404` — unknown job
* `409` — job is already in a terminal state
  (`completed`, `failed`, `cancelled`, `dead_letter`)

Cancelling a `pending`/`retrying` job prevents it from starting. Cancelling a
`running` job is durable — the worker cannot overwrite `cancelled` with
`completed` — but it is not preemptive: the payload finishes and its result is
discarded.

`DELETE /jobs/{job_id}` is an alias with identical semantics.

## GET /health

```json
{
  "status": "healthy",
  "timestamp": "2026-11-21T21:30:00",
  "version": "1.0.0",
  "database_status": "ok",
  "worker_status": "running"
}
```

`status` is `degraded` when the database is unreachable, or when workers are
disabled/stopped but `ENABLE_WORKERS` is true.

## GET /stats

Aggregate counters: `total_jobs`, `pending_jobs`, `claimed_jobs`,
`running_jobs`, `completed_jobs`, `failed_jobs`, `cancelled_jobs`,
`retrying_jobs`, `dead_letter_jobs`, `oldest_pending_job`, plus a
`status_counts` map.

## GET /metrics

Everything from `/stats` plus `average_execution_time`, `worker_count`,
`active_workers`, `processor_running`, `worker_id`,
`processed_by_this_processor`, `failed_by_this_processor`.

## GET /metrics/prometheus

Prometheus text format (`text/plain; version=1.0.0`), suitable for scraping:

```yaml
scrape_configs:
  - job_name: job-engine
    static_configs:
      - targets: ["127.0.0.1:8000"]
    metrics_path: /api/v1/metrics/prometheus
```

| Metric | Type | Meaning |
| --- | --- | --- |
| `jobs_submitted_total{priority}` | counter | Submissions accepted (idempotent replays are not counted) |
| `jobs_completed_total` | counter | Jobs that reached `completed` |
| `jobs_failed_total` | counter | Jobs that reached `failed` |
| `jobs_dead_letter_total` | counter | Jobs that exhausted their retries |
| `jobs_cancelled_total` | counter | Jobs cancelled through the API |
| `job_execution_seconds` | histogram | Payload execution time |
| `jobs_by_status{status}` | gauge | Current row count per status |
| `workers_active` | gauge | Worker coroutines alive in this process |
| `oldest_pending_job_age_seconds` | gauge | Age of the oldest `pending` job, `0` when empty |

Counters are cumulative for the lifetime of the process and reset when it
restarts. The gauges are recomputed on every scrape from the database, so they
stay correct across restarts.

This endpoint is excluded from the OpenAPI schema because it is not a JSON API.

## Job object

```json
{
  "id": 1,
  "job_id": "0f5c…",
  "idempotency_key": "order-1234",
  "payload": "{\"task\":\"noop\"}",
  "priority": "high",
  "status": "completed",
  "created_at": "2026-11-21T21:30:00.123456",
  "started_at": "2026-11-21T21:30:00.200000",
  "claimed_at": "2026-11-21T21:30:00.199000",
  "completed_at": "2026-11-21T21:30:00.310000",
  "retry_count": 0,
  "max_retries": 3,
  "next_retry_at": null,
  "worker_id": "worker-1",
  "timeout": 300,
  "result": "noop",
  "error": null,
  "execution_time": 0.11
}
```

Timestamps are UTC without a timezone suffix.
