"""Shared pytest fixtures.

The API is exercised through httpx's ASGI transport with the application
lifespan driven explicitly, so startup/shutdown logic is covered too.

By default every test gets its own SQLite file. Set ``TEST_DATABASE_URL`` to a
PostgreSQL server URL to run the same suite against PostgreSQL; a throw-away
database is created and dropped per test so tests stay isolated.

    TEST_DATABASE_URL=postgresql+psycopg2://user:pass@localhost/postgres \
        pytest -q
"""

import os
import uuid

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from src.config import JobEngineConfig
from src.main import VERSION, create_app
from src.services.database import DatabaseService
from src.services.job_processor import JobProcessor


def make_config(tmp_path, database_url=None, **overrides) -> JobEngineConfig:
    defaults = dict(
        database_url=database_url or f"sqlite:///{tmp_path / 'jobs.db'}",
        worker_count=2,
        poll_interval=0.01,
        health_check_interval=0.01,
        initial_backoff=0.02,
        max_backoff=0.1,
        max_retries=2,
        log_level="WARNING",
    )
    defaults.update(overrides)
    return JobEngineConfig(**defaults)


@pytest.fixture
def db_url(tmp_path):
    """A database URL that is empty for this test.

    SQLite: a file under ``tmp_path``. PostgreSQL: a database created for the
    duration of the test and dropped afterwards.
    """
    base = os.environ.get("TEST_DATABASE_URL")
    if not base:
        yield f"sqlite:///{tmp_path / 'jobs.db'}"
        return

    name = f"je_test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(base).set(database=name)
    try:
        yield url.render_as_string(hide_password=False)
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def config(tmp_path, db_url):
    return make_config(tmp_path, database_url=db_url)


@pytest.fixture
async def db(config):
    service = DatabaseService(config)
    await service.initialize()
    yield service
    await service.close()


@pytest.fixture
async def processor(config, db):
    instance = JobProcessor(config, db)
    yield instance
    await instance.stop()


@pytest.fixture
async def api_client(tmp_path, db_url):
    """API client with background workers disabled (deterministic API tests)."""
    config = make_config(
        tmp_path, database_url=db_url, worker_count=0, enable_workers=False
    )
    db_service = DatabaseService(config)
    processor = JobProcessor(config, db_service)
    await db_service.initialize()

    app = create_app(config)
    app.state.db_service = db_service
    app.state.job_processor = processor
    app.state.config = config
    app.state.version = VERSION

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield client
    finally:
        await processor.stop()
        await db_service.close()


@pytest.fixture
async def api_client_factory(tmp_path, db_url):
    """Factory building an API client for an arbitrary config."""
    clients = []

    async def factory(**overrides):
        config = make_config(tmp_path, database_url=db_url, **overrides)
        db_service = DatabaseService(config)
        processor = JobProcessor(config, db_service)
        await db_service.initialize()

        app = create_app(config)
        app.state.db_service = db_service
        app.state.job_processor = processor
        app.state.config = config
        app.state.version = VERSION

        transport = httpx.ASGITransport(app=app)
        client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
        clients.append((client, db_service, processor))
        return client

    yield factory

    for client, db_service, processor in clients:
        await client.aclose()
        await processor.stop()
        await db_service.close()


@pytest.fixture
async def running_engine(tmp_path, db_url):
    """A fully started engine (workers on) plus its database service."""
    config = make_config(tmp_path, database_url=db_url, worker_count=4)
    service = DatabaseService(config)
    await service.initialize()
    processor = JobProcessor(config, service)
    await processor.start()
    try:
        yield config, service, processor
    finally:
        await processor.stop()
        await service.close()
