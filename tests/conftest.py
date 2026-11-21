import pytest
import asyncio
import tempfile
import os
from pathlib import Path
from unittest.mock import AsyncMock

from src.config import JobEngineConfig
from src.services.database import DatabaseService
from src.services.job_processor import JobProcessor
from src.models import JobStatus, JobPriority


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name
    
    # Use in-memory SQLite for faster tests
    config = JobEngineConfig(database_url="sqlite:///:memory:")
    
    yield config
    
    # Cleanup
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)


@pytest.fixture
async def db_service(temp_db):
    """Create a database service for testing"""
    service = DatabaseService(temp_db)
    await service._init_db()
    yield service
    await service.engine.dispose()


@pytest.fixture
async def job_processor(db_service, temp_db):
    """Create a job processor for testing"""
    processor = JobProcessor(temp_db, db_service)
    yield processor


@pytest.fixture
async def mock_http_client():
    """Mock HTTP client for API testing"""
    from httpx import AsyncClient
    
    client = AsyncClient(app=src.main.app, base_url="http://test")
    yield client
    await client.aclose()


@pytest.fixture
def sample_jobs():
    """Sample job data for testing"""
    return [
        {
            "payload": "test job 1",
            "priority": JobPriority.NORMAL,
            "idempotency_key": "test-1"
        },
        {
            "payload": "test job 2",
            "priority": JobPriority.HIGH,
            "idempotency_key": "test-2"
        },
        {
            "payload": "test job 3",
            "priority": JobPriority.CRITICAL,
            "idempotency_key": "test-3"
        }
    ]