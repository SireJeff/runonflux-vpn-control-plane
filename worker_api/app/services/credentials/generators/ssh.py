"""
SSH Credential Generator

SECURITY NOTICE - Password-Only Authentication:
===============================================
This generator uses password-only authentication for SSH connections.

PRIVATE KEY GENERATION HAS BEEN REMOVED FOR SECURITY REASONS.
Key-based authentication with NoEncryption() private keys is insecure.

All SSH connections now use strong random passwords (20+ characters).
"""

import secrets
from typing import Any, Dict

from .base import BaseCredentialGenerator


class SSHCredentialGenerator(BaseCredentialGenerator):
    """
    Generates SSH tunnel credentials with PASSWORD-ONLY authentication

    SECURITY: Private key generation has been removed for security.
    All SSH connections use strong random passwords (20+ characters).

    SSH can be used as a SOCKS proxy via dynamic port forwarding:
    ssh -D 1080 -p port user@server

    This creates a SOCKS5 proxy on localhost:1080
    """

    protocol_name = "ssh"
    default_ports = [22, 2222]

    def generate(
        self,
        server_ip: str,
        port: int,
        user_id: int,
        subscription_id: int,
        country_code: str = "NL",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Generate SSH credentials with PASSWORD-ONLY authentication

        SECURITY: Private key generation has been removed.
        All SSH connections use strong random passwords.
        """
        username = self.generate_username(user_id, prefix="flux")
        # Use cryptographically secure random password (20 bytes = ~26 chars in base64)
        password = secrets.token_urlsafe(20)

        credential_data = {
            "server": server_ip,
            "port": port,
            "username": username,
            "password": password,
            "country_code": country_code,
            "protocol": self.protocol_name,
            "local_port": kwargs.get("local_port", 1080),  # Default SOCKS proxy port
            "auth_method": "password",  # Always password-only
            "security_notice": (
                "Private key authentication has been disabled for security. "
                "Using strong random password instead."
            ),
        }

        # Build SSH command
        credential_data["ssh_command"] = self._build_ssh_command(credential_data)

        return credential_data

    def _build_ssh_command(self, credential_data: Dict[str, Any]) -> str:
        """
        Build SSH dynamic port forwarding command (PASSWORD-ONLY)

        Example:
            ssh -D 1080 -p 2222 flux_user123@192.168.1.1
        """
        return (
            f"ssh -D {credential_data['local_port']} "
            f"-p {credential_data['port']} "
            f"{credential_data['username']}@{credential_data['server']}"
        )

    def build_connection_uri(self, credential_data: Dict[str, Any]) -> str:
        """Build SSH URI (not a standard format, for display purposes)"""
        return f"ssh://{credential_data['username']}@{credential_data['server']}:{credential_data['port']}"

    def build_config_file(
        self, credential_data: Dict[str, Any], config_type: str = "default"
    ) -> str:
        """Generate SSH config file"""
        if config_type == "ssh" or config_type == "config":
            return self._build_ssh_config(credential_data)
        elif config_type == "putty":
            return self._build_putty_instructions(credential_data)
        elif config_type == "private_key" or config_type == "public_key":
            # Return error message - key-based auth is disabled
            return (
                "# PRIVATE KEY AUTHENTICATION DISABLED\n"
                "# For security reasons, key-based authentication has been removed.\n"
                "# Please use password-based authentication instead.\n"
                "# Your credentials are:\n"
                f"# Username: {credential_data['username']}\n"
                f"# Password: {credential_data['password']}\n"
                f"# Server: {credential_data['server']}:{credential_data['port']}\n"
            )
        else:
            return credential_data.get("ssh_command") or self._build_ssh_command(
                credential_data
            )

    def _build_ssh_config(self, credential_data: Dict[str, Any]) -> str:
        """Build OpenSSH config file"""
        country = credential_data.get("country_code", "").lower()
        return f"""# FluxVPN SSH Configuration (Password-Only)
# Add this to ~/.ssh/config

Host fluxvpn-{country}
    HostName {credential_data['server']}
    Port {credential_data['port']}
    User {credential_data['username']}
    # Password will be prompted when connecting
    DynamicForward {credential_data.get('local_port', 1080)}
    ServerAliveInterval 60
    ServerAliveCountMax 3

# Usage: ssh fluxvpn-{country}
# Enter your password when prompted
# Then configure your browser to use SOCKS5 proxy: 127.0.0.1:{credential_data.get('local_port', 1080)}
"""

    def _build_putty_instructions(self, credential_data: Dict[str, Any]) -> str:
        """Build PuTTY configuration instructions"""
        return f"""PuTTY Configuration for FluxVPN SSH (Password-Only)

1. Host Name: {credential_data['server']}
2. Port: {credential_data['port']}
3. Connection > SSH > Tunnels:
   - Source port: {credential_data.get('local_port', 1080)}
   - Dynamic
   - Click 'Add'
4. Go back to Session, save as "FluxVPN"
5. Click Open and login:
   - Username: {credential_data['username']}
   - Password: {credential_data['password']}

After connected, configure your browser:
- Proxy Type: SOCKS5
- Host: 127.0.0.1
- Port: {credential_data.get('local_port', 1080)}
"""

    def get_download_links(self) -> Dict[str, str]:
        """Get SSH client download links"""
        return {
            "windows": "https://www.putty.org/",
            "macos": "Built-in Terminal (ssh command)",
            "linux": "Built-in OpenSSH (ssh command)",
            "android": "https://play.google.com/store/apps/details?id=com.sonelli.juicessh",
            "ios": "https://apps.apple.com/app/termius/id549039908",
        }

    def get_connection_guide(self, platform: str) -> Dict[str, Any]:
        """Get connection guide for SSH (PASSWORD-ONLY)"""
        guides: Dict[str, Dict[str, Any]] = {
            "windows": {
                "steps": [
                    "1. Download PuTTY from putty.org",
                    "2. Open PuTTY and enter server details",
                    "3. Go to Connection > SSH > Tunnels",
                    "4. Add Dynamic port 1080",
                    "5. Connect and enter username/password",
                    "6. Configure browser to use SOCKS5 proxy at 127.0.0.1:1080",
                ],
                "app_download_url": self.get_download_links()["windows"],
                "config_instructions": "Use PuTTY with dynamic port forwarding",
            },
            "linux": {
                "steps": [
                    "1. Open Terminal",
                    "2. Run the SSH command provided",
                    "3. Enter your password when prompted",
                    "4. Keep the terminal open",
                    "5. Configure browser to use SOCKS5 proxy at 127.0.0.1:1080",
                ],
                "app_download_url": None,
                "config_instructions": "Use built-in ssh with -D flag for dynamic forwarding",
            },
            "macos": {
                "steps": [
                    "1. Open Terminal",
                    "2. Run the SSH command provided",
                    "3. Enter your password when prompted",
                    "4. Keep the terminal open",
                    "5. System Preferences > Network > Advanced > Proxies > SOCKS",
                ],
                "app_download_url": None,
                "config_instructions": "Use built-in ssh with -D flag for dynamic forwarding",
            },
            "android": {
                "steps": [
                    "1. Install JuiceSSH from Play Store",
                    "2. Create new connection with server details",
                    "3. Use password authentication (NOT key-based)",
                    "4. In connection settings, enable 'Dynamic Port Forward'",
                    "5. Set local port to 1080",
                    "6. Connect and use with apps that support SOCKS proxy",
                ],
                "app_download_url": self.get_download_links()["android"],
                "config_instructions": "Configure dynamic port forwarding in SSH client",
            },
            "ios": {
                "steps": [
                    "1. Install Termius from App Store",
                    "2. Tap '+' to add a new host",
                    "3. Enter server address, port, username, and password",
                    "4. Tap on 'Port Forwarding' in host settings",
                    "5. Add new rule: Type 'Dynamic', Local port '1080'",
                    "6. Connect and use with apps that support SOCKS proxy",
                ],
                "app_download_url": self.get_download_links()["ios"],
                "config_instructions": "Use Termius with dynamic port forwarding",
            },
        }

        return guides.get(platform, super().get_connection_guide(platform))
