"""
Trojan Credential Generator
"""

import hashlib
from typing import Any, Dict
from urllib.parse import quote

from .base import BaseCredentialGenerator


class TrojanCredentialGenerator(BaseCredentialGenerator):
    """
    Generates Trojan protocol credentials

    Trojan URI format:
    trojan://password@server:port?sni=domain#remark

    Trojan uses TLS for encryption and disguises as HTTPS traffic.
    Password is typically hashed with SHA224 for internal use.
    """

    protocol_name = "trojan"
    default_ports = [443, 80]

    def generate(
        self,
        server_ip: str,
        port: int,
        user_id: int,
        subscription_id: int,
        country_code: str = "NL",
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate Trojan credentials"""
        password = self.generate_password(32)
        sni = kwargs.get("sni", f"fluxvpn-{country_code.lower()}.runonflux.io")

        # Trojan internally uses SHA224 hash of password
        password_hash = hashlib.sha224(password.encode()).hexdigest()

        # Transport settings (tcp or ws)
        transport = kwargs.get("transport", "tcp")  # tcp or ws
        ws_path = kwargs.get("ws_path", f"/trojan-{subscription_id}")
        ws_host = kwargs.get("ws_host", sni)

        credential_data = {
            "server": server_ip,
            "port": port,
            "password": password,
            "password_hash": password_hash,
            "sni": sni,
            "country_code": country_code,
            "protocol": self.protocol_name,
            "tls": True,
            "verify_cert": True,
            # WebSocket transport settings
            "transport": transport,
            "ws_path": ws_path,
            "ws_host": ws_host,
        }

        # Build and add the Trojan URI
        credential_data["trojan_uri"] = self.build_connection_uri(credential_data)

        return credential_data

    def build_connection_uri(self, credential_data: Dict[str, Any]) -> str:
        """Build Trojan URI"""
        password = credential_data["password"]
        server = credential_data["server"]
        port = credential_data["port"]
        sni = credential_data.get("sni", "")
        country = credential_data.get("country_code", "")
        transport = credential_data.get("transport", "tcp")

        # trojan://password@server:port?sni=domain&type=tcp#remark
        params = []
        if sni:
            params.append(f"sni={quote(sni)}")

        if transport == "ws":
            params.append("type=ws")
            ws_path = credential_data.get("ws_path", "/")
            params.append(f"path={quote(ws_path)}")
            ws_host = credential_data.get("ws_host", "")
            if ws_host:
                params.append(f"host={ws_host}")
        else:
            params.append("type=tcp")

        params.append("security=tls")

        query = "&".join(params)
        remark = quote(f"FluxVPN-Trojan-{country}")

        return f"trojan://{password}@{server}:{port}?{query}#{remark}"

    def build_config_file(
        self, credential_data: Dict[str, Any], config_type: str = "default"
    ) -> str:
        """Generate Trojan config file"""
        if config_type == "clash":
            return self._build_clash_config(credential_data)
        elif config_type == "trojan-go" or config_type == "trojan_go":
            return self._build_trojan_go_config(credential_data)
        elif config_type == "json":
            return self._build_json_config(credential_data)
        else:
            return credential_data.get(
                "trojan_uri", self.build_connection_uri(credential_data)
            )

    def _build_clash_config(self, credential_data: Dict[str, Any]) -> str:
        """Build Clash proxy config"""
        country = credential_data.get("country_code", "")
        return f"""proxies:
  - name: FluxVPN-Trojan-{country}
    type: trojan
    server: {credential_data['server']}
    port: {credential_data['port']}
    password: {credential_data['password']}
    sni: {credential_data.get('sni', '')}
    skip-cert-verify: false
    udp: true
"""

    def _build_trojan_go_config(self, credential_data: Dict[str, Any]) -> str:
        """Build Trojan-Go JSON config (enhanced features)"""
        import json

        config = {
            "run_type": "client",
            "local_addr": "127.0.0.1",
            "local_port": 1080,
            "remote_addr": credential_data["server"],
            "remote_port": credential_data["port"],
            "password": [credential_data["password"]],
            "ssl": {
                "verify": True,
                "verify_hostname": True,
                "sni": credential_data.get("sni", ""),
                "alpn": ["h2", "http/1.1"],
                "fingerprint": "chrome",
            },
            "mux": {"enabled": True, "concurrency": 8, "idle_timeout": 60},
            "websocket": {
                "enabled": False,
                "path": "/",
                "host": credential_data.get("sni", ""),
            },
            "tcp": {"no_delay": True, "keep_alive": True, "prefer_ipv4": False},
        }
        return json.dumps(config, indent=2)

    def _build_json_config(self, credential_data: Dict[str, Any]) -> str:
        """Build Trojan JSON config"""
        import json

        config = {
            "run_type": "client",
            "local_addr": "127.0.0.1",
            "local_port": 1080,
            "remote_addr": credential_data["server"],
            "remote_port": credential_data["port"],
            "password": [credential_data["password"]],
            "ssl": {
                "verify": True,
                "verify_hostname": True,
                "sni": credential_data.get("sni", ""),
                "alpn": ["h2", "http/1.1"],
            },
            "tcp": {"no_delay": True, "keep_alive": True},
        }
        return json.dumps(config, indent=2)

    def get_download_links(self) -> Dict[str, str]:
        """Get Trojan client download links"""
        return {
            "windows": "https://github.com/trojan-gfw/trojan/releases",
            "macos": "https://github.com/trojan-gfw/trojan/releases",
            "linux": "https://github.com/trojan-gfw/trojan/releases",
            "android": "https://github.com/AnyTrojan/AnyTrojan/releases",
            "ios": "https://apps.apple.com/app/shadowrocket/id932747118",
        }

    def get_connection_guide(self, platform: str) -> Dict[str, Any]:
        """Get connection guide for Trojan"""
        guides = {
            "windows": {
                "steps": [
                    "1. Download Trojan client from the link below",
                    "2. Extract to a folder and open config.json",
                    "3. Replace with your FluxVPN Trojan config",
                    "4. Run trojan.exe to start the proxy",
                    "5. Configure your browser/apps to use SOCKS5 proxy at 127.0.0.1:1080",
                ],
                "app_download_url": self.get_download_links()["windows"],
                "config_instructions": "Download the JSON config and replace config.json",
            },
            "macos": {
                "steps": [
                    "1. Download Trojan-Qt5 from the link below",
                    "2. Open DMG and drag to Applications",
                    "3. Launch Trojan-Qt5",
                    "4. Click 'Connection' → 'Add' → 'URI'",
                    "5. Paste your Trojan URI",
                    "6. Select the server and click 'Connect'",
                ],
                "app_download_url": self.get_download_links()["macos"],
                "config_instructions": "Import Trojan URI via Connection menu",
            },
            "linux": {
                "steps": [
                    "1. Install trojan: sudo apt install trojan (or download from link)",
                    "2. Download your Trojan JSON config file",
                    "3. Save as /etc/trojan/config.json",
                    "4. Run: sudo trojan /etc/trojan/config.json",
                    "5. Configure browser to use SOCKS5 proxy at 127.0.0.1:1080",
                ],
                "app_download_url": self.get_download_links()["linux"],
                "config_instructions": "Use trojan CLI with JSON config file",
            },
            "android": {
                "steps": [
                    "1. Install v2rayNG from Play Store or GitHub",
                    "2. Tap the '+' button",
                    "3. Select 'Import config from clipboard'",
                    "4. Copy your Trojan URI",
                    "5. Tap the server and click the connect button",
                ],
                "app_download_url": self.get_download_links()["android"],
                "config_instructions": "Import Trojan URI via v2rayNG",
            },
            "ios": {
                "steps": [
                    "1. Install Shadowrocket from App Store",
                    "2. Tap '+' to add server",
                    "3. Select 'Trojan' as type",
                    "4. Enter server details or import Trojan URI",
                    "5. Tap to connect",
                ],
                "app_download_url": self.get_download_links()["ios"],
                "config_instructions": "Import the Trojan URI or enter details manually",
            },
        }

        return guides.get(platform, super().get_connection_guide(platform))
