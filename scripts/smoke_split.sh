#!/usr/bin/env bash
# Split deployment smoke test: the API runs without workers and a separate
# process executes jobs from the same database.
#
# Usage:
#   scripts/smoke_split.sh                       # uses the installed `job-engine`
#   JOB_ENGINE="python3 -m src.cli" scripts/smoke_split.sh   # from the repo root
set -euo pipefail

JOB_ENGINE="${JOB_ENGINE:-job-engine}"
PORT="${PORT:-8123}"
BASE="http://127.0.0.1:${PORT}/api/v1"
WORKDIR="$(mktemp -d)"

# Respect an externally provided DATABASE_URL (for example PostgreSQL in CI);
# fall back to a throw-away SQLite file.
if [ -z "${DATABASE_URL:-}" ]; then
  export DATABASE_URL="sqlite:///${WORKDIR}/jobs.db"
fi
export LOG_LEVEL="${LOG_LEVEL:-WARNING}"

cleanup() {
  kill "${API_PID:-}" "${WORKER_PID:-}" 2>/dev/null || true
  wait "${API_PID:-}" "${WORKER_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT

$JOB_ENGINE serve --no-workers --host 127.0.0.1 --port "$PORT" >"${WORKDIR}/api.log" 2>&1 &
API_PID=$!

for _ in $(seq 1 30); do
  curl -fsS "${BASE}/health" >/dev/null 2>&1 && break
  sleep 1
done
if ! curl -fsS "${BASE}/health" >/dev/null 2>&1; then
  echo "API did not become healthy"
  tail -20 "${WORKDIR}/api.log"
  exit 1
fi

$JOB_ENGINE worker --workers 2 >"${WORKDIR}/worker.log" 2>&1 &
WORKER_PID=$!

JOB_ID=$(curl -fsS -X POST "${BASE}/jobs" \
  -H 'content-type: application/json' \
  -d '{"payload":"{\"task\":\"noop\"}","priority":"high"}' |
  python3 -c 'import json,sys; print(json.load(sys.stdin)["job_id"])')

STATUS="unknown"
for _ in $(seq 1 30); do
  STATUS=$(curl -fsS "${BASE}/jobs/${JOB_ID}" |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')
  if [ "$STATUS" = "completed" ]; then
    echo "split deployment ok: job ${JOB_ID} completed"
    exit 0
  fi
  sleep 1
done

echo "job ${JOB_ID} did not complete (last status: ${STATUS})"
echo "--- api log ---"
tail -20 "${WORKDIR}/api.log"
echo "--- worker log ---"
tail -20 "${WORKDIR}/worker.log"
exit 1
