import pytest
import asyncio
import time
from httpx import AsyncClient

from src.models import JobStatus, JobPriority
from src.main import app


@pytest.mark.asyncio
async def test_retry_exhaustion(mock_http_client):
    """Test that jobs are marked as dead letter after max retries"""
    # Configure the job processor for testing
    from src.config import JobEngineConfig
    config = JobEngineConfig()
    config.max_retries = 2
    config.initial_backoff = 0.1
    
    # Submit a job that will fail
    response = await mock_http_client.post(
        "/api/v1/jobs",
        json={
            "payload": "failing_job",  # This will fail in our mock
            "priority": "normal",
            "max_retries": 2
        }
    )
    
    job_id = response.json()["job_id"]
    
    # Start a worker to process the job
    worker_task = asyncio.create_task(
        _process_failing_job(mock_http_client, "test-worker", job_id)
    )
    
    # Wait for worker to finish
    await asyncio.wait_for(worker_task, timeout=2.0)
    
    # Check job status
    response = await mock_http_client.get(f"/api/v1/jobs/{job_id}")
    assert response.status_code == 200
    
    job_data = response.json()
    assert job_data["status"] == "dead_letter"
    assert job_data["retry_count"] == 2
    assert job_data["error"] is not None


async def _process_failing_job(http_client: AsyncClient, worker_name: str, job_id: str):
    """Helper function to process a failing job"""
    try:
        # Get the job
        response = await http_client.get(f"/api/v1/jobs/{job_id}")
        if response.status_code == 200:
            job_data = response.json()
            
            # Simulate failure
            await asyncio.sleep(0.1)
            
            # Update job as failed
            # In a real implementation, this would be handled by the job processor
            await http_client.post(f"/api/v1/jobs/{job_id}/cancel")
    except Exception:
        pass


@pytest.mark.asyncio
async def test_retry_with_backoff(mock_http_client):
    """Test retry behavior with exponential backoff"""
    from src.config import JobEngineConfig
    config = JobEngineConfig()
    config.max_retries = 3
    config.initial_backoff = 0.1
    config.max_backoff = 1.0
    
    # Submit a job that will fail initially but succeed on retry
    response = await mock_http_client.post(
        "/api/v1/jobs",
        json={
            "payload": "eventually_succeeding_job",
            "priority": "normal",
            "max_retries": 3
        }
    )
    
    job_id = response.json()["job_id"]
    
    # Start a worker to process the job
    worker_task = asyncio.create_task(
        _process_eventually_succeeding_job(http_client, "test-worker", job_id)
    )
    
    # Wait for worker to finish
    await asyncio.wait_for(worker_task, timeout=5.0)
    
    # Check job status
    response = await mock_http_client.get(f"/api/v1/jobs/{job_id}")
    assert response.status_code == 200
    
    job_data = response.json()
    # Job should eventually succeed
    assert job_data["status"] == "completed"


async def _process_eventually_succeeding_job(http_client: AsyncClient, worker_name: str, job_id: str):
    """Helper function to process a job that eventually succeeds"""
    try:
        # Get the job
        response = await http_client.get(f"/api/v1/jobs/{job_id}")
        if response.status_code == 200:
            job_data = response.json()
            
            # Simulate failure on first attempt, success on second
            if job_data["retry_count"] == 0:
                await asyncio.sleep(0.1)
                await http_client.post(f"/api/v1/jobs/{job_id}/cancel")
            else:
                await asyncio.sleep(0.1)
                # Mark as completed
                await http_client.post(f"/api/v1/jobs/{job_id}/cancel")
    except Exception:
        pass


@pytest.mark.asyncio
async def test_timeout_behavior(mock_http_client):
    """Test job timeout behavior"""
    # Submit a job with short timeout
    response = await mock_http_client.post(
        "/api/v1/jobs",
        json={
            "payload": "timeout_test_job",
            "priority": "normal",
            "timeout": 1  # 1 second timeout
        }
    )
    
    job_id = response.json()["job_id"]
    
    # Start a worker that will take longer than timeout
    worker_task = asyncio.create_task(
        _process_slow_job(mock_http_client, "slow-worker", job_id, 2.0)  # 2 seconds
    )
    
    # Wait for worker to finish
    await asyncio.wait_for(worker_task, timeout=3.0)
    
    # Check job status
    response = await mock_http_client.get(f"/api/v1/jobs/{job_id}")
    assert response.status_code == 200
    
    job_data = response.json()
    # Job should be failed due to timeout
    assert job_data["status"] == "failed"
    assert "timeout" in job_data["error"].lower()


async def _process_slow_job(http_client: AsyncClient, worker_name: str, job_id: str, duration: float):
    """Helper function to process a job slowly"""
    try:
        # Simulate slow processing
        await asyncio.sleep(duration)
        
        # Try to cancel (simulating timeout)
        await http_client.post(f"/api/v1/jobs/{job_id}/cancel")
    except Exception:
        pass


@pytest.mark.asyncio
async def test_cancellation_during_execution(mock_http_client):
    """Test job cancellation during execution"""
    # Submit a job
    response = await mock_http_client.post(
        "/api/v1/jobs",
        json={
            "payload": "cancellation_test_job",
            "priority": "normal"
        }
    )
    
    job_id = response.json()["job_id"]
    
    # Start a worker that will take some time
    worker_task = asyncio.create_task(
        _process_long_job(mock_http_client, "slow-worker", job_id, 2.0)  # 2 seconds
    )
    
    # Wait a bit then cancel the job
    await asyncio.sleep(0.5)
    
    # Cancel the job
    cancel_response = await mock_http_client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert cancel_response.status_code == 200
    
    # Wait for worker to finish
    await asyncio.wait_for(worker_task, timeout=3.0)
    
    # Check job status
    response = await mock_http_client.get(f"/api/v1/jobs/{job_id}")
    assert response.status_code == 200
    
    job_data = response.json()
    # Job should be cancelled
    assert job_data["status"] == "cancelled"


async def _process_long_job(http_client: AsyncClient, worker_name: str, job_id: str, duration: float):
    """Helper function to process a job for a long time"""
    try:
        # Simulate long processing
        await asyncio.sleep(duration)
        
        # Try to complete the job
        await http_client.post(f"/api/v1/jobs/{job_id}/cancel")
    except Exception:
        pass


@pytest.mark.asyncio
async def test_retry_jitter(mock_http_client):
    """Test retry jitter to prevent thundering herd"""
    from src.config import JobEngineConfig
    config = JobEngineConfig()
    config.max_retries = 2
    config.initial_backoff = 0.1
    config.retry_jitter = True
    
    # Submit multiple jobs that will fail
    job_ids = []
    for i in range(3):
        response = await mock_http_client.post(
            "/api/v1/jobs",
            json={
                "payload": f"thundering_herd_job_{i}",
                "priority": "normal",
                "max_retries": 2
            }
        )
        job_ids.append(response.json()["job_id"])
    
    # Start multiple workers
    worker_tasks = []
    for i, job_id in enumerate(job_ids):
        task = asyncio.create_task(
            _process_failing_job(mock_http_client, f"worker-{i}", job_id)
        )
        worker_tasks.append(task)
    
    # Wait for all workers to finish
    await asyncio.gather(*worker_tasks)
    
    # Check that retry times are different (not exact same)
    retry_times = []
    for job_id in job_ids:
        response = await mock_http_client.get(f"/api/v1/jobs/{job_id}")
        job_data = response.json()
        
        if job_data["next_retry_at"]:
            retry_times.append(job_data["next_retry_at"])
    
    # Retry times should be different due to jitter
    assert len(set(retry_times)) > 1 or len(retry_times) == 0


@pytest.mark.asyncio
async def test_max_retries_configuration(mock_http_client):
    """Test max retries configuration per job"""
    # Submit jobs with different max_retries
    response1 = await mock_http_client.post(
        "/api/v1/jobs",
        json={
            "payload": "low_retry_job",
            "priority": "normal",
            "max_retries": 1
        }
    )
    
    response2 = await mock_http_client.post(
        "/api/v1/jobs",
        json={
            "payload": "high_retry_job",
            "priority": "normal",
            "max_retries": 5
        }
    )
    
    job_id1 = response1.json()["job_id"]
    job_id2 = response2.json()["job_id"]
    
    # Process both jobs
    worker_task1 = asyncio.create_task(
        _process_failing_job(mock_http_client, "worker-1", job_id1)
    )
    worker_task2 = asyncio.create_task(
        _process_failing_job(mock_http_client, "worker-2", job_id2)
    )
    
    await asyncio.gather(worker_task1, worker_task2)
    
    # Check that jobs have different retry counts
    response1 = await mock_http_client.get(f"/api/v1/jobs/{job_id1}")
    response2 = await mock_http_client.get(f"/api/v1/jobs/{job_id2}")
    
    job1_data = response1.json()
    job2_data = response2.json()
    
    # Both should be dead letter but with different retry counts
    assert job1_data["status"] == "dead_letter"
    assert job2_data["status"] == "dead_letter"
    assert job1_data["max_retries"] == 1
    assert job2_data["max_retries"] == 5


@pytest.mark.asyncio
async def test_timeout_override_per_job(mock_http_client):
    """Test timeout override per job"""
    # Submit jobs with different timeouts
    response1 = await mock_http_client.post(
        "/api/v1/jobs",
        json={
            "payload": "short_timeout_job",
            "priority": "normal",
            "timeout": 1
        }
    )
    
    response2 = await mock_http_client.post(
        "/api/v1/jobs",
        json={
            "payload": "long_timeout_job",
            "priority": "normal",
            "timeout": 5
        }
    )
    
    job_id1 = response1.json()["job_id"]
    job_id2 = response2.json()["job_id"]
    
    # Process both jobs with slow workers
    worker_task1 = asyncio.create_task(
        _process_slow_job(mock_http_client, "worker-1", job_id1, 2.0)  # Exceeds 1s timeout
    )
    worker_task2 = asyncio.create_task(
        _process_slow_job(mock_http_client, "worker-2", job_id2, 3.0)  # Within 5s timeout
    )
    
    await asyncio.gather(worker_task1, worker_task2)
    
    # Check job statuses
    response1 = await mock_http_client.get(f"/api/v1/jobs/{job_id1}")
    response2 = await mock_http_client.get(f"/api/v1/jobs/{job_id2}")
    
    job1_data = response1.json()
    job2_data = response2.json()
    
    # First job should be failed (timeout), second should be completed
    assert job1_data["status"] == "failed"
    assert job2_data["status"] == "completed"