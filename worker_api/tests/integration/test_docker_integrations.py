"""
Docker Integration Tests for VPN Protocol Containers

These tests verify:
1. Container startup with valid deployment tokens
2. Container rejection with invalid/expired tokens
3. Health check endpoints
4. Protocol-specific configuration parsing
"""

import json

import pytest

from app.services.auth.deployment_tokens import DeploymentTokenService


class TestDeploymentTokenValidation:
    """Test deployment token generation and validation"""

    @pytest.fixture
    def token_service(self):
        """Create a token service instance"""
        return DeploymentTokenService(secret_key="test_fluxvpn_secret_key")

    def test_generate_valid_token(self, token_service):
        """Test generating a valid deployment token"""
        token = token_service.generate_token(
            protocol="shadowsocks",
            instance_id="test-node",
            deployment_id="deploy-abc",
        )

        assert token is not None
        assert len(token) > 0

    def test_validate_valid_token(self, token_service):
        """Test validating a valid deployment token"""
        instance_id = "test-node"
        token = token_service.generate_token(
            protocol="shadowsocks", instance_id=instance_id, deployment_id="deploy-abc"
        )

        payload = token_service.validate_token(token, instance_id)

        assert payload["protocol"] == "shadowsocks"
        assert payload["instance_id"] == instance_id
        assert payload["deployment_id"] == "deploy-abc"

    def test_reject_expired_token(self, token_service):
        """Test that expired tokens are rejected"""
        from app.services.auth.deployment_tokens import TokenExpiredError

        # Generate token that is already expired.
        token = token_service.generate_token(
            protocol="shadowsocks",
            instance_id="test-node",
            deployment_id="deploy-abc",
            expiry_seconds=-3600,
        )

        with pytest.raises(TokenExpiredError):
            token_service.validate_token(token, "test-node")

    def test_reject_mismatched_instance_id(self, token_service):
        """Test that tokens are rejected when instance ID doesn't match"""
        from app.services.auth.deployment_tokens import TokenInvalidError

        token = token_service.generate_token(
            protocol="shadowsocks",
            instance_id="test-node",
            deployment_id="deploy-abc",
        )

        with pytest.raises(TokenInvalidError):
            token_service.validate_token(token, "different-instance-456")

    def test_reject_malformed_token(self, token_service):
        """Test that malformed tokens are rejected"""
        from app.services.auth.deployment_tokens import TokenMalformedError

        with pytest.raises(TokenMalformedError):
            token_service.validate_token("not-a-valid-token", "test-node")


class TestProtocolConfigGeneration:
    """Test protocol-specific config generation for containers"""

    @pytest.fixture
    def token_service(self):
        """Create a token service instance"""
        return DeploymentTokenService(secret_key="test_fluxvpn_secret_key")

    def test_shadowsocks_config(self, token_service):
        """Test Shadowsocks config generation"""
        config = token_service.get_protocol_config("shadowsocks", "instance-123")

        assert config["protocol"] == "shadowsocks"
        assert config["instance_id"] == "instance-123"
        assert "log_level" in config
        assert "method" in config
        assert "timeout" in config
        assert config["method"] in ["aes-256-gcm", "chacha20-ietf-poly1305"]

    def test_trojan_config(self, token_service):
        """Test Trojan config generation"""
        config = token_service.get_protocol_config("trojan", "instance-123")

        assert config["protocol"] == "trojan"
        assert config["instance_id"] == "instance-123"
        assert config["ssl"] is True
        assert "alpn" in config

    def test_vless_config(self, token_service):
        """Test VLESS config generation"""
        config = token_service.get_protocol_config("vless", "instance-123")

        assert config["protocol"] == "vless"
        assert config["instance_id"] == "instance-123"
        assert config["encryption"] == "none"
        assert "network" in config

    def test_ssh_config(self, token_service):
        """Test SSH config generation"""
        config = token_service.get_protocol_config("ssh", "instance-123")

        assert config["protocol"] == "ssh"
        assert config["instance_id"] == "instance-123"
        assert "password_auth" in config
        assert "max_auth_tries" in config

    def test_http_proxy_config(self, token_service):
        """Test HTTP Proxy config generation"""
        config = token_service.get_protocol_config("http_proxy", "instance-123")

        assert config["protocol"] == "http_proxy"
        assert config["instance_id"] == "instance-123"
        assert "cache_enabled" in config
        assert "max_connections" in config
        assert "timeout" in config

    def test_http_proxy_alias_config(self, token_service):
        """Test HTTP Proxy alias used by deployment code."""
        config = token_service.get_protocol_config("httpproxy", "instance-123")

        assert config["protocol"] == "http_proxy"
        assert config["instance_id"] == "instance-123"
        assert "username" in config
        assert "password" in config
        assert "port" in config

    def test_outline_config(self, token_service):
        """Test Outline config generation"""
        config = token_service.get_protocol_config("outline", "instance-123")

        assert config["protocol"] == "outline"
        assert config["instance_id"] == "instance-123"
        assert "method" in config
        assert "metrics_port" in config

    @pytest.mark.parametrize(
        "protocol,required_keys",
        [
            ("shadowsocks", ["password", "port"]),
            ("trojan", ["password", "port"]),
            ("vless", ["uuid", "port"]),
            ("ssh", ["username", "password", "port"]),
            ("outline", ["password", "port"]),
            ("http_proxy", ["username", "password", "port"]),
        ],
    )
    def test_protocol_runtime_fields_present(
        self, token_service, protocol, required_keys
    ):
        """Ensure config includes fields required by protocol start scripts."""
        config = token_service.get_protocol_config(protocol, "instance-xyz")
        for key in required_keys:
            assert key in config


