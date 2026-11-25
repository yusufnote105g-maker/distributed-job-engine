"""Alembic environment.

The URL comes from the Alembic config when the command is run
programmatically (`job-engine migrate`) and from ``DATABASE_URL`` when it is run
through the repository ``alembic.ini``.
"""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

# Make the models importable both from a checkout (`src.models`) and from an
# installed wheel (`distributed_job_engine.models`).
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:  # installed distribution
    from distributed_job_engine.models import Base  # noqa: E402
except ModuleNotFoundError:  # source checkout
    from src.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    configured = config.get_main_option("sqlalchemy.url")
    url = configured or os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError(
            "No database URL: set DATABASE_URL or pass sqlalchemy.url to Alembic"
        )
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql+psycopg://"):
        # SQLAlchemy 1.4 has no psycopg 3 dialect.
        url = "postgresql+psycopg2://" + url[len("postgresql+psycopg://") :]
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_database_url(), poolclass=pool.NullPool)
    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
