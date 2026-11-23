# Database schema

SQLite, one table. Created automatically on startup
(`Base.metadata.create_all`).

## `jobs`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | INTEGER | primary key, autoincrement |
| `job_id` | VARCHAR(36) | unique, UUID4, the public identifier |
| `idempotency_key` | VARCHAR(64) | nullable, **unique** — deduplicates submissions |
| `payload` | TEXT | the opaque job body |
| `priority` | VARCHAR(16) | `low` / `normal` / `high` / `critical` |
| `timeout` | INTEGER | per-job timeout in seconds |
| `status` | VARCHAR(16) | see state machine in `architecture.md` |
| `retry_count` | INTEGER | attempts already consumed |
| `max_retries` | INTEGER | per-job retry budget |
| `next_retry_at` | DATETIME | set while `retrying` |
| `created_at` | DATETIME | submission time |
| `started_at` | DATETIME | when a worker began executing |
| `claimed_at` | DATETIME | when a worker claimed it |
| `completed_at` | DATETIME | terminal timestamp |
| `worker_id` | VARCHAR(64) | last worker that owned the job |
| `result` | TEXT | success value |
| `error` | TEXT | last failure message |
| `execution_time` | FLOAT | last attempt duration in seconds |

Enums are stored as their string **values** (`pending`, `high`) using
`native_enum=False`, so the column is a plain VARCHAR with no CHECK constraint
and reads stay readable from `sqlite3`.

## Indexes

| Index | Purpose |
| --- | --- |
| `ix_jobs_job_id` (unique) | lookup by public id |
| `ix_jobs_idempotency_key` (unique) | deduplication, including under concurrency |
| `ux_jobs_idempotency_key` (unique, partial, `WHERE idempotency_key IS NOT NULL`) | added on startup for databases created before uniqueness was enforced |
| `ix_jobs_status` | queue scans, status filters, counters |
| `ix_jobs_priority` | priority grouping |
| `ix_jobs_created_at` | listing order, oldest-pending metric |

The claim query orders by priority then `created_at`, then `id`. SQLite uses
`ix_jobs_status` for the filter and sorts the (usually small) pending set in
memory; this is adequate up to tens of thousands of pending rows.

## Pragmas

Set on every connection:

```sql
PRAGMA journal_mode=WAL;    -- readers don't block the writer
PRAGMA busy_timeout=30000;  -- wait instead of failing on lock contention
PRAGMA synchronous=NORMAL;  -- durable enough for WAL, much faster
```

## Inspecting

```bash
sqlite3 data/jobs.db "SELECT status, COUNT(*) FROM jobs GROUP BY status;"
sqlite3 data/jobs.db "SELECT job_id, retry_count, error FROM jobs WHERE status='dead_letter';"
```

## Migrations

There is no migration tool. The table is additive-only in practice; if you
change a column, either recreate the database or add an explicit migration
script. For anything beyond a prototype, introduce Alembic at that point.
