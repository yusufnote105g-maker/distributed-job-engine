# Quick start

```bash
pip install -r requirements.txt
scripts/run.sh
```

In another terminal:

```bash
# health
curl -s localhost:8000/api/v1/health

# submit a job
curl -s -X POST localhost:8000/api/v1/jobs \
  -H 'content-type: application/json' \
  -d '{"payload":"{\"task\":\"sleep\",\"seconds\":1}","priority":"high"}'

# list, then poll one job
curl -s 'localhost:8000/api/v1/jobs?limit=5'
curl -s localhost:8000/api/v1/jobs/<job_id>

# counters
curl -s localhost:8000/api/v1/metrics
```

Run the checks:

```bash
scripts/run_tests.sh
scripts/run_benchmark.sh 500 4 0.01
```

Configuration is environment-based; see the table in `README.md`.
