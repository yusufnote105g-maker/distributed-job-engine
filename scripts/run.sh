#!/usr/bin/env bash
# Start the Distributed Job Engine API.
set -euo pipefail

cd "$(dirname "$0")/.."

: "${API_HOST:=0.0.0.0}"
: "${API_PORT:=8000}"
: "${WORKER_COUNT:=4}"
: "${LOG_LEVEL:=INFO}"
export API_HOST API_PORT WORKER_COUNT LOG_LEVEL

mkdir -p data
: "${DATABASE_URL:=sqlite:///./data/jobs.db}"
export DATABASE_URL

echo "🚀 Distributed Job Engine"
echo "   database : $DATABASE_URL"
echo "   workers  : $WORKER_COUNT"
echo "   address  : http://$API_HOST:$API_PORT"
echo "   health   : http://localhost:$API_PORT/api/v1/health"
echo "   docs     : http://localhost:$API_PORT/docs"

exec python3 -m uvicorn src.main:app --host "$API_HOST" --port "$API_PORT"
