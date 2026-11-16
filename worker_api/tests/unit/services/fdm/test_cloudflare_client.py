"""
Tests for Cloudflare DNS client

These tests use mocking and don't require a database connection.
Run with: pytest -m "not database" tests/unit/services/fdm/test_cloudflare_client.py
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../../"))
)


def test_client_initialization():
    """Test client initializes with correct parameters"""
    from worker_api.app.services.fdm.cloudflare_client import CloudflareDnsClient

    client = CloudflareDnsClient(
        api_token="test_token", zone_id="test_zone_id", domain="example.com"
    )

    assert client.api_token == "test_token"
    assert client.zone_id == "test_zone_id"
    assert client.domain == "example.com"


def test_build_dns_record_payload():
    """Test DNS record payload building"""
    from worker_api.app.services.fdm.cloudflare_client import CloudflareDnsClient

    client = CloudflareDnsClient(
        api_token="test_token", zone_id="test_zone_id", domain="example.com"
    )

    payload = client._build_dns_record_payload("us-01-a1", "192.168.1.1", 120)

    assert payload["type"] == "A"
    assert payload["name"] == "us-01-a1"
    assert payload["content"] == "192.168.1.1"
    assert payload["ttl"] == 120
    assert payload["proxied"] is False


def test_validate_ttl_below_minimum():
    """Test TTL validation for values below minimum"""
    from worker_api.app.services.fdm.cloudflare_client import (
        MIN_TTL,
        CloudflareDnsClient,
    )

    client = CloudflareDnsClient(
        api_token="test_token", zone_id="test_zone_id", domain="example.com"
    )

    result = client._validate_ttl(30)
    assert result == MIN_TTL  # MIN_TTL is 60


def test_validate_ttl_valid():
    """Test TTL validation for valid values"""
    from worker_api.app.services.fdm.cloudflare_client import CloudflareDnsClient

    client = CloudflareDnsClient(
        api_token="test_token", zone_id="test_zone_id", domain="example.com"
    )

    result = client._validate_ttl(120)
    assert result == 120


def test_validate_ttl_exactly_minimum():
    """Test TTL validation for value exactly at minimum"""
    from worker_api.app.services.fdm.cloudflare_client import (
        MIN_TTL,
        CloudflareDnsClient,
    )

    client = CloudflareDnsClient(
        api_token="test_token", zone_id="test_zone_id", domain="example.com"
    )

    result = client._validate_ttl(MIN_TTL)
    assert result == MIN_TTL


@pytest.mark.asyncio
async def test_context_manager():
    """Test async context manager pattern"""
    from worker_api.app.services.fdm.cloudflare_client import CloudflareDnsClient

    async with CloudflareDnsClient(
        api_token="test_token", zone_id="test_zone_id", domain="example.com"
    ) as client:
        assert client is not None
        assert client.api_token == "test_token"
