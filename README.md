# Distributed Job Engine

[![CI](https://github.com/yusufnote105g-maker/distributed-job-engine/actions/workflows/test.yml/badge.svg?branch=master)](https://github.com/yusufnote105g-maker/distributed-job-engine/actions/workflows/test.yml)
[![Release](https://img.shields.io/github/v/release/yusufnote105g-maker/distributed-job-engine)](https://github.com/yusufnote105g-maker/distributed-job-engine/releases)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)

An asynchronous job engine with a REST API, priority queue, concurrent
workers, retries with exponential backoff, per-job timeouts, and durable
storage in SQLite or PostgreSQL.

Python ≥ 3.11 · FastAPI · SQLAlchemy 1.4 · SQLite (WAL) / PostgreSQL

## What it does

* **Submit** jobs over HTTP with a priority (`low` → `critical`).
* **Process** them with a pool of asyncio workers; jobs are claimed atomically,
  so no job is ever handed to two workers.
* **Retry** failures with exponential backoff + jitter, up to a per-job budget,
  then move them to a dead-letter state.
* **Time out** slow jobs and record why they failed.
* **Recover** jobs left in `claimed`/`running` after a crash, on next startup.
* **Deduplicate** submissions with an `idempotency_key` enforced by a unique
  index.
* **Observe** everything through `/health`, `/stats`, `/metrics` and a
  Prometheus scrape endpoint at `/metrics/prometheus`.

## Install

Three ways, pick one.

**Wheel from the release** — no clone, no build:

```bash
pip install https://github.com/yusufnote105g-maker/distributed-job-engine/releases/download/v1.5.0/distributed_job_engine-1.5.0-py3-none-any.whl
job-engine version
job-engine serve --host 0.0.0.0 --port 8000
```

Every `v*` tag also gets a source archive and a `.tar.gz` attached to the
release.

**Docker image** — published to GHCR on every `v*` tag:

```bash
docker pull ghcr.io/yusufnote105g-maker/distributed-job-engine:v1.5.0
docker run -p 8000:8000 -v job-data:/data \
  -e DATABASE_URL=sqlite:////data/jobs.db \
  ghcr.io/yusufnote105g-maker/distributed-job-engine:v1.5.0
```

**From source** — see Quick start below.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

scripts/run.sh
```

Then:

```bash
curl -s localhost:8000/api/v1/health
curl -s -X POST localhost:8000/api/v1/jobs \
     -H 'content-type: application/json' \
     -d '{"payload":"{\"task\":\"sleep\",\"seconds\":1}","priority":"high"}'
curl -s localhost:8000/api/v1/jobs
curl -s localhost:8000/api/v1/metrics
```

Interactive docs: <http://localhost:8000/docs>

Or submit and wait for the result with the bundled client:

```bash
python3 examples/client.py '{"task":"sleep","seconds":1}' --priority high
```

It prints the final job as JSON and exits `0` on `completed`, `2` on
`failed`/`cancelled`/`dead_letter`, `3` on timeout.

## Run API and workers separately

For CPU-heavy payloads, keep the HTTP API responsive by moving execution to its
own process:

```bash
job-engine serve --no-workers --host 127.0.0.1 --port 8000   # HTTP only
job-engine worker --workers 4                                # execution only
```

Both use the same `DATABASE_URL`. When more than one process shares the
database, set `STALE_JOB_AGE` above `WORKER_TIMEOUT` so a restart cannot requeue
jobs that a live process is still running.

## PostgreSQL

SQLite is the default and needs no setup. For more than one host, or for
concurrent writers, use PostgreSQL:

```bash
pip install 'distributed-job-engine[postgres]'   # psycopg2 + alembic

export DATABASE_URL='postgresql+psycopg2://jobengine:secret@localhost:5432/jobs'
job-engine migrate                # create/migrate the schema
job-engine serve --no-workers     # any number of API replicas
job-engine worker --workers 8     # any number of worker replicas
```

Claims use `SELECT ... FOR UPDATE SKIP LOCKED`, so concurrent workers take
different rows instead of colliding. `serve` and `worker` apply pending
migrations on startup by default; set `AUTO_MIGRATE=false` to make
`job-engine migrate` an explicit deployment step.

## Authentication

Auth is off by default. Set one key or several with scopes:

```bash
API_KEYS="ci:read+write:$CI_SECRET; dashboard:read:$DASH_SECRET" job-engine serve
```

`read` covers GET endpoints, `write` covers submit/cancel/delete, `admin` covers
both. Keys are rotated without downtime by adding the new one, switching clients
and removing the old one. `GET /health` stays public.

## Configuration

All settings are environment variables (`src/config.py`).

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./jobs.db` | SQLAlchemy URL: SQLite (WAL) or `postgresql+psycopg2://` |
| `AUTO_MIGRATE` | `true` | PostgreSQL: apply Alembic migrations on startup |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | `5` / `10` | PostgreSQL connection pool |
| `WORKER_COUNT` | `4` | concurrent worker tasks |
| `WORKER_TIMEOUT` | `300` | default per-job timeout, seconds |
| `POLL_INTERVAL` | `0.5` | idle poll interval, seconds |
| `MAX_RETRIES` | `3` | default retry budget |
| `INITIAL_BACKOFF` / `MAX_BACKOFF` | `1.0` / `60.0` | backoff bounds, seconds |
| `RETRY_JITTER` | `true` | randomise backoff in `[0.5, 1.0] × delay` |
| `HEALTH_CHECK_INTERVAL` | `1.0` | retry-sweep interval, seconds |
| `API_HOST` / `API_PORT` | `0.0.0.0` / `8000` | bind address |
| `API_PREFIX` | `/api/v1` | route prefix |
| `SECRET_KEY` | *(empty)* | single key with all scopes; enables auth |
| `API_KEYS` | *(empty)* | `name:scopes:secret;...` with scopes `read`/`write`/`admin` |
| `API_KEY_HEADER` | `X-API-Key` | header name for the key |
| `RATE_LIMIT_PER_MINUTE` | `0` | per-key request limit; `0` disables |
| `LOG_FORMAT` | `text` | `json` for structured logs with a request id |
| `REQUEST_ID_HEADER` | `X-Request-ID` | request id echoed back and logged |
| `ENABLE_WORKERS` | `true` | run the worker pool in this process |
| `RECOVER_STALE_JOBS` | `true` | requeue stuck jobs at startup |
| `STALE_JOB_AGE` | `0` | only recover jobs older than this; set above `WORKER_TIMEOUT` with several processes |
| `LOG_LEVEL` | `INFO` | logging level |

## API

Full reference: [`docs/api.md`](docs/api.md).

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/jobs` | submit a job |
| `GET` | `/api/v1/jobs` | list jobs (`status`, `limit`, `offset`) |
| `GET` | `/api/v1/jobs/{job_id}` | fetch one job |
| `POST` | `/api/v1/jobs/{job_id}/cancel` | cancel a job |
| `DELETE` | `/api/v1/jobs/{job_id}` | cancel a job (alias) |
| `GET` | `/api/v1/health` | liveness + dependency status |
| `GET` | `/api/v1/stats` | counters |
| `GET` | `/api/v1/metrics` | counters + worker info (JSON) |
| `GET` | `/api/v1/metrics/prometheus` | Prometheus text format |

## Payloads and handlers

A payload is an opaque string. If it is a JSON object, its `task` field selects
a registered handler:

```python
from distributed_job_engine.handlers import handler

@handler("send-email")
async def send_email(spec, context):
    # spec: decoded payload, context: job_id, retry_count, payload
    return "sent"
```

Handlers may be sync or async. Exceptions follow the retry policy; an unknown
task name goes straight to `dead_letter`. Built-in handlers (`noop`, `sleep`,
`fail`, `flaky`) exist for examples and smoke tests. Payloads that are not JSON
objects complete as opaque blobs.

See [`docs/architecture.md`](docs/architecture.md#task-handlers).

## Tests

```bash
scripts/run_tests.sh            # or: python3 -m pytest
```

The suite covers the HTTP contract, priority ordering, atomic claiming under
parallelism, retry/backoff/dead-letter, timeouts, cancellation, idempotency
races and crash recovery. Tests run against a temporary SQLite file and start
real workers, so they exercise the same code paths as production. CI runs the
suite on Python 3.11, 3.12, 3.13 and 3.14, repeats it against a real PostgreSQL
16 service (`TEST_DATABASE_URL`), plus lint, a benchmark smoke run and a Docker
build.

## Benchmark

```bash
scripts/run_benchmark.sh 500 4 0.01   # jobs, workers, simulated work per job
```

Runs the engine in-process against a throwaway database and writes
`benchmark/benchmark_results.json` with submit/processing throughput, p50/p95
latency and worker utilisation. Numbers from this device are in
[`docs/benchmark.md`](docs/benchmark.md).

## Docker

```bash
docker build -t distributed-job-engine .
docker run -p 8000:8000 -v job-data:/data distributed-job-engine
# or
docker compose up --build
```

## Documentation

* [`docs/architecture.md`](docs/architecture.md) — components, claiming algorithm, state machine
* [`docs/api.md`](docs/api.md) — endpoints, fields, status codes
* [`docs/database_schema.md`](docs/database_schema.md) — table, indexes, pragmas
* [`docs/known_limitations.md`](docs/known_limitations.md) — honest limits (at-least-once, single writer, polling)
* [`docs/security_analysis.md`](docs/security_analysis.md) — threat model and hardening steps
* [`SECURITY.md`](SECURITY.md) — vulnerability reporting and deployment checklist
* [`docs/benchmark.md`](docs/benchmark.md) — measured throughput and latency
* [`docs/deployment.md`](docs/deployment.md) — env vars, Docker, systemd, nginx, backups, troubleshooting
* [`CHANGELOG.md`](CHANGELOG.md) — release history

## Layout

```
src/
  main.py                 app factory + lifespan
  config.py               env-driven settings
  api/routes.py           HTTP layer
  models/job.py           SQLAlchemy model + enums
  services/database.py    data access, atomic claiming (asyncio.to_thread)
  services/job_processor.py  workers, retries, scheduler
tests/                    pytest suite
benchmark/benchmark.py    reproducible benchmark
docs/                     architecture and reference
```
