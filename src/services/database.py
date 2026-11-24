"""Data-access layer with asyncio for SQLite."""

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ..config import JobEngineConfig
from .. import metrics
from ..models import Base, Job, JobPriority, JobStatus
from ..utils import utcnow

logger = logging.getLogger(__name__)

PRIORITY_RANK = case(
    (Job.priority == JobPriority.CRITICAL, 0),
    (Job.priority == JobPriority.HIGH, 1),
    (Job.priority == JobPriority.NORMAL, 2),
    else_=3,
)


class DatabaseService:
    def __init__(self, config: JobEngineConfig):
        self.config = config
        self.engine = None
        self.Session = None

    # ------------------------------------------------------------------ setup
    async def initialize(self) -> None:
        if self.engine is not None:
            return

        from sqlalchemy import create_engine, event

        url = self.config.database_url
        kwargs: Dict[str, Any] = {"echo": False}
        is_sqlite = url.startswith("sqlite")
        if is_sqlite and ":memory:" not in url:
            # Make sure the parent directory exists; SQLite refuses to create a
            # database file inside a missing directory.
            from sqlalchemy.engine import make_url

            db_path = make_url(url).database
            if db_path and db_path != ":memory:":
                os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
            kwargs["connect_args"] = {"check_same_thread": False}
        elif is_sqlite:
            # Allow the connection to be shared between worker threads and
            # wait for write locks instead of failing fast under contention.
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}

        self.engine = create_engine(url, **kwargs)
        self.Session = sessionmaker(self.engine, expire_on_commit=False)

        if is_sqlite:
            @event.listens_for(self.engine, "connect")
            def _sqlite_pragmas(dbapi_connection, _record):  # noqa: ANN001
                cursor = dbapi_connection.cursor()
                try:
                    cursor.execute("PRAGMA journal_mode=WAL")
                    cursor.execute("PRAGMA busy_timeout=30000")
                    cursor.execute("PRAGMA synchronous=NORMAL")
                finally:
                    cursor.close()

        Base.metadata.create_all(self.engine)

        if is_sqlite:
            self._ensure_idempotency_index()

        logger.info("Database initialized: %s", self.config.database_url)

    def _ensure_idempotency_index(self) -> None:
        """Add the unique idempotency index to databases created before it existed.

        `create_all` never alters an existing table, so older SQLite files would
        silently miss the uniqueness guarantee. Creating the index is safe and
        idempotent; if legacy duplicate keys are present we log a warning and
        keep running rather than failing startup.
        """
        from sqlalchemy import text

        try:
            with self.engine.begin() as conn:
                conn.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS "
                        "ux_jobs_idempotency_key "
                        "ON jobs (idempotency_key) "
                        "WHERE idempotency_key IS NOT NULL"
                    )
                )
        except Exception:  # pragma: no cover - defensive, legacy data only
            logger.warning(
                "Could not create unique idempotency index (duplicate legacy "
                "keys?). Idempotency remains best-effort.",
                exc_info=True,
            )

    async def close(self) -> None:
        if self.engine is not None:
            self.engine.dispose()
            self.engine = None
            self.Session = None

    # ------------------------------------------------------------------- jobs
    async def submit_job(
        self,
        payload: str,
        priority: JobPriority = JobPriority.NORMAL,
        idempotency_key: Optional[str] = None,
        timeout: int = 300,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self._submit_job_sync, payload, priority, idempotency_key, timeout, max_retries)

    def _submit_job_sync(
        self,
        payload: str,
        priority: JobPriority,
        idempotency_key: Optional[str],
        timeout: int,
        max_retries: int,
    ) -> Dict[str, Any]:
        last_error: Optional[Exception] = None
        for _attempt in range(20):
            session = self.Session()
            try:
                if idempotency_key:
                    existing = session.execute(
                        select(Job)
                        .where(Job.idempotency_key == idempotency_key)
                        .limit(1)
                    ).scalar_one_or_none()
                    if existing:
                        # Idempotent replay: always return the job already
                        # associated with this key, whatever its state.
                        return existing.to_dict()

                job = Job(
                    payload=payload,
                    priority=priority,
                    idempotency_key=idempotency_key,
                    timeout=timeout,
                    max_retries=max_retries,
                )
                session.add(job)
                try:
                    session.commit()
                except IntegrityError:
                    # Another concurrent submission won the unique race.
                    session.rollback()
                    existing = session.execute(
                        select(Job)
                        .where(Job.idempotency_key == idempotency_key)
                        .limit(1)
                    ).scalar_one_or_none()
                    if existing:
                        return existing.to_dict()
                    last_error = IntegrityError(
                        "duplicate idempotency key", None, Exception()
                    )
                    time.sleep(0.01)
                    continue

                session.refresh(job)
                metrics.JOBS_SUBMITTED.labels(priority=priority.value).inc()
                logger.info(
                    "Job submitted: %s (priority=%s)", job.job_id, priority.value
                )
                return job.to_dict()
            except OperationalError as exc:
                # SQLite write contention ("database is locked"): retry.
                session.rollback()
                last_error = exc
                time.sleep(0.01)
            finally:
                session.close()

        raise RuntimeError(f"Could not submit job after retries: {last_error}")

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        return await asyncio.to_thread(self._get_job_sync, job_id)

    def _get_job_sync(self, job_id: str) -> Optional[Dict[str, Any]]:
        session = self.Session()
        try:
            result = session.execute(select(Job).where(Job.job_id == job_id))
            job = result.scalar_one_or_none()
            return job.to_dict() if job else None
        finally:
            session.close()

    async def list_jobs(
        self,
        status: Optional[JobStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self._list_jobs_sync, status, limit, offset)

    def _list_jobs_sync(
        self,
        status: Optional[JobStatus],
        limit: int,
        offset: int,
    ) -> Dict[str, Any]:
        session = self.Session()
        try:
            query = select(Job)
            count_query = select(func.count()).select_from(Job)
            if status is not None:
                query = query.where(Job.status == status)
                count_query = count_query.where(Job.status == status)

            total = session.execute(count_query).scalar_one()
            result = session.execute(
                query.order_by(Job.created_at.desc(), Job.id.desc())
                .limit(limit)
                .offset(offset)
            )
            jobs = [job.to_dict() for job in result.scalars().all()]
            return {"jobs": jobs, "total": total, "limit": limit, "offset": offset}
        finally:
            session.close()

    # ------------------------------------------------------------- claiming
    async def claim_job(self, worker_id: str) -> Optional[Dict[str, Any]]:
        return await asyncio.to_thread(self._claim_job_sync, worker_id)

    def _claim_job_sync(self, worker_id: str) -> Optional[Dict[str, Any]]:
        # SQLite has no row-level locking, so a claim is a two-step optimistic
        # operation: pick a candidate, then update it only if it is still
        # pending. If another worker won the race we retry with a fresh
        # candidate instead of giving up (otherwise parallel claimers can
        # starve and leave jobs unclaimed). Each attempt uses a fresh session so
        # a failed attempt never leaves a stale read snapshot behind.
        for _attempt in range(100):
            session = self.Session()
            try:
                now = utcnow()
                result = session.execute(
                    select(Job.id)
                    .where(
                        Job.status == JobStatus.PENDING,
                        or_(Job.next_retry_at.is_(None), Job.next_retry_at <= now),
                    )
                    .order_by(PRIORITY_RANK, Job.created_at, Job.id)
                    .limit(1)
                )
                job_pk = result.scalar_one_or_none()
                if job_pk is None:
                    return None

                update_result = session.execute(
                    update(Job)
                    .where(Job.id == job_pk, Job.status == JobStatus.PENDING)
                    .values(
                        status=JobStatus.CLAIMED,
                        worker_id=worker_id,
                        claimed_at=now,
                        started_at=now,
                        next_retry_at=None,
                    )
                )
                session.commit()

                if update_result.rowcount == 1:
                    job = session.get(Job, job_pk)
                    return job.to_dict() if job else None
                # Lost the race; loop and try the next candidate.
            except OperationalError:
                session.rollback()
                time.sleep(0.01)
            finally:
                session.close()

        return None

    # -------------------------------------------------------------- updates
    # Every terminal transition is guarded by the set of statuses it is allowed
    # to leave. This makes cancellation durable: a worker that finishes after a
    # job was cancelled cannot overwrite `cancelled` with `completed`.
    async def _update_where_status(
        self, job_id: str, allowed: set, **values
    ) -> bool:
        return await asyncio.to_thread(
            self._update_where_status_sync, job_id, allowed, **values
        )

    def _update_where_status_sync(self, job_id: str, allowed: set, **values) -> bool:
        session = self.Session()
        try:
            result = session.execute(
                update(Job)
                .where(Job.job_id == job_id, Job.status.in_(allowed))
                .values(**values)
            )
            session.commit()
            return result.rowcount == 1
        finally:
            session.close()

    async def mark_running(self, job_id: str, worker_id: str) -> bool:
        return await self._update_where_status(
            job_id,
            {JobStatus.CLAIMED, JobStatus.RUNNING},
            status=JobStatus.RUNNING,
            worker_id=worker_id,
        )

    async def complete_job(
        self, job_id: str, result: str, execution_time: float
    ) -> bool:
        updated = await self._update_where_status(
            job_id,
            {JobStatus.CLAIMED, JobStatus.RUNNING},
            status=JobStatus.COMPLETED,
            result=result,
            error=None,
            execution_time=execution_time,
            completed_at=utcnow(),
        )
        if updated:
            metrics.JOBS_COMPLETED.inc()
            metrics.JOB_EXECUTION_SECONDS.observe(execution_time)
        return updated

    async def mark_failed(
        self, job_id: str, error: str, execution_time: float
    ) -> bool:
        updated = await self._update_where_status(
            job_id,
            {JobStatus.PENDING, JobStatus.CLAIMED, JobStatus.RUNNING},
            status=JobStatus.FAILED,
            error=error,
            execution_time=execution_time,
            completed_at=utcnow(),
        )
        if updated:
            metrics.JOBS_FAILED.inc()
        return updated

    async def schedule_retry(
        self,
        job_id: str,
        error: str,
        execution_time: float,
        retry_count: int,
        next_retry_at: datetime,
    ) -> bool:
        return await self._update_where_status(
            job_id,
            {JobStatus.PENDING, JobStatus.CLAIMED, JobStatus.RUNNING},
            status=JobStatus.RETRYING,
            error=error,
            execution_time=execution_time,
            retry_count=retry_count,
            next_retry_at=next_retry_at,
            claimed_at=None,
            worker_id=None,
        )

    async def mark_dead_letter(
        self,
        job_id: str,
        error: str,
        execution_time: float,
        retry_count: int,
    ) -> bool:
        updated = await self._update_where_status(
            job_id,
            {JobStatus.PENDING, JobStatus.CLAIMED, JobStatus.RUNNING},
            status=JobStatus.DEAD_LETTER,
            error=error,
            execution_time=execution_time,
            retry_count=retry_count,
            completed_at=utcnow(),
        )
        if updated:
            metrics.JOBS_DEAD_LETTER.inc()
        return updated

    async def cancel_job(self, job_id: str) -> bool:
        updated = await self._update_where_status(
            job_id,
            {
                JobStatus.PENDING,
                JobStatus.CLAIMED,
                JobStatus.RUNNING,
                JobStatus.RETRYING,
            },
            status=JobStatus.CANCELLED,
            completed_at=utcnow(),
            claimed_at=None,
            worker_id=None,
        )
        if updated:
            metrics.JOBS_CANCELLED.inc()
        return updated

    async def requeue_stale_jobs(self, older_than_seconds: float = 0.0) -> int:
        return await asyncio.to_thread(
            self._requeue_stale_jobs_sync, older_than_seconds
        )

    def _requeue_stale_jobs_sync(self, older_than_seconds: float = 0.0) -> int:
        session = self.Session()
        try:
            statement = update(Job).where(
                Job.status.in_([JobStatus.CLAIMED, JobStatus.RUNNING])
            )
            if older_than_seconds > 0:
                cutoff = utcnow() - timedelta(seconds=older_than_seconds)
                statement = statement.where(
                    func.coalesce(Job.started_at, Job.claimed_at, Job.created_at)
                    <= cutoff
                )
            # `coalesce` cannot be evaluated in Python, so the ORM must not try
            # to synchronise loaded objects for this bulk update.
            statement = statement.execution_options(synchronize_session=False)
            result = session.execute(
                statement.values(
                    status=JobStatus.PENDING,
                    claimed_at=None,
                    started_at=None,
                    worker_id=None,
                )
            )
            session.commit()
            if result.rowcount:
                logger.warning("Requeued %d stale job(s)", result.rowcount)
            return result.rowcount
        finally:
            session.close()

    async def promote_due_retries(self, now: Optional[datetime] = None) -> int:
        return await asyncio.to_thread(self._promote_due_retries_sync, now)

    def _promote_due_retries_sync(self, now: Optional[datetime] = None) -> int:
        now = now or utcnow()
        session = self.Session()
        try:
            result = session.execute(
                update(Job)
                .where(
                    Job.status == JobStatus.RETRYING,
                    Job.next_retry_at.isnot(None),
                    Job.next_retry_at <= now,
                )
                .values(status=JobStatus.PENDING, next_retry_at=None)
            )
            session.commit()
            return result.rowcount
        finally:
            session.close()

    # ---------------------------------------------------------------- stats
    async def count_by_status(self) -> Dict[str, int]:
        return await asyncio.to_thread(self._count_by_status_sync)

    def _count_by_status_sync(self) -> Dict[str, int]:
        session = self.Session()
        try:
            result = session.execute(
                select(Job.status, func.count()).group_by(Job.status)
            )
            counts = {status.value: 0 for status in JobStatus}
            for status, count in result.all():
                key = status.value if isinstance(status, JobStatus) else str(status)
                counts[key] = count
            return counts
        finally:
            session.close()

    async def average_execution_time(self) -> Optional[float]:
        return await asyncio.to_thread(self._average_execution_time_sync)

    def _average_execution_time_sync(self) -> Optional[float]:
        session = self.Session()
        try:
            result = session.execute(
                select(func.avg(Job.execution_time)).where(
                    Job.status == JobStatus.COMPLETED,
                    Job.execution_time.isnot(None),
                )
            )
            value = result.scalar_one_or_none()
            return float(value) if value is not None else None
        finally:
            session.close()

    async def stats(self) -> Dict[str, Any]:
        counts = await self.count_by_status()
        oldest = await asyncio.to_thread(self._oldest_pending_sync)
        return {
            "total_jobs": sum(counts.values()),
            "status_counts": counts,
            "pending_jobs": counts.get(JobStatus.PENDING.value, 0),
            "claimed_jobs": counts.get(JobStatus.CLAIMED.value, 0),
            "running_jobs": counts.get(JobStatus.RUNNING.value, 0),
            "completed_jobs": counts.get(JobStatus.COMPLETED.value, 0),
            "failed_jobs": counts.get(JobStatus.FAILED.value, 0),
            "cancelled_jobs": counts.get(JobStatus.CANCELLED.value, 0),
            "retrying_jobs": counts.get(JobStatus.RETRYING.value, 0),
            "dead_letter_jobs": counts.get(JobStatus.DEAD_LETTER.value, 0),
            "oldest_pending_job": oldest,
        }

    def _oldest_pending_sync(self) -> Optional[str]:
        session = self.Session()
        try:
            result = session.execute(
                select(func.min(Job.created_at)).where(
                    Job.status == JobStatus.PENDING
                )
            )
            oldest_pending = result.scalar_one_or_none()
            return oldest_pending.isoformat() if oldest_pending else None
        finally:
            session.close()

    async def job_status_counts_by_priority(self) -> Dict[str, int]:
        return await asyncio.to_thread(self._job_status_counts_by_priority_sync)

    def _job_status_counts_by_priority_sync(self) -> Dict[str, int]:
        session = self.Session()
        try:
            result = session.execute(
                select(Job.priority, func.count()).group_by(Job.priority)
            )
            return {
                (priority.value if isinstance(priority, JobPriority) else str(priority)): count
                for priority, count in result.all()
            }
        finally:
            session.close()
