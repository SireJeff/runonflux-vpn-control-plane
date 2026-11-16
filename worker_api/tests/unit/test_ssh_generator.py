import secrets
from unittest.mock import MagicMock, patch

import pytest

from app.services.credentials.generators.ssh import SSHCredentialGenerator


class TestSSHCredentialGenerator:
    @pytest.fixture
    def generator(self):
        return SSHCredentialGenerator()

    def test_protocol_name(self, generator):
        assert generator.protocol_name == "ssh"

    def test_default_ports(self, generator):
        assert generator.default_ports == [22, 2222]

    def test_generate_basic(self, generator):
        server_ip = "1.2.3.4"
        port = 2222
        user_id = 123
        subscription_id = 456

        with patch("secrets.token_urlsafe", return_value="mocked_password_20_chars"):
            # Mock generate_username to be deterministic
            with patch.object(
                SSHCredentialGenerator,
                "generate_username",
                return_value="flux_123_timestamp_random",
            ):
                credential_data = generator.generate(
                    server_ip=server_ip,
                    port=port,
                    user_id=user_id,
                    subscription_id=subscription_id,
                )

        assert credential_data["server"] == server_ip
        assert credential_data["port"] == port
        assert credential_data["username"] == "flux_123_timestamp_random"
        assert credential_data["password"] == "mocked_password_20_chars"
        assert credential_data["protocol"] == "ssh"
        assert credential_data["local_port"] == 1080
        assert credential_data["auth_method"] == "password"
        assert "ssh_command" in credential_data
        assert (
            "ssh -D 1080 -p 2222 flux_123_timestamp_random@1.2.3.4"
            in credential_data["ssh_command"]
        )

    def test_generate_custom_local_port(self, generator):
        credential_data = generator.generate(
            server_ip="1.2.3.4", port=22, user_id=1, subscription_id=1, local_port=9090
        )
        assert credential_data["local_port"] == 9090
        assert "ssh -D 9090" in credential_data["ssh_command"]

    def test_build_ssh_command(self, generator):
        data = {"local_port": 1080, "port": 22, "username": "user", "server": "1.1.1.1"}
        command = generator._build_ssh_command(data)
        assert command == "ssh -D 1080 -p 22 user@1.1.1.1"

    def test_build_connection_uri(self, generator):
        data = {"username": "user", "server": "1.1.1.1", "port": 22}
        uri = generator.build_connection_uri(data)
        assert uri == "ssh://user@1.1.1.1:22"

    def test_build_config_file_ssh(self, generator):
        data = {
            "server": "1.1.1.1",
            "port": 22,
            "username": "user",
            "local_port": 1080,
            "country_code": "NL",
        }
        config = generator.build_config_file(data, config_type="ssh")
        assert "Host fluxvpn-nl" in config
        assert "HostName 1.1.1.1" in config
        assert "Port 22" in config
        assert "User user" in config
        assert "DynamicForward 1080" in config

    def test_build_config_file_putty(self, generator):
        data = {
            "server": "1.1.1.1",
            "port": 22,
            "username": "user",
            "password": "password123",
            "local_port": 1080,
        }
        config = generator.build_config_file(data, config_type="putty")
        assert "PuTTY Configuration" in config
        assert "Host Name: 1.1.1.1" in config
        assert "Port: 22" in config
        assert "Username: user" in config
        assert "Password: password123" in config

    def test_build_config_file_keys_disabled(self, generator):
        data = {
            "username": "user",
            "password": "password123",
            "server": "1.1.1.1",
            "port": 22,
        }
        config = generator.build_config_file(data, config_type="private_key")
        assert "PRIVATE KEY AUTHENTICATION DISABLED" in config
        assert "password-based authentication" in config
        assert "Username: user" in config

    def test_build_config_file_default(self, generator):
        data = {"ssh_command": "ssh -D 1080 -p 22 user@server"}
        config = generator.build_config_file(data, config_type="unknown")
        assert config == "ssh -D 1080 -p 22 user@server"

    def test_get_download_links(self, generator):
        links = generator.get_download_links()
        assert "windows" in links
        assert "macos" in links
        assert "linux" in links
        assert "android" in links
        assert "ios" in links
        assert "putty.org" in links["windows"]

    def test_get_connection_guide_linux(self, generator):
        guide = generator.get_connection_guide("linux")
        assert "steps" in guide
        assert any("SSH command" in step for step in guide["steps"])

    def test_get_connection_guide_windows(self, generator):
        guide = generator.get_connection_guide("windows")
        assert any("PuTTY" in step for step in guide["steps"])

    def test_get_connection_guide_android(self, generator):
        guide = generator.get_connection_guide("android")
        assert any("JuiceSSH" in step for step in guide["steps"])

    def test_get_connection_guide_ios(self, generator):
        guide = generator.get_connection_guide("ios")
        assert any("Termius" in step for step in guide["steps"])
