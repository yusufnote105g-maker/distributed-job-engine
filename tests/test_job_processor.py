"""Job processor tests (real database, real workers)."""

import asyncio

import pytest

from src.models import JobPriority, JobStatus


async def wait_for_status(db, job_id, statuses, timeout=5.0):
    """Poll until the job reaches one of the given statuses."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        job = await db.get_job(job_id)
        if job and job["status"] in statuses:
            return job
        await asyncio.sleep(0.01)
    raise AssertionError(f"job {job_id} did not reach {statuses}; last={job}")


@pytest.mark.asyncio
async def test_submit_job(processor):
    job = await processor.submit_job(
        payload="hello", priority=JobPriority.HIGH, idempotency_key="k1"
    )
    assert job["status"] == "pending"
    assert job["priority"] == "high"
    assert job["idempotency_key"] == "k1"
    assert job["retry_count"] == 0
    assert job["max_retries"] == processor.config.max_retries


@pytest.mark.asyncio
async def test_duplicate_submission_returns_same_job(processor):
    first = await processor.submit_job(payload="a", idempotency_key="dup")
    second = await processor.submit_job(payload="b", idempotency_key="dup")
    assert first["job_id"] == second["job_id"]
    assert second["payload"] == "a"


@pytest.mark.asyncio
async def test_claim_marks_job_claimed(processor, db):
    job = await processor.submit_job(payload="claim me")
    claimed = await db.claim_job("worker-x")
    assert claimed is not None
    assert claimed["job_id"] == job["job_id"]
    assert claimed["status"] == "claimed"
    assert claimed["worker_id"] == "worker-x"

    # A second claim must not return the same job.
    assert await db.claim_job("worker-y") is None


@pytest.mark.asyncio
async def test_priority_ordering(processor, db):
    await processor.submit_job(payload="low", priority=JobPriority.LOW)
    await processor.submit_job(payload="normal", priority=JobPriority.NORMAL)
    await processor.submit_job(payload="high", priority=JobPriority.HIGH)
    await processor.submit_job(payload="critical", priority=JobPriority.CRITICAL)

    order = []
    for _ in range(4):
        claimed = await db.claim_job("worker")
        order.append(claimed["payload"])

    assert order == ["critical", "high", "normal", "low"]


@pytest.mark.asyncio
async def test_worker_completes_job(running_engine):
    _, db, processor = running_engine
    job = await processor.submit_job(payload='{"task":"noop"}')
    done = await wait_for_status(db, job["job_id"], {"completed"})
    assert done["result"] == "noop"
    assert done["execution_time"] is not None
    assert done["completed_at"] is not None


@pytest.mark.asyncio
async def test_failed_job_is_retried_then_dead_lettered(running_engine):
    _, db, processor = running_engine
    job = await processor.submit_job(
        payload='{"task":"fail","message":"boom"}', max_retries=2
    )
    done = await wait_for_status(db, job["job_id"], {"dead_letter"}, timeout=8.0)
    assert done["retry_count"] == 2
    assert "boom" in done["error"]


@pytest.mark.asyncio
async def test_flaky_job_recovers_after_retries(running_engine):
    _, db, processor = running_engine
    job = await processor.submit_job(
        payload='{"task":"flaky","fail_times":1}', max_retries=3
    )
    done = await wait_for_status(db, job["job_id"], {"completed"}, timeout=8.0)
    assert done["retry_count"] == 1
    assert done["result"] == "recovered after retries"


@pytest.mark.asyncio
async def test_timeout_fails_job(running_engine):
    _, db, processor = running_engine
    job = await processor.submit_job(
        payload='{"task":"sleep","seconds":2}', timeout=1
    )
    done = await wait_for_status(db, job["job_id"], {"failed"}, timeout=6.0)
    assert "timed out" in done["error"].lower()


@pytest.mark.asyncio
async def test_cancel_pending_job(processor, db):
    job = await processor.submit_job(payload="cancel me")
    assert await processor.cancel_job(job["job_id"]) is True
    updated = await db.get_job(job["job_id"])
    assert updated["status"] == "cancelled"

    assert await processor.cancel_job(job["job_id"]) is False


@pytest.mark.asyncio
async def test_cancel_unknown_job(processor):
    assert await processor.cancel_job("missing") is False


@pytest.mark.asyncio
async def test_graceful_shutdown(tmp_path):
    from src.services.database import DatabaseService
    from src.services.job_processor import JobProcessor

    from conftest import make_config

    config = make_config(tmp_path, worker_count=3)
    db = DatabaseService(config)
    await db.initialize()
    processor = __import__(
        "src.services.job_processor", fromlist=["JobProcessor"]
    ).JobProcessor(config, db)
    await processor.start()
    assert processor.running is True
    assert len(processor.workers) == 3

    await processor.stop()
    assert processor.running is False
    assert processor.workers == []
    await db.close()


@pytest.mark.asyncio
async def test_stale_jobs_are_requeued(db):
    from src.services.database import DatabaseService  # noqa: F401

    job = await db.submit_job(payload="stale")
    await db.claim_job("dead-worker")
    assert (await db.get_job(job["job_id"]))["status"] == "claimed"

    requeued = await db.requeue_stale_jobs()
    assert requeued == 1
    recovered = await db.get_job(job["job_id"])
    assert recovered["status"] == "pending"
    assert recovered["worker_id"] is None


@pytest.mark.asyncio
async def test_metrics(processor):
    await processor.submit_job(payload="one")
    await processor.submit_job(payload="two", priority=JobPriority.CRITICAL)
    metrics = await processor.metrics()
    assert metrics["worker_count"] == processor.config.worker_count
    assert metrics["status_counts"]["pending"] == 2
    assert metrics["worker_id"]
    assert metrics["processor_running"] is False


@pytest.mark.asyncio
async def test_cancel_running_job_is_durable(running_engine):
    """A worker finishing after a cancel must not overwrite `cancelled`."""
    _, db, processor = running_engine
    job = await processor.submit_job(payload='{"task":"sleep","seconds":0.3}')

    await wait_for_status(db, job["job_id"], {"claimed", "running"})
    assert await db.cancel_job(job["job_id"]) is True

    # Let the worker finish the (now pointless) execution.
    await asyncio.sleep(0.6)
    final = await db.get_job(job["job_id"])
    assert final["status"] == "cancelled"


@pytest.mark.asyncio
async def test_double_cancel_returns_false(processor):
    job = await processor.submit_job(payload="cancel-twice")
    assert await processor.cancel_job(job["job_id"]) is True
    assert await processor.cancel_job(job["job_id"]) is False
