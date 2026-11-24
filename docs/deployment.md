# Deployment guide

The service is a single process that serves the HTTP API and runs the workers in
the same event loop. One SQLite file is the only state.

## Configuration

All settings come from environment variables (`src/config.py`).

| Variable | Default | Notes |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./jobs.db` | Parent directory is created automatically |
| `WORKER_COUNT` | `4` | Keep ≤ CPU cores for I/O-bound work |
| `WORKER_TIMEOUT` | `300` | Per-job timeout, seconds |
| `POLL_INTERVAL` | `0.5` | Idle poll interval, seconds |
| `MAX_RETRIES` | `3` | Default for jobs that do not override it |
| `INITIAL_BACKOFF` | `1.0` | First retry delay, seconds |
| `MAX_BACKOFF` | `60.0` | Backoff ceiling, seconds |
| `RETRY_JITTER` | `true` | Spreads retries so they do not synchronise |
| `API_HOST` | `0.0.0.0` | Bind address |
| `API_PORT` | `8000` | Bind port |
| `API_PREFIX` | `/api/v1` | Route prefix |
| `HEALTH_CHECK_INTERVAL` | `1.0` | Scheduler tick, seconds |
| `LOG_LEVEL` | `INFO` | Python log level |
| `SECRET_KEY` | *(empty)* | Empty disables authentication |
| `API_KEY_HEADER` | `X-API-Key` | Header carrying the key |
| `ENABLE_WORKERS` | `true` | Set `false` for an API-only node |
| `RECOVER_STALE_JOBS` | `true` | Requeue `claimed`/`running` rows on startup |

## Docker

```bash
docker build -t distributed-job-engine .
docker run -d --name job-engine \
  -p 8000:8000 \
  -v job-data:/data \
  -e DATABASE_URL=sqlite:////data/jobs.db \
  -e WORKER_COUNT=4 \
  -e SECRET_KEY="$SECRET_KEY" \
  --restart unless-stopped \
  distributed-job-engine
```

`docker compose up --build` uses the same settings from `docker-compose.yml`.
The image runs as a non-root user (uid 10001), so the mounted volume must be
writable by that uid.

## Bare metal (systemd)

```ini
# /etc/systemd/system/job-engine.service
[Unit]
Description=Distributed Job Engine
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=jobengine
Group=jobengine
WorkingDirectory=/opt/job-engine
Environment=DATABASE_URL=sqlite:////var/lib/job-engine/jobs.db
Environment=WORKER_COUNT=4
Environment=SECRET_KEY=change-me
Environment=LOG_LEVEL=INFO
ExecStart=/opt/job-engine/venv/bin/python -m uvicorn src.main:app \
    --host 127.0.0.1 --port 8000 --log-level info
Restart=always
RestartSec=3
TimeoutStopSec=30
KillSignal=SIGTERM

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now job-engine
journalctl -u job-engine -f
```

`SIGTERM` triggers the lifespan shutdown: workers stop, in-flight tasks are
cancelled, the engine closes the database. Allow up to `TimeoutStopSec`.

## Reverse proxy

Terminate TLS and add rate limiting at the proxy — the app has neither.

```nginx
server {
    listen 443 ssl http2;
    server_name jobs.example.com;

    ssl_certificate     /etc/letsencrypt/live/jobs.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/jobs.example.com/privkey.pem;

    client_max_body_size 256k;   # payload cap is 100 kB in the API

    location / {
        limit_req zone=jobs burst=20 nodelay;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 30s;
    }
}
```

Bind the app to `127.0.0.1` (`API_HOST=127.0.0.1`) when a proxy is in front.

## Health checks and alerting

* Liveness: `GET /api/v1/health` returns `200` with `status: healthy`.
  `status: degraded` means the database is unreachable or workers are stopped
  while `ENABLE_WORKERS=true`.
* Backlog: `GET /api/v1/stats` → `pending_jobs` and `oldest_pending_job`.
  Alert when `pending_jobs` grows for longer than your acceptable latency, or
  when `oldest_pending_job` is older than that.
* Failures: `failed_jobs` and especially `dead_letter_jobs` — alert on any
  growth, because dead-letter jobs need manual attention.
* Capacity: `/metrics` → `active_workers`, `processed_by_this_processor`.

## Backup and restore

SQLite in WAL mode must not be copied with `cp` while the service runs.

```bash
# Consistent online backup
sqlite3 /var/lib/job-engine/jobs.db ".backup '/backup/jobs-$(date +%F).db'"

# Or, with the service stopped
systemctl stop job-engine
cp /var/lib/job-engine/jobs.db /backup/jobs-$(date +%F).db
systemctl start job-engine
```

Restore by stopping the service, replacing the file (and removing stale
`jobs.db-wal` / `jobs.db-shm`), then starting it again.

## Upgrade

1. Back up the database.
2. `git fetch && git checkout vX.Y.Z` (or pull the new image).
3. Reinstall dependencies if `requirements.txt` changed.
4. Restart the service; `SIGTERM` drains workers first.
5. Check `/health` and `/stats`.

Schema changes are additive only: `Base.metadata.create_all` creates missing
tables but does not alter existing ones. A release that changes a column
requires a manual migration — there is no Alembic yet.

## Scaling

* **One writer only.** SQLite serialises writes. Do not run two containers
  against the same file over a network filesystem.
* **API-only replicas.** Set `ENABLE_WORKERS=false` to serve reads from extra
  nodes; they must share the same database file, which in practice means the
  same host.
* **More workers** help only for I/O-bound payloads. CPU-bound work blocks the
  event loop for every worker — move it out of process.
* **Beyond one host**, move the queue to PostgreSQL. This is a code change, not
  a configuration flag (see `docs/known_limitations.md`).

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `unable to open database file` | Directory missing or not writable by the process uid | Create it and fix ownership; the app creates missing directories but cannot fix permissions |
| `database is locked` | Another writer, or a long transaction | Keep one writer; check for stray processes |
| `/health` says `degraded` | Database unreachable or workers stopped | Check logs and `ENABLE_WORKERS` |
| `409` on cancel | Job already terminal | Expected; read the job first |
| `401` on writes | `SECRET_KEY` set but header missing/wrong | Send the configured `API_KEY_HEADER` |
| Jobs stay `pending` | `ENABLE_WORKERS=false` or workers crashed | Check `/metrics` → `active_workers` |
| Jobs pile up in `dead_letter` | Payload keeps failing | Inspect `error`, fix the payload, resubmit with a new `idempotency_key` |
