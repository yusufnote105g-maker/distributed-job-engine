# Benchmark

Measured on the development device (Android/aarch64, Python 3.14, SQLite WAL,
local flash storage). These numbers are indicative, not a guarantee: they are
dominated by SQLite's synchronous commit cost on this host.

## How to reproduce

```bash
scripts/run_benchmark.sh 500 4 0.01
# jobs=500, workers=4, simulated work per job=0.01s
```

The benchmark runs the engine in-process against a throwaway SQLite database
and writes `benchmark/benchmark_results.json`.

## Result

| Metric | Value |
| --- | --- |
| Jobs / workers | 500 / 4 |
| Simulated work per job | 0.01 s |
| Completed / failed / dead-letter | 500 / 0 / 0 |
| Submission throughput | 17.0 jobs/s |
| Submit latency p50 / p95 | 0.055 s / 0.114 s |
| End-to-end throughput | 16.9 jobs/s |
| Execution latency p50 / p95 | 0.044 s / 0.088 s |
| Worker utilisation | 100 % |

Run-to-run variance on this device is significant (observed end-to-end throughput
of 16.9–29.6 jobs/s for the same workload), because submission throughput is
dominated by flash-storage fsync latency. Treat the figures as an order of
magnitude, not a benchmark of the engine's CPU efficiency.

## How to read this

* **Submission is the bottleneck, not processing.** Every submission is its own
  SQLite transaction with an fsync. With four workers and 10 ms of work per job,
  the theoretical processing rate is ~400 jobs/s, but the run only reaches
  17–30 jobs/s end-to-end because the producer commits one row at a time. The
  processing-phase throughput (thousands of jobs/s) only reflects the small
  tail left after the producer finished.
* **Worker utilisation is 100 %** during the measured window: workers keep
  claiming jobs as they arrive.
* To raise end-to-end throughput on SQLite, batch submissions or accept weaker
  durability (`PRAGMA synchronous=OFF`). For sustained production load, move the
  queue to PostgreSQL (see `docs/known_limitations.md`).
