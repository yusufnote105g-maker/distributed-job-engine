# Distributed Job Engine

An asynchronous job engine with a REST API, priority queue, concurrent
workers, retries with exponential backoff, per-job timeouts, and durable
storage in SQLite.

Python ≥ 3.11 · FastAPI · SQLAlchemy 1.4 · SQLite (WAL)

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
* **Observe** everything through `/health`, `/stats` and `/metrics`.

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

## Configuration

All settings are environment variables (`src/config.py`).

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./jobs.db` | SQLAlchemy URL (SQLite, WAL mode) |
| `WORKER_COUNT` | `4` | concurrent worker tasks |
| `WORKER_TIMEOUT` | `300` | default per-job timeout, seconds |
| `POLL_INTERVAL` | `0.5` | idle poll interval, seconds |
| `MAX_RETRIES` | `3` | default retry budget |
| `INITIAL_BACKOFF` / `MAX_BACKOFF` | `1.0` / `60.0` | backoff bounds, seconds |
| `RETRY_JITTER` | `true` | randomise backoff in `[0.5, 1.0] × delay` |
| `HEALTH_CHECK_INTERVAL` | `1.0` | retry-sweep interval, seconds |
| `API_HOST` / `API_PORT` | `0.0.0.0` / `8000` | bind address |
| `API_PREFIX` | `/api/v1` | route prefix |
| `SECRET_KEY` | *(empty)* | enables `X-API-Key` auth when set |
| `API_KEY_HEADER` | `X-API-Key` | header name for the key |
| `ENABLE_WORKERS` | `true` | run the worker pool in this process |
| `RECOVER_STALE_JOBS` | `true` | requeue stuck jobs at startup |
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
| `GET` | `/api/v1/metrics` | counters + worker info |

## Payloads

A payload is an opaque string. The bundled runner understands JSON objects with
a `task` key — `noop`, `sleep`, `fail`, `flaky` — which is enough to exercise
retries, timeouts and priorities. Everything else completes as an opaque blob.
See [`docs/architecture.md`](docs/architecture.md#payload-execution) for how to
plug in real work.

## Tests

```bash
scripts/run_tests.sh            # or: python3 -m pytest
```

The suite covers the HTTP contract, priority ordering, atomic claiming under
parallelism, retry/backoff/dead-letter, timeouts, cancellation, idempotency
races and crash recovery. Tests run against a temporary SQLite file and start
real workers, so they exercise the same code paths as production.

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
* [`docs/benchmark.md`](docs/benchmark.md) — measured throughput and latency

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
