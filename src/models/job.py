from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, Boolean, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from enum import Enum as PyEnum
from datetime import datetime
import uuid

Base = declarative_base()


class JobStatus(PyEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"
    DEAD_LETTER = "dead_letter"


class JobPriority(PyEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class Job(Base):
    __tablename__ = "jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String(36), unique=True, index=True, default=lambda: str(uuid.uuid4()))
    idempotency_key = Column(String(64), index=True, nullable=True)
    
    # Job content
    payload = Column(Text, nullable=False)
    priority = Column(Enum(JobPriority), default=JobPriority.NORMAL, index=True)
    
    # Status and metadata
    status = Column(Enum(JobStatus), default=JobStatus.PENDING, index=True)
    created_at = Column(DateTime, default=func.now(), index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    claimed_at = Column(DateTime, nullable=True)
    
    # Retry configuration
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    next_retry_at = Column(DateTime, nullable=True)
    
    # Worker tracking
    worker_id = Column(String(64), nullable=True)
    timeout = Column(Integer, default=300)  # seconds
    
    # Results and errors
    result = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    
    # Performance metrics
    execution_time = Column(Float, nullable=True)
    
    def to_dict(self):
        return {
            "id": self.id,
            "job_id": self.job_id,
            "idempotency_key": self.idempotency_key,
            "payload": self.payload,
            "priority": self.priority.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "claimed_at": self.claimed_at.isoformat() if self.claimed_at else None,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "next_retry_at": self.next_retry_at.isoformat() if self.next_retry_at else None,
            "worker_id": self.worker_id,
            "timeout": self.timeout,
            "result": self.result,
            "error": self.error,
            "execution_time": self.execution_time
        }