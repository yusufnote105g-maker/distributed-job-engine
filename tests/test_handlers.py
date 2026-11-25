"""Task handler registry: custom handlers, context, unknown tasks."""

import asyncio

import pytest

from src.handlers import (
    HandlerContext,
    HandlerRegistry,
    JobExecutionError,
    UnknownTaskError,
    handler,
    register_handler,
    registry,
)


async def wait_for_status(db, job_id, statuses, timeout=5.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        job = await db.get_job(job_id)
        if job and job["status"] in statuses:
            return job
        await asyncio.sleep(0.01)
    raise AssertionError(f"job {job_id} did not reach {statuses}; last={job}")


def test_builtin_tasks_are_registered():
    assert {"noop", "sleep", "fail", "flaky"} <= set(registry.names())


def test_register_sync_and_async_handlers():
    local = HandlerRegistry()

    def sync_handler(spec, context):
        return "sync"

    async def async_handler(spec, context):
        return "async"

    local.register("sync", sync_handler)
    local.register("async", async_handler)

    assert local.get("sync") is sync_handler
    assert local.get("async") is async_handler
    assert local.names() == ["async", "sync"]
    assert "sync" in local


def test_decorator_registration():
    local = HandlerRegistry()

    @local.register("decorated")
    def decorated(spec, context):
        return "ok"

    assert local.get("decorated") is decorated


def test_duplicate_registration_is_rejected():
    local = HandlerRegistry()
    local.register("task", lambda spec, context: "a")
    with pytest.raises(ValueError, match="already registered"):
        local.register("task", lambda spec, context: "b")


def test_invalid_task_name_is_rejected():
    local = HandlerRegistry()
    with pytest.raises(ValueError):
        local.register("", lambda spec, context: "x")


def test_unregister_removes_the_handler():
    local = HandlerRegistry()
    local.register("temp", lambda spec, context: "x")
    local.unregister("temp")
    assert local.get("temp") is None
    local.unregister("temp")  # idempotent


def test_unknown_task_error_is_a_job_execution_error():
    assert issubclass(UnknownTaskError, JobExecutionError)


@pytest.mark.asyncio
async def test_custom_handler_runs_and_result_is_stored(running_engine):
    _, db, processor = running_engine

    @handler("test-echo")
    async def echo(spec, context: HandlerContext):
        return f"{spec['value']}:{context.job_id}"

    try:
        job = await processor.submit_job(
            payload='{"task":"test-echo","value":"hi"}'
        )
        final = await wait_for_status(db, job["job_id"], {"completed"})
        assert final["result"] == f"hi:{job['job_id']}"
    finally:
        registry.unregister("test-echo")


@pytest.mark.asyncio
async def test_sync_handler_is_supported(running_engine):
    _, db, processor = running_engine

    def sync_handler(spec, context):
        return "sync-result"

    register_handler("test-sync", sync_handler)
    try:
        job = await processor.submit_job(payload='{"task":"test-sync"}')
        final = await wait_for_status(db, job["job_id"], {"completed"})
        assert final["result"] == "sync-result"
    finally:
        registry.unregister("test-sync")


@pytest.mark.asyncio
async def test_unknown_task_is_dead_lettered_without_retries(running_engine):
    _, db, processor = running_engine

    job = await processor.submit_job(
        payload='{"task":"definitely-not-registered"}', max_retries=5
    )
    final = await wait_for_status(db, job["job_id"], {"dead_letter"})
    assert final["retry_count"] == 0
    assert "definitely-not-registered" in final["error"]


@pytest.mark.asyncio
async def test_handler_context_exposes_retry_count(running_engine):
    _, db, processor = running_engine
    seen = []

    @handler("test-context")
    async def record(spec, context):
        seen.append((context.job_id, context.retry_count, context.payload))
        return "ok"

    try:
        job = await processor.submit_job(payload='{"task":"test-context"}')
        await wait_for_status(db, job["job_id"], {"completed"})
        assert seen and seen[0][0] == job["job_id"]
        assert seen[0][1] == 0
        assert '"task":"test-context"' in seen[0][2]
    finally:
        registry.unregister("test-context")


@pytest.mark.asyncio
async def test_non_json_payload_is_accepted(running_engine):
    _, db, processor = running_engine
    job = await processor.submit_job(payload="plain text, not json")
    final = await wait_for_status(db, job["job_id"], {"completed"})
    assert final["result"].startswith("processed payload")
