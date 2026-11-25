# Database schema

One table, `jobs`, on two supported engines:

* **SQLite** (default) — created automatically on startup with
  `Base.metadata.create_all`. Zero configuration, one writer.
* **PostgreSQL** — schema owned by Alembic and applied with `job-engine migrate`
  (or automatically at startup when `AUTO_MIGRATE=true`, the default).

Both paths produce the same columns and indexes; `tests/test_migrations.py`
compares them so they cannot drift silently.

## `jobs`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | INTEGER | primary key, autoincrement (`SERIAL` on PostgreSQL) |
| `job_id` | VARCHAR(36) | unique, UUID4, the public identifier |
| `idempotency_key` | VARCHAR(64) | nullable, **unique** — deduplicates submissions |
| `payload` | TEXT | the opaque job body |
| `priority` | VARCHAR(8) | `low` / `normal` / `high` / `critical` |
| `timeout` | INTEGER | per-job timeout in seconds |
| `status` | VARCHAR(11) | see state machine in `architecture.md` |
| `retry_count` | INTEGER | attempts already consumed |
| `max_retries` | INTEGER | per-job retry budget |
| `next_retry_at` | TIMESTAMP | set while `retrying` |
| `created_at` | TIMESTAMP | submission time |
| `started_at` | TIMESTAMP | when a worker began executing |
| `claimed_at` | TIMESTAMP | when a worker claimed it |
| `completed_at` | TIMESTAMP | terminal timestamp |
| `worker_id` | VARCHAR(64) | last worker that owned the job |
| `result` | TEXT | success value |
| `error` | TEXT | last failure message |
| `execution_time` | FLOAT | last attempt duration in seconds |

Enums are stored as their string **values** (`pending`, `high`) using
`native_enum=False`, so the column is a plain VARCHAR with no CHECK constraint
and reads stay readable from `sqlite3` or `psql`.

## Indexes

| Index | Purpose |
| --- | --- |
| unique constraint on `job_id` | lookup by public id |
| `ix_jobs_idempotency_key` (unique) | deduplication, including under concurrency |
| `ux_jobs_idempotency_key` (unique, partial, `WHERE idempotency_key IS NOT NULL`) | SQLite only: added on startup for files created before uniqueness was enforced |
| `ix_jobs_status` | queue scans, status filters, counters |
| `ix_jobs_priority` | priority grouping |
| `ix_jobs_created_at` | listing order, oldest-pending metric |

The claim query orders by priority, then `created_at`, then `id`.

* On **SQLite** it uses `ix_jobs_status` and sorts the (usually small) pending
  set in memory; claims are optimistic compare-and-set updates.
* On **PostgreSQL** the same query runs with `FOR UPDATE SKIP LOCKED`, so
  concurrent workers never fight over the same row and never block each other.

## SQLite pragmas

Set on every connection:

```sql
PRAGMA journal_mode=WAL;    -- readers don't block the writer
PRAGMA busy_timeout=30000;  -- wait instead of failing on lock contention
PRAGMA synchronous=NORMAL;  -- durable enough for WAL, much faster
```

## Migrations

```bash
job-engine migrate                        # upgrade to head
job-engine migrate --revision 0001_initial
job-engine migrate --database-url postgresql+psycopg2://user:pass@host/jobs
```

The scripts live in `src/migrations/versions/` and ship inside the wheel.

* PostgreSQL: `job-engine migrate` creates the schema. With
  `AUTO_MIGRATE=true` (default) `serve` and `worker` also run
  `upgrade head` on startup.
* SQLite: the file is created by `create_all`. If you point `job-engine migrate`
  at an existing SQLite file that has no `alembic_version` table, it stamps the
  baseline revision instead of replaying the initial migration.

Developers can use the repository `alembic.ini` instead:

```bash
DATABASE_URL=postgresql+psycopg2://user:pass@localhost/jobs alembic upgrade head
DATABASE_URL=... alembic revision --autogenerate -m "add column"
```

## Inspecting

```bash
sqlite3 data/jobs.db "SELECT status, COUNT(*) FROM jobs GROUP BY status;"
sqlite3 data/jobs.db "SELECT job_id, retry_count, error FROM jobs WHERE status='dead_letter';"

psql "$DATABASE_URL" -c "SELECT status, COUNT(*) FROM jobs GROUP BY status;"
psql "$DATABASE_URL" -c "SELECT * FROM alembic_version;"
```
