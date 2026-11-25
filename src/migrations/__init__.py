"""Programmatic Alembic entry point.

The migration scripts ship inside the installed package, so `job-engine migrate`
works without a checkout and without a hand-written ``alembic.ini``:

    job-engine migrate            # upgrade to head
    job-engine migrate --revision 0001_initial

Developers can also use the ``alembic.ini`` in the repository root.
"""

from pathlib import Path
from typing import Optional

MIGRATIONS_DIR = Path(__file__).resolve().parent


def make_config(database_url: str):
    """Build an Alembic ``Config`` pointing at the packaged migrations."""
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def upgrade(database_url: str, revision: str = "head") -> None:
    from alembic import command

    command.upgrade(make_config(database_url), revision)


def downgrade(database_url: str, revision: str = "-1") -> None:
    from alembic import command

    command.downgrade(make_config(database_url), revision)


def current_revision(database_url: str) -> Optional[str]:
    """Return the revision the database is on, or ``None`` if unmanaged."""
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


__all__ = [
    "MIGRATIONS_DIR",
    "make_config",
    "upgrade",
    "downgrade",
    "current_revision",
]
