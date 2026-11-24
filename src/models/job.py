"""SQLAlchemy models for the job engine."""

import uuid
from enum import Enum as PyEnum

from sqlalchemy import Column, DateTime, Enum, Float, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base

from ..utils import utcnow


Base = declarative_base()


class JobStatus(str, PyEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"
    DEAD_LETTER = "dead_letter"


class JobPriority(str, PyEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def weight(self) -> int:
        return _PRIORITY_WEIGHT[self]


_PRIORITY_WEIGHT = {
    JobPriority.LOW: 0,
    JobPriority.NORMAL: 1,
    JobPriority.HIGH: 2,
    JobPriority.CRITICAL: 3,
}


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(
        String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4())
    )
    idempotency_key = Column(String(64), nullable=True, unique=True, index=True)

    payload = Column(Text, nullable=False)
    priority = Column(
        Enum(
            JobPriority,
            values_callable=lambda e: [x.value for x in e],
            native_enum=False,
        ),
        nullable=False,
        default=JobPriority.NORMAL,
        index=True,
    )
    timeout = Column(Integer, nullable=False, default=300)

    status = Column(
        Enum(
            JobStatus,
            values_callable=lambda e: [x.value for x in e],
            native_enum=False,
        ),
        nullable=False,
        default=JobStatus.PENDING,
        index=True,
    )
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    next_retry_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, default=utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    claimed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    worker_id = Column(String(64), nullable=True)

    result = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    execution_time = Column(Float, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "idempotency_key": self.idempotency_key,
            "payload": self.payload,
            "priority": self.priority.value if self.priority else None,
            "status": self.status.value if self.status else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "claimed_at": self.claimed_at.isoformat() if self.claimed_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "next_retry_at": (
                self.next_retry_at.isoformat() if self.next_retry_at else None
            ),
            "worker_id": self.worker_id,
            "timeout": self.timeout,
            "result": self.result,
            "error": self.error,
            "execution_time": self.execution_time,
        }
