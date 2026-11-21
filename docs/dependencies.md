# Project Dependencies

## Core Dependencies

### FastAPI
- **Version**: 0.104.1
- **Purpose**: Web framework for building APIs
- **Usage**: Main application framework in `src/main.py` and `src/api/routes.py`

### Uvicorn
- **Version**: 0.24.0 (with standard extras)
- **Purpose**: ASGI server for FastAPI applications
- **Usage**: Server startup in `src/main.py`

### Pydantic
- **Version**: 1.10.13
- **Purpose**: Data validation using Python type annotations
- **Usage**: API request/response models in `src/api/routes.py`

### SQLAlchemy
- **Version**: 2.0.23
- **Purpose**: SQL toolkit and Object-Relational Mapping
- **Usage**: Database models and operations in `src/models/` and `src/services/database.py`

## Testing Dependencies

### Pytest
- **Version**: 7.4.3
- **Purpose**: Testing framework
- **Usage**: All test files in `tests/`

### Pytest-Asyncio
- **Version**: 0.21.1
- **Purpose**: Asyncio support for pytest
- **Usage**: Async test functions in `tests/`

### HTTPX
- **Version**: 0.25.2
- **Purpose**: Async HTTP client for testing
- **Usage**: API testing in `tests/` and benchmarking in `benchmark/benchmark.py`

## Utility Dependencies

### Structlog
- **Version**: 23.2.0
- **Purpose**: Structured logging library
- **Usage**: Logging setup in `src/utils/logging.py`

### Tenacity
- **Version**: 8.2.3
- **Purpose**: Retry library
- **Usage**: Retry logic in `src/services/job_processor.py`

## Removed Dependencies

### Alembic
- **Status**: Removed
- **Reason**: Not used in the project
- **Previous Version**: 1.13.1

### Psutil
- **Status**: Removed (commented out)
- **Reason**: Not available on Android platform
- **Previous Version**: 5.9.6

## Installation

```bash
pip install -r requirements.txt
```

## Dependency Management

- All dependencies are pinned to specific versions for reproducibility
- Dependencies are kept minimal and only include what's actually used
- Regular review of dependencies to remove unused ones
- Cache is cleaned using `scripts/clean_python_cache.py`