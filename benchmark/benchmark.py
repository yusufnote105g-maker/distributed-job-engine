#!/usr/bin/env python3
"""Reproducible benchmark for the Distributed Job Engine.

Runs the engine in-process against a throwaway SQLite database, so results do
not depend on a separately started server.

Usage:
    python3 benchmark/benchmark.py --jobs 500 --workers 4 --sleep 0.01
"""

import argparse
import asyncio
import json
import statistics
import tempfile
import time
from pathlib import Path

from src.config import JobEngineConfig
from src.services.database import DatabaseService
from src.services.job_processor import JobProcessor

TERMINAL = {"completed", "failed", "dead_letter", "cancelled"}


def percentile(values, pct):
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((pct / 100) * (len(ordered) - 1))))
    return ordered[index]


def summarize(values):
    if not values:
        return {"count": 0, "avg": None, "p50": None, "p95": None, "max": None}
    return {
        "count": len(values),
        "avg": round(statistics.fmean(values), 6),
        "p50": round(percentile(values, 50), 6),
        "p95": round(percentile(values, 95), 6),
        "max": round(max(values), 6),
    }


async def run(args) -> dict:
    db_path = Path(args.db) if args.db else Path(
        tempfile.mkdtemp(prefix="job-engine-bench-")
    ) / "bench.db"

    config = JobEngineConfig(
        database_url=f"sqlite:///{db_path}",
        worker_count=args.workers,
        poll_interval=0.005,
        health_check_interval=0.05,
        max_retries=2,
        initial_backoff=0.05,
        max_backoff=0.5,
        log_level="ERROR",
    )

    db = DatabaseService(config)
    await db.initialize()
    processor = JobProcessor(config, db)
    await processor.start()

    payload = json.dumps({"task": "sleep", "seconds": args.sleep})

    submit_latencies = []
    job_ids = []
    submit_started = time.perf_counter()
    for _ in range(args.jobs):
        started = time.perf_counter()
        job = await processor.submit_job(payload=payload)
        submit_latencies.append(time.perf_counter() - started)
        job_ids.append(job["job_id"])
    submit_elapsed = time.perf_counter() - submit_started

    processing_started = time.perf_counter()
    deadline = processing_started + args.timeout
    while time.perf_counter() < deadline:
        stats = await db.stats()
        if stats["pending_jobs"] == 0 and stats["claimed_jobs"] == 0 and stats["running_jobs"] == 0:
            break
        await asyncio.sleep(0.02)
    processing_elapsed = time.perf_counter() - processing_started
    total_elapsed = time.perf_counter() - submit_started

    await processor.stop()

    final = await db.stats()
    execution_times = []
    for job_id in job_ids:
        job = await db.get_job(job_id)
        if job and job["execution_time"] is not None:
            execution_times.append(job["execution_time"])

    processed = final["completed_jobs"] + final["failed_jobs"] + final["dead_letter_jobs"]
    busy_time = sum(execution_times)
    capacity = args.workers * processing_elapsed if processing_elapsed > 0 else 0

    result = {
        "config": {
            "jobs": args.jobs,
            "workers": args.workers,
            "payload_sleep_seconds": args.sleep,
            "database": str(db_path),
        },
        "submission": {
            "wall_seconds": round(submit_elapsed, 4),
            "throughput_per_second": round(len(job_ids) / submit_elapsed, 2)
            if submit_elapsed
            else None,
            "latency": summarize(submit_latencies),
        },
        "processing": {
            "wall_seconds": round(processing_elapsed, 4),
            "jobs_processed": processed,
            "throughput_per_second": round(processed / processing_elapsed, 2)
            if processing_elapsed
            else None,
            "execution_latency": summarize(execution_times),
            "worker_utilization": round(min(busy_time / capacity, 1.0), 4)
            if capacity
            else 0.0,
        },
        "end_to_end": {
            "wall_seconds": round(total_elapsed, 4),
            "throughput_per_second": round(len(job_ids) / total_elapsed, 2)
            if total_elapsed
            else None,
        },
        "outcome": {
            "completed": final["completed_jobs"],
            "failed": final["failed_jobs"],
            "dead_letter": final["dead_letter_jobs"],
            "pending": final["pending_jobs"],
        },
    }

    await db.close()
    return result


def main():
    parser = argparse.ArgumentParser(description="Benchmark the job engine")
    parser.add_argument("--jobs", type=int, default=500)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--sleep", type=float, default=0.01, help="Simulated work per job (s)")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--db", default=None, help="SQLite file path (temp by default)")
    parser.add_argument(
        "--out", default="benchmark/benchmark_results.json", help="Output JSON path"
    )
    args = parser.parse_args()

    result = asyncio.run(run(args))
    result["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    sub = result["submission"]
    proc = result["processing"]
    print("=" * 62)
    print("DISTRIBUTED JOB ENGINE — BENCHMARK")
    print("=" * 62)
    print(f"Jobs / workers          : {args.jobs} / {args.workers}")
    print(f"Submit throughput       : {sub['throughput_per_second']} jobs/s")
    print(f"Submit latency p50/p95  : {sub['latency']['p50']}s / {sub['latency']['p95']}s")
    print(f"Processing throughput   : {proc['throughput_per_second']} jobs/s")
    print(f"End-to-end throughput   : {result['end_to_end']['throughput_per_second']} jobs/s")
    print(
        "Execution latency p50/p95: "
        f"{proc['execution_latency']['p50']}s / {proc['execution_latency']['p95']}s"
    )
    print(f"Worker utilization      : {proc['worker_utilization'] * 100:.1f}%")
    print(f"Outcome                 : {result['outcome']}")
    print(f"Saved to                : {out_path}")
    print("=" * 62)


if __name__ == "__main__":
    main()
