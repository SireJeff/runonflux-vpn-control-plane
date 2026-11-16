"""
Base Credential Generator
Abstract base class for all protocol-specific credential generators
"""

import secrets
import string
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class CredentialData:
    """Standard credential data structure"""

    server: str
    port: int
    username: str
    password: str
    connection_uri: str
    config_data: Dict[str, Any]
    qr_code_data: Optional[str] = None


class BaseCredentialGenerator(ABC):
    """
    Abstract base class for protocol-specific credential generators

    Each protocol implements its own generate() method that returns
    credential_data compatible with the JSONB schema.
    """

    # Protocol identifier (lowercase)
    protocol_name: str = ""

    # Default ports for the protocol
    default_ports: list = []

    @abstractmethod
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
        Generate protocol-specific credentials

        Args:
            server_ip: Server IP address
            port: Server port
            user_id: User ID for unique credential generation
            subscription_id: Subscription ID
            country_code: Country code for the server
            **kwargs: Protocol-specific options

        Returns:
            Dictionary with credential_data for JSONB storage
        """
        pass

    @abstractmethod
    def build_connection_uri(self, credential_data: Dict[str, Any]) -> str:
        """
        Build connection URI/URL for the protocol

        Args:
            credential_data: The generated credential data

        Returns:
            Connection URI string (for importing into clients)
        """
        pass

    @abstractmethod
    def build_config_file(
        self, credential_data: Dict[str, Any], config_type: str = "default"
    ) -> str:
        """
        Generate configuration file content

        Args:
            credential_data: The generated credential data
            config_type: Type of config (clash, v2ray, etc.)

        Returns:
            Configuration file content as string
        """
        pass

    def generate_password(self, length: int = 24) -> str:
        """Generate a secure random password"""
        # Use base64-safe characters to avoid URL encoding issues
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    def generate_username(self, user_id: int, prefix: str = "") -> str:
        """Generate a unique username"""
        import time

        timestamp = int(time.time())
        random_suffix = "".join(
            secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6)
        )
        if prefix:
            return f"{prefix}_{user_id}_{timestamp}_{random_suffix}"
        return f"flux_{self.protocol_name}_{user_id}_{timestamp}_{random_suffix}"

    def generate_qr_code(self, credential_data: Dict[str, Any], size: int = 256) -> str:
        """
        Generate a QR code from the connection URI

        Args:
            credential_data: The generated credential data
            size: Size of the QR code image in pixels (default 256)

        Returns:
            Base64-encoded PNG image data URI
        """
        try:
            import base64
            from io import BytesIO

            import qrcode

            # Get the connection URI for this protocol
            connection_uri = self.build_connection_uri(credential_data)

            # Generate QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=2,
            )
            qr.add_data(connection_uri)
            qr.make(fit=True)

            # Create image
            img = qr.make_image(fill_color="black", back_color="white")

            # Resize if needed
            if size != 256:
                from PIL import Image

                img = img.resize((size, size), Image.Resampling.LANCZOS)

            # Convert to base64
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)
            qr_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

            return f"data:image/png;base64,{qr_base64}"

        except ImportError:
            # qrcode library not installed
            return ""
        except Exception:
            # Log error but don't fail
            return ""

    def get_download_links(self) -> Dict[str, str]:
        """Get app download links for this protocol"""
        return {}

    def get_connection_guide(self, platform: str) -> Dict[str, Any]:
        """Get connection guide for a specific platform"""
        return {
            "steps": [
                "1. Download the recommended app for your platform",
                "2. Import the configuration file or connection URI",
                "3. Connect to FluxVPN",
            ],
            "app_download_url": self.get_download_links().get(platform),
            "config_instructions": "Use the connection URI or download the config file",
        }
