"""
Integration tests for health check endpoints
"""

import pytest


class TestHealthEndpoints:
    """Test cases for health check API endpoints"""

    def test_main_health_endpoint(self, client):
        """Test main health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "worker-api"

    def test_database_health_endpoint(self, client, db):
        """Test database health check endpoint"""
        response = client.get("/health/db")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ok"
        assert data["database"] == "connected"

    def test_redis_health_endpoint(self, client, redis_client):
        """Test Redis health check endpoint"""
        response = client.get("/health/redis")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ok"
        assert data["redis"] in {"connected", "disabled"}

    def test_root_endpoint(self, client):
        """Test root endpoint"""
        response = client.get("/")
        assert response.status_code == 200

        data = response.json()
        assert data["service"] == "FluxVPN Worker/API"
        assert data["status"] == "running"


@pytest.mark.integration
class TestAPIDocumentation:
    """Test cases for API documentation endpoints"""

    def test_openapi_docs(self, client):
        """Test OpenAPI documentation endpoint"""
        response = client.get("/api/docs")
        assert response.status_code == 200

    def test_openapi_json(self, client):
        """Test OpenAPI JSON schema endpoint"""
        response = client.get("/openapi.json")
        assert response.status_code == 200

        data = response.json()
        assert "openapi" in data
        assert "info" in data
        assert "paths" in data
