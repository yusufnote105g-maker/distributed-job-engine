"""Retry policy and timeout behaviour."""

import asyncio

import pytest

from src.models import JobPriority  # noqa: F401
from src.services.job_processor import JobProcessor


async def wait_for_status(db, job_id, statuses, timeout=8.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        job = await db.get_job(job_id)
        if job and job["status"] in statuses:
            return job
        await asyncio.sleep(0.01)
    raise AssertionError(f"job {job_id} did not reach {statuses}: {job}")


@pytest.mark.asyncio
async def test_failure_schedules_retry_with_backoff(processor, db):
    processor.config.initial_backoff = 10.0
    processor.config.max_backoff = 60.0
    processor.config.retry_jitter = False

    job = await processor.submit_job(payload='{"task":"fail"}', max_retries=3)
    stored = await db.get_job(job["job_id"])
    await processor._handle_failure(stored, "boom", 0.01)

    retried = await db.get_job(job["job_id"])
    assert retried["status"] == "retrying"
    assert retried["retry_count"] == 1
    assert retried["next_retry_at"] is not None
    assert retried["error"] == "boom"


@pytest.mark.asyncio
async def test_zero_retries_goes_straight_to_dead_letter(processor, db):
    job = await processor.submit_job(payload='{"task":"fail"}', max_retries=0)
    stored = await db.get_job(job["job_id"])
    await processor._handle_failure(stored, "fatal", 0.01)

    dead = await db.get_job(job["job_id"])
    assert dead["status"] == "dead_letter"
    assert dead["retry_count"] == 0
    assert dead["error"] == "fatal"


@pytest.mark.asyncio
async def test_exponential_backoff_is_capped(processor):
    processor.config.initial_backoff = 1.0
    processor.config.max_backoff = 5.0
    processor.config.retry_jitter = False

    assert processor._backoff_delay(1) == 1.0
    assert processor._backoff_delay(2) == 2.0
    assert processor._backoff_delay(3) == 4.0
    assert processor._backoff_delay(4) == 5.0
    assert processor._backoff_delay(10) == 5.0


@pytest.mark.asyncio
async def test_jitter_stays_within_bounds(processor):
    processor.config.initial_backoff = 4.0
    processor.config.max_backoff = 60.0
    processor.config.retry_jitter = True

    samples = [processor._backoff_delay(1) for _ in range(200)]
    assert all(2.0 <= value <= 4.0 for value in samples)
    assert max(samples) - min(samples) > 0.1  # actual jitter, not a constant


@pytest.mark.asyncio
async def test_timeout_is_reported(running_engine):
    _, db, processor = running_engine
    job = await processor.submit_job(
        payload='{"task":"sleep","seconds":5}', timeout=1
    )
    failed = await wait_for_status(db, job["job_id"], {"failed"}, timeout=6.0)
    assert "timed out after 1s" in failed["error"]
    assert failed["completed_at"] is not None


@pytest.mark.asyncio
async def test_per_job_timeout_is_honoured(running_engine):
    _, db, processor = running_engine
    job = await processor.submit_job(
        payload='{"task":"sleep","seconds":0.2}', timeout=5
    )
    done = await wait_for_status(db, job["job_id"], {"completed"}, timeout=6.0)
    assert done["timeout"] == 5
    assert done["execution_time"] >= 0.2


@pytest.mark.asyncio
async def test_unknown_payload_succeeds_as_opaque_data(running_engine):
    _, db, processor = running_engine
    job = await processor.submit_job(payload="not-json-at-all")
    done = await wait_for_status(db, job["job_id"], {"completed"})
    assert done["result"].startswith("processed payload")


@pytest.mark.asyncio
async def test_processor_start_stop_is_idempotent(config, db):
    processor = JobProcessor(config, db)
    await processor.start()
    await processor.start()  # second start is a no-op
    assert processor.running
    await processor.stop()
    await processor.stop()  # second stop is a no-op
    assert not processor.running
