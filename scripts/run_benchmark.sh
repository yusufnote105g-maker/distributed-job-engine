#!/bin/bash

# Script to run the Distributed Job Engine benchmark

set -e

# Configuration
JOBS=${1:-1000}
WORKERS=${2:-4}
DURATION=${3:-60}
HOST=${4:-localhost}
PORT=${5:-8000}

echo "=== Distributed Job Engine Benchmark ==="
echo "Jobs: $JOBS"
echo "Workers: $WORKERS"
echo "Duration: $DURATION seconds"
echo "Host: $HOST"
echo "Port: $PORT"
echo "======================================"

# Check if the job engine is running
echo "Checking if job engine is running..."
if ! curl -s "http://$HOST:$PORT/api/v1/health" > /dev/null; then
    echo "Error: Job engine is not running at http://$HOST:$PORT"
    echo "Please start the job engine first:"
    echo "  python -m uvicorn src.main:app --host $HOST --port $PORT"
    exit 1
fi

echo "Job engine is running. Starting benchmark..."

# Run the benchmark
cd "$(dirname "$0")/.."
python benchmark/benchmark.py \
    --jobs $JOBS \
    --workers $WORKERS \
    --duration $DURATION \
    --host $HOST \
    --port $PORT

echo "Benchmark completed. Results saved to benchmark/benchmark_results.json"

# Display summary if results exist
if [ -f "benchmark/benchmark_results.json" ]; then
    echo ""
    echo "=== BENCHMARK SUMMARY ==="
    python -c "
import json
with open('benchmark/benchmark_results.json', 'r') as f:
    results = json.load(f)
    
metrics = results['metrics']
print(f'Total jobs: {metrics[\"total_jobs\"]}')
print(f'Jobs completed: {metrics[\"jobs_completed\"]}')
print(f'Jobs failed: {metrics[\"jobs_failed\"]}')
print(f'Throughput: {metrics[\"throughput_jobs_per_sec\"]:.2f} jobs/sec')
print(f'Average latency: {metrics[\"avg_latency_ms\"]:.2f}ms')
print(f'P95 latency: {metrics[\"p95_latency_ms\"]:.2f}ms')
print(f'Worker utilization: {metrics[\"avg_worker_utilization\"]:.2%}')
"
fi