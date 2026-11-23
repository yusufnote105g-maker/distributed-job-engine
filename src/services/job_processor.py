"""Concurrent job processor."""

import asyncio
import json
import logging
import random
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..config import JobEngineConfig
from ..models import JobPriority
from .database import DatabaseService

logger = logging.getLogger(__name__)


class JobExecutionError(Exception):
    """Raised when a job payload asks to fail."""


class JobProcessor:
    def __init__(self, config: JobEngineConfig, db_service: DatabaseService):
        self.config = config
        self.db = db_service
        self.worker_id = f"worker-{uuid.uuid4().hex[:8]}"
        self.workers: List[asyncio.Task] = []
        self.scheduler_task: Optional[asyncio.Task] = None
        self.running = False
        self._processed = 0
        self._failed = 0

    # ------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        if self.running:
            return
        await self.db.initialize()
        if self.config.recover_stale_jobs:
            await self.db.requeue_stale_jobs()

        self.running = True
        for index in range(self.config.worker_count):
            task = asyncio.create_task(
                self._worker(f"worker-{index}"), name=f"job-worker-{index}"
            )
            self.workers.append(task)

        self.scheduler_task = asyncio.create_task(
            self._scheduler(), name="job-scheduler"
        )
        logger.info(
            "Job processor started with %d worker(s)", self.config.worker_count
        )

    async def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        tasks = [*self.workers]
        if self.scheduler_task is not None:
            tasks.append(self.scheduler_task)

        for task in tasks:
            task.cancel()

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception) and not isinstance(
                result, asyncio.CancelledError
            ):
                logger.warning("Task shutdown error: %s", result)

        self.workers.clear()
        self.scheduler_task = None
        logger.info("Job processor stopped")

    # -------------------------------------------------------------- workers
    async def _worker(self, worker_name: str) -> None:
        logger.info("%s started", worker_name)
        try:
            while self.running:
                try:
                    job = await self.db.claim_job(worker_name)
                except Exception:
                    logger.exception("%s failed to claim a job", worker_name)
                    await asyncio.sleep(min(5.0, self.config.poll_interval * 4))
                    continue

                if job is None:
                    await asyncio.sleep(self.config.poll_interval)
                    continue

                await self._process(job, worker_name)
        except asyncio.CancelledError:
            logger.info("%s cancelled", worker_name)
            raise
        finally:
            logger.info("%s stopped", worker_name)

    async def _process(self, job: Dict[str, Any], worker_name: str) -> None:
        job_id = job["job_id"]
        started = time.perf_counter()
        timeout_seconds = job.get("timeout") or self.config.worker_timeout

        if not await self.db.mark_running(job_id, worker_name):
            # The job was cancelled between claim and execution.
            logger.info("%s skipped %s (no longer runnable)", worker_name, job_id)
            return

        try:
            result = await asyncio.wait_for(
                self._execute_payload(job["payload"], job.get("retry_count", 0)),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            elapsed = time.perf_counter() - started
            message = f"Job timed out after {timeout_seconds}s"
            if await self.db.mark_failed(job_id, message, elapsed):
                self._failed += 1
                logger.warning("%s: %s", job_id, message)
            else:
                logger.info("%s: %s (job already cancelled)", job_id, message)
            return
        except asyncio.CancelledError:
            elapsed = time.perf_counter() - started
            await self.db.mark_failed(job_id, "Job cancelled during shutdown", elapsed)
            raise
        except Exception as exc:  # noqa: BLE001 - job failure is expected
            elapsed = time.perf_counter() - started
            await self._handle_failure(job, str(exc) or exc.__class__.__name__, elapsed)
            return

        elapsed = time.perf_counter() - started
        if await self.db.complete_job(job_id, result, elapsed):
            self._processed += 1
            logger.info("%s completed %s in %.3fs", worker_name, job_id, elapsed)
        else:
            # Cancelled while running: discard the result.
            logger.info("%s discarded result for cancelled job %s", worker_name, job_id)

    async def _handle_failure(
        self, job: Dict[str, Any], error: str, elapsed: float
    ) -> None:
        job_id = job["job_id"]
        retry_count = job.get("retry_count", 0) + 1
        max_retries = job.get("max_retries", self.config.max_retries)

        if retry_count > max_retries:
            if await self.db.mark_dead_letter(
                job_id, error, elapsed, retry_count - 1
            ):
                self._failed += 1
                logger.error("%s exhausted retries: %s", job_id, error)
            else:
                logger.info("%s failure ignored (job already cancelled)", job_id)
            return

        delay = self._backoff_delay(retry_count)
        next_retry_at = datetime.utcnow() + timedelta(seconds=delay)
        if await self.db.schedule_retry(
            job_id, error, elapsed, retry_count, next_retry_at
        ):
            logger.warning(
                "%s failed (attempt %d/%d), retry in %.2fs: %s",
                job_id,
                retry_count,
                max_retries,
                delay,
                error,
            )
        else:
            logger.info("%s retry skipped (job already cancelled)", job_id)

    def _backoff_delay(self, retry_count: int) -> float:
        delay = min(
            self.config.initial_backoff * (2 ** (retry_count - 1)),
            self.config.max_backoff,
        )
        if self.config.retry_jitter:
            # Jitter between 50% and 100% of base delay
            jitter = 0.5 + random.random() * 0.5
            delay = delay * jitter
        return max(0.0, delay)

    async def _execute_payload(self, payload: str, retry_count: int) -> str:
        try:
            spec = json.loads(payload)
        except (TypeError, ValueError):
            return f"processed payload ({len(payload)} bytes)"

        if not isinstance(spec, dict):
            return "processed payload"

        task = spec.get("task", "noop")

        if task == "sleep":
            await asyncio.sleep(float(spec.get("seconds", 0)))
            return f"slept {spec.get('seconds', 0)}s"

        if task == "fail":
            raise JobExecutionError(spec.get("message", "job failed"))

        if task == "flaky":
            fail_times = int(spec.get("fail_times", 1))
            if retry_count < fail_times:
                raise JobExecutionError(
                    f"flaky failure {retry_count + 1}/{fail_times}"
                )
            return "recovered after retries"

        return "noop"

    # ------------------------------------------------------------ scheduler
    async def _scheduler(self) -> None:
        try:
            while self.running:
                try:
                    promoted = await self.db.promote_due_retries()
                    if promoted:
                        logger.info("Promoted %d due retry job(s)", promoted)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Retry scheduler iteration failed")
                await asyncio.sleep(self.config.health_check_interval)
        except asyncio.CancelledError:
            logger.info("Scheduler cancelled")
            raise

    # ----------------------------------------------------------- public API
    async def submit_job(
        self,
        payload: str,
        priority: JobPriority = JobPriority.NORMAL,
        idempotency_key: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
    ) -> Dict[str, Any]:
        return await self.db.submit_job(
            payload=payload,
            priority=priority,
            idempotency_key=idempotency_key,
            timeout=timeout or self.config.worker_timeout,
            max_retries=(
                self.config.max_retries if max_retries is None else max_retries
            ),
        )

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        return await self.db.get_job(job_id)

    async def list_jobs(self, **kwargs) -> Dict[str, Any]:
        return await self.db.list_jobs(**kwargs)

    async def cancel_job(self, job_id: str) -> bool:
        return await self.db.cancel_job(job_id)

    async def metrics(self) -> Dict[str, Any]:
        stats = await self.db.stats()
        stats.update(
            {
                "average_execution_time": await self.db.average_execution_time(),
                "worker_count": self.config.worker_count,
                "active_workers": sum(1 for w in self.workers if not w.done()),
                "processor_running": self.running,
                "worker_id": self.worker_id,
                "processed_by_this_processor": self._processed,
                "failed_by_this_processor": self._failed,
            }
        )
        return stats
