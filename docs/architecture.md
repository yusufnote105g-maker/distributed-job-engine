# Distributed Job Engine - Architecture Documentation

## Overview

The Distributed Job Engine is a production-oriented distributed job processing engine built with FastAPI and SQLite. It provides reliable background job processing with support for priorities, retries, timeouts, and concurrent workers.

## Architecture Components

### 1. Core Components

#### JobProcessor
The main processing engine that manages job lifecycle:
- **Job Submission**: Accepts new jobs with configurable priorities and timeouts
- **Job Distribution**: Distributes jobs among multiple workers based on priority
- **Job Execution**: Monitors job execution and handles timeouts
- **Retry Logic**: Implements exponential backoff for failed jobs
- **Graceful Shutdown**: Ensures all jobs are completed before shutdown

#### DatabaseService
Handles all database operations:
- **Connection Management**: Manages SQLite database connections
- **Transaction Safety**: Ensures atomic operations for job claiming
- **Session Management**: Provides async database sessions
- **Health Checks**: Monitors database connectivity

#### API Routes
RESTful API endpoints for job management:
- **POST /jobs**: Submit new jobs
- **GET /jobs/{job_id}: Get job status
- **GET /jobs**: List jobs with pagination
- **POST /jobs/{job_id}/cancel**: Cancel jobs
- **GET /health**: Health check
- **GET /metrics**: System metrics

### 2. Data Model

#### Job Entity
```python
class Job(Base):
    id = Column(Integer, primary_key=True)
    job_id = Column(String(36), unique=True, index=True)
    idempotency_key = Column(String(64), index=True)
    payload = Column(Text, nullable=False)
    priority = Column(Enum(JobPriority), default=JobPriority.NORMAL)
    status = Column(Enum(JobStatus), default=JobStatus.PENDING)
    created_at = Column(DateTime, default=func.now())
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    next_retry_at = Column(DateTime, nullable=True)
    worker_id = Column(String(64), nullable=True)
    timeout = Column(Integer, default=300)
    result = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    execution_time = Column(Float, nullable=True)
```

#### Job States
- **PENDING**: Job is waiting to be processed
- **CLAIMED**: Job has been claimed by a worker
- **RUNNING**: Job is currently being processed
- **COMPLETED**: Job completed successfully
- **FAILED**: Job failed but can be retried
- **CANCELLED**: Job was cancelled by user
- **RETRYING**: Job failed and is scheduled for retry
- **DEAD_LETTER**: Job failed permanently after max retries

#### Job Priorities
- **CRITICAL**: Highest priority, processed first
- **HIGH**: High priority
- **NORMAL**: Default priority
- **LOW**: Lowest priority

### 3. Concurrency Model

#### Worker Architecture
- Multiple independent worker processes
- Each worker polls for available jobs
- Jobs are claimed atomically to prevent race conditions
- Workers process jobs independently with no shared state

#### Job Claiming Mechanism
1. Worker queries for available jobs
2. Uses `FOR UPDATE` to lock the job row
3. Updates job status to CLAIMED atomically
4. Only one worker can claim each job

#### Race Condition Prevention
- Database-level row locking
- Atomic job status updates
- Idempotency keys for duplicate prevention
- Transaction isolation for concurrent operations

### 4. Error Handling and Recovery

#### Retry Strategy
- Exponential backoff with jitter
- Configurable maximum retry attempts
- Automatic retry scheduling
- Dead letter queue for permanently failed jobs

#### Timeout Handling
- Per-job timeout configuration
- Automatic timeout detection
- Graceful failure on timeout
- Timeout cancellation of running jobs

#### Crash Recovery
- Jobs survive application restarts
- In-progress jobs are retried
- Failed jobs are automatically rescheduled
- No data loss on application failure

### 5. Performance Considerations

#### Database Optimization
- Indexes on frequently queried fields
- Efficient job ordering by priority and creation time
- Connection pooling for better performance
- Minimal locking duration

#### Memory Usage
- Lightweight SQLite database
- Efficient job serialization
- No in-memory job queues
- Minimal worker memory footprint

#### Scalability
- Horizontal scaling via multiple workers
- Database remains the bottleneck (as designed)
- No external dependencies
- Simple deployment model

### 6. Security Features

#### Input Validation
- Payload size limits
- Priority validation
- Timeout bounds checking
- Idempotency key validation

#### API Security
- Optional API key authentication
- Configurable secret key
- Request size limits
- Rate limiting capabilities

#### Database Security
- No hardcoded credentials
- Environment variable support
- Secure default configuration
- No sensitive data logging

### 7. Monitoring and Observability

#### Metrics Collection
- Job status counts
- Processing times
- Worker utilization
- Throughput measurements

#### Health Checks
- Database connectivity
- Worker status
- System resources
- API availability

#### Logging
- Structured logging with JSON format
- Job lifecycle events
- Error tracking
- Performance metrics

### 8. Configuration

#### Environment Variables
- `DATABASE_URL`: Database connection string
- `WORKER_COUNT`: Number of worker processes
- `MAX_RETRIES`: Maximum retry attempts
- `INITIAL_BACKOFF`: Initial retry delay
- `API_KEY`: Optional API key for authentication

#### Runtime Configuration
- Worker timeout settings
- Job batch size
- Health check intervals
- Log levels and formats

### 9. Deployment

#### Requirements
- Python 3.11+
- SQLite (no external dependencies)
- Network access for API endpoints
- Sufficient CPU for worker processes

#### Deployment Options
- Single instance with multiple workers
- Multiple instances behind load balancer
- Containerized deployment (Docker)
- Cloud deployment (AWS, GCP, Azure)

#### Resource Requirements
- CPU: 1 core per worker + system overhead
- Memory: ~50MB per worker + database
- Storage: Database file grows with job history
- Network: Minimal for local deployment

### 10. Known Limitations

#### Database Limitations
- SQLite is not designed for high concurrency
- Single writer bottleneck
- No built-in clustering
- Limited scalability for very high throughput

#### Architecture Limitations
- Single point of failure at database level
- No distributed coordination
- Limited job history management
- No built-in job dependencies

#### Operational Limitations
- Manual job history cleanup
- No built-in monitoring dashboard
- Limited configuration management
- No built-in backup/recovery

### 11. Future Enhancements

#### Planned Improvements
- PostgreSQL/MySQL support for better scalability
- Redis for job queuing and coordination
- Built-in monitoring dashboard
- Job dependency support
- Scheduled jobs support
- Job history management

#### Scaling Considerations
- Database sharding for horizontal scaling
- Worker pools for better resource utilization
- Load balancing for multiple instances
- Queue-based architecture for higher throughput

This architecture provides a solid foundation for reliable job processing with good performance characteristics for most use cases. The simplicity of the design makes it easy to understand, deploy, and maintain while providing robust functionality for background job processing.