import pytest
import asyncio
import json
from datetime import datetime
from httpx import AsyncClient

from src.models import JobStatus, JobPriority
from src.main import app


@pytest.mark.asyncio
async def test_submit_job_endpoint(mock_http_client):
    """Test job submission via API"""
    response = await mock_http_client.post(
        "/api/v1/jobs",
        json={
            "payload": "test job via API",
            "priority": "high",
            "idempotency_key": "api-test-1"
        }
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["payload"] == "test job via API"
    assert data["priority"] == "high"
    assert data["status"] == "pending"
    assert data["job_id"] is not None


@pytest.mark.asyncio
async def test_submit_job_invalid_payload(mock_http_client):
    """Test job submission with invalid payload"""
    response = await mock_http_client.post(
        "/api/v1/jobs",
        json={
            "payload": "",  # Empty payload
            "priority": "invalid_priority"
        }
    )
    
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_job_endpoint(mock_http_client):
    """Test getting a specific job"""
    # First submit a job
    response = await mock_http_client.post(
        "/api/v1/jobs",
        json={
            "payload": "test job for get",
            "priority": "normal"
        }
    )
    
    job_id = response.json()["job_id"]
    
    # Then get it
    response = await mock_http_client.get(f"/api/v1/jobs/{job_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job_id
    assert data["payload"] == "test job for get"


@pytest.mark.asyncio
async def test_get_nonexistent_job(mock_http_client):
    """Test getting a non-existent job"""
    response = await mock_http_client.get("/api/v1/jobs/nonexistent-id")
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_jobs_endpoint(mock_http_client):
    """Test getting jobs list with pagination"""
    # Submit multiple jobs
    for i in range(5):
        await mock_http_client.post(
            "/api/v1/jobs",
            json={
                "payload": f"test job {i}",
                "priority": "normal"
            }
        )
    
    # Get jobs list
    response = await mock_http_client.get("/api/v1/jobs?limit=3&offset=0")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data["jobs"]) == 3
    assert data["total"] >= 3
    assert data["limit"] == 3
    assert data["offset"] == 0


@pytest.mark.asyncio
async def test_get_jobs_by_status(mock_http_client):
    """Test filtering jobs by status"""
    # Submit a job
    response = await mock_http_client.post(
        "/api/v1/jobs",
        json={
            "payload": "test job for status filter",
            "priority": "normal"
        }
    )
    
    job_id = response.json()["job_id"]
    
    # Filter by pending status
    response = await mock_http_client.get(f"/api/v1/jobs?status=pending")
    
    assert response.status_code == 200
    data = response.json()
    assert any(job["job_id"] == job_id for job in data["jobs"])


@pytest.mark.asyncio
async def test_cancel_job_endpoint(mock_http_client):
    """Test job cancellation"""
    # Submit a job
    response = await mock_http_client.post(
        "/api/v1/jobs",
        json={
            "payload": "test job for cancellation",
            "priority": "normal"
        }
    )
    
    job_id = response.json()["job_id"]
    
    # Cancel the job
    response = await mock_http_client.post(f"/api/v1/jobs/{job_id}/cancel")
    
    assert response.status_code == 200
    assert response.json()["message"] == "Job cancelled successfully"


@pytest.mark.asyncio
async def test_cancel_nonexistent_job(mock_http_client):
    """Test cancelling a non-existent job"""
    response = await mock_http_client.post("/api/v1/jobs/nonexistent-id/cancel")
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_health_check_endpoint(mock_http_client):
    """Test health check endpoint"""
    response = await mock_http_client.get("/api/v1/health")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert "timestamp" in data
    assert "database_status" in data
    assert "worker_status" in data


@pytest.mark.asyncio
async def test_metrics_endpoint(mock_http_client):
    """Test metrics endpoint"""
    response = await mock_http_client.get("/api/v1/metrics")
    
    assert response.status_code == 200
    data = response.json()
    assert "status_counts" in data
    assert "total_jobs" in data
    assert "worker_count" in data
    assert "worker_id" in data


@pytest.mark.asyncio
async def test_duplicate_submission_with_idempotency(mock_http_client):
    """Test duplicate job submission with idempotency key"""
    # Submit first job
    response1 = await mock_http_client.post(
        "/api/v1/jobs",
        json={
            "payload": "duplicate test job",
            "idempotency_key": "duplicate-key"
        }
    )
    
    job_id = response1.json()["job_id"]
    
    # Submit duplicate job with same idempotency key
    response2 = await mock_http_client.post(
        "/api/v1/jobs",
        json={
            "payload": "different job",
            "idempotency_key": "duplicate-key"
        }
    )
    
    # Should return the same job
    assert response2.status_code == 201
    assert response2.json()["job_id"] == job_id


@pytest.mark.asyncio
async def test_api_key_protection(mock_http_client):
    """Test API key protection"""
    # Try without API key
    response = await mock_http_client.post(
        "/api/v1/jobs",
        json={
            "payload": "test job",
            "priority": "normal"
        }
    )
    
    # Should succeed (no API key configured by default)
    assert response.status_code == 201
    
    # Configure API key and test
    from src.config import JobEngineConfig
    config = JobEngineConfig()
    config.api_key_header = "X-API-Key"
    config.secret_key = "test-secret-key"
    
    # Try with wrong API key
    response = await mock_http_client.post(
        "/api/v1/jobs",
        headers={"X-API-Key": "wrong-key"},
        json={
            "payload": "test job",
            "priority": "normal"
        }
    )
    
    # Should fail
    assert response.status_code == 401
    
    # Try with correct API key
    response = await mock_http_client.post(
        "/api/v1/jobs",
        headers={"X-API-Key": "test-secret-key"},
        json={
            "payload": "test job",
            "priority": "normal"
        }
    )
    
    # Should succeed
    assert response.status_code == 201