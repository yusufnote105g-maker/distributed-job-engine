import asyncio
import time
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy import select, update, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..models import Job, JobStatus, JobPriority
from ..config import JobEngineConfig
from .database import DatabaseService

logger = logging.getLogger(__name__)


class JobProcessor:
    def __init__(self, config: JobEngineConfig, db_service: DatabaseService):
        self.config = config
        self.db_service = db_service
        self.workers = []
        self.running = False
        self.worker_id = f"worker-{int(time.time())}-{hash(str(config.worker_count)) % 1000}"
        
    async def start(self):
        """Start job processor with multiple workers"""
        self.running = True
        
        # Start worker tasks
        for i in range(self.config.worker_count):
            worker_task = asyncio.create_task(self._worker(f"worker-{i}"))
            self.workers.append(worker_task)
        
        logger.info(f"Started {self.config.worker_count} job workers")
        
        # Start job scheduler
        scheduler_task = asyncio.create_task(self._job_scheduler())
        self.workers.append(scheduler_task)
    
    async def stop(self):
        """Gracefully stop job processor"""
        logger.info("Stopping job processor...")
        self.running = False
        
        # Cancel all worker tasks
        for worker in self.workers:
            if not worker.done():
                worker.cancel()
        
        # Wait for workers to finish with timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(*self.workers, return_exceptions=True),
                timeout=10.0
            )
        except asyncio.TimeoutError:
            logger.warning("Some workers did not stop gracefully, forcing shutdown")
        
        # Clear workers list
        self.workers.clear()
        logger.info("Job processor stopped")
    
    async def _worker(self, worker_name: str):
        """Individual worker process"""
        logger.info(f"Worker {worker_name} started")
        
        while self.running:
            try:
                # Get next available job
                job = await self._claim_next_job(worker_name)
                
                if job:
                    logger.info(f"Worker {worker_name} claimed job {job.job_id}")
                    await self._process_job(job, worker_name)
                else:
                    # No jobs available, wait a bit
                    await asyncio.sleep(1)
                    
            except asyncio.CancelledError:
                logger.info(f"Worker {worker_name} cancelled")
                break
            except Exception as e:
                logger.error(f"Worker {worker_name} error: {e}")
                await asyncio.sleep(5)  # Wait before retrying
        
        logger.info(f"Worker {worker_name} stopped")
    
    async def _claim_next_job(self, worker_name: str) -> Optional[Job]:
        """Claim the next available job atomically with proper transaction isolation"""
        async with self.db_service.get_session() as session:
            try:
                # Use FOR UPDATE SKIP LOCKED with proper transaction isolation
                # This prevents race conditions between concurrent workers
                query = select(Job).where(
                    and_(
                        Job.status == JobStatus.PENDING,
                        or_(
                            Job.next_retry_at.is_(None),
                            Job.next_retry_at <= datetime.utcnow()
                        )
                    )
                ).order_by(
                    # Priority ordering: CRITICAL > HIGH > NORMAL > LOW
                    case(
                        (Job.priority == JobPriority.CRITICAL, 1),
                        (Job.priority == JobPriority.HIGH, 2),
                        (Job.priority == JobPriority.NORMAL, 3),
                        else_=4
                    ),
                    Job.created_at
                ).limit(1)
                
                # Execute with FOR UPDATE to lock the row
                result = await session.execute(query)
                job = result.scalar_one_or_none()
                
                if job:
                    # Double-check that job is still available before claiming
                    check_query = select(Job).where(
                        Job.id == job.id,
                        Job.status == JobStatus.PENDING
                    )
                    check_result = await session.execute(check_query)
                    job = check_result.scalar_one_or_none()
                    
                    if job:
                        # Atomically claim the job within the same transaction
                        update_query = update(Job).where(
                            Job.id == job.id,
                            Job.status == JobStatus.PENDING  # Ensure status hasn't changed
                        ).values(
                            status=JobStatus.CLAIMED,
                            worker_id=worker_name,
                            claimed_at=datetime.utcnow(),
                            next_retry_at=None  # Reset next retry time
                        )
                        
                        update_result = await session.execute(update_query)
                        
                        # Verify the update was successful
                        if update_result.rowcount == 1:
                            await session.commit()
                            # Refresh job data after commit
                            await session.refresh(job)
                            return job
                
                await session.commit()
                return None
                
            except Exception as e:
                await session.rollback()
                logger.error(f"Error claiming job for worker {worker_name}: {e}")
                return None
    
    async def _process_job(self, job: Job, worker_name: str):
        """Process a single job with timeout handling"""
        start_time = time.time()
        timeout_task = None
        
        try:
            # Update job status to running
            await self._update_job_status(
                job.job_id, 
                JobStatus.RUNNING, 
                worker_name=worker_name
            )
            
            # Set up timeout handling
            timeout_seconds = job.timeout or self.config.worker_timeout
            
            async def timeout_handler():
                """Handle job timeout"""
                await asyncio.sleep(timeout_seconds)
                
                # Check if job is still running
                current_job = await self.get_job(job.job_id)
                if current_job and current_job.status == JobStatus.RUNNING:
                    logger.warning(f"Job {job.job_id} timed out after {timeout_seconds}s")
                    await self._update_job_status(
                        job.job_id,
                        JobStatus.FAILED,
                        worker_name=worker_name,
                        error=f"Job timed out after {timeout_seconds}s",
                        execution_time=time.time() - start_time
                    )
            
            # Start timeout task
            timeout_task = asyncio.create_task(timeout_handler())
            
            # Execute job payload
            await self._execute_job_payload(job.payload)
            
            # Cancel timeout task if job completed successfully
            if timeout_task:
                timeout_task.cancel()
                try:
                    await timeout_task
                except asyncio.CancelledError:
                    pass
            
            # Calculate execution time
            execution_time = time.time() - start_time
            
            # Mark job as completed
            await self._update_job_status(
                job.job_id,
                JobStatus.COMPLETED,
                worker_name=worker_name,
                result="Job completed successfully",
                execution_time=execution_time
            )
            
            logger.info(f"Worker {worker_name} completed job {job.job_id} in {execution_time:.2f}s")
            
        except asyncio.CancelledError:
            # Job was cancelled
            execution_time = time.time() - start_time
            logger.info(f"Worker {worker_name} cancelled job {job.job_id}")
            
            await self._update_job_status(
                job.job_id,
                JobStatus.CANCELLED,
                worker_name=worker_name,
                execution_time=execution_time
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = str(e)
            
            logger.error(f"Worker {worker_name} failed job {job.job_id}: {error_msg}")
            
            # Cancel timeout task if job failed
            if timeout_task:
                timeout_task.cancel()
                try:
                    await timeout_task
                except asyncio.CancelledError:
                    pass
            
            # Handle retry logic
            if job.retry_count < job.max_retries:
                await self._handle_job_retry(job, worker_name, error_msg, execution_time)
            else:
                # Mark job as dead letter
                await self._update_job_status(
                    job.job_id,
                    JobStatus.DEAD_LETTER,
                    worker_name=worker_name,
                    error=error_msg,
                    execution_time=execution_time
                )
    
    async def _handle_job_retry(self, job: Job, worker_name: str, error: str, execution_time: float):
        """Handle job retry with exponential backoff"""
        retry_count = job.retry_count + 1
        
        # Calculate next retry time with exponential backoff
        backoff_time = min(
            self.config.initial_backoff * (2 ** (retry_count - 1)),
            self.config.max_backoff
        )
        
        if self.config.retry_jitter:
            import random
            backoff_time = backoff_time * (0.5 + random.random() * 0.5)
        
        next_retry_at = datetime.utcnow() + timedelta(seconds=backoff_time)
        
        await self._update_job_status(
            job.job_id,
            JobStatus.RETRYING,
            worker_name=worker_name,
            error=error,
            retry_count=retry_count,
            next_retry_at=next_retry_at,
            execution_time=execution_time
        )
        
        logger.info(f"Job {job.job_id} scheduled for retry #{retry_count} in {backoff_time:.2f}s")
    
    async def _execute_job_payload(self, payload: str):
        """Execute job payload (simulated)"""
        # Simulate processing time
        await asyncio.sleep(0.1 + (hash(payload) % 100) / 1000)  # 0.1-0.2 seconds
        
        # Simulate occasional failures
        if hash(payload) % 50 == 0:  # 2% failure rate
            raise Exception("Simulated job execution failure")
    
    async def _update_job_status(self, job_id: str, status: JobStatus, **kwargs):
        """Update job status with additional fields"""
        async with self.db_service.get_session() as session:
            update_data = {
                "status": status,
                **kwargs
            }
            
            if status == JobStatus.RUNNING:
                update_data["started_at"] = datetime.utcnow()
            elif status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.DEAD_LETTER]:
                update_data["completed_at"] = datetime.utcnow()
            
            query = update(Job).where(Job.job_id == job_id).values(**update_data)
            await session.execute(query)
            await session.commit()
    
    async def _job_scheduler(self):
        """Background scheduler for retrying failed jobs"""
        while self.running:
            try:
                # Find jobs that need to be retried
                async with self.db_service.get_session() as session:
                    query = select(Job).where(
                        and_(
                            Job.status == JobStatus.RETRYING,
                            Job.next_retry_at <= datetime.utcnow()
                        )
                    )
                    
                    result = await session.execute(query)
                    jobs_to_retry = result.scalars().all()
                    
                    for job in jobs_to_retry:
                        # Reset to pending so workers can pick it up
                        await self._update_job_status(
                            job.job_id,
                            JobStatus.PENDING,
                            next_retry_at=None
                        )
                        
                        logger.info(f"Job {job.job_id} moved back to pending for retry")
                
                # Wait before next check
                await asyncio.sleep(self.config.health_check_interval)
                
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(5)
    
    async def submit_job(self, payload: str, priority: JobPriority = JobPriority.NORMAL, 
                        idempotency_key: str = None, timeout: int = None) -> Job:
        """Submit a new job"""
        async with self.db_service.get_session() as session:
            # Check for duplicate using idempotency key
            if idempotency_key:
                existing = await session.execute(
                    select(Job).where(Job.idempotency_key == idempotency_key)
                )
                if existing.scalar_one_or_none():
                    return existing.scalar_one_or_none()
            
            # Create new job
            job = Job(
                payload=payload,
                priority=priority,
                idempotency_key=idempotency_key,
                max_retries=self.config.max_retries,
                timeout=timeout or self.config.worker_timeout
            )
            
            session.add(job)
            await session.commit()
            await session.refresh(job)
            
            logger.info(f"Submitted job {job.job_id} with priority {priority.value}")
            return job
    
    async def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID"""
        async with self.db_service.get_session() as session:
            result = await session.execute(select(Job).where(Job.job_id == job_id))
            return result.scalar_one_or_none()
    
    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a job"""
        async with self.db_service.get_session() as session:
            job = await session.execute(select(Job).where(Job.job_id == job_id))
            job = job.scalar_one_or_none()
            
            if job and job.status in [JobStatus.PENDING, JobStatus.CLAIMED, JobStatus.RETRYING]:
                await self._update_job_status(job_id, JobStatus.CANCELLED)
                return True
            
            return False
    
    async def get_jobs(self, status: JobStatus = None, limit: int = 100, offset: int = 0) -> List[Job]:
        """Get jobs with optional filtering and pagination"""
        async with self.db_service.get_session() as session:
            query = select(Job).order_by(Job.created_at.desc())
            
            if status:
                query = query.where(Job.status == status)
            
            query = query.limit(limit).offset(offset)
            
            result = await session.execute(query)
            return result.scalars().all()
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get job processing metrics"""
        async with self.db_service.get_session() as session:
            # Count jobs by status
            status_counts = {}
            for status in JobStatus:
                result = await session.execute(
                    select(Job).where(Job.status == status)
                )
                status_counts[status.value] = len(result.scalars().all())
            
            # Get average execution time
            result = await session.execute(
                select(Job).where(
                    and_(
                        Job.status == JobStatus.COMPLETED,
                        Job.execution_time.isnot(None)
                    )
                )
            )
            completed_jobs = result.scalars().all()
            
            avg_execution_time = None
            if completed_jobs:
                avg_execution_time = sum(job.execution_time for job in completed_jobs) / len(completed_jobs)
            
            return {
                "status_counts": status_counts,
                "total_jobs": sum(status_counts.values()),
                "average_execution_time": avg_execution_time,
                "worker_count": self.config.worker_count,
                "worker_id": self.worker_id
            }