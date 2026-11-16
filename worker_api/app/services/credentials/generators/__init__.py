"""
Protocol-specific credential generators
"""

from typing import Callable

from .base import BaseCredentialGenerator
from .http_proxy import HTTPProxyCredentialGenerator
from .outline import OutlineCredentialGenerator
from .shadowsocks import ShadowsocksCredentialGenerator
from .ssh import SSHCredentialGenerator
from .trojan import TrojanCredentialGenerator
from .vless import VLESSCredentialGenerator

# Protocol name to generator mapping
GENERATORS: dict[str, Callable[[], BaseCredentialGenerator]] = {
    "shadowsocks": ShadowsocksCredentialGenerator,
    "trojan": TrojanCredentialGenerator,
    "vless": VLESSCredentialGenerator,
    "ssh": SSHCredentialGenerator,
    "outline": OutlineCredentialGenerator,
    "http_proxy": HTTPProxyCredentialGenerator,
}


def get_credential_generator(protocol_name: str) -> BaseCredentialGenerator:
    """
    Factory function to get the appropriate credential generator

    Args:
        protocol_name: Name of the protocol (case-insensitive)

    Returns:
        Credential generator instance

    Raises:
        ValueError: If protocol is not supported
    """
    protocol_key = protocol_name.lower().replace("-", "_")

    if protocol_key not in GENERATORS:
        raise ValueError(
            f"Unsupported protocol: {protocol_name}. Supported: {list(GENERATORS.keys())}"
        )

    return GENERATORS[protocol_key]()


__all__ = [
    "BaseCredentialGenerator",
    "ShadowsocksCredentialGenerator",
    "TrojanCredentialGenerator",
    "VLESSCredentialGenerator",
    "SSHCredentialGenerator",
    "OutlineCredentialGenerator",
    "HTTPProxyCredentialGenerator",
    "get_credential_generator",
    "GENERATORS",
]
