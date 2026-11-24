"""Smoke tests for the bundled example client.

`examples/` is not imported by the engine, so nothing else would catch it
drifting away from the real job states.
"""

import importlib.util
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "client.py"


def load_client():
    spec = importlib.util.spec_from_file_location("example_client", EXAMPLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_terminal_states_match_engine():
    from src.models import JobStatus

    client = load_client()
    engine_terminal = {
        JobStatus.COMPLETED.value,
        JobStatus.FAILED.value,
        JobStatus.CANCELLED.value,
        JobStatus.DEAD_LETTER.value,
    }
    assert client.TERMINAL == engine_terminal


def test_defaults_are_sane():
    client = load_client()
    args = client.parse_args(['{"task":"noop"}'])

    assert args.url.endswith("/api/v1")
    assert args.priority == "normal"
    assert args.no_wait is False
    assert args.max_wait > 0
    assert args.poll_interval > 0


def test_optional_fields_are_omitted_by_default():
    client = load_client()
    args = client.parse_args(['{"task":"noop"}'])

    assert args.timeout is None
    assert args.max_retries is None
    assert args.idempotency_key is None
    assert client.headers(args) == {}
