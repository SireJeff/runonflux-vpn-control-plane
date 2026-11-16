"""
HTTP Proxy Credential Generator
"""

from typing import Any, Dict
from urllib.parse import quote

from .base import BaseCredentialGenerator


class HTTPProxyCredentialGenerator(BaseCredentialGenerator):
    """
    Generates HTTP Proxy (Squid) credentials

    HTTP Proxy URL format:
    http://username:password@server:port

    Uses Basic authentication with Squid proxy server.
    Supports both HTTP and HTTPS CONNECT tunneling.
    """

    protocol_name = "http_proxy"
    default_ports = [3128]

    def generate(
        self,
        server_ip: str,
        port: int,
        user_id: int,
        subscription_id: int,
        country_code: str = "NL",
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate HTTP Proxy credentials"""
        username = self.generate_username(user_id, prefix="flux")
        password = self.generate_password(20)

        credential_data = {
            "server": server_ip,
            "port": port,
            "username": username,
            "password": password,
            "country_code": country_code,
            "protocol": self.protocol_name,
            "proxy_type": "http",  # http or https
        }

        # Build proxy URL
        credential_data["proxy_url"] = self.build_connection_uri(credential_data)

        return credential_data

    def build_connection_uri(self, credential_data: Dict[str, Any]) -> str:
        """Build HTTP Proxy URL"""
        username = quote(credential_data["username"], safe="")
        password = quote(credential_data["password"], safe="")
        server = credential_data["server"]
        port = credential_data["port"]

        return f"http://{username}:{password}@{server}:{port}"

    def build_config_file(
        self, credential_data: Dict[str, Any], config_type: str = "default"
    ) -> str:
        """Generate proxy config"""
        if config_type == "pac":
            return self._build_pac_file(credential_data)
        elif config_type == "env":
            return self._build_env_vars(credential_data)
        elif config_type == "curl":
            return self._build_curl_example(credential_data)
        else:
            return credential_data.get(
                "proxy_url", self.build_connection_uri(credential_data)
            )

    def _build_pac_file(self, credential_data: Dict[str, Any]) -> str:
        """Build PAC (Proxy Auto-Config) file"""
        server = credential_data["server"]
        port = credential_data["port"]

        return f"""function FindProxyForURL(url, host) {{
    // Direct connection for local addresses
    if (isPlainHostName(host) ||
        shExpMatch(host, "*.local") ||
        isInNet(dnsResolve(host), "10.0.0.0", "255.0.0.0") ||
        isInNet(dnsResolve(host), "172.16.0.0", "255.240.0.0") ||
        isInNet(dnsResolve(host), "192.168.0.0", "255.255.0.0") ||
        isInNet(dnsResolve(host), "127.0.0.0", "255.255.255.0")) {{
        return "DIRECT";
    }}

    // Use FluxVPN proxy for all other traffic
    return "PROXY {server}:{port}";
}}
"""

    def _build_env_vars(self, credential_data: Dict[str, Any]) -> str:
        """Build environment variables for proxy"""
        proxy_url = credential_data.get(
            "proxy_url", self.build_connection_uri(credential_data)
        )

        return f"""# Add these to your shell profile (.bashrc, .zshrc, etc.)
export http_proxy="{proxy_url}"
export https_proxy="{proxy_url}"
export HTTP_PROXY="{proxy_url}"
export HTTPS_PROXY="{proxy_url}"

# To exclude local addresses:
export no_proxy="localhost,127.0.0.1,*.local"
export NO_PROXY="localhost,127.0.0.1,*.local"
"""

    def _build_curl_example(self, credential_data: Dict[str, Any]) -> str:
        """Build curl command example"""
        server = credential_data["server"]
        port = credential_data["port"]
        username = credential_data["username"]
        password = credential_data["password"]

        return f"""# Using curl with FluxVPN HTTP Proxy

# Method 1: Proxy URL
curl -x "http://{username}:{password}@{server}:{port}" https://api.ipify.org

# Method 2: Separate options
curl --proxy "http://{server}:{port}" \\
     --proxy-user "{username}:{password}" \\
     https://api.ipify.org

# Method 3: Environment variable
export https_proxy="http://{username}:{password}@{server}:{port}"
curl https://api.ipify.org
"""

    def get_download_links(self) -> Dict[str, str]:
        """Get HTTP proxy setup links (no special client needed)"""
        return {
            "windows": "Built-in: Settings > Network > Proxy",
            "macos": "Built-in: System Preferences > Network > Proxies",
            "linux": "Built-in: Network Settings or environment variables",
            "android": "Built-in: WiFi Settings > Modify Network > Proxy",
            "ios": "Built-in: Settings > WiFi > (i) > HTTP Proxy",
        }

    def get_connection_guide(self, platform: str) -> Dict[str, Any]:
        """Get connection guide for HTTP Proxy"""
        guides = {
            "windows": {
                "steps": [
                    "1. Open Settings > Network & Internet > Proxy",
                    "2. Under 'Manual proxy setup', turn on 'Use a proxy server'",
                    "3. Enter server address and port",
                    "4. When prompted, enter username and password",
                    "5. Click Save",
                ],
                "app_download_url": None,
                "config_instructions": "Configure in Windows proxy settings",
            },
            "macos": {
                "steps": [
                    "1. Open System Preferences > Network",
                    "2. Select your network connection",
                    "3. Click 'Advanced' > 'Proxies'",
                    "4. Check 'Web Proxy (HTTP)' and 'Secure Web Proxy (HTTPS)'",
                    "5. Enter server, port, username, and password",
                    "6. Click OK and Apply",
                ],
                "app_download_url": None,
                "config_instructions": "Configure in macOS Network preferences",
            },
            "linux": {
                "steps": [
                    "1. Open System Settings > Network > Network Proxy",
                    "2. Select 'Manual' method",
                    "3. Enter HTTP and HTTPS proxy details",
                    "4. Or set environment variables (see config file)",
                    "5. Log out and back in for system-wide effect",
                ],
                "app_download_url": None,
                "config_instructions": "Use GUI settings or export environment variables",
            },
            "android": {
                "steps": [
                    "1. Open Settings > WiFi",
                    "2. Long-press your connected network > Modify network",
                    "3. Show advanced options",
                    "4. Set Proxy to 'Manual'",
                    "5. Enter proxy hostname, port",
                    "6. Authentication: enter username/password when prompted",
                ],
                "app_download_url": None,
                "config_instructions": "Configure in WiFi network settings",
            },
            "ios": {
                "steps": [
                    "1. Open Settings > WiFi",
                    "2. Tap the (i) next to your network",
                    "3. Scroll down and tap 'Configure Proxy'",
                    "4. Select 'Manual'",
                    "5. Enter server, port, username, and password",
                    "6. Tap 'Save'",
                ],
                "app_download_url": None,
                "config_instructions": "Configure in WiFi network settings",
            },
        }

        return guides.get(platform, super().get_connection_guide(platform))
