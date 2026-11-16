"""
Unit tests for Consensus Manager

Tests the multi-node consensus algorithm.
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.services.flux.consensus_manager import (
    ConsensusManager,
    ConsensusResult,
    find_ip_consensus,
    find_status_consensus,
)
from app.services.flux.node_discovery import FluxNode


@pytest.fixture
def consensus_manager():
    """Create a ConsensusManager instance for testing."""
    return ConsensusManager(min_nodes=3, quorum_ratio=0.5)


@pytest.fixture
def sample_nodes():
    """Create sample FluxNode objects for testing."""
    return [
        FluxNode(ip="1.2.3.4", tier="Stratus", geolocation="US"),
        FluxNode(ip="5.6.7.8", tier="Nimbus", geolocation="EU"),
        FluxNode(ip="9.10.11.12", tier="Cumulus", geolocation="ASIA"),
        FluxNode(ip="13.14.15.16", tier="Stratus", geolocation="US"),
        FluxNode(ip="17.18.19.20", tier="Nimbus", geolocation="EU"),
    ]


@pytest.fixture
def sample_app_responses():
    """Create sample app location responses for testing."""
    return {
        "1.2.3.4": {
            "name": "msz109476",
            "ip": ["10.0.0.1", "10.0.0.2"],
            "status": "active",
        },
        "5.6.7.8": {
            "name": "msz109476",
            "ip": ["10.0.0.1", "10.0.0.3"],
            "status": "active",
        },
        "9.10.11.12": {
            "name": "msz109476",
            "ip": ["10.0.0.2", "10.0.0.4"],
            "status": "active",
        },
        "13.14.15.16": {"error": "timeout"},
        "17.18.19.20": {"name": "msz109476", "ip": ["10.0.0.1"], "status": "active"},
    }


class TestConsensusManager:
    """Tests for ConsensusManager class"""

    @pytest.mark.asyncio
    async def test_get_app_consensus(
        self, consensus_manager, sample_nodes, sample_app_responses
    ):
        """Test getting consensus for an app."""
        with patch.object(
            consensus_manager.node_client,
            "query_multiple_nodes",
            return_value=sample_app_responses,
        ):
            result = await consensus_manager.get_app_consensus(
                "msz109476", sample_nodes
            )

            assert result is not None
            assert result.app_name == "msz109476"
            assert result.status == "active"
            assert len(result.ips) > 0
            # Confidence = valid_ratio * ip_agreement = 0.8 * (3/7) ~ 0.34 < 0.5
            assert result.has_consensus is False

    @pytest.mark.asyncio
    async def test_get_app_consensus_insufficient_nodes(self, consensus_manager):
        """Test consensus with insufficient nodes returns None."""
        result = await consensus_manager.get_app_consensus("test_app", [])
        assert result is None

    @pytest.mark.asyncio
    async def test_list_apps_consensus(self, consensus_manager, sample_nodes):
        """Test listing apps with consensus."""
        mock_responses = {
            "1.2.3.4": {
                "data": [
                    {"name": "app1", "ip": ["1.2.3.4"], "status": "active"},
                    {"name": "app2", "ip": ["5.6.7.8"], "status": "active"},
                ]
            },
            "5.6.7.8": {
                "data": [
                    {"name": "app1", "ip": ["1.2.3.4"], "status": "active"},
                    {"name": "app3", "ip": ["9.10.11.12"], "status": "active"},
                ]
            },
            "9.10.11.12": {
                "data": [
                    {"name": "app1", "ip": ["1.2.3.4"], "status": "active"},
                ]
            },
        }

        with patch.object(
            consensus_manager.node_client,
            "query_multiple_nodes",
            return_value=mock_responses,
        ):
            result = await consensus_manager.list_apps_consensus(sample_nodes)

            assert len(result) >= 1
            # app1 should appear in results (present in all 3 nodes)
            app1 = next((a for a in result if a["name"] == "app1"), None)
            assert app1 is not None
            assert app1["count"] == 3

    def test_analyze_app_responses(self, consensus_manager):
        """Test analyzing app responses for consensus."""
        responses = {
            "1.2.3.4": {
                "name": "test_app",
                "ip": ["10.0.0.1", "10.0.0.2"],
                "status": "active",
            },
            "5.6.7.8": {
                "name": "test_app",
                "ip": ["10.0.0.1", "10.0.0.3"],
                "status": "active",
            },
            "9.10.11.12": {
                "name": "test_app",
                "ip": ["10.0.0.2", "10.0.0.4"],
                "status": "active",
            },
        }

        result = consensus_manager._analyze_app_responses("test_app", responses, 3)

        assert result is not None
        assert result.app_name == "test_app"
        assert result.status == "active"
        assert result.instance_count > 0

    def test_analyze_app_responses_with_errors(self, consensus_manager):
        """Test analyzing responses with some errors -- insufficient valid responses."""
        responses = {
            "1.2.3.4": {"name": "test_app", "ip": ["10.0.0.1"], "status": "active"},
            "5.6.7.8": {"error": "timeout"},
            "9.10.11.12": {"name": "test_app", "ip": ["10.0.0.1"], "status": "active"},
        }

        result = consensus_manager._analyze_app_responses("test_app", responses, 3)

        # 2 valid responses < min_nodes(3) -> returns None
        assert result is None

    def test_aggregate_app_lists(self, consensus_manager):
        """Test aggregating app lists from multiple nodes."""
        responses = {
            "1.2.3.4": {"data": [{"name": "app1", "ip": ["1.2.3.4"]}]},
            "5.6.7.8": {
                "data": [
                    {"name": "app1", "ip": ["5.6.7.8"]},
                    {"name": "app2", "ip": ["9.10.11.12"]},
                ]
            },
            "9.10.11.12": {"data": [{"name": "app1", "ip": ["9.10.11.12"]}]},
        }

        result = consensus_manager._aggregate_app_lists(responses, 3)

        assert len(result) >= 2  # At least app1 and app2
        app1 = next((a for a in result if a["name"] == "app1"), None)
        assert app1 is not None
        assert app1["count"] == 3

    def test_score_response_completeness(self, consensus_manager):
        """Test scoring response completeness."""
        complete_response = {
            "name": "test_app",
            "ip": ["1.2.3.4"],
            "status": "active",
            "owner": "zelid",
            "description": "Test",
            "repotag": "nginx:latest",
            "ports": [80],
            "cpu": 0.5,
            "ram": 512,
            "hdd": 5,
        }

        score = consensus_manager._score_response_completeness(complete_response)
        assert score > 8  # Should have high score

        minimal_response = {"name": "test_app"}
        score = consensus_manager._score_response_completeness(minimal_response)
        assert score < 3  # Should have low score

    def test_is_consensus_sufficient(self, consensus_manager):
        """Test checking if consensus is sufficient."""
        # Good consensus
        good_result = ConsensusResult(
            app_name="test",
            ips=["1.2.3.4", "5.6.7.8"],
            status="active",
            instance_count=2,
            consensus_level="3/3",
            confidence=0.9,
        )

        assert consensus_manager.is_consensus_sufficient(good_result) is True

        # Poor consensus
        poor_result = ConsensusResult(
            app_name="test",
            ips=[],
            status="unknown",
            instance_count=0,
            consensus_level="1/3",
            confidence=0.1,
        )

        assert consensus_manager.is_consensus_sufficient(poor_result) is False


class TestUtilityFunctions:
    """Tests for utility functions"""

    def test_find_ip_consensus(self):
        """Test finding IP consensus from responses."""
        responses = [
            {"ip": ["1.2.3.4", "5.6.7.8"]},
            {"ip": ["1.2.3.4", "9.10.11.12"]},
            {"ip": ["1.2.3.4", "13.14.15.16"]},
        ]

        result = find_ip_consensus(responses)

        # 1.2.3.4 appears in all 3 responses, should be in result
        assert "1.2.3.4" in result

    def test_find_ip_consensus_no_agreement(self):
        """Test IP consensus when no IPs appear multiple times."""
        responses = [
            {"ip": ["1.2.3.4"]},
            {"ip": ["5.6.7.8"]},
            {"ip": ["9.10.11.12"]},
        ]

        result = find_ip_consensus(responses)

        # No IP appears twice, should be empty
        assert len(result) == 0

    def test_find_status_consensus_active(self):
        """Test status consensus when active is present."""
        responses = [
            {"status": "active"},
            {"status": "inactive"},
            {"status": "active"},
        ]

        result = find_status_consensus(responses)

        assert result == "active"

    def test_find_status_consensus_no_active(self):
        """Test status consensus when no active status."""
        responses = [
            {"status": "inactive"},
            {"status": "inactive"},
            {"status": "unknown"},
        ]

        result = find_status_consensus(responses)

        assert result == "inactive"

    def test_find_status_consensus_empty(self):
        """Test status consensus with no status data."""
        responses = [
            {"name": "app1"},
            {"ip": ["1.2.3.4"]},
        ]

        result = find_status_consensus(responses)

        assert result == "unknown"


class TestConsensusResult:
    """Tests for ConsensusResult class"""

    def test_consensus_result_properties(self):
        """Test ConsensusResult properties."""
        result = ConsensusResult(
            app_name="test_app",
            ips=["1.2.3.4", "5.6.7.8"],
            status="active",
            instance_count=2,
            consensus_level="3/3",
            confidence=0.8,
        )

        assert result.app_name == "test_app"
        assert result.is_active is True
        assert result.has_consensus is True
        assert result.instance_count == 2

    def test_to_dict(self):
        """Test converting ConsensusResult to dictionary."""
        result = ConsensusResult(
            app_name="test_app",
            ips=["1.2.3.4"],
            status="active",
            instance_count=1,
            consensus_level="2/3",
            confidence=0.6,
        )

        result_dict = result.to_dict()

        assert result_dict["name"] == "test_app"
        assert result_dict["ip"] == ["1.2.3.4"]
        assert result_dict["status"] == "active"
        assert result_dict["confidence"] == 0.6
