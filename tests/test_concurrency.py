"""Concurrency and race-condition tests against the real engine."""

import asyncio
from datetime import timedelta

import pytest

from src.utils import utcnow


async def wait_until(predicate, timeout=10.0, interval=0.02):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if await predicate():
            return True
        await asyncio.sleep(interval)
    return False


@pytest.mark.asyncio
async def test_jobs_are_claimed_exactly_once(running_engine):
    """Many jobs, four workers: every job completes exactly once."""
    _, db, processor = running_engine
    total = 30
    job_ids = []
    for index in range(total):
        job = await processor.submit_job(
            payload='{"task":"sleep","seconds":0.02}'
        )
        job_ids.append(job["job_id"])

    async def all_finished():
        stats = await db.stats()
        return stats["completed_jobs"] == total

    assert await wait_until(all_finished), await db.stats()

    completed = 0
    for job_id in job_ids:
        job = await db.get_job(job_id)
        assert job["status"] == "completed", job
        completed += 1

    assert completed == total
    stats = await db.stats()
    assert stats["pending_jobs"] == 0
    assert stats["claimed_jobs"] == 0
    assert stats["running_jobs"] == 0


@pytest.mark.asyncio
async def test_no_duplicate_claims_under_parallel_claim_calls(db):
    """Parallel claim_job calls must never hand out the same job twice."""
    jobs = [await db.submit_job(payload=f"job-{i}") for i in range(10)]

    claimed = await asyncio.gather(*[db.claim_job(f"worker-{i}") for i in range(20)])
    claimed_ids = [c["job_id"] for c in claimed if c is not None]

    assert len(claimed_ids) == len(jobs)
    assert len(set(claimed_ids)) == len(claimed_ids)


@pytest.mark.asyncio
async def test_concurrent_duplicate_submissions(db):
    results = await asyncio.gather(
        *[
            db.submit_job(payload=f"dup-{i}", idempotency_key="same-key")
            for i in range(10)
        ]
    )
    assert len({r["job_id"] for r in results}) == 1


@pytest.mark.asyncio
async def test_retry_promotion_under_load(running_engine):
    """Failing jobs must not be lost: they either retry or dead-letter."""
    _, db, processor = running_engine
    jobs = [
        await processor.submit_job(payload='{"task":"fail"}', max_retries=1)
        for _ in range(10)
    ]

    async def all_terminal():
        stats = await db.stats()
        return (
            stats["dead_letter_jobs"] + stats["completed_jobs"] == len(jobs)
        )

    assert await wait_until(all_terminal, timeout=15.0), await db.stats()
    for job in jobs:
        stored = await db.get_job(job["job_id"])
        assert stored["status"] == "dead_letter"
        assert stored["error"] is not None


@pytest.mark.asyncio
async def test_crash_recovery_requeues_running_jobs(db):
    job = await db.submit_job(payload="crash")
    await db.claim_job("worker-1")
    await db.mark_running(job["job_id"], "worker-1")

    assert await db.requeue_stale_jobs() == 1
    recovered = await db.get_job(job["job_id"])
    assert recovered["status"] == "pending"


@pytest.mark.asyncio
async def test_requeue_respects_age_threshold(db):
    """With several processes on one database, a restart must not steal live work."""
    job = await db.submit_job(payload="in-flight")
    await db.claim_job("worker-1")
    await db.mark_running(job["job_id"], "worker-1")

    # Just started: older than 60s is false, so nothing is requeued.
    assert await db.requeue_stale_jobs(older_than_seconds=60) == 0
    assert (await db.get_job(job["job_id"]))["status"] == "running"

    # Without a threshold the single-process behaviour is preserved.
    assert await db.requeue_stale_jobs() == 1
    assert (await db.get_job(job["job_id"]))["status"] == "pending"


@pytest.mark.asyncio
async def test_due_retry_is_promoted(db):
    job = await db.submit_job(payload="retry")
    await db.schedule_retry(
        job["job_id"],
        error="boom",
        execution_time=0.1,
        retry_count=1,
        next_retry_at=utcnow() - timedelta(seconds=1),
    )
    assert (await db.get_job(job["job_id"]))["status"] == "retrying"

    assert await db.promote_due_retries() == 1
    promoted = await db.get_job(job["job_id"])
    assert promoted["status"] == "pending"
    assert promoted["retry_count"] == 1


@pytest.mark.asyncio
async def test_future_retry_is_not_promoted(db):
    job = await db.submit_job(payload="retry")
    await db.schedule_retry(
        job["job_id"],
        error="boom",
        execution_time=0.1,
        retry_count=1,
        next_retry_at=utcnow() + timedelta(minutes=5),
    )
    assert await db.promote_due_retries() == 0
    assert (await db.get_job(job["job_id"]))["status"] == "retrying"
