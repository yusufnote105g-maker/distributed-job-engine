"""Application configuration."""

import os
from dataclasses import dataclass


def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    return default if value is None else value


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return default if value is None else int(value)


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    return default if value is None else float(value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class JobEngineConfig:
    # Database
    database_url: str = "sqlite:///./jobs.db"
    # PostgreSQL only: apply Alembic migrations on startup. SQLite schemas are
    # still created with `create_all`, so nothing changes for existing files.
    auto_migrate: bool = True
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # Workers
    worker_count: int = 4
    worker_timeout: int = 300  # seconds
    poll_interval: float = 0.5  # seconds

    # Retry policy
    max_retries: int = 3
    initial_backoff: float = 1.0
    max_backoff: float = 60.0
    retry_jitter: bool = True

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_prefix: str = "/api/v1"

    # Scheduler
    health_check_interval: float = 1.0  # seconds

    # Logging
    log_level: str = "INFO"
    log_format: str = "text"  # "text" or "json"
    request_id_header: str = "X-Request-ID"

    # Security
    secret_key: str = ""
    api_key_header: str = "X-API-Key"
    # Semicolon-separated `name:scopes:secret` entries. Scopes are separated by
    # `+` (read, write, admin). Example:
    #   API_KEYS="ci:read+write:long-secret; dashboard:read:other-secret"
    api_keys: str = ""
    # Per-key (or per-IP when auth is off) request limit per minute; 0 disables.
    rate_limit_per_minute: int = 0
    trust_forwarded_for: bool = False

    # Testing / operations
    enable_workers: bool = True
    recover_stale_jobs: bool = True
    # Requeue claimed/running jobs on startup. 0 requeues every such job
    # (safe for a single process); set it above WORKER_TIMEOUT when several
    # processes share one database so a restart cannot steal live work.
    stale_job_age: float = 0.0

    @classmethod
    def from_env(cls) -> "JobEngineConfig":
        return cls(
            database_url=_env_str("DATABASE_URL", cls.database_url),
            auto_migrate=_env_bool("AUTO_MIGRATE", cls.auto_migrate),
            db_pool_size=_env_int("DB_POOL_SIZE", cls.db_pool_size),
            db_max_overflow=_env_int("DB_MAX_OVERFLOW", cls.db_max_overflow),
            worker_count=_env_int("WORKER_COUNT", cls.worker_count),
            worker_timeout=_env_int("WORKER_TIMEOUT", cls.worker_timeout),
            poll_interval=_env_float("POLL_INTERVAL", cls.poll_interval),
            max_retries=_env_int("MAX_RETRIES", cls.max_retries),
            initial_backoff=_env_float("INITIAL_BACKOFF", cls.initial_backoff),
            max_backoff=_env_float("MAX_BACKOFF", cls.max_backoff),
            retry_jitter=_env_bool("RETRY_JITTER", cls.retry_jitter),
            api_host=_env_str("API_HOST", cls.api_host),
            api_port=_env_int("API_PORT", cls.api_port),
            api_prefix=_env_str("API_PREFIX", cls.api_prefix),
            health_check_interval=_env_float(
                "HEALTH_CHECK_INTERVAL", cls.health_check_interval
            ),
            log_level=_env_str("LOG_LEVEL", cls.log_level),
            log_format=_env_str("LOG_FORMAT", cls.log_format),
            request_id_header=_env_str("REQUEST_ID_HEADER", cls.request_id_header),
            secret_key=_env_str("SECRET_KEY", cls.secret_key),
            api_key_header=_env_str("API_KEY_HEADER", cls.api_key_header),
            api_keys=_env_str("API_KEYS", cls.api_keys),
            rate_limit_per_minute=_env_int(
                "RATE_LIMIT_PER_MINUTE", cls.rate_limit_per_minute
            ),
            trust_forwarded_for=_env_bool(
                "TRUST_FORWARDED_FOR", cls.trust_forwarded_for
            ),
            enable_workers=_env_bool("ENABLE_WORKERS", cls.enable_workers),
            recover_stale_jobs=_env_bool("RECOVER_STALE_JOBS", cls.recover_stale_jobs),
            stale_job_age=_env_float("STALE_JOB_AGE", cls.stale_job_age),
        )
