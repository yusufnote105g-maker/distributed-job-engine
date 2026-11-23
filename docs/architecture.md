# Architecture

## Overview

The engine is a single Python process that hosts two things:

1. a **FastAPI application** exposing a REST API (`/api/v1`), and
2. an **asyncio worker pool** plus a retry scheduler that live in the same
   event loop and process jobs from a SQLite database.

There is no separate broker (no Redis, no RabbitMQ). SQLite is the queue *and*
the durable store. This keeps the system to one deployable unit while still
giving atomic claiming, priority ordering and crash recovery.

```
        HTTP clients
             │
             ▼
   ┌──────────────────┐        ┌────────────────────────────┐
   │  FastAPI (src/)  │        │  JobProcessor              │
   │  routes.py       │        │  4 × asyncio worker tasks  │
   └────────┬─────────┘        │  1 × retry scheduler task  │
            │                  └───────────┬────────────────┘
            └──────────┬───────────────────┘
                       ▼
              ┌─────────────────┐
              │ DatabaseService │  SQLAlchemy 1.4 + asyncio.to_thread
              └────────┬────────┘
                       ▼
                  jobs.db (SQLite, WAL)
```

## Components

### `src/main.py`

* `create_app(config)` builds the FastAPI app and wires the lifespan:
  initialise the database, optionally start the worker pool, expose services
  on `app.state`, and shut everything down on exit.
* Startup also **requeues stale jobs** (rows left in `claimed`/`running` by a
  previous crash) so they are not lost.
* `config.enable_workers=False` runs the API without workers — used by the
  API test-suite to keep assertions deterministic.

### `src/services/database.py`

Every method returns plain dictionaries, so no ORM object ever escapes the
service and there are no lazy-load surprises after commit.

Claiming is the critical section:

```sql
UPDATE jobs
   SET status='claimed', worker_id=?, claimed_at=?, started_at=?, next_retry_at=NULL
 WHERE id = (SELECT id FROM jobs
              WHERE status='pending'
                AND (next_retry_at IS NULL OR next_retry_at <= now)
              ORDER BY priority_rank, created_at, id
              LIMIT 1)
   AND status='pending';
```

The `AND status='pending'` guard on the UPDATE means that if two workers pick
the same candidate row, only the one whose UPDATE actually changes the row gets
`rowcount == 1`; the loser returns `None` and polls again. This is what makes
concurrent claiming safe without a separate lock table.

SQLite is opened with `journal_mode=WAL`, `busy_timeout=5000` and
`synchronous=NORMAL`, which allows concurrent readers while a writer holds the
lock.

### `src/services/job_processor.py`

* `_worker(name)` — loop: claim → process → repeat; sleeps `poll_interval`
  when the queue is empty; survives unexpected exceptions.
* `_process(job)` — marks the job `running`, executes the payload under
  `asyncio.wait_for(timeout)`, then writes `completed`, `failed` (timeout), or
  schedules a retry.
* `_handle_failure` — increments `retry_count`; while
  `retry_count <= max_retries` the job becomes `retrying` with
  `next_retry_at = now + backoff`; after that it becomes `dead_letter`.
* `_scheduler()` — periodically promotes `retrying` jobs whose backoff has
  elapsed back to `pending`.
* `stop()` — cancels all tasks, awaits them, and is idempotent.

### Payload execution

The payload is an opaque string. If it parses as a JSON object with a `task`
key, a small built-in runner is used (useful for tests and benchmarks):

| Payload | Behaviour |
| --- | --- |
| `{"task":"noop"}` | completes immediately |
| `{"task":"sleep","seconds":1.5}` | sleeps, then completes |
| `{"task":"fail","message":"boom"}` | always raises |
| `{"task":"flaky","fail_times":2}` | fails while `retry_count < fail_times`, then completes |

Any other payload succeeds without side effects and is reported as
`processed payload (N bytes)`. Real workloads replace `_execute_payload` with
their own dispatcher.

## State machine

```
pending ──claim──▶ claimed ──▶ running ──▶ completed
   ▲                  │            │
   │                  │            ├──▶ failed (timeout / non-retryable)
   │                  ▼            ▼
   │              cancelled     retrying ──backoff elapsed──▶ pending
   │                                │
   └────────────────────────────────┴──▶ dead_letter (retries exhausted)
```

`cancelled` and `dead_letter` are terminal. `failed` is terminal for timeouts
and for jobs whose retry budget is already exhausted; retryable failures go to
`retrying` instead.

## Concurrency model

* All I/O is `async`; one event loop per process.
* Workers are `asyncio.Task`s, so a worker waiting on `sleep` does not block
  others.
* Cross-process safety comes from the atomic UPDATE above plus WAL, not from
  in-process locks. Several processes may share the same database file, though
  SQLite serialises writers (see `known_limitations.md`).

## Scaling out

The design is stateless apart from SQLite, so running several containers
against one database file works for moderate load. Beyond that, the database
becomes the bottleneck — the documented upgrade path is Postgres with
`SELECT ... FOR UPDATE SKIP LOCKED`.
