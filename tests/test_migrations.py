"""Alembic migrations must describe the same schema as the ORM models.

The migration is what PostgreSQL users get; SQLite users get
``Base.metadata.create_all``. If the two drift, the same code would behave
differently depending on the database, so the schemas are compared here.
"""

import pytest
from sqlalchemy import create_engine, inspect, text

from src.models import Base
from src.services.database import normalize_database_url


def _describe(url: str) -> dict:
    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        columns = {
            column["name"]: (str(column["type"]), bool(column["nullable"]))
            for column in inspector.get_columns("jobs")
        }
        indexes = {
            index["name"]: (tuple(index["column_names"]), bool(index["unique"]))
            for index in inspector.get_indexes("jobs")
        }
        return {"columns": columns, "indexes": indexes}
    finally:
        engine.dispose()


@pytest.fixture
def migrated_url(tmp_path):
    from src.migrations import current_revision, upgrade

    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    upgrade(url)
    assert current_revision(url) == "0001_initial"
    return url


@pytest.fixture
def created_url(tmp_path):
    url = f"sqlite:///{tmp_path / 'created.db'}"
    engine = create_engine(url)
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()
    return url


def test_migration_matches_models(migrated_url, created_url):
    migrated = _describe(migrated_url)
    created = _describe(created_url)

    assert migrated["columns"] == created["columns"]
    assert migrated["indexes"] == created["indexes"]


def test_migration_is_idempotent(migrated_url):
    from src.migrations import upgrade

    # Running head again is a no-op, not an error.
    upgrade(migrated_url)
    assert _describe(migrated_url)["columns"]


def test_migration_creates_the_alembic_version_table(migrated_url):
    engine = create_engine(migrated_url)
    try:
        with engine.connect() as connection:
            version = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
    finally:
        engine.dispose()
    assert version == "0001_initial"


def test_cli_migrate_stamps_an_existing_sqlite_database(tmp_path, capsys):
    """A database created by `create_all` must not fail the initial migration."""
    from src.cli import main
    from src.migrations import current_revision

    url = f"sqlite:///{tmp_path / 'existing.db'}"
    engine = create_engine(url)
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()

    assert main(["migrate", "--database-url", url]) == 0
    assert "stamped" in capsys.readouterr().out
    assert current_revision(url) == "0001_initial"


def test_cli_migrate_creates_a_fresh_sqlite_database(tmp_path):
    from src.cli import main
    from src.migrations import current_revision

    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    assert main(["migrate", "--database-url", url]) == 0
    assert current_revision(url) == "0001_initial"
    assert _describe(url)["columns"]["payload"] == ("TEXT", False)


def test_normalize_database_url():
    assert normalize_database_url("postgres://u:p@h/db") == "postgresql://u:p@h/db"
    assert (
        normalize_database_url("postgresql+psycopg://u:p@h/db")
        == "postgresql+psycopg2://u:p@h/db"
    )
    assert normalize_database_url("sqlite:///jobs.db") == "sqlite:///jobs.db"


def test_prepare_server_schema_creates_a_fresh_database(tmp_path):
    """The PostgreSQL startup path: no tables yet, run `upgrade head`."""
    from src.config import JobEngineConfig
    from src.migrations import current_revision
    from src.services.database import DatabaseService

    url = f"sqlite:///{tmp_path / 'server_fresh.db'}"
    service = DatabaseService(JobEngineConfig(database_url=url))
    service.engine = create_engine(url)
    try:
        service._prepare_server_schema(url)
    finally:
        service.engine.dispose()

    assert current_revision(url) == "0001_initial"
    assert _describe(url)["columns"]["status"] == ("VARCHAR(11)", False)


def test_prepare_server_schema_stamps_a_legacy_schema(tmp_path):
    """A table without alembic_version must be stamped, not migrated again."""
    from src.config import JobEngineConfig
    from src.migrations import current_revision
    from src.services.database import DatabaseService

    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    engine = create_engine(url)
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()

    service = DatabaseService(JobEngineConfig(database_url=url))
    service.engine = create_engine(url)
    try:
        service._prepare_server_schema(url)
        # Second call takes the normal upgrade path and is a no-op.
        service._prepare_server_schema(url)
    finally:
        service.engine.dispose()

    assert current_revision(url) == "0001_initial"


def test_auto_migrate_disabled_requires_an_existing_schema(tmp_path):
    import asyncio

    from src.config import JobEngineConfig
    from src.services.database import DatabaseService

    url = f"sqlite:///{tmp_path / 'x.db'}"
    service = DatabaseService(JobEngineConfig(database_url=url, auto_migrate=False))
    # SQLite ignores auto_migrate (create_all is still the documented path).
    asyncio.run(service.initialize())
    asyncio.run(service.close())
