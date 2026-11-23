# Known limitations

These are real constraints of the current implementation, not TODOs that are
already solved elsewhere in the repository.

## Delivery semantics: at-least-once

A job that is claimed and then interrupted (process killed, host rebooted) is
put back into `pending` on the next startup by `requeue_stale_jobs()` and will
run again. A job can therefore execute more than once. Handlers must be
idempotent, or must use `idempotency_key` at the submission boundary.

There is no exactly-once delivery.

## Single-node database

SQLite allows many readers but **one writer at a time**. WAL plus a 30 s
`busy_timeout` absorbs short bursts, but write throughput is bounded by fsync
and lock handoff. In the bundled benchmark, throughput is dominated by the
number of DB writes per job (claim, running, complete ≈ 3 writes) and by the
synchronous commit on every submission.

Running multiple containers against one SQLite file works only when the file
lives on a filesystem with working POSIX locking (local disk, not most network
filesystems).

## In-process workers only

Workers live in the API process. A CPU-bound payload blocks the event loop for
all workers and for request handling. Long CPU work must be offloaded to a
thread/process executor or to a separate worker deployment.

## Polling, not notification

Workers poll every `POLL_INTERVAL` (default 0.5 s) when idle. Idle latency and
CPU wake-ups are a direct consequence; a real queue would block on a
notification instead.

## Cancellation is durable but not preemptive

Cancelling a running job marks it `cancelled` immediately and the transition is
guarded, so a worker that finishes later cannot overwrite it with `completed`.
The worker is not forcibly interrupted, though: the payload runs to completion
and its result is discarded. Cancelling a `pending`/`retrying` job prevents it
from starting at all.

## Timeouts are cooperative

`asyncio.wait_for` cancels the coroutine, which is fine for `await`-based work.
A payload that blocks the loop (sync I/O, tight CPU loop) cannot be interrupted,
so its timeout will fire late.

## Timeout does not retry

A timed-out job goes to `failed`, not `retrying`. This is deliberate (a
repeatedly timing-out job usually indicates a real problem), but it means
timeouts do not consume the retry budget.

## Auth is a shared static key

`SECRET_KEY` is a single shared secret compared with `==`. No users, no scopes,
no rotation, no rate limiting, and auth is disabled entirely when the key is
empty. Put the service behind a gateway if it is exposed.

## No payload isolation

Payloads are not sandboxed. Anything that can submit a job can influence what
the worker executes (in the default runner only a fixed set of no-op tasks; in
a real deployment, whatever your dispatcher allows).

## Timestamps are naive UTC

`datetime.utcnow()` is used throughout; values have no timezone information and
`datetime.utcnow()` is deprecated in newer Pythons. Consistent internally, but
it will need to become timezone-aware.

## No pagination cursor

`GET /jobs` uses `LIMIT/OFFSET`. Deep offsets get slower and pages can shift
when rows are inserted concurrently.

## No metrics export

`/metrics` returns JSON. There is no Prometheus endpoint, no tracing, and no
log shipping configuration.

## Payload size is unbounded in practice

The API caps payloads at 100 kB, but the database and the process hold them in
memory. Large payloads belong in object storage with a reference in the job.

## Dependency pinning for Python 3.14 / bionic

The project targets pydantic 1.10.x and SQLAlchemy 1.4.x on purpose: they are
pure-Python or ship broad wheels and therefore install on hosts (such as
Android/bionic) where pydantic 2's `pydantic-core` has no wheel and cannot be
built without a Rust toolchain. FastAPI is pinned below 1.0 to match pydantic 1.
Upgrading to pydantic 2 requires a host with a working `pydantic-core` build.
