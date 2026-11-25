"""Logging setup: plain text by default, structured JSON on demand.

Every log record carries the current request id (``-`` outside a request), so a
single request can be followed across the API and the workers without shipping
logs to a special backend:

    LOG_FORMAT=json job-engine serve
    {"ts": "...", "level": "INFO", "logger": "src.api", "message": "request",
     "request_id": "9f2c...", "method": "POST", "path": "/api/v1/jobs",
     "status": 201, "duration_ms": 4.1, "client": "127.0.0.1", "api_key": "ci"}
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# Extra attributes that the access-log middleware attaches to a record.
_EXTRA_FIELDS = (
    "method",
    "path",
    "status",
    "duration_ms",
    "client",
    "api_key",
    "job_id",
)


class RequestIdFilter(logging.Filter):
    """Inject the current request id into every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line, stable field names, no secrets."""

    def format(self, record: logging.LogRecord) -> str:
        request_id = getattr(record, "request_id", None)
        if request_id in (None, "-"):
            # Direct formatting (tests, third-party handlers) may skip filters.
            request_id = request_id_var.get()
        payload: Dict[str, Any] = {
            "ts": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id,
        }
        for field in _EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(config) -> None:
    """Configure the root logger once, honouring ``LOG_FORMAT``."""
    handler = logging.StreamHandler(sys.stderr)
    if getattr(config, "log_format", "text").lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - "
                "[%(request_id)s] %(message)s"
            )
        )
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))
