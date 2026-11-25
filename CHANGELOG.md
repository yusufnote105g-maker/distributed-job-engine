# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] — 2026-11-24

The engine now runs on PostgreSQL as well as SQLite, and the HTTP API can be
deployed separately from the workers.

### Added

- **PostgreSQL support.** `DATABASE_URL=postgresql+psycopg2://...` selects a
  server-side database. Claims use `SELECT ... FOR UPDATE SKIP LOCKED`, so
  concurrent workers take different rows and never block each other; the
  single-writer limit of SQLite no longer applies. Connection pooling is
  configured with `DB_POOL_SIZE` / `DB_MAX_OVERFLOW`.
- **Alembic migrations** in `src/migrations/`, shipped inside the wheel, with a
  new `job-engine migrate` command (`--revision`, `--database-url`). PostgreSQL
  schemas are applied on startup when `AUTO_MIGRATE=true` (default). SQLite
  keeps the zero-config `create_all`; pointing `migrate` at an existing SQLite
  file stamps the baseline revision instead of replaying it.
- New CI job that runs the whole suite and the split-deployment smoke against a
  real PostgreSQL 16 service.
- `job-engine worker` runs workers in a dedicated process and
  `job-engine serve --no-workers` serves HTTP only, so CPU-heavy payloads no
  longer block the API. `scripts/smoke_split.sh` verifies the split deployment.
- `STALE_JOB_AGE`: startup recovery can be limited to jobs older than a
  threshold, so restarting one process cannot requeue work that another live
  process is executing. `0` keeps the previous single-process behaviour.
- Prometheus scrape endpoint `GET /metrics/prometheus` with job counters
  (submitted by priority, completed, failed, dead-letter, cancelled), an
  execution-time histogram, and gauges for queue depth per status, live workers
  and the age of the oldest pending job. The existing JSON `/metrics` endpoint is
  unchanged.

### Changed

- `postgres` extra now installs `psycopg2-binary` + `alembic`. The previous
  `psycopg[binary]` entry could not work: SQLAlchemy 1.4 has no psycopg 3
  dialect.
- `postgres://` URLs are normalised to `postgresql://`, and
  `postgresql+psycopg://` to `postgresql+psycopg2://`.
- The Docker image accepts `--build-arg INSTALL_POSTGRES=true` to include the
  PostgreSQL driver and Alembic; the default image is unchanged.

### Fixed

- Starlette appended a second `charset=utf-8` to the Prometheus content type;
  the header is now set directly.
- `requeue_stale_jobs` used `coalesce` in a bulk update, which SQLAlchemy 1.4
  cannot evaluate in Python. It now uses `synchronize_session=False`.

## [1.2.0] — 2026-11-24

The project is now an installable distribution, not only a source tree.

### Added

- `pyproject.toml` with the `distributed_job_engine` package, a `job-engine`
  console script (`serve`, `version`) and extras `postgres`, `metrics`, `otel`
  and `dev`.
- `src/cli.py` — `job-engine serve --host/--port/--reload` and
  `job-engine version`.
- `tests/test_packaging.py` — the version in `pyproject.toml`, in the package,
  in the FastAPI app and in the CLI output must all agree.

### Changed

- `VERSION` is read from the package instead of being duplicated in
  `src/main.py`.
- `uvicorn.run(app)` is used instead of the `"src.main:app"` import string, so
  the installed package can start the server.
- pytest configuration moved from `pytest.ini` into `pyproject.toml`.

## [1.1.0] — 2026-11-24

### Added

- CI runs on Python 3.14 as well, and on `v*` tags.
- `docs/deployment.md`: environment variables, Docker, systemd, nginx with TLS
  and rate limiting, online SQLite backups, upgrade, scaling, troubleshooting.
- `examples/client.py` — submit a job and wait for the result; covered by
  `tests/test_examples.py`.
- Contract tests for `/health`, `/stats`, `/metrics` and an OpenAPI test listing
  every documented endpoint.

### Changed

- `datetime.utcnow()` (deprecated since Python 3.12) replaced by
  `src.utils.utcnow()`; the stored naive-UTC format is unchanged.

## [1.0.0] — 2026-11-23

First release that runs on Python 3.14 (Android/bionic) as well as on the
supported server runtimes, with a verified concurrency model.

### Added

- REST API: submit, list, fetch, cancel jobs; `/health`, `/stats`, `/metrics`.
- Priority queue with `critical`/`high`/`normal`/`low` and stable FIFO ordering
  inside a priority.
- `asyncio` worker pool with configurable `WORKER_COUNT` and poll interval.
- Retries with exponential backoff and jitter, per-job timeouts, and a
  `dead_letter` terminal state.
- Idempotent submissions: a unique `idempotency_key` always returns the original
  job, including under concurrent duplicate requests.
- Optional shared-key authentication via `X-API-Key`, compared in constant time.
- `benchmark/benchmark.py` with submission, processing and end-to-end metrics.
- Documentation: `docs/api.md`, `docs/architecture.md`, `docs/benchmark.md`,
  `docs/database_schema.md`, `docs/known_limitations.md`,
  `docs/security_analysis.md`, plus `SECURITY.md`.
- CI: lint, tests on Python 3.11/3.12/3.13, benchmark smoke and Docker build.

### Changed

- Dependencies pinned to pydantic 1.10 and SQLAlchemy 1.4 so no Rust
  `pydantic-core` build is required.
- `DatabaseService` uses synchronous SQLAlchemy on a thread pool instead of
  `aiosqlite`.
- SQLite tuned with WAL, `busy_timeout=30000`, `synchronous=NORMAL` and
  `check_same_thread=False`.
- Job claiming replaced with an optimistic select-then-update loop that is safe
  under parallel workers.
- CI triggers on both `main` and `master`.

### Fixed

- Concurrent `claim_job` calls could hand the same job to two workers.
- Duplicate `idempotency_key` submissions raced and produced two jobs.
- Cancelling a running job was overwritten with `completed`; cancellation is now
  durable and the worker discards the result.
- `DatabaseService.initialize()` failed with `unable to open database file` when
  the parent directory of the SQLite file did not exist.
- `benchmark/benchmark.py` could not be started without `PYTHONPATH`.

[Unreleased]: https://github.com/yusufnote105g-maker/distributed-job-engine/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/yusufnote105g-maker/distributed-job-engine/releases/tag/v1.2.0
[1.1.0]: https://github.com/yusufnote105g-maker/distributed-job-engine/releases/tag/v1.1.0
[1.0.0]: https://github.com/yusufnote105g-maker/distributed-job-engine/releases/tag/v1.0.0
