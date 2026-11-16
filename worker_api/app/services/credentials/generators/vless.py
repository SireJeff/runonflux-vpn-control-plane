"""
VLESS Credential Generator
"""

import uuid
from typing import Any, Dict
from urllib.parse import quote

from .base import BaseCredentialGenerator


class VLESSCredentialGenerator(BaseCredentialGenerator):
    """
    Generates VLESS protocol credentials

    VLESS URI format:
    vless://uuid@server:port?encryption=none&type=ws&host=xxx&path=/xxx#remark

    VLESS is a lightweight protocol from V2Ray project,
    designed for better performance and flexibility.
    """

    protocol_name = "vless"
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
        """Generate VLESS credentials"""
        # VLESS uses UUID as the user ID
        vless_uuid = str(uuid.uuid4())

        # Transport settings
        network = kwargs.get("network", "ws")  # tcp, ws, grpc
        ws_path = kwargs.get("ws_path", f"/fluxvpn-{subscription_id}")
        ws_host = kwargs.get("ws_host", f"fluxvpn-{country_code.lower()}.runonflux.io")

        # TLS settings
        tls = kwargs.get("tls", True)
        sni = kwargs.get("sni", ws_host)

        # REALITY TLS settings (next-gen anti-detection)
        reality = kwargs.get("reality", False)
        reality_public_key = kwargs.get("reality_public_key", "")
        reality_short_id = kwargs.get("reality_short_id", "")
        reality_fingerprint = kwargs.get("reality_fingerprint", "chrome")
        reality_server_name = kwargs.get("reality_server_name", "www.google.com")

        # gRPC settings
        grpc_service = kwargs.get("grpc_service", "")

        # Flow control (for XTLS)
        flow = kwargs.get("flow", "")

        credential_data = {
            "server": server_ip,
            "port": port,
            "uuid": vless_uuid,
            "network": network,
            "ws_path": ws_path,
            "ws_host": ws_host,
            "tls": tls,
            "sni": sni,
            "encryption": "none",  # VLESS uses none encryption by default
            "country_code": country_code,
            "protocol": self.protocol_name,
            # REALITY settings
            "reality": reality,
            "reality_public_key": reality_public_key,
            "reality_short_id": reality_short_id,
            "reality_fingerprint": reality_fingerprint,
            "reality_server_name": reality_server_name,
            # gRPC settings
            "grpc_service": grpc_service,
            # Flow control
            "flow": flow,
        }

        # Build and add the VLESS URI
        credential_data["vless_uri"] = self.build_connection_uri(credential_data)

        return credential_data

    def build_connection_uri(self, credential_data: Dict[str, Any]) -> str:
        """Build VLESS URI"""
        vless_uuid = str(
            credential_data.get("uuid")
            or credential_data.get("username")
            or uuid.uuid4()
        )
        server = credential_data.get("server") or credential_data.get("server_ip")
        if not server:
            raise ValueError("Missing server for VLESS credential")
        port = int(credential_data.get("port") or 443)
        network = credential_data.get("network", "ws")
        country = credential_data.get("country_code", "")

        params = [
            "encryption=none",
            f"type={network}",
        ]

        if network == "ws":
            ws_path = credential_data.get("ws_path", "/")
            ws_host = credential_data.get("ws_host", "")
            params.append(f"path={quote(ws_path)}")
            if ws_host:
                params.append(f"host={ws_host}")
        elif network == "grpc":
            grpc_service = credential_data.get("grpc_service", "")
            if grpc_service:
                params.append(f"serviceName={grpc_service}")
            params.append("mode=gun")

        # REALITY TLS (advanced anti-detection)
        if credential_data.get("reality"):
            params.append("security=reality")
            params.append(
                f"sni={credential_data.get('reality_server_name', 'www.google.com')}"
            )
            params.append(f"fp={credential_data.get('reality_fingerprint', 'chrome')}")
            if credential_data.get("reality_public_key"):
                params.append(f"pbk={credential_data['reality_public_key']}")
            if credential_data.get("reality_short_id"):
                params.append(f"sid={credential_data['reality_short_id']}")
            if credential_data.get("flow"):
                params.append(f"flow={credential_data['flow']}")
        elif credential_data.get("tls"):
            params.append("security=tls")
            sni = credential_data.get("sni", "")
            if sni:
                params.append(f"sni={sni}")

        query = "&".join(params)
        remark = quote(f"FluxVPN-VLESS-{country}")

        return f"vless://{vless_uuid}@{server}:{port}?{query}#{remark}"

    def build_config_file(
        self, credential_data: Dict[str, Any], config_type: str = "default"
    ) -> str:
        """Generate VLESS config file"""
        if config_type == "clash":
            return self._build_clash_config(credential_data)
        elif config_type == "xray":
            return self._build_xray_config(credential_data)
        elif config_type == "surge":
            return self._build_surge_config(credential_data)
        elif config_type == "v2ray" or config_type == "json":
            return self._build_v2ray_config(credential_data)
        else:
            return credential_data.get(
                "vless_uri", self.build_connection_uri(credential_data)
            )

    def _build_clash_config(self, credential_data: Dict[str, Any]) -> str:
        """Build Clash Meta proxy config (Clash Premium doesn't support VLESS)"""
        vless_uuid = str(
            credential_data.get("uuid")
            or credential_data.get("username")
            or uuid.uuid4()
        )
        country = credential_data.get("country_code", "")
        network = credential_data.get("network", "ws")
        server = credential_data.get("server") or credential_data.get("server_ip") or ""
        port = int(credential_data.get("port") or 443)

        config = f"""proxies:
  - name: FluxVPN-VLESS-{country}
    type: vless
    server: {server}
    port: {port}
    uuid: {vless_uuid}
    network: {network}
    tls: {str(credential_data.get('tls', True)).lower()}
"""
        if network == "ws":
            config += f"""    ws-opts:
      path: {credential_data.get('ws_path', '/')}
      headers:
        Host: {credential_data.get('ws_host', '')}
"""
        if credential_data.get("tls"):
            config += f"""    servername: {credential_data.get('sni', '')}
    skip-cert-verify: false
"""
        return config

    def _build_v2ray_config(self, credential_data: Dict[str, Any]) -> str:
        """Build V2Ray JSON config"""
        import json

        server = credential_data.get("server") or credential_data.get("server_ip")
        port = int(credential_data.get("port") or 443)
        vless_uuid = str(
            credential_data.get("uuid")
            or credential_data.get("username")
            or uuid.uuid4()
        )

        stream_settings = {
            "network": credential_data.get("network", "ws"),
        }

        if stream_settings["network"] == "ws":
            stream_settings["wsSettings"] = {
                "path": credential_data.get("ws_path", "/"),
                "headers": {"Host": credential_data.get("ws_host", "")},
            }

        if credential_data.get("tls"):
            stream_settings["security"] = "tls"
            stream_settings["tlsSettings"] = {
                "serverName": credential_data.get("sni", ""),
                "allowInsecure": False,
            }

        config = {
            "inbounds": [
                {"port": 1080, "protocol": "socks", "settings": {"auth": "noauth"}}
            ],
            "outbounds": [
                {
                    "protocol": "vless",
                    "settings": {
                        "vnext": [
                            {
                                "address": server,
                                "port": port,
                                "users": [
                                    {
                                        "id": vless_uuid,
                                        "encryption": "none",
                                    }
                                ],
                            }
                        ]
                    },
                    "streamSettings": stream_settings,
                }
            ],
        }
        return json.dumps(config, indent=2)

    def _build_xray_config(self, credential_data: Dict[str, Any]) -> str:
        """Build Xray JSON config (v5 format with XTLS support)"""
        import json

        server = credential_data.get("server") or credential_data.get("server_ip")
        port = int(credential_data.get("port") or 443)
        vless_uuid = str(
            credential_data.get("uuid")
            or credential_data.get("username")
            or uuid.uuid4()
        )

        stream_settings = {
            "network": credential_data.get("network", "ws"),
        }

        if stream_settings["network"] == "ws":
            stream_settings["wsSettings"] = {
                "path": credential_data.get("ws_path", "/"),
                "headers": {"Host": credential_data.get("ws_host", "")},
            }
        elif stream_settings["network"] == "grpc":
            stream_settings["grpcSettings"] = {
                "serviceName": credential_data.get("grpc_service", ""),
                "multiMode": True,
            }

        if credential_data.get("tls"):
            stream_settings["security"] = "tls"
            stream_settings["tlsSettings"] = {
                "serverName": credential_data.get("sni", ""),
                "allowInsecure": False,
                "fingerprint": "chrome",
                "alpn": ["h2", "http/1.1"],
            }

        config = {
            "log": {"loglevel": "warning"},
            "inbounds": [
                {
                    "tag": "socks",
                    "port": 1080,
                    "listen": "127.0.0.1",
                    "protocol": "socks",
                    "sniffing": {"enabled": True, "destOverride": ["http", "tls"]},
                    "settings": {"auth": "noauth", "udp": True},
                }
            ],
            "outbounds": [
                {
                    "tag": "proxy",
                    "protocol": "vless",
                    "settings": {
                        "vnext": [
                            {
                                "address": server,
                                "port": port,
                                "users": [
                                    {
                                        "id": vless_uuid,
                                        "encryption": "none",
                                        "flow": credential_data.get("flow", ""),
                                    }
                                ],
                            }
                        ]
                    },
                    "streamSettings": stream_settings,
                },
                {"tag": "direct", "protocol": "freedom"},
            ],
            "routing": {
                "rules": [
                    {"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"}
                ]
            },
        }
        return json.dumps(config, indent=2)

    def _build_surge_config(self, credential_data: Dict[str, Any]) -> str:
        """Build Surge proxy config (iOS/macOS)"""
        vless_uuid = str(
            credential_data.get("uuid")
            or credential_data.get("username")
            or uuid.uuid4()
        )
        country = credential_data.get("country_code", "")
        network = credential_data.get("network", "ws")
        server = credential_data.get("server") or credential_data.get("server_ip") or ""
        port = int(credential_data.get("port") or 443)

        # Basic VLESS config for Surge
        config_lines = [
            f"FluxVPN-VLESS-{country} = vless, {server}, {port}, username={vless_uuid}"
        ]

        if credential_data.get("tls"):
            config_lines[0] += f", tls=true, sni={credential_data.get('sni', '')}"

        if network == "ws":
            config_lines[
                0
            ] += f", ws=true, ws-path={credential_data.get('ws_path', '/')}"
            if credential_data.get("ws_host"):
                config_lines[0] += f", ws-headers=Host:{credential_data['ws_host']}"

        return config_lines[0]

    def get_download_links(self) -> Dict[str, str]:
        """Get V2Ray/VLESS client download links"""
        return {
            "windows": "https://github.com/2dust/v2rayN/releases",
            "macos": "https://github.com/yanue/V2rayU/releases",
            "linux": "https://github.com/v2fly/v2ray-core/releases",
            "android": "https://github.com/2dust/v2rayNG/releases",
            "ios": "https://apps.apple.com/app/shadowrocket/id932747118",
        }

    def get_connection_guide(self, platform: str) -> Dict[str, Any]:
        """Get connection guide for VLESS"""
        guides = {
            "windows": {
                "steps": [
                    "1. Download V2rayN from the link below",
                    "2. Extract and run v2rayN.exe",
                    "3. Click 'Server' → 'Import server from clipboard'",
                    "4. Copy your VLESS URI",
                    "5. Right-click system tray → 'System Proxy' → 'Enable'",
                ],
                "app_download_url": self.get_download_links()["windows"],
                "config_instructions": "Import VLESS URI or use the V2Ray JSON config",
            },
            "macos": {
                "steps": [
                    "1. Download V2rayU from the link below",
                    "2. Open DMG and drag to Applications",
                    "3. Launch V2rayU from Applications",
                    "4. Click the 'V' icon in menu bar → 'Import'",
                    "5. Select 'Import from pasteboard' and paste VLESS URI",
                    "6. Click 'V' icon → 'Turn V2ray On'",
                ],
                "app_download_url": self.get_download_links()["macos"],
                "config_instructions": "Import VLESS URI via menu bar",
            },
            "linux": {
                "steps": [
                    "1. Download v2ray-core from the link below",
                    "2. Extract: unzip v2ray-linux-64.zip -d /usr/local/v2ray",
                    "3. Download your V2Ray JSON config file",
                    "4. Save as /usr/local/v2ray/config.json",
                    "5. Run: /usr/local/v2ray/v2ray run -c /usr/local/v2ray/config.json",
                    "6. Configure browser to use SOCKS5 proxy at 127.0.0.1:1080",
                ],
                "app_download_url": self.get_download_links()["linux"],
                "config_instructions": "Use v2ray-core with JSON config file",
            },
            "android": {
                "steps": [
                    "1. Install v2rayNG from Play Store or GitHub",
                    "2. Tap the '+' button",
                    "3. Select 'Import config from clipboard'",
                    "4. Copy your VLESS URI",
                    "5. Tap the server and click the connect button",
                ],
                "app_download_url": self.get_download_links()["android"],
                "config_instructions": "Import VLESS URI from clipboard",
            },
            "ios": {
                "steps": [
                    "1. Install Shadowrocket from App Store ($2.99)",
                    "2. Open Shadowrocket and tap '+' in top right",
                    "3. Select 'Type' as VLESS",
                    "4. Or tap 'Add from clipboard' if VLESS URI is copied",
                    "5. Toggle the switch to connect",
                ],
                "app_download_url": self.get_download_links()["ios"],
                "config_instructions": "Import VLESS URI or enter details manually",
            },
        }

        return guides.get(platform, super().get_connection_guide(platform))
