"""
Shadowsocks Credential Generator
"""

import base64
from typing import Any, Dict

from .base import BaseCredentialGenerator


class ShadowsocksCredentialGenerator(BaseCredentialGenerator):
    """
    Generates Shadowsocks protocol credentials

    Shadowsocks URI format:
    ss://BASE64(method:password)@server:port#remark

    Supported encryption methods:
    - chacha20-ietf-poly1305 (recommended)
    - aes-256-gcm
    - aes-128-gcm
    """

    protocol_name = "shadowsocks"
    default_ports = [8388, 8389]

    # Default encryption method
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
        """Generate Shadowsocks credentials"""
        method = kwargs.get("method", self.DEFAULT_METHOD)
        password = self.generate_password(32)  # SS passwords should be long

        credential_data = {
            "server": server_ip,
            "port": port,
            "password": password,
            "method": method,
            "country_code": country_code,
            "protocol": self.protocol_name,
        }

        # Build and add the SS URI
        credential_data["ss_uri"] = self.build_connection_uri(credential_data)

        return credential_data

    def build_connection_uri(self, credential_data: Dict[str, Any]) -> str:
        """Build Shadowsocks URI (SIP002 format)"""
        method = credential_data["method"]
        password = credential_data["password"]
        server = credential_data["server"]
        port = credential_data["port"]
        country = credential_data.get("country_code", "")

        # SIP002 format: ss://BASE64(method:password)@server:port#remark
        userinfo = f"{method}:{password}"
        userinfo_b64 = base64.urlsafe_b64encode(userinfo.encode()).decode().rstrip("=")

        remark = f"FluxVPN-{country}"
        return f"ss://{userinfo_b64}@{server}:{port}#{remark}"

    def build_config_file(
        self, credential_data: Dict[str, Any], config_type: str = "default"
    ) -> str:
        """Generate Shadowsocks config file"""
        if config_type == "clash":
            return self._build_clash_config(credential_data)
        elif config_type == "json":
            return self._build_json_config(credential_data)
        else:
            # Default to connection URI
            return credential_data.get(
                "ss_uri", self.build_connection_uri(credential_data)
            )

    def _build_clash_config(self, credential_data: Dict[str, Any]) -> str:
        """Build Clash proxy config"""
        country = credential_data.get("country_code", "")
        return f"""proxies:
  - name: FluxVPN-SS-{country}
    type: ss
    server: {credential_data['server']}
    port: {credential_data['port']}
    cipher: {credential_data['method']}
    password: {credential_data['password']}
    udp: true
"""

    def _build_json_config(self, credential_data: Dict[str, Any]) -> str:
        """Build JSON config for ss-local"""
        import json

        config = {
            "server": credential_data["server"],
            "server_port": credential_data["port"],
            "local_address": "127.0.0.1",
            "local_port": 1080,
            "password": credential_data["password"],
            "method": credential_data["method"],
            "timeout": 300,
            "fast_open": False,
        }
        return json.dumps(config, indent=2)

    def get_download_links(self) -> Dict[str, str]:
        """Get Shadowsocks client download links"""
        return {
            "windows": "https://github.com/shadowsocks/shadowsocks-windows/releases",
            "macos": "https://github.com/shadowsocks/ShadowsocksX-NG/releases",
            "linux": "https://github.com/shadowsocks/shadowsocks-libev",
            "android": "https://play.google.com/store/apps/details?id=com.github.shadowsocks",
            "ios": "https://apps.apple.com/app/shadowrocket/id932747118",
        }

    def get_connection_guide(self, platform: str) -> Dict[str, Any]:
        """Get connection guide for Shadowsocks"""
        guides = {
            "windows": {
                "steps": [
                    "1. Download Shadowsocks Windows from the link below",
                    "2. Extract and run Shadowsocks.exe",
                    "3. Right-click the system tray icon → Servers → Import from clipboard",
                    "4. Copy your SS URI and it will auto-import",
                    "5. Right-click → Enable System Proxy",
                ],
                "app_download_url": self.get_download_links()["windows"],
                "config_instructions": "Copy the SS URI and import via clipboard",
            },
            "macos": {
                "steps": [
                    "1. Download ShadowsocksX-NG from the link below",
                    "2. Open the DMG and drag to Applications",
                    "3. Launch ShadowsocksX-NG from Applications",
                    "4. Click the paper plane icon in menu bar → Servers → Import from clipboard",
                    "5. Copy your SS URI to import",
                    "6. Click the icon → Turn Shadowsocks On",
                ],
                "app_download_url": self.get_download_links()["macos"],
                "config_instructions": "Import SS URI via menu bar icon",
            },
            "linux": {
                "steps": [
                    "1. Install shadowsocks-libev: sudo apt install shadowsocks-libev",
                    "2. Download your JSON config file",
                    "3. Save config as /etc/shadowsocks-libev/config.json",
                    "4. Run: ss-local -c /etc/shadowsocks-libev/config.json",
                    "5. Configure browser to use SOCKS5 proxy at 127.0.0.1:1080",
                ],
                "app_download_url": self.get_download_links()["linux"],
                "config_instructions": "Use ss-local with JSON config file",
            },
            "android": {
                "steps": [
                    "1. Install Shadowsocks from Play Store",
                    "2. Open the app and tap the '+' button",
                    "3. Select 'Scan QR code' or 'Import from clipboard'",
                    "4. Copy your SS URI to import",
                    "5. Tap the profile and click the paper plane icon to connect",
                ],
                "app_download_url": self.get_download_links()["android"],
                "config_instructions": "Scan QR code or import SS URI",
            },
            "ios": {
                "steps": [
                    "1. Install Shadowrocket from App Store ($2.99)",
                    "2. Open Shadowrocket and tap '+' in top right",
                    "3. Select 'Type' as Shadowsocks",
                    "4. Or tap 'Add from clipboard' if SS URI is copied",
                    "5. Toggle the switch to connect",
                ],
                "app_download_url": self.get_download_links()["ios"],
                "config_instructions": "Import SS URI or scan QR code",
            },
        }

        return guides.get(platform, super().get_connection_guide(platform))
