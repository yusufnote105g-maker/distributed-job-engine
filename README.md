# Distributed Job Engine

A production-oriented distributed job processing engine built with FastAPI and SQLite.

## Features

- **Job Processing**: Background job processing with multiple concurrent workers
- **Priorities**: Support for job priorities (LOW, NORMAL, HIGH, CRITICAL)
- **Retry Logic**: Configurable retry policy with exponential backoff
- **Timeout Handling**: Per-job timeout configuration
- **Idempotency**: Idempotency keys to prevent duplicate submissions
- **Atomic Operations**: Atomic job claiming to prevent race conditions
- **Graceful Shutdown**: Clean shutdown with job completion
- **REST API**: Full REST API for job management
- **Monitoring**: Health checks and metrics collection
- **Recovery**: Automatic recovery from application restarts

## Quick Start

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd distributed_job_engine

# Install dependencies
pip install -r requirements.txt

# Run the application
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
```

### Basic Usage

```python
import httpx

# Submit a job
response = httpx.post("http://localhost:8000/api/v1/jobs", json={
    "payload": "test job",
    "priority": "normal"
})

job_id = response.json()["job_id"]

# Check job status
response = httpx.get(f"http://localhost:8000/api/v1/jobs/{job_id}")
print(response.json())
```

## API Documentation

### Submit Job

```http
POST /api/v1/jobs
Content-Type: application/json

{
    "payload": "job payload",
    "priority": "normal",
    "idempotency_key": "unique-key",
    "timeout": 300
}
```

### Get Job

```http
GET /api/v1/jobs/{job_id}
```

### List Jobs

```http
GET /api/v1/jobs?status=pending&limit=100&offset=0
```

### Cancel Job

```http
POST /api/v1/jobs/{job_id}/cancel
```

### Health Check

```http
GET /api/v1/health
```

### Metrics

```http
GET /api/v1/metrics
```

## Configuration

### Environment Variables

- `DATABASE_URL`: Database connection string (default: `sqlite:///./jobs.db`)
- `WORKER_COUNT`: Number of worker processes (default: 4)
- `MAX_RETRIES`: Maximum retry attempts (default: 3)
- `INITIAL_BACKOFF`: Initial retry delay in seconds (default: 1.0)
- `MAX_BACKOFF`: Maximum retry delay in seconds (default: 60.0)
- `API_KEY`: Optional API key for authentication
- `LOG_LEVEL`: Log level (default: INFO)

### Configuration File

Create a `.env` file in the project root:

```env
DATABASE_URL=sqlite:///./jobs.db
WORKER_COUNT=4
MAX_RETRIES=3
INITIAL_BACKOFF=1.0
MAX_BACKOFF=60.0
API_KEY=your-secret-api-key
LOG_LEVEL=INFO
```

## Architecture

### Components

1. **JobProcessor**: Main processing engine
2. **DatabaseService**: Database operations
3. **API Routes**: REST API endpoints
4. **Workers**: Concurrent job processing
5. **Scheduler**: Background job scheduler

### Job States

- `PENDING`: Job is waiting to be processed
- `CLAIMED`: Job has been claimed by a worker
- `RUNNING`: Job is currently being processed
- `COMPLETED`: Job completed successfully
- `FAILED`: Job failed but can be retried
- `CANCELLED`: Job was cancelled by user
- `RETRYING`: Job failed and is scheduled for retry
- `DEAD_LETTER`: Job failed permanently after max retries

### Job Priorities

- `CRITICAL`: Highest priority, processed first
- `HIGH`: High priority
- `NORMAL`: Default priority
- `LOW`: Lowest priority

## Testing

### Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src

# Run specific test file
pytest tests/test_job_processor.py
```

### Test Coverage

The test suite covers:
- Normal job execution
- Concurrent job processing
- Retry logic
- Timeout handling
- Job cancellation
- API endpoints
- Error scenarios
- Race conditions

## Benchmarking

### Run Benchmark

```bash
# Run benchmark with default settings
python benchmark/benchmark.py

# Run with custom settings
python benchmark/benchmark.py --jobs 1000 --workers 8 --duration 60

# Using the script
./scripts/run_benchmark.sh 1000 8 60
```

### Benchmark Metrics

- **Throughput**: Jobs processed per second
- **Latency**: Average and P95 latency
- **Worker Utilization**: Percentage of active workers
- **Database Operations**: Total database operations

## Documentation

- [Architecture](docs/architecture.md)
- [Database Schema](docs/database_schema.md)
- [Security Analysis](docs/security_analysis.md)
- [Known Limitations](docs/known_limitations.md)
- [Production Risks](docs/production_risks.md)

## Deployment

### Requirements

- Python 3.11+
- SQLite (no external dependencies)
- Network access for API endpoints

### Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Production Considerations

1. **HTTPS**: Use HTTPS for production deployments
2. **Database**: Consider PostgreSQL for better scalability
3. **Monitoring**: Implement comprehensive monitoring
4. **Logging**: Use structured logging
5. **Security**: Implement proper authentication and authorization

## Development

### Project Structure

```
distributed_job_engine/
├── src/
│   ├── models/          # Data models
│   ├── services/        # Core services
│   ├── api/            # API routes
│   ├── utils/          # Utility functions
│   └── main.py         # Application entry point
├── tests/              # Test suite
├── benchmark/          # Benchmarking tools
├── docs/               # Documentation
├── scripts/            # Utility scripts
└── requirements.txt    # Dependencies
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run the test suite
6. Submit a pull request

### License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support and questions:
- Create an issue in the repository
- Check the documentation
- Review the test cases for usage examples

## Changelog

### Version 1.0.0
- Initial release
- Basic job processing functionality
- REST API
- Concurrent workers
- Retry logic
- Timeout handling
- Comprehensive test suite
- Benchmarking tools
- Documentation