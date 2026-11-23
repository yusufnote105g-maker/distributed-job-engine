"""HTTP API routes."""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from ..config import JobEngineConfig
from ..models import JobPriority, JobStatus
from ..services.database import DatabaseService
from ..services.job_processor import JobProcessor

logger = logging.getLogger(__name__)

router = APIRouter()


# --------------------------------------------------------------------- models
class JobSubmissionRequest(BaseModel):
    payload: str = Field(
        ..., min_length=1, max_length=100_000, description="Opaque job payload"
    )
    priority: JobPriority = Field(JobPriority.NORMAL, description="Scheduling priority")
    idempotency_key: Optional[str] = Field(
        None, max_length=64, description="Deduplication key"
    )
    timeout: Optional[int] = Field(
        None, ge=1, le=86_400, description="Per-job timeout in seconds"
    )
    max_retries: Optional[int] = Field(
        None, ge=0, le=100, description="Per-job retry budget"
    )


class JobResponse(BaseModel):
    id: int
    job_id: str
    idempotency_key: Optional[str] = None
    payload: str
    priority: str
    status: str
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    claimed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int
    max_retries: int
    next_retry_at: Optional[datetime] = None
    worker_id: Optional[str] = None
    timeout: int
    result: Optional[str] = None
    error: Optional[str] = None
    execution_time: Optional[float] = None


class JobsListResponse(BaseModel):
    jobs: List[JobResponse]
    total: int
    limit: int
    offset: int


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    version: str
    database_status: str
    worker_status: str


class MessageResponse(BaseModel):
    message: str


# --------------------------------------------------------------- dependencies
def get_db(request: Request) -> DatabaseService:
    return request.app.state.db_service


def get_processor(request: Request) -> JobProcessor:
    return request.app.state.job_processor


def get_config(request: Request) -> JobEngineConfig:
    return request.app.state.config


def require_api_key(request: Request) -> None:
    config: JobEngineConfig = request.app.state.config
    if not config.secret_key:
        return
    provided = request.headers.get(config.api_key_header)
    if provided != config.secret_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )


# ------------------------------------------------------------------- endpoints
@router.post(
    "/jobs",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
)
async def submit_job(
    body: JobSubmissionRequest,
    processor: JobProcessor = Depends(get_processor),
):
    """Submit a job for asynchronous processing."""
    try:
        job = await processor.submit_job(
            payload=body.payload,
            priority=body.priority,
            idempotency_key=body.idempotency_key,
            timeout=body.timeout,
            max_retries=body.max_retries,
        )
    except Exception:
        logger.exception("Job submission failed")
        raise HTTPException(status_code=500, detail="Job submission failed")
    return JobResponse(**job)


@router.get("/jobs", response_model=JobsListResponse)
async def list_jobs(
    status_filter: Optional[JobStatus] = Query(
        None, alias="status", description="Filter by status"
    ),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: DatabaseService = Depends(get_db),
):
    data = await db.list_jobs(status=status_filter, limit=limit, offset=offset)
    return JobsListResponse(
        jobs=[JobResponse(**job) for job in data["jobs"]],
        total=data["total"],
        limit=data["limit"],
        offset=data["offset"],
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, db: DatabaseService = Depends(get_db)):
    job = await db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return JobResponse(**job)


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=MessageResponse,
    dependencies=[Depends(require_api_key)],
)
async def cancel_job(job_id: str, db: DatabaseService = Depends(get_db)):
    job = await db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    if not await db.cancel_job(job_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job in status '{job['status']}' cannot be cancelled",
        )
    return MessageResponse(message="Job cancelled successfully")


@router.delete(
    "/jobs/{job_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_api_key)],
)
async def delete_job(job_id: str, db: DatabaseService = Depends(get_db)):
    """REST-style alias of POST /jobs/{job_id}/cancel."""
    return await cancel_job(job_id, db)


@router.get("/health", response_model=HealthResponse)
async def health_check(
    request: Request,
    db: DatabaseService = Depends(get_db),
    processor: JobProcessor = Depends(get_processor),
):
    database_status = "ok"
    try:
        await db.count_by_status()
    except Exception:
        logger.exception("Health check: database unreachable")
        database_status = "error"

    worker_status = "running" if processor.running else "stopped"
    healthy = database_status == "ok" and (
        worker_status == "running" or not request.app.state.config.enable_workers
    )

    return HealthResponse(
        status="healthy" if healthy else "degraded",
        timestamp=datetime.utcnow(),
        version=request.app.state.version,
        database_status=database_status,
        worker_status=worker_status,
    )


@router.get("/stats")
async def get_stats(db: DatabaseService = Depends(get_db)):
    return await db.stats()


@router.get("/metrics")
async def get_metrics(processor: JobProcessor = Depends(get_processor)):
    return await processor.metrics()
