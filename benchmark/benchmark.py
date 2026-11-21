#!/usr/bin/env python3
"""
Benchmark script for Distributed Job Engine

This script measures:
- Jobs processed per second
- Average execution latency
- P95 latency
- Worker utilization
- Database contention

Usage:
    python benchmark.py --jobs 1000 --workers 4 --duration 60
"""

import asyncio
import argparse
import time
import statistics
import json
from datetime import datetime
from typing import List, Dict, Any
import httpx
import psutil
import os

from src.config import JobEngineConfig
from src.services.database import DatabaseService
from src.services.job_processor import JobProcessor


class BenchmarkMetrics:
    def __init__(self):
        self.jobs_completed = 0
        self.jobs_failed = 0
        self.jobs_cancelled = 0
        self.latencies = []
        self.start_time = time.time()
        self.end_time = None
        self.worker_utilization = []
        self.database_operations = 0
        
    def add_job_result(self, success: bool, latency: float):
        if success:
            self.jobs_completed += 1
        else:
            self.jobs_failed += 1
        self.latencies.append(latency)
        
    def add_cancelled_job(self):
        self.jobs_cancelled += 1
        
    def record_worker_utilization(self, utilization: float):
        self.worker_utilization.append(utilization)
        
    def record_database_operation(self):
        self.database_operations += 1
        
    def get_stats(self) -> Dict[str, Any]:
        if not self.latencies:
            return {
                "total_jobs": 0,
                "jobs_completed": 0,
                "jobs_failed": 0,
                "jobs_cancelled": 0,
                "throughput_jobs_per_sec": 0,
                "avg_latency_ms": 0,
                "p95_latency_ms": 0,
                "min_latency_ms": 0,
                "max_latency_ms": 0,
                "avg_worker_utilization": 0,
                "total_database_operations": 0,
                "duration_seconds": 0
            }
        
        duration = self.end_time - self.start_time if self.end_time else time.time() - self.start_time
        
        return {
            "total_jobs": len(self.latencies) + self.jobs_cancelled,
            "jobs_completed": self.jobs_completed,
            "jobs_failed": self.jobs_failed,
            "jobs_cancelled": self.jobs_cancelled,
            "throughput_jobs_per_sec": len(self.latencies) / duration,
            "avg_latency_ms": statistics.mean(self.latencies) * 1000,
            "p95_latency_ms": statistics.quantiles(self.latencies, n=20)[18] * 1000,  # 95th percentile
            "min_latency_ms": min(self.latencies) * 1000,
            "max_latency_ms": max(self.latencies) * 1000,
            "avg_worker_utilization": statistics.mean(self.worker_utilization) if self.worker_utilization else 0,
            "total_database_operations": self.database_operations,
            "duration_seconds": duration
        }


class JobSubmitter:
    def __init__(self, api_url: str, num_jobs: int):
        self.api_url = api_url
        self.num_jobs = num_jobs
        self.submitted_jobs = []
        self.client = httpx.AsyncClient(timeout=30.0)
        
    async def submit_jobs(self) -> List[str]:
        """Submit all jobs and return job IDs"""
        job_ids = []
        
        for i in range(self.num_jobs):
            payload = f"benchmark_job_{i}_{int(time.time())}"
            
            try:
                response = await self.client.post(
                    f"{self.api_url}/api/v1/jobs",
                    json={
                        "payload": payload,
                        "priority": "normal",
                        "idempotency_key": f"benchmark_{i}"
                    }
                )
                
                if response.status_code == 201:
                    job_data = response.json()
                    job_ids.append(job_data["job_id"])
                    self.submitted_jobs.append({
                        "job_id": job_data["job_id"],
                        "submitted_at": time.time()
                    })
                else:
                    print(f"Failed to submit job {i}: {response.status_code}")
                    
            except Exception as e:
                print(f"Error submitting job {i}: {e}")
                
        return job_ids
    
    async def check_job_status(self, job_id: str) -> Dict[str, Any]:
        """Check the status of a specific job"""
        try:
            response = await self.client.get(f"{self.api_url}/api/v1/jobs/{job_id}")
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get system metrics"""
        try:
            response = await self.client.get(f"{self.api_url}/api/v1/metrics")
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}
    
    async def close(self):
        await self.client.aclose()


class SystemMonitor:
    def __init__(self, interval: float = 1.0):
        self.interval = interval
        self.running = False
        
    async def monitor_worker_utilization(self, job_processor: JobProcessor) -> float:
        """Monitor worker utilization"""
        if not job_processor.workers:
            return 0.0
        
        active_workers = 0
        for worker in job_processor.workers:
            if not worker.done():
                active_workers += 1
                
        return active_workers / len(job_processor.workers)
    
    async def monitor_database_operations(self, db_service: DatabaseService) -> int:
        """Monitor database operations"""
        # This is a simplified implementation
        # In a real system, you would track actual database operations
        return 0
    
    async def monitor_system_resources(self) -> Dict[str, float]:
        """Monitor system resources"""
        cpu_percent = psutil.cpu_percent()
        memory_percent = psutil.virtual_memory().percent
        disk_percent = psutil.disk_usage('/').percent
        
        return {
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent,
            "disk_percent": disk_percent
        }


async def run_benchmark(args):
    """Run the benchmark"""
    print(f"Starting benchmark with {args.jobs} jobs, {args.workers} workers, duration: {args.duration}s")
    
    # Initialize services
    config = JobEngineConfig()
    config.worker_count = args.workers
    config.max_retries = 0  # Disable retries for benchmark
    
    db_service = DatabaseService(config)
    await db_service._init_db()
    
    job_processor = JobProcessor(config, db_service)
    
    # Start job processor
    await job_processor.start()
    
    # Wait for services to be ready
    await asyncio.sleep(2)
    
    # Initialize metrics
    metrics = BenchmarkMetrics()
    monitor = SystemMonitor()
    
    # Submit jobs
    print("Submitting jobs...")
    submitter = JobSubmitter(f"http://{config.api_host}:{config.api_port}", args.jobs)
    job_ids = await submitter.submit_jobs()
    
    print(f"Submitted {len(job_ids)} jobs")
    
    # Monitor job processing
    print("Monitoring job processing...")
    start_time = time.time()
    
    async def monitor_progress():
        """Monitor progress and collect metrics"""
        while time.time() - start_time < args.duration:
            # Check job status
            for job_info in metrics.submitted_jobs[:]:  # Use a copy to allow modification
                job_id = job_info["job_id"]
                
                job_data = await submitter.check_job_status(job_id)
                
                if "error" not in job_data:
                    if job_data["status"] in ["completed", "failed", "dead_letter"]:
                        latency = time.time() - job_info["submitted_at"]
                        success = job_data["status"] == "completed"
                        metrics.add_job_result(success, latency)
                        metrics.submitted_jobs.remove(job_info)
                        
                        # Record worker utilization
                        utilization = await monitor.monitor_worker_utilization(job_processor)
                        metrics.record_worker_utilization(utilization)
                        
                        # Record database operations
                        await monitor.monitor_database_operations(db_service)
                        metrics.record_database_operation()
                        
                        print(f"Job {job_id} completed in {latency:.3f}s (status: {job_data['status']})")
    
    # Start monitoring
    monitor_task = asyncio.create_task(monitor_progress())
    
    # Wait for benchmark duration
    await asyncio.sleep(args.duration)
    
    # Stop monitoring
    metrics.end_time = time.time()
    monitor_task.cancel()
    
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass
    
    # Get final metrics
    final_metrics = await submitter.get_metrics()
    
    # Calculate final statistics
    stats = metrics.get_stats()
    
    # Print results
    print("\n=== BENCHMARK RESULTS ===")
    print(f"Total duration: {stats['duration_seconds']:.2f}s")
    print(f"Jobs submitted: {len(job_ids)}")
    print(f"Jobs completed: {stats['jobs_completed']}")
    print(f"Jobs failed: {stats['jobs_failed']}")
    print(f"Jobs cancelled: {stats['jobs_cancelled']}")
    print(f"Throughput: {stats['throughput_jobs_per_sec']:.2f} jobs/sec")
    print(f"Average latency: {stats['avg_latency_ms']:.2f}ms")
    print(f"P95 latency: {stats['p95_latency_ms']:.2f}ms")
    print(f"Min latency: {stats['min_latency_ms']:.2f}ms")
    print(f"Max latency: {stats['max_latency_ms']:.2f}ms")
    print(f"Average worker utilization: {stats['avg_worker_utilization']:.2%}")
    print(f"Total database operations: {stats['total_database_operations']}")
    print(f"System metrics: {final_metrics}")
    
    # Save results to file
    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "config": {
            "jobs": args.jobs,
            "workers": args.workers,
            "duration": args.duration
        },
        "metrics": stats,
        "system_metrics": final_metrics
    }
    
    with open("benchmark_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print("\nResults saved to benchmark_results.json")
    
    # Cleanup
    await submitter.close()
    await job_processor.stop()
    await db_service.engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Benchmark Distributed Job Engine")
    parser.add_argument("--jobs", type=int, default=1000, help="Number of jobs to submit")
    parser.add_argument("--workers", type=int, default=4, help="Number of worker processes")
    parser.add_argument("--duration", type=int, default=60, help="Benchmark duration in seconds")
    parser.add_argument("--host", type=str, default="localhost", help="API host")
    parser.add_argument("--port", type=int, default=8000, help="API port")
    
    args = parser.parse_args()
    
    # Run benchmark
    asyncio.run(run_benchmark(args))


if __name__ == "__main__":
    main()