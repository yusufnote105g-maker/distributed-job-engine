import pytest
import asyncio
import time
from datetime import datetime, timedelta

from src.models import JobStatus, JobPriority
from src.services.job_processor import JobProcessor


@pytest.mark.asyncio
async def test_submit_job(db_service, job_processor, temp_db):
    """Test job submission"""
    job = await job_processor.submit_job(
        payload="test job",
        priority=JobPriority.HIGH,
        idempotency_key="test-idempotency"
    )
    
    assert job is not None
    assert job.payload == "test job"
    assert job.priority == JobPriority.HIGH
    assert job.idempotency_key == "test-idempotency"
    assert job.status == JobStatus.PENDING


@pytest.mark.asyncio
async def test_duplicate_job_submission(db_service, job_processor, temp_db):
    """Test duplicate job submission with idempotency key"""
    # Submit first job
    job1 = await job_processor.submit_job(
        payload="test job",
        idempotency_key="duplicate-test"
    )
    
    # Submit duplicate job
    job2 = await job_processor.submit_job(
        payload="different job",
        idempotency_key="duplicate-test"
    )
    
    # Should return the same job
    assert job1.id == job2.id


@pytest.mark.asyncio
async def test_job_claiming(db_service, job_processor, temp_db):
    """Test atomic job claiming"""
    # Submit a job
    job = await job_processor.submit_job(payload="test job")
    
    # Start a worker to claim the job
    worker_task = asyncio.create_task(job_processor._worker("test-worker"))
    
    # Wait a bit for worker to claim the job
    await asyncio.sleep(0.1)
    
    # Check that job is claimed
    updated_job = await job_processor.get_job(job.job_id)
    assert updated_job.status == JobStatus.CLAIMED
    assert updated_job.worker_id == "test-worker"
    
    # Stop worker
    job_processor.running = False
    await worker_task


@pytest.mark.asyncio
async def test_job_processing(db_service, job_processor, temp_db):
    """Test job processing and completion"""
    # Submit a job
    job = await job_processor.submit_job(payload="test job")
    
    # Start a worker
    worker_task = asyncio.create_task(job_processor._worker("test-worker"))
    
    # Wait for job to complete
    await asyncio.sleep(0.5)
    
    # Check job status
    updated_job = await job_processor.get_job(job.job_id)
    assert updated_job.status == JobStatus.COMPLETED
    assert updated_job.result is not None
    assert updated_job.execution_time is not None
    
    # Stop worker
    job_processor.running = False
    await worker_task


@pytest.mark.asyncio
async def test_job_retry(db_service, job_processor, temp_db):
    """Test job retry mechanism"""
    # Configure retry settings
    job_processor.config.max_retries = 2
    job_processor.config.initial_backoff = 0.1
    job_processor.config.max_backoff = 1.0
    
    # Submit a job that will fail
    job = await job_processor.submit_job(payload="failing_job")
    
    # Start a worker
    worker_task = asyncio.create_task(job_processor._worker("test-worker"))
    
    # Wait for job to fail and be retried
    await asyncio.sleep(1.0)
    
    # Check job status
    updated_job = await job_processor.get_job(job.job_id)
    assert updated_job.status == JobStatus.RETRYING
    assert updated_job.retry_count == 1
    assert updated_job.next_retry_at is not None
    
    # Stop worker
    job_processor.running = False
    await worker_task


@pytest.mark.asyncio
async def test_job_retry_exhaustion(db_service, job_processor, temp_db):
    """Test job retry exhaustion and dead letter handling"""
    # Configure retry settings
    job_processor.config.max_retries = 1
    job_processor.config.initial_backoff = 0.1
    
    # Submit a job that will fail
    job = await job_processor.submit_job(payload="failing_job")
    
    # Start a worker
    worker_task = asyncio.create_task(job_processor._worker("test-worker"))
    
    # Wait for job to exhaust retries
    await asyncio.sleep(1.0)
    
    # Check job status
    updated_job = await job_processor.get_job(job.job_id)
    assert updated_job.status == JobStatus.DEAD_LETTER
    assert updated_job.retry_count == 1
    assert updated_job.error is not None
    
    # Stop worker
    job_processor.running = False
    await worker_task


@pytest.mark.asyncio
async def test_job_cancellation(db_service, job_processor, temp_db):
    """Test job cancellation"""
    # Submit a job
    job = await job_processor.submit_job(payload="test job")
    
    # Cancel the job
    success = await job_processor.cancel_job(job.job_id)
    assert success is True
    
    # Check job status
    updated_job = await job_processor.get_job(job.job_id)
    assert updated_job.status == JobStatus.CANCELLED


@pytest.mark.asyncio
async def test_job_cancellation_already_running(db_service, job_processor, temp_db):
    """Test job cancellation of already running job"""
    # Submit a job
    job = await job_processor.submit_job(payload="test job")
    
    # Start a worker
    worker_task = asyncio.create_task(job_processor._worker("test-worker"))
    
    # Wait for job to be claimed
    await asyncio.sleep(0.1)
    
    # Try to cancel the job (should fail as it's already running)
    success = await job_processor.cancel_job(job.job_id)
    assert success is False
    
    # Stop worker
    job_processor.running = False
    await worker_task


@pytest.mark.asyncio
async def test_priority_ordering(db_service, job_processor, temp_db):
    """Test job priority ordering"""
    # Submit jobs with different priorities
    await job_processor.submit_job(payload="low priority", priority=JobPriority.LOW)
    await job_processor.submit_job(payload="high priority", priority=JobPriority.HIGH)
    await job_processor.submit_job(payload="critical priority", priority=JobPriority.CRITICAL)
    await job_processor.submit_job(payload="normal priority", priority=JobPriority.NORMAL)
    
    # Start multiple workers
    worker_tasks = []
    for i in range(4):
        worker_task = asyncio.create_task(job_processor._worker(f"worker-{i}"))
        worker_tasks.append(worker_task)
    
    # Wait for all jobs to be processed
    await asyncio.sleep(1.0)
    
    # Check processing order (critical should be processed first)
    jobs = await job_processor.get_jobs()
    
    # The first job processed should be critical
    critical_job = next((job for job in jobs if job.payload == "critical priority"), None)
    assert critical_job is not None
    
    # Stop workers
    job_processor.running = False
    await asyncio.gather(*worker_tasks)


@pytest.mark.asyncio
async def test_job_scheduler(db_service, job_processor, temp_db):
    """Test job scheduler for retrying failed jobs"""
    # Configure retry settings
    job_processor.config.max_retries = 3
    job_processor.config.initial_backoff = 0.1
    job_processor.config.health_check_interval = 0.05
    
    # Submit a job that will fail and be scheduled for retry
    job = await job_processor.submit_job(payload="failing_job")
    
    # Manually set job to retrying with past retry time
    from src.models import Job
    async with db_service.get_session() as session:
        await session.execute(
            f"UPDATE jobs SET status='{JobStatus.RETRYING.value}', "
            f"next_retry_at=datetime('now', '-1 second') WHERE job_id='{job.job_id}'"
        )
        await session.commit()
    
    # Start scheduler
    scheduler_task = asyncio.create_task(job_processor._job_scheduler())
    
    # Wait for scheduler to process the job
    await asyncio.sleep(0.2)
    
    # Check that job is back to pending
    updated_job = await job_processor.get_job(job.job_id)
    assert updated_job.status == JobStatus.PENDING
    
    # Stop scheduler
    job_processor.running = False
    await scheduler_task


@pytest.mark.asyncio
async def test_graceful_shutdown(db_service, job_processor, temp_db):
    """Test graceful shutdown of job processor"""
    # Submit a job
    job = await job_processor.submit_job(payload="test job")
    
    # Start workers
    worker_tasks = []
    for i in range(2):
        worker_task = asyncio.create_task(job_processor._worker(f"worker-{i}"))
        worker_tasks.append(worker_task)
    
    # Wait a bit for workers to start
    await asyncio.sleep(0.1)
    
    # Shutdown gracefully
    shutdown_task = asyncio.create_task(job_processor.stop())
    
    # Wait for shutdown to complete
    await shutdown_task
    
    # Check that workers are stopped
    assert job_processor.running is False
    
    # Check that job is still in pending (workers were stopped)
    updated_job = await job_processor.get_job(job.job_id)
    assert updated_job.status == JobStatus.PENDING


@pytest.mark.asyncio
async def test_race_condition_prevention(db_service, job_processor, temp_db):
    """Test prevention of race conditions in job claiming"""
    # Submit multiple jobs
    jobs = []
    for i in range(10):
        job = await job_processor.submit_job(payload=f"test job {i}")
        jobs.append(job)
    
    # Start multiple workers simultaneously
    worker_tasks = []
    for i in range(4):
        worker_task = asyncio.create_task(job_processor._worker(f"worker-{i}"))
        worker_tasks.append(worker_task)
    
    # Wait for all jobs to be processed
    await asyncio.sleep(1.0)
    
    # Stop workers
    job_processor.running = False
    await asyncio.gather(*worker_tasks)
    
    # Check that each job was processed exactly once
    processed_jobs = await job_processor.get_jobs()
    claimed_jobs = [job for job in processed_jobs if job.status in [JobStatus.COMPLETED, JobStatus.FAILED]]
    
    # All jobs should be claimed
    assert len(claimed_jobs) == len(jobs)
    
    # No job should be in claimed status (all should be completed or failed)
    remaining_claimed = [job for job in claimed_jobs if job.status == JobStatus.CLAIMED]
    assert len(remaining_claimed) == 0