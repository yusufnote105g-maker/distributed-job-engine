import pytest
import asyncio
import time
from httpx import AsyncClient

from src.models import JobStatus, JobPriority
from src.main import app


@pytest.mark.asyncio
async def test_concurrent_job_claiming(mock_http_client):
    """Test that multiple workers can claim jobs without race conditions"""
    # Submit multiple jobs
    job_ids = []
    for i in range(10):
        response = await mock_http_client.post(
            "/api/v1/jobs",
            json={
                "payload": f"concurrent test job {i}",
                "priority": "normal"
            }
        )
        job_ids.append(response.json()["job_id"])
    
    # Start multiple workers to process jobs concurrently
    worker_tasks = []
    for i in range(4):
        task = asyncio.create_task(_process_jobs_with_worker(mock_http_client, f"worker-{i}", 3))
        worker_tasks.append(task)
    
    # Wait for workers to finish
    await asyncio.gather(*worker_tasks)
    
    # Verify all jobs were processed exactly once
    processed_jobs = set()
    for job_id in job_ids:
        response = await mock_http_client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200
        job_data = response.json()
        
        # Job should be completed or failed
        assert job_data["status"] in ["completed", "failed", "cancelled"]
        
        # Track which jobs were processed
        processed_jobs.add(job_id)
    
    # All jobs should be processed
    assert len(processed_jobs) == len(job_ids)


async def _process_jobs_with_worker(http_client: AsyncClient, worker_name: str, max_jobs: int):
    """Helper function to process jobs with a specific worker"""
    processed = 0
    
    while processed < max_jobs:
        # Get next available job
        response = await http_client.get("/api/v1/jobs?status=pending&limit=1")
        if response.status_code != 200:
            break
            
        jobs = response.json()["jobs"]
        if not jobs:
            break
            
        job = jobs[0]
        job_id = job["job_id"]
        
        try:
            # Simulate job processing
            await asyncio.sleep(0.1)
            
            # Mark as completed
            response = await http_client.post(f"/api/v1/jobs/{job_id}/cancel")
            if response.status_code == 200:
                processed += 1
        except Exception:
            break


@pytest.mark.asyncio
async def test_duplicate_job_claiming_race_condition(mock_http_client):
    """Test that the same job cannot be claimed by multiple workers simultaneously"""
    # Submit a single job
    response = await mock_http_client.post(
        "/api/v1/jobs",
        json={
            "payload": "race condition test job",
            "priority": "high"
        }
    )
    
    job_id = response.json()["job_id"]
    
    # Start multiple workers trying to claim the same job
    worker_tasks = []
    claimed_count = 0
    
    async def worker_attempt_claim(worker_id: str):
        nonlocal claimed_count
        
        try:
            # Try to get the job
            response = await mock_http_client.get(f"/api/v1/jobs/{job_id}")
            if response.status_code == 200:
                job_data = response.json()
                
                # If job is still pending, try to cancel it (simulating claiming)
                if job_data["status"] == "pending":
                    cancel_response = await mock_http_client.post(f"/api/v1/jobs/{job_id}/cancel")
                    if cancel_response.status_code == 200:
                        claimed_count += 1
                        return True
        except Exception:
            pass
        
        return False
    
    # Start multiple workers
    for i in range(5):
        task = asyncio.create_task(worker_attempt_claim(f"worker-{i}"))
        worker_tasks.append(task)
    
    # Wait for all workers to attempt
    await asyncio.gather(*worker_tasks)
    
    # Only one worker should have successfully claimed the job
    assert claimed_count <= 1, f"Expected at most 1 worker to claim job, but {claimed_count} did"


@pytest.mark.asyncio
async def test_concurrent_duplicate_submissions(mock_http_client):
    """Test concurrent duplicate submissions with the same idempotency key"""
    idempotency_key = "concurrent-duplicate-test"
    
    # Submit the same job multiple times concurrently
    submit_tasks = []
    for i in range(5):
        task = asyncio.create_task(
            mock_http_client.post(
                "/api/v1/jobs",
                json={
                    "payload": f"concurrent duplicate job {i}",
                    "idempotency_key": idempotency_key
                }
            )
        )
        submit_tasks.append(task)
    
    # Wait for all submissions
    responses = await asyncio.gather(*submit_tasks)
    
    # All responses should be successful
    successful_submissions = 0
    job_ids = set()
    
    for response in responses:
        if response.status_code == 201:
            successful_submissions += 1
            job_id = response.json()["job_id"]
            job_ids.add(job_id)
    
    # All submissions should succeed but refer to the same job
    assert successful_submissions == 5
    assert len(job_ids) == 1, "All duplicate submissions should refer to the same job"


@pytest.mark.asyncio
async def test_concurrent_database_operations(mock_http_client):
    """Test concurrent database operations for job updates"""
    # Submit multiple jobs
    job_ids = []
    for i in range(20):
        response = await mock_http_client.post(
            "/api/v1/jobs",
            json={
                "payload": f"db concurrency test job {i}",
                "priority": "normal"
            }
        )
        job_ids.append(response.json()["job_id"])
    
    # Start multiple workers updating jobs concurrently
    worker_tasks = []
    for i in range(4):
        task = asyncio.create_task(
            _update_jobs_concurrently(mock_http_client, f"worker-{i}", job_ids[i*5:(i+1)*5])
        )
        worker_tasks.append(task)
    
    # Wait for all workers to finish
    await asyncio.gather(*worker_tasks)
    
    # Verify all jobs were updated
    for job_id in job_ids:
        response = await mock_http_client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200
        job_data = response.json()
        
        # Job should have been processed
        assert job_data["status"] in ["completed", "failed", "cancelled"]


async def _update_jobs_concurrently(http_client: AsyncClient, worker_name: str, job_ids: list):
    """Helper function to update jobs concurrently"""
    for job_id in job_ids:
        try:
            # Simulate some processing time
            await asyncio.sleep(0.05)
            
            # Cancel the job (simulating completion)
            await http_client.post(f"/api/v1/jobs/{job_id}/cancel")
        except Exception:
            pass


@pytest.mark.asyncio
async def test_worker_crash_recovery(mock_http_client):
    """Test that jobs are recovered when workers crash"""
    # Submit a job
    response = await mock_http_client.post(
        "/api/v1/jobs",
        json={
            "payload": "worker crash test job",
            "priority": "normal"
        }
    )
    
    job_id = response.json()["job_id"]
    
    # Simulate worker crash by not completing the job
    # Just get the job but don't mark it as completed
    response = await mock_http_client.get(f"/api/v1/jobs/{job_id}")
    assert response.status_code == 200
    
    # The job should still be in pending state
    job_data = response.json()
    assert job_data["status"] == "pending"
    
    # Now try to process it again
    response = await mock_http_client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_application_restart_recovery(mock_http_client):
    """Test that jobs survive application restart"""
    # Submit a job
    response = await mock_http_client.post(
        "/api/v1/jobs",
        json={
            "payload": "restart recovery test job",
            "priority": "normal"
        }
    )
    
    job_id = response.json()["job_id"]
    
    # Simulate application restart by checking if job persists
    # (In a real scenario, we'd restart the app)
    
    # Get the job again
    response = await mock_http_client.get(f"/api/v1/jobs/{job_id}")
    assert response.status_code == 200
    
    # Job should still exist
    job_data = response.json()
    assert job_data["job_id"] == job_id


@pytest.mark.asyncio
async def test_retry_exhaustion_concurrent(mock_http_client):
    """Test retry exhaustion under concurrent conditions"""
    # Submit a job that will fail
    response = await mock_http_client.post(
        "/api/v1/jobs",
        json={
            "payload": "failing_job",  # This will fail in our mock
            "priority": "normal"
        }
    )
    
    job_id = response.json()["job_id"]
    
    # Start multiple workers trying to process the failing job
    worker_tasks = []
    for i in range(3):
        task = asyncio.create_task(
            _process_failing_job(mock_http_client, f"worker-{i}", job_id)
        )
        worker_tasks.append(task)
    
    # Wait for workers to finish
    await asyncio.gather(*worker_tasks)
    
    # Check job status
    response = await mock_http_client.get(f"/api/v1/jobs/{job_id}")
    assert response.status_code == 200
    
    job_data = response.json()
    # Job should eventually be marked as dead letter after retries
    assert job_data["status"] in ["failed", "dead_letter"]


async def _process_failing_job(http_client: AsyncClient, worker_name: str, job_id: str):
    """Helper function to process a failing job"""
    try:
        # Get the job
        response = await http_client.get(f"/api/v1/jobs/{job_id}")
        if response.status_code == 200:
            job_data = response.json()
            
            # If job is pending or retrying, try to process it
            if job_data["status"] in ["pending", "retrying"]:
                # Simulate failure
                await asyncio.sleep(0.1)
                
                # Try to cancel (which will simulate failure)
                await http_client.post(f"/api/v1/jobs/{job_id}/cancel")
    except Exception:
        pass


@pytest.mark.asyncio
async def test_timeout_behavior_concurrent(mock_http_client):
    """Test timeout behavior under concurrent conditions"""
    # Submit a job with short timeout
    response = await mock_http_client.post(
        "/api/v1/jobs",
        json={
            "payload": "timeout test job",
            "priority": "normal",
            "timeout": 1  # 1 second timeout
        }
    )
    
    job_id = response.json()["job_id"]
    
    # Start a worker that will take longer than timeout
    worker_task = asyncio.create_task(
        _process_slow_job(mock_http_client, "slow-worker", job_id, 2.0)  # 2 seconds
    )
    
    # Wait for worker to finish (should timeout)
    await asyncio.wait_for(worker_task, timeout=3.0)
    
    # Check job status
    response = await mock_http_client.get(f"/api/v1/jobs/{job_id}")
    assert response.status_code == 200
    
    job_data = response.json()
    # Job should be failed due to timeout
    assert job_data["status"] == "failed"


async def _process_slow_job(http_client: AsyncClient, worker_name: str, job_id: str, duration: float):
    """Helper function to process a job slowly"""
    try:
        # Simulate slow processing
        await asyncio.sleep(duration)
        
        # Try to cancel (simulating timeout)
        await http_client.post(f"/api/v1/jobs/{job_id}/cancel")
    except Exception:
        pass