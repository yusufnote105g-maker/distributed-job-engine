# Distributed Job Engine Benchmark

This directory contains benchmarking tools for the Distributed Job Engine.

## Running the Benchmark

### Prerequisites
- Python 3.11+
- Required packages (see `requirements.txt`)
- The job engine must be running on the specified host and port

### Basic Usage

```bash
# Run benchmark with default settings (1000 jobs, 4 workers, 60 seconds)
python benchmark.py

# Customize benchmark parameters
python benchmark.py --jobs 5000 --workers 8 --duration 120

# Specify different host/port
python benchmark.py --host localhost --port 8001
```

### Benchmark Parameters

- `--jobs`: Number of jobs to submit (default: 1000)
- `--workers`: Number of worker processes (default: 4)
- `--duration`: Benchmark duration in seconds (default: 60)
- `--host`: API host (default: localhost)
- `--port`: API port (default: 8000)

### Output

The benchmark produces two types of output:

1. **Console Output**: Real-time progress updates and final results
2. **JSON File**: `benchmark_results.json` containing detailed metrics

### Metrics Collected

- **Throughput**: Jobs processed per second
- **Latency**: 
  - Average latency
  - P95 latency (95th percentile)
  - Min/Max latency
- **Worker Utilization**: Average percentage of active workers
- **Database Operations**: Total database operations performed
- **System Metrics**: Job status counts from the API

### Example Results

```json
{
  "timestamp": "2024-01-01T12:00:00.000000",
  "config": {
    "jobs": 1000,
    "workers": 4,
    "duration": 60
  },
  "metrics": {
    "total_jobs": 1000,
    "jobs_completed": 980,
    "jobs_failed": 20,
    "jobs_cancelled": 0,
    "throughput_jobs_per_sec": 16.33,
    "avg_latency_ms": 245.67,
    "p95_latency_ms": 312.45,
    "min_latency_ms": 123.45,
    "max_latency_ms": 567.89,
    "avg_worker_utilization": 0.85,
    "total_database_operations": 1200,
    "duration_seconds": 60.0
  }
}
```

### Analyzing Results

1. **Throughput**: Higher values indicate better processing capacity
2. **Latency**: Lower values indicate faster processing
3. **Worker Utilization**: Should be close to 1.0 (100%) for optimal scaling
4. **Error Rate**: Jobs failed / Total jobs should be low (< 1%)

### Performance Considerations

- Ensure the job engine is running before starting the benchmark
- Monitor system resources (CPU, memory) during the benchmark
- Run multiple iterations for stable results
- Consider adjusting worker count based on available CPU cores

### Troubleshooting

- Connection errors: Ensure the job engine is running and accessible
- High error rates: Check job payloads and system resources
- Low throughput: Consider increasing worker count or optimizing job processing