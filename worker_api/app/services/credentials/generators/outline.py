"""
Outline VPN Credential Generator
"""

import base64
from typing import Any, Dict

from .base import BaseCredentialGenerator


class OutlineCredentialGenerator(BaseCredentialGenerator):
    """
    Generates Outline VPN credentials

    Outline uses Shadowsocks protocol under the hood.
    Access URL format:
    ss://BASE64(method:password)@server:port/?outline=1#remark

    Outline provides easier key management and is designed for
    activists and journalists in restricted regions.
    """

    protocol_name = "outline"
    default_ports = [443, 8081]

    # Outline uses specific encryption methods
    DEFAULT_METHOD = "chacha20-ietf-poly1305"

    def generate(
        self,
        server_ip: str,
        port: int,
        user_id: int,
        subscription_id: int,
        country_code: str = "NL",
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate Outline credentials"""
        method = kwargs.get("method", self.DEFAULT_METHOD)
        password = self.generate_password(32)

        credential_data = {
            "server": server_ip,
            "port": port,
            "password": password,
            "method": method,
            "country_code": country_code,
            "protocol": self.protocol_name,
        }

        # Build and add the Outline access URL
        credential_data["access_url"] = self.build_connection_uri(credential_data)

        return credential_data

    def build_connection_uri(self, credential_data: Dict[str, Any]) -> str:
        """Build Outline access URL (Shadowsocks format with outline marker)"""
        method = credential_data["method"]
        password = credential_data["password"]
        server = credential_data["server"]
        port = credential_data["port"]
        country = credential_data.get("country_code", "")

        # Outline format: ss://BASE64(method:password)@server:port/?outline=1
        userinfo = f"{method}:{password}"
        userinfo_b64 = base64.urlsafe_b64encode(userinfo.encode()).decode().rstrip("=")

        remark = f"FluxVPN-Outline-{country}"
        return f"ss://{userinfo_b64}@{server}:{port}/?outline=1#{remark}"

    def build_config_file(
        self, credential_data: Dict[str, Any], config_type: str = "default"
    ) -> str:
        """Generate Outline config"""
        if config_type == "clash":
            return self._build_clash_config(credential_data)
        elif config_type == "json":
            return self._build_json_config(credential_data)
        else:
            # Return access URL for Outline client
            return credential_data.get(
                "access_url", self.build_connection_uri(credential_data)
            )

    def _build_clash_config(self, credential_data: Dict[str, Any]) -> str:
        """Build Clash proxy config (Outline uses Shadowsocks protocol)"""
        country = credential_data.get("country_code", "")
        return f"""proxies:
  - name: FluxVPN-Outline-{country}
    type: ss
    server: {credential_data['server']}
    port: {credential_data['port']}
    cipher: {credential_data['method']}
    password: {credential_data['password']}
    udp: true
"""

    def _build_json_config(self, credential_data: Dict[str, Any]) -> str:
        """Build JSON config (Shadowsocks format)"""
        import json

        config = {
            "server": credential_data["server"],
            "server_port": credential_data["port"],
            "local_address": "127.0.0.1",
            "local_port": 1080,
            "password": credential_data["password"],
            "method": credential_data["method"],
            "timeout": 300,
        }
        return json.dumps(config, indent=2)

    def get_download_links(self) -> Dict[str, str]:
        """Get Outline client download links"""
        return {
            "windows": "https://getoutline.org/get-started/#step-3",
            "macos": "https://getoutline.org/get-started/#step-3",
            "linux": "https://getoutline.org/get-started/#step-3",
            "android": "https://play.google.com/store/apps/details?id=org.outline.android.client",
            "ios": "https://apps.apple.com/app/outline-app/id1356177741",
        }

    def get_connection_guide(self, platform: str) -> Dict[str, Any]:
        """Get connection guide for Outline"""
        base_steps = [
            "1. Download Outline client from getoutline.org",
            "2. Open the Outline app",
            "3. Click 'Add server' or the '+' icon",
            "4. Paste your access key (the URL starting with ss://)",
            "5. Click 'Add server' and then 'Connect'",
        ]

        guides = {
            "windows": {
                "steps": base_steps,
                "app_download_url": self.get_download_links()["windows"],
                "config_instructions": "Paste the access URL in Outline client",
            },
            "macos": {
                "steps": base_steps,
                "app_download_url": self.get_download_links()["macos"],
                "config_instructions": "Paste the access URL in Outline client",
            },
            "linux": {
                "steps": [
                    "1. Download Outline AppImage from getoutline.org",
                    "2. Make it executable: chmod +x Outline-Client.AppImage",
                    "3. Run: ./Outline-Client.AppImage",
                    "4. Click 'Add server'",
                    "5. Paste your access key (ss:// URL)",
                    "6. Click 'Add server' then 'Connect'",
                ],
                "app_download_url": self.get_download_links()["linux"],
                "config_instructions": "Paste the access URL in Outline AppImage client",
            },
            "android": {
                "steps": [
                    "1. Install Outline from Google Play Store",
                    "2. Open the app",
                    "3. Tap 'Add server'",
                    "4. Paste your access key or scan QR code",
                    "5. Tap 'Add server' then 'Connect'",
                ],
                "app_download_url": self.get_download_links()["android"],
                "config_instructions": "Paste access URL or scan QR code",
            },
            "ios": {
                "steps": [
                    "1. Install Outline from App Store",
                    "2. Open the app",
                    "3. Tap 'Add server'",
                    "4. Paste your access key",
                    "5. Tap 'Add server' then 'Connect'",
                ],
                "app_download_url": self.get_download_links()["ios"],
                "config_instructions": "Paste access URL in Outline app",
            },
        }

        return guides.get(
            platform,
            {
                "steps": base_steps,
                "app_download_url": "https://getoutline.org/get-started/",
                "config_instructions": "Paste the access URL in Outline client",
            },
        )
