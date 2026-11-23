# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/yusufnote105g-maker/distributed-job-engine/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/yusufnote105g-maker/distributed-job-engine/releases/tag/v1.0.0
