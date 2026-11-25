"""Task handler registry.

A job payload is a JSON object with a ``task`` key. The worker resolves that key
in a registry instead of hard-coding behaviour, so applications can plug their
own work in without patching the engine:

    from distributed_job_engine.handlers import handler

    @handler("resize-image")
    async def resize(spec, context):
        # spec is the decoded payload, context carries job_id/retry_count
        return "done"

    job-engine worker

Handlers may be sync or async. A returned value becomes the job result; a
returned ``None`` is stored as an empty result. Raising any exception marks the
attempt as failed and follows the normal retry policy, except
``UnknownTaskError``, which is dead-lettered immediately because retrying cannot
help.

The built-in handlers (``noop``, ``sleep``, ``fail``, ``flaky``) exist so the
engine is runnable and testable without extra code. In production, register
real handlers and submit payloads that name them.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class JobExecutionError(Exception):
    """Raised by a handler to mark the attempt as failed."""


class UnknownTaskError(JobExecutionError):
    """The payload names a task that has no registered handler."""


@dataclass(frozen=True)
class HandlerContext:
    """Read-only information a handler may need."""

    job_id: str
    retry_count: int
    payload: str


HandlerResult = Union[str, None]
Handler = Callable[[Dict, HandlerContext], Union[HandlerResult, Awaitable[HandlerResult]]]


class HandlerRegistry:
    """Name -> callable mapping shared by every worker in the process."""

    def __init__(self) -> None:
        self._handlers: Dict[str, Handler] = {}

    def register(self, task: str, func: Optional[Handler] = None):
        """Register a handler, either directly or as a decorator."""
        if not task or not isinstance(task, str):
            raise ValueError("task name must be a non-empty string")

        if func is None:

            def decorator(handler: Handler) -> Handler:
                self.register(task, handler)
                return handler

            return decorator

        existing = self._handlers.get(task)
        if existing is not None and existing is not func:
            raise ValueError(
                f"a handler is already registered for task {task!r}: "
                f"{existing.__module__}.{existing.__qualname__}"
            )
        self._handlers[task] = func
        logger.debug("Registered handler for task %r", task)
        return func

    def get(self, task: str) -> Optional[Handler]:
        return self._handlers.get(task)

    def unregister(self, task: str) -> None:
        self._handlers.pop(task, None)

    def names(self) -> List[str]:
        return sorted(self._handlers)

    def __contains__(self, task: object) -> bool:
        return task in self._handlers

    def __len__(self) -> int:
        return len(self._handlers)


#: Process-wide registry. Register handlers before the workers start.
registry = HandlerRegistry()


def handler(task: str):
    """Decorator shorthand: ``@handler("my-task")``."""
    return registry.register(task)


def register_handler(task: str, func: Handler) -> Handler:
    """Non-decorator form: ``register_handler("my-task", func)``."""
    return registry.register(task, func)


# ------------------------------------------------------------- built-in tasks
@handler("noop")
async def _noop(spec: Dict, context: HandlerContext) -> str:
    return "noop"


@handler("sleep")
async def _sleep(spec: Dict, context: HandlerContext) -> str:
    seconds = float(spec.get("seconds", 0))
    await asyncio.sleep(seconds)
    return f"slept {spec.get('seconds', 0)}s"


@handler("fail")
async def _fail(spec: Dict, context: HandlerContext) -> str:
    raise JobExecutionError(spec.get("message", "job failed"))


@handler("flaky")
async def _flaky(spec: Dict, context: HandlerContext) -> str:
    fail_times = int(spec.get("fail_times", 1))
    if context.retry_count < fail_times:
        raise JobExecutionError(
            f"flaky failure {context.retry_count + 1}/{fail_times}"
        )
    return "recovered after retries"
