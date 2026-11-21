from fastapi import APIRouter, Depends, HTTPException, Query, Header
from typing import Optional, List
from pydantic import BaseModel, Field
import logging
from datetime import datetime

from ..models import JobStatus, JobPriority
from ..services.database import DatabaseService
from ..services.job_processor import JobProcessor
from ..config import JobEngineConfig

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic models for request/response
class JobSubmissionRequest(BaseModel):
    payload: str = Field(..., min_length=1, max_length=10000)
    priority: JobPriority = JobPriority.NORMAL
    idempotency_key: Optional[str] = Field(None, max_length=64)
    timeout: Optional[int] = Field(None, ge=1, le=3600)


class JobResponse(BaseModel):
    id: int
    job_id: str
    idempotency_key: Optional[str]
    payload: str
    priority: str
    status: str
    created_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    claimed_at: Optional[datetime]
    retry_count: int
    max_retries: int
    next_retry_at: Optional[datetime]
    worker_id: Optional[str]
    timeout: int
    result: Optional[str]
    error: Optional[str]
    execution_time: Optional[float]


class JobsListResponse(BaseModel):
    jobs: List[JobResponse]
    total: int
    limit: int
    offset: int


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    database_status: bool
    worker_status: dict


class MetricsResponse(BaseModel):
    status_counts: dict
    total_jobs: int
    average_execution_time: Optional[float]
    worker_count: int
    worker_id: str


# Dependency injection
def get_db_service() -> DatabaseService:
    # This would normally be injected via FastAPI's dependency system
    # For simplicity, we'll create a new instance each time
    config = JobEngineConfig()
    return DatabaseService(config)


def get_job_processor() -> JobProcessor:
    # This would normally be injected via FastAPI's dependency system
    # For simplicity, we'll create a new instance each time
    config = JobEngineConfig()
    db_service = get_db_service()
    return JobProcessor(config, db_service)


@router.post("/jobs", response_model=JobResponse, status_code=201)
async def submit_job(
    request: JobSubmissionRequest,
    x_api_key: Optional[str] = Header(None),
    db_service: DatabaseService = Depends(get_db_service),
    job_processor: JobProcessor = Depends(get_job_processor)
):
    """Submit a new job for processing"""
    
    # Validate API key if configured
    if JobEngineConfig().api_key_header and x_api_key != JobEngineConfig().secret_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    try:
        job = await job_processor.submit_job(
            payload=request.payload,
            priority=request.priority,
            idempotency_key=request.idempotency_key,
            timeout=request.timeout
        )
        return JobResponse(**job.to_dict())
    except Exception as e:
        logger.error(f"Failed to submit job: {e}")
        raise HTTPException(status_code=500, detail="Failed to submit job")


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    db_service: DatabaseService = Depends(get_db_service),
    job_processor: JobProcessor = Depends(get_job_processor)
):
    """Get job by ID"""
    
    job = await job_processor.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return JobResponse(**job.to_dict())


@router.get("/jobs", response_model=JobsListResponse)
async def get_jobs(
    status: Optional[JobStatus] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db_service: DatabaseService = Depends(get_db_service),
    job_processor: JobProcessor = Depends(get_job_processor)
):
    """Get jobs with optional filtering and pagination"""
    
    jobs = await job_processor.get_jobs(status=status, limit=limit, offset=offset)
    
    return JobsListResponse(
        jobs=[JobResponse(**job.to_dict()) for job in jobs],
        total=len(jobs),
        limit=limit,
        offset=offset
    )


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    db_service: DatabaseService = Depends(get_db_service),
    job_processor: JobProcessor = Depends(get_job_processor)
):
    """Cancel a job"""
    
    success = await job_processor.cancel_job(job_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Job not found or cannot be cancelled")
    
    return {"message": "Job cancelled successfully"}


@router.get("/health", response_model=HealthResponse)
async def health_check(
    db_service: DatabaseService = Depends(get_db_service),
    job_processor: JobProcessor = Depends(get_job_processor)
):
    """Health check endpoint"""
    
    database_status = await db_service.health_check()
    
    return HealthResponse(
        status="healthy" if database_status else "degraded",
        timestamp=datetime.utcnow(),
        database_status=database_status,
        worker_status={
            "worker_count": job_processor.config.worker_count,
            "worker_id": job_processor.worker_id,
            "running": job_processor.running
        }
    )


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    db_service: DatabaseService = Depends(get_db_service),
    job_processor: JobProcessor = Depends(get_job_processor)
):
    """Get job processing metrics"""
    
    metrics = await job_processor.get_metrics()
    
    return MetricsResponse(**metrics)