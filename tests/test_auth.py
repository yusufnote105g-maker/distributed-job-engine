"""API-key scopes, rotation and rate limiting."""

import pytest

from src.api.auth import (
    ALL_SCOPES,
    RateLimiter,
    build_keys,
    has_scope,
    parse_api_keys,
)
from src.config import JobEngineConfig

API = "/api/v1"


def test_parse_api_keys():
    keys = parse_api_keys("ci:read+write:secret-one; dash:read:secret-two")
    assert [key.name for key in keys] == ["ci", "dash"]
    assert keys[0].scopes == frozenset({"read", "write"})
    assert keys[1].scopes == frozenset({"read"})
    assert keys[0].secret == "secret-one"


def test_parse_rejects_malformed_entries():
    with pytest.raises(ValueError):
        parse_api_keys("no-separators")
    with pytest.raises(ValueError):
        parse_api_keys("name:read")
    with pytest.raises(ValueError):
        parse_api_keys("name::secret")
    with pytest.raises(ValueError):
        parse_api_keys("name:fly:secret")


def test_parse_rejects_unknown_scope():
    with pytest.raises(ValueError, match="Unknown scope"):
        parse_api_keys("ci:read+delete:secret")


def test_build_keys_adds_legacy_secret_key():
    config = JobEngineConfig(api_keys="ci:read:one", secret_key="legacy")
    keys = build_keys(config)
    assert {key.name for key in keys} == {"ci", "default"}
    assert keys[-1].scopes == ALL_SCOPES


def test_build_keys_does_not_duplicate_the_same_secret():
    config = JobEngineConfig(api_keys="ci:read:same", secret_key="same")
    assert len(build_keys(config)) == 1


def test_admin_scope_grants_everything():
    assert has_scope(frozenset({"admin"}), "read")
    assert has_scope(frozenset({"admin"}), "write")
    assert not has_scope(frozenset({"read"}), "write")


def test_rate_limiter_window():
    limiter = RateLimiter(limit_per_minute=2)
    assert limiter.allow("k") is True
    assert limiter.allow("k") is True
    assert limiter.allow("k") is False
    assert limiter.allow("other") is True


def test_rate_limiter_disabled():
    limiter = RateLimiter(limit_per_minute=0)
    assert all(limiter.allow("k") for _ in range(100))


@pytest.mark.asyncio
async def test_scopes_are_enforced(api_client_factory):
    client = await api_client_factory(
        api_keys="reader:read:r-secret; writer:write:w-secret", worker_count=0
    )
    read_headers = {"X-API-Key": "r-secret"}
    write_headers = {"X-API-Key": "w-secret"}

    assert (await client.get(f"{API}/jobs", headers=read_headers)).status_code == 200
    assert (
        await client.post(
            f"{API}/jobs", json={"payload": "x"}, headers=read_headers
        )
    ).status_code == 403

    assert (
        await client.post(
            f"{API}/jobs", json={"payload": "x"}, headers=write_headers
        )
    ).status_code == 201
    assert (
        await client.get(f"{API}/jobs", headers=write_headers)
    ).status_code == 403


@pytest.mark.asyncio
async def test_admin_key_can_read_and_write(api_client_factory):
    client = await api_client_factory(api_keys="ops:admin:a-secret", worker_count=0)
    headers = {"X-API-Key": "a-secret"}

    assert (
        await client.post(f"{API}/jobs", json={"payload": "x"}, headers=headers)
    ).status_code == 201
    assert (await client.get(f"{API}/jobs", headers=headers)).status_code == 200
    assert (await client.get(f"{API}/stats", headers=headers)).status_code == 200


@pytest.mark.asyncio
async def test_two_keys_allow_rotation_without_downtime(api_client_factory):
    client = await api_client_factory(
        api_keys="old:read+write:old-secret; new:read+write:new-secret",
        worker_count=0,
    )
    for secret in ("old-secret", "new-secret"):
        response = await client.post(
            f"{API}/jobs",
            json={"payload": "x"},
            headers={"X-API-Key": secret},
        )
        assert response.status_code == 201


@pytest.mark.asyncio
async def test_metrics_require_read_scope(api_client_factory):
    client = await api_client_factory(api_keys="reader:read:r-secret", worker_count=0)
    headers = {"X-API-Key": "r-secret"}

    assert (await client.get(f"{API}/metrics", headers=headers)).status_code == 200
    assert (
        await client.get(f"{API}/metrics/prometheus", headers=headers)
    ).status_code == 200
    assert (await client.get(f"{API}/metrics")).status_code == 401


@pytest.mark.asyncio
async def test_rate_limit_per_key(api_client_factory):
    client = await api_client_factory(
        api_keys="reader:read:r-secret; writer:read:r2-secret",
        rate_limit_per_minute=2,
        worker_count=0,
    )
    headers = {"X-API-Key": "r-secret"}

    assert (await client.get(f"{API}/stats", headers=headers)).status_code == 200
    assert (await client.get(f"{API}/stats", headers=headers)).status_code == 200
    limited = await client.get(f"{API}/stats", headers=headers)
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"

    # The other key has its own budget.
    assert (
        await client.get(f"{API}/stats", headers={"X-API-Key": "r2-secret"})
    ).status_code == 200


@pytest.mark.asyncio
async def test_auth_disabled_when_no_keys_configured(api_client):
    assert (await api_client.get(f"{API}/jobs")).status_code == 200
    assert (await api_client.post(f"{API}/jobs", json={"payload": "x"})).status_code == 201


@pytest.mark.asyncio
async def test_invalid_scope_configuration_fails_at_startup(api_client_factory):
    with pytest.raises(ValueError, match="Unknown scope"):
        await api_client_factory(api_keys="bad:fly:secret", worker_count=0)