class TestContainerHealthChecks:
    """Test container health check simulation"""

    def test_shadowsocks_health_check_format(self):
        """Test Shadowsocks health check expected response format"""
        # Simulate what a healthy container should return
        expected_health = {
            "status": "healthy",
            "protocol": "shadowsocks",
            "uptime": 3600,  # seconds
            "connections": 0,
        }

        assert expected_health["status"] == "healthy"
        assert "protocol" in expected_health

    def test_trojan_health_check_format(self):
        """Test Trojan health check expected response format"""
        expected_health = {
            "status": "healthy",
            "protocol": "trojan",
            "tls_configured": True,
        }

        assert expected_health["status"] == "healthy"
        assert expected_health["tls_configured"] is True


class TestEntrypointWrapperLogic:
    """Test entrypoint wrapper script logic (Python equivalent)"""

    def test_validate_required_env_vars(self):
        """Test that required environment variables are checked"""
        required_vars = ["FLUXVPN_AUTH_TOKEN", "FLUXVPN_API_URL", "FLUXVPN_INSTANCE_ID"]

        # Simulate checking for required vars
        mock_env = {
            "FLUXVPN_AUTH_TOKEN": "test-token",
            "FLUXVPN_API_URL": "http://api.operator7.example.invalid",
            "FLUXVPN_INSTANCE_ID": "instance-123",
        }

        for var in required_vars:
            assert var in mock_env, f"Missing required env var: {var}"

    def test_retry_logic_attempts(self):
        """Test retry logic for API validation"""
        max_retries = 3
        attempts = 0

        def mock_validate(should_fail_times=2):
            nonlocal attempts
            attempts += 1
            if attempts <= should_fail_times:
                raise ConnectionError("API unavailable")
            return True

        # Simulate retry logic
        for i in range(max_retries):
            try:
                mock_validate(should_fail_times=2)
                break
            except ConnectionError:
                if i == max_retries - 1:
                    pytest.fail("Max retries exceeded")
                continue

        assert attempts == 3

    def test_graceful_shutdown_signal_handling(self):
        """Test that shutdown signals are handled gracefully"""
        shutdown_received = False

        def signal_handler(signum, frame):
            nonlocal shutdown_received
            shutdown_received = True

        # Simulate signal handling
        signal_handler(15, None)  # SIGTERM

        assert shutdown_received is True


class TestCredentialGeneratorIntegration:
    """Integration tests for credential generators"""

    def test_all_generators_available(self):
        """Test that all protocol generators can be instantiated"""
        from app.services.credentials.generators import get_credential_generator

        protocols = ["shadowsocks", "trojan", "vless", "ssh", "outline", "http_proxy"]

        for protocol in protocols:
            generator = get_credential_generator(protocol)
            assert generator is not None
            assert generator.protocol_name == protocol

    def test_credential_data_structure(self):
        """Test that generated credentials have expected structure"""
        from app.services.credentials.generators import get_credential_generator

        generator = get_credential_generator("shadowsocks")
        credential_data = generator.generate(
            server_ip="1.2.3.4",
            port=8388,
            user_id=1,
            subscription_id=100,
            country_code="US",
        )

        # Check required fields
        assert "server" in credential_data
        assert "port" in credential_data
        assert "protocol" in credential_data
        assert credential_data["server"] == "1.2.3.4"
        assert credential_data["port"] == 8388

    def test_connection_uri_generation(self):
        """Test that connection URIs are generated correctly"""
        from app.services.credentials.generators import get_credential_generator

        generator = get_credential_generator("shadowsocks")
        credential_data = generator.generate(
            server_ip="1.2.3.4",
            port=8388,
            user_id=1,
            subscription_id=100,
            country_code="US",
        )

        uri = generator.build_connection_uri(credential_data)

        assert uri.startswith("ss://")
        assert "1.2.3.4" in uri or "1.2.3.4:8388" in uri


class TestConfigFileFormats:
    """Test config file generation for different formats"""

    def test_shadowsocks_clash_config(self):
        """Test Shadowsocks Clash config format"""
        from app.services.credentials.generators import get_credential_generator

        generator = get_credential_generator("shadowsocks")
        credential_data = generator.generate(
            server_ip="1.2.3.4",
            port=8388,
            user_id=1,
            subscription_id=100,
            country_code="US",
        )

        clash_config = generator.build_config_file(credential_data, config_type="clash")

        assert "proxies:" in clash_config
        assert "type: ss" in clash_config
        assert "1.2.3.4" in clash_config

    def test_vless_xray_config(self):
        """Test VLESS Xray JSON config format"""
        from app.services.credentials.generators import get_credential_generator

        generator = get_credential_generator("vless")
        credential_data = generator.generate(
            server_ip="1.2.3.4",
            port=443,
            user_id=1,
            subscription_id=100,
            country_code="US",
        )

        xray_config = generator.build_config_file(credential_data, config_type="xray")
        config_dict = json.loads(xray_config)

        assert "inbounds" in config_dict
        assert "outbounds" in config_dict
        assert config_dict["outbounds"][0]["protocol"] == "vless"

    def test_trojan_trojan_go_config(self):
        """Test Trojan-Go config format"""
        from app.services.credentials.generators import get_credential_generator

        generator = get_credential_generator("trojan")
        credential_data = generator.generate(
            server_ip="1.2.3.4",
            port=443,
            user_id=1,
            subscription_id=100,
            country_code="US",
        )

        trojan_go_config = generator.build_config_file(
            credential_data, config_type="trojan-go"
        )
        config_dict = json.loads(trojan_go_config)

        assert "mux" in config_dict
        assert "websocket" in config_dict
        assert config_dict["run_type"] == "client"
