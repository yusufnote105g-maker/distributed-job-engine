"""Structured logging and request-id propagation."""

import json
import logging

import pytest

from src.logging_config import (
    JsonFormatter,
    RequestIdFilter,
    configure_logging,
    request_id_var,
)

API = "/api/v1"


def make_record(message: str = "hello", **extra) -> logging.LogRecord:
    record = logging.LogRecord(
        name="src.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_contains_request_id():
    token = request_id_var.set("req-123")
    try:
        payload = json.loads(JsonFormatter().format(make_record()))
    finally:
        request_id_var.reset(token)

    assert payload["request_id"] == "req-123"
    assert payload["level"] == "INFO"
    assert payload["message"] == "hello"
    assert payload["logger"] == "src.test"
    assert "ts" in payload


def test_json_formatter_includes_access_fields():
    payload = json.loads(
        JsonFormatter().format(
            make_record(
                "request",
                request_id="r1",
                method="POST",
                path="/api/v1/jobs",
                status=201,
                duration_ms=3.5,
                client="127.0.0.1",
                api_key="ci",
            )
        )
    )
    assert payload["method"] == "POST"
    assert payload["status"] == 201
    assert payload["duration_ms"] == 3.5
    assert payload["api_key"] == "ci"


def test_json_formatter_serialises_exceptions():
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        import sys

        record = make_record("failed", exc_info=sys.exc_info())
    payload = json.loads(JsonFormatter().format(record))
    assert "RuntimeError: boom" in payload["exception"]


def test_request_id_filter_defaults_to_dash():
    record = make_record()
    assert RequestIdFilter().filter(record) is True
    assert record.request_id == "-"


def test_configure_logging_json_mode():
    root = logging.getLogger()
    saved = (list(root.handlers), root.level)
    try:
        configure_logging(_config(log_format="json"))
        handlers = root.handlers
        assert len(handlers) == 1
        assert isinstance(handlers[0].formatter, JsonFormatter)
    finally:
        root.handlers[:] = saved[0]
        root.setLevel(saved[1])


def test_configure_logging_text_mode():
    root = logging.getLogger()
    saved = (list(root.handlers), root.level)
    try:
        configure_logging(_config(log_format="text"))
        handler = root.handlers[0]
        assert not isinstance(handler.formatter, JsonFormatter)
        assert "[%(request_id)s]" in handler.formatter._fmt
    finally:
        root.handlers[:] = saved[0]
        root.setLevel(saved[1])


def _config(**overrides):
    from src.config import JobEngineConfig

    return JobEngineConfig(log_level="WARNING", **overrides)


@pytest.mark.asyncio
async def test_request_id_is_echoed(api_client):
    response = await api_client.get(
        f"{API}/health", headers={"X-Request-ID": "trace-42"}
    )
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "trace-42"


@pytest.mark.asyncio
async def test_request_id_is_generated_when_missing(api_client):
    response = await api_client.get(f"{API}/health")
    request_id = response.headers.get("x-request-id")
    assert request_id and request_id != "-"
    assert len(request_id) >= 16
