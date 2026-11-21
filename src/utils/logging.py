import logging
import structlog
from typing import Any, Dict, Optional
from datetime import datetime
import json

from ..config import JobEngineConfig


def setup_logging(config: JobEngineConfig):
    """Setup structured logging"""
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Configure standard logging
    logging.basicConfig(
        format="message",
        level=getattr(logging, config.log_level.upper()),
        handlers=[
            logging.StreamHandler()
        ]
    )
    
    return structlog.get_logger()


def log_job_event(
    event: str,
    job_id: str,
    worker_id: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """Create a structured log entry for job events"""
    
    log_data = {
        "event": event,
        "job_id": job_id,
        "timestamp": datetime.utcnow().isoformat(),
        **kwargs
    }
    
    if worker_id:
        log_data["worker_id"] = worker_id
    
    return log_data


class JobLogger:
    """Logger specifically for job-related events"""
    
    def __init__(self, name: str):
        self.logger = structlog.get_logger(name)
    
    def job_submitted(self, job_id: str, priority: str, idempotency_key: Optional[str] = None):
        """Log job submission"""
        self.logger.info(
            "Job submitted",
            job_id=job_id,
            priority=priority,
            idempotency_key=idempotency_key
        )
    
    def job_claimed(self, job_id: str, worker_id: str):
        """Log job claiming"""
        self.logger.info(
            "Job claimed",
            job_id=job_id,
            worker_id=worker_id
        )
    
    def job_started(self, job_id: str, worker_id: str):
        """Log job start"""
        self.logger.info(
            "Job started",
            job_id=job_id,
            worker_id=worker_id
        )
    
    def job_completed(self, job_id: str, worker_id: str, execution_time: float):
        """Log job completion"""
        self.logger.info(
            "Job completed",
            job_id=job_id,
            worker_id=worker_id,
            execution_time=execution_time
        )
    
    def job_failed(self, job_id: str, worker_id: str, error: str, retry_count: int, max_retries: int):
        """Log job failure"""
        self.logger.error(
            "Job failed",
            job_id=job_id,
            worker_id=worker_id,
            error=error,
            retry_count=retry_count,
            max_retries=max_retries
        )
    
    def job_retried(self, job_id: str, worker_id: str, retry_count: int, next_retry_at: str):
        """Log job retry"""
        self.logger.info(
            "Job retried",
            job_id=job_id,
            worker_id=worker_id,
            retry_count=retry_count,
            next_retry_at=next_retry_at
        )
    
    def job_cancelled(self, job_id: str, worker_id: Optional[str] = None):
        """Log job cancellation"""
        self.logger.info(
            "Job cancelled",
            job_id=job_id,
            worker_id=worker_id
        )