"""Prometheus metrics must reflect real work and real queue state."""

import pytest
from prometheus_client import REGISTRY

API = "/api/v1"


def sample(name: str, labels: dict | None = None) -> float:
    value = REGISTRY.get_sample_value(name, labels or {})
    return 0.0 if value is None else value


@pytest.mark.asyncio
async def test_scrape_endpoint_reports_queue_state(api_client):
    await api_client.post(
        f"{API}/jobs",
        json={"payload": '{"task":"noop"}', "priority": "high"},
    )

    response = await api_client.get(f"{API}/metrics/prometheus")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["content-type"].count("charset=") == 1

    body = response.text
    assert "jobs_submitted_total" in body
    assert 'priority="high"' in body
    assert 'jobs_by_status{status="pending"} 1.0' in body
    assert "workers_active 0.0" in body
    assert "oldest_pending_job_age_seconds" in body


@pytest.mark.asyncio
async def test_scrape_endpoint_reports_empty_queue(api_client):
    response = await api_client.get(f"{API}/metrics/prometheus")
    assert response.status_code == 200
    assert "oldest_pending_job_age_seconds 0.0" in response.text


@pytest.mark.asyncio
async def test_completed_counter_and_histogram(db):
    before_completed = sample("jobs_completed_total")
    before_observations = sample("job_execution_seconds_count")

    job = await db.submit_job(payload="work")
    claimed = await db.claim_job("worker-test")
    assert claimed["job_id"] == job["job_id"]

    assert await db.complete_job(job["job_id"], "done", 0.25) is True

    assert sample("jobs_completed_total") == before_completed + 1
    assert sample("job_execution_seconds_count") == before_observations + 1


@pytest.mark.asyncio
async def test_failed_and_dead_letter_counters(db):
    before_failed = sample("jobs_failed_total")
    before_dead = sample("jobs_dead_letter_total")

    first = await db.submit_job(payload="fail")
    await db.claim_job("worker-test")
    assert await db.mark_failed(first["job_id"], "boom", 0.1) is True

    second = await db.submit_job(payload="fail")
    await db.claim_job("worker-test")
    assert await db.mark_dead_letter(second["job_id"], "boom", 0.1, 3) is True

    assert sample("jobs_failed_total") == before_failed + 1
    assert sample("jobs_dead_letter_total") == before_dead + 1


@pytest.mark.asyncio
async def test_cancel_counter(db):
    before = sample("jobs_cancelled_total")

    job = await db.submit_job(payload="cancel-me")
    assert await db.cancel_job(job["job_id"]) is True
    assert sample("jobs_cancelled_total") == before + 1


@pytest.mark.asyncio
async def test_replayed_submission_is_not_counted_twice(db):
    """An idempotent replay returns the same job and must not inflate counters."""
    before = sample("jobs_submitted_total", {"priority": "normal"})

    first = await db.submit_job(payload="x", idempotency_key="k-metrics")
    second = await db.submit_job(payload="x", idempotency_key="k-metrics")

    assert first["job_id"] == second["job_id"]
    assert sample("jobs_submitted_total", {"priority": "normal"}) == before + 1


@pytest.mark.asyncio
async def test_json_metrics_endpoint_is_unchanged(api_client):
    response = await api_client.get(f"{API}/metrics")
    assert response.status_code == 200
    assert response.json()["worker_count"] == 0
