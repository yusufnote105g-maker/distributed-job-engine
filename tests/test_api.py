"""API contract tests (workers disabled for determinism)."""

import asyncio

import pytest

API = "/api/v1"


@pytest.mark.asyncio
async def test_submit_job(api_client):
    response = await api_client.post(
        f"{API}/jobs",
        json={"payload": '{"task":"noop"}', "priority": "high"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["payload"] == '{"task":"noop"}'
    assert data["priority"] == "high"
    assert data["status"] == "pending"
    assert data["retry_count"] == 0
    assert data["job_id"]


@pytest.mark.asyncio
async def test_submit_rejects_empty_payload(api_client):
    response = await api_client.post(f"{API}/jobs", json={"payload": ""})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_submit_rejects_invalid_priority(api_client):
    response = await api_client.post(
        f"{API}/jobs", json={"payload": "x", "priority": "urgent"}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_submit_rejects_invalid_timeout(api_client):
    response = await api_client.post(
        f"{API}/jobs", json={"payload": "x", "timeout": 0}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_job_and_404(api_client):
    created = await api_client.post(f"{API}/jobs", json={"payload": "hello"})
    job_id = created.json()["job_id"]

    response = await api_client.get(f"{API}/jobs/{job_id}")
    assert response.status_code == 200
    assert response.json()["job_id"] == job_id

    missing = await api_client.get(f"{API}/jobs/does-not-exist")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_list_jobs_pagination_and_filter(api_client):
    for index in range(5):
        await api_client.post(f"{API}/jobs", json={"payload": f"job-{index}"})

    response = await api_client.get(f"{API}/jobs?limit=3&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert len(data["jobs"]) == 3
    assert data["total"] == 5
    assert data["limit"] == 3

    second_page = await api_client.get(f"{API}/jobs?limit=3&offset=3")
    assert len(second_page.json()["jobs"]) == 2

    filtered = await api_client.get(f"{API}/jobs?status=pending")
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 5

    empty = await api_client.get(f"{API}/jobs?status=completed")
    assert empty.json()["total"] == 0


@pytest.mark.asyncio
async def test_cancel_pending_job(api_client):
    created = await api_client.post(f"{API}/jobs", json={"payload": "cancel-me"})
    job_id = created.json()["job_id"]

    response = await api_client.post(f"{API}/jobs/{job_id}/cancel")
    assert response.status_code == 200
    assert response.json()["message"] == "Job cancelled successfully"

    job = await api_client.get(f"{API}/jobs/{job_id}")
    assert job.json()["status"] == "cancelled"

    again = await api_client.post(f"{API}/jobs/{job_id}/cancel")
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_cancel_nonexistent_job(api_client):
    response = await api_client.post(f"{API}/jobs/nope/cancel")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_job_alias(api_client):
    created = await api_client.post(f"{API}/jobs", json={"payload": "delete-me"})
    job_id = created.json()["job_id"]

    response = await api_client.delete(f"{API}/jobs/{job_id}")
    assert response.status_code == 200
    assert (await api_client.get(f"{API}/jobs/{job_id}")).json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_health_endpoint(api_client):
    response = await api_client.get(f"{API}/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database_status"] == "ok"
    assert data["worker_status"] == "stopped"  # workers disabled in this fixture
    assert data["version"]


@pytest.mark.asyncio
async def test_stats_and_metrics_endpoints(api_client):
    await api_client.post(f"{API}/jobs", json={"payload": "one", "priority": "low"})
    await api_client.post(f"{API}/jobs", json={"payload": "two", "priority": "critical"})

    stats = await api_client.get(f"{API}/stats")
    assert stats.status_code == 200
    assert stats.json()["total_jobs"] == 2
    assert stats.json()["pending_jobs"] == 2

    metrics = await api_client.get(f"{API}/metrics")
    assert metrics.status_code == 200
    data = metrics.json()
    assert data["worker_count"] == 0
    assert data["status_counts"]["pending"] == 2
    assert data["worker_id"]


@pytest.mark.asyncio
async def test_idempotency_key_returns_same_job(api_client):
    first = await api_client.post(
        f"{API}/jobs", json={"payload": "a", "idempotency_key": "key-1"}
    )
    second = await api_client.post(
        f"{API}/jobs", json={"payload": "b", "idempotency_key": "key-1"}
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["job_id"] == second.json()["job_id"]


@pytest.mark.asyncio
async def test_concurrent_duplicate_submissions(api_client):
    responses = await asyncio.gather(
        *[
            api_client.post(
                f"{API}/jobs",
                json={"payload": f"dup-{index}", "idempotency_key": "race-key"},
            )
            for index in range(5)
        ]
    )
    assert all(r.status_code == 201 for r in responses)
    assert len({r.json()["job_id"] for r in responses}) == 1


@pytest.mark.asyncio
async def test_api_key_protection(api_client_factory):
    client = await api_client_factory(secret_key="s3cret", worker_count=0)

    unauthorized = await client.post(f"{API}/jobs", json={"payload": "x"})
    assert unauthorized.status_code == 401

    wrong = await client.post(
        f"{API}/jobs", json={"payload": "x"}, headers={"X-API-Key": "wrong"}
    )
    assert wrong.status_code == 401

    allowed = await client.post(
        f"{API}/jobs", json={"payload": "x"}, headers={"X-API-Key": "s3cret"}
    )
    assert allowed.status_code == 201

    # Reads are protected too: they expose payloads and results.
    assert (await client.get(f"{API}/jobs")).status_code == 401
    assert (
        await client.get(f"{API}/jobs", headers={"X-API-Key": "s3cret"})
    ).status_code == 200

    # Health stays public so probes do not need credentials.
    assert (await client.get(f"{API}/health")).status_code == 200


@pytest.mark.asyncio
async def test_openapi_documents_all_endpoints(api_client):
    response = await api_client.get("/openapi.json")
    assert response.status_code == 200

    paths = response.json()["paths"]
    expected = {
        f"{API}/jobs",
        f"{API}/jobs/{{job_id}}",
        f"{API}/jobs/{{job_id}}/cancel",
        f"{API}/health",
        f"{API}/stats",
        f"{API}/metrics",
    }
    assert expected <= set(paths)


STATS_KEYS = {
    "total_jobs",
    "status_counts",
    "pending_jobs",
    "claimed_jobs",
    "running_jobs",
    "completed_jobs",
    "failed_jobs",
    "cancelled_jobs",
    "retrying_jobs",
    "dead_letter_jobs",
    "oldest_pending_job",
}

METRICS_EXTRA_KEYS = {
    "average_execution_time",
    "worker_count",
    "active_workers",
    "processor_running",
    "worker_id",
    "processed_by_this_processor",
    "failed_by_this_processor",
}


@pytest.mark.asyncio
async def test_stats_and_metrics_match_documented_contract(api_client):
    """`docs/api.md` lists these exact fields; keep the two in sync."""
    stats = await api_client.get(f"{API}/stats")
    assert stats.status_code == 200
    assert set(stats.json()) == STATS_KEYS

    metrics = await api_client.get(f"{API}/metrics")
    assert metrics.status_code == 200
    assert set(metrics.json()) == STATS_KEYS | METRICS_EXTRA_KEYS


@pytest.mark.asyncio
async def test_health_matches_documented_contract(api_client):
    health = await api_client.get(f"{API}/health")
    assert health.status_code == 200
    assert set(health.json()) == {
        "status",
        "timestamp",
        "version",
        "database_status",
        "worker_status",
    }


@pytest.mark.asyncio
async def test_jobs_cursor_pagination(api_client):
    """next_cursor pages through the list without duplicates or gaps."""
    created = []
    for index in range(5):
        response = await api_client.post(
            f"{API}/jobs", json={"payload": f"job-{index}"}
        )
        created.append(response.json()["job_id"])

    seen = []
    cursor = None
    for _page in range(10):
        url = f"{API}/jobs?limit=2" + (f"&before={cursor}" if cursor else "")
        response = await api_client.get(url)
        assert response.status_code == 200
        body = response.json()
        assert len(body["jobs"]) <= 2
        seen.extend(job["job_id"] for job in body["jobs"])
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert seen == list(reversed(created))
    assert len(seen) == len(set(seen))


@pytest.mark.asyncio
async def test_jobs_cursor_respects_status_filter(api_client):
    for index in range(3):
        await api_client.post(f"{API}/jobs", json={"payload": f"p-{index}"})

    page = await api_client.get(f"{API}/jobs?limit=1&status=pending")
    assert page.status_code == 200
    body = page.json()
    assert len(body["jobs"]) == 1
    assert body["jobs"][0]["status"] == "pending"

    next_page = await api_client.get(
        f"{API}/jobs?limit=1&status=pending&before={body['next_cursor']}"
    )
    assert next_page.status_code == 200
    assert next_page.json()["jobs"][0]["job_id"] != body["jobs"][0]["job_id"]


@pytest.mark.asyncio
async def test_jobs_unknown_cursor_returns_404(api_client):
    response = await api_client.get(f"{API}/jobs?before=does-not-exist")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_jobs_last_page_has_no_cursor(api_client):
    await api_client.post(f"{API}/jobs", json={"payload": "only-one"})
    response = await api_client.get(f"{API}/jobs?limit=10")
    assert response.json()["next_cursor"] is None
