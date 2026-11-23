#!/usr/bin/env bash
# Run the benchmark in-process (no server needed).
# Usage: scripts/run_benchmark.sh [JOBS] [WORKERS] [SLEEP_SECONDS]
set -euo pipefail

cd "$(dirname "$0")/.."

JOBS="${1:-500}"
WORKERS="${2:-4}"
SLEEP="${3:-0.01}"

python3 benchmark/benchmark.py --jobs "$JOBS" --workers "$WORKERS" --sleep "$SLEEP"
