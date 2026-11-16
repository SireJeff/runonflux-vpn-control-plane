"""
FluxVPN Reseller Credential Service
Protocol-specific credential generation and management for the reseller platform.
Generates per-user VPN credentials across all protocols using AdminUser + UserCredentialV2.
"""

import base64
import hashlib
import logging
import secrets
import uuid
from typing import Dict

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.admin_users import AdminUser
from app.models.user_credentials_v2 import UserCredentialV2

logger = logging.getLogger(__name__)

PROTOCOLS = ["ssh", "ss", "vless", "trojan", "outline", "http_proxy"]


class CredentialService:
    """Generates and manages per-user VPN credentials across all protocols."""

    def __init__(self, db: Session):
        self.db = db

    def generate_user_credentials(
        self, user: AdminUser, *, commit: bool = True
    ) -> Dict[str, UserCredentialV2]:
        """Generate credentials for all protocols for a given user.

        Returns dict mapping protocol_name -> UserCredentialV2.
        With commit=False, flush only; the caller owns the transaction.
        """
        credentials = {}

        for protocol in PROTOCOLS:
            # Skip if already exists
            existing = (
                self.db.query(UserCredentialV2)
                .filter(
                    UserCredentialV2.user_id == user.id,
                    UserCredentialV2.protocol == protocol,
                )
                .first()
            )
            if existing:
                credentials[protocol] = existing
                continue

            cred_data = self._generate_protocol_credential(user, protocol)

            cred = UserCredentialV2(
                user_id=user.id,
                protocol=protocol,
                credential_data=cred_data,
            )
            self.db.add(cred)
            credentials[protocol] = cred

        if commit:
            self.db.commit()
        else:
            self.db.flush()
        logger.info(
            "Generated credentials for user %s across %d protocols",
            user.username,
            len(credentials),
        )
        return credentials

    def _generate_protocol_credential(self, user: AdminUser, protocol: str) -> dict:
        """Generate credential data for a specific protocol."""

        if protocol == "ssh":
            return {
                "username": user.username,
                "password": secrets.token_urlsafe(12),
            }

        elif protocol == "ss":  # Shadowsocks
            return {
                "method": "aes-256-gcm",
                "password": secrets.token_urlsafe(32),
            }

        elif protocol == "vless":
            return {
                "uuid": str(uuid.uuid4()),
            }

        elif protocol == "trojan":
            return {"password": self._trojan_password(user.username)}

        elif protocol == "outline":
            return {
                "access_key": f"ss://{secrets.token_urlsafe(24)}@",
                "method": "chacha20-ietf-poly1305",
                "password": secrets.token_urlsafe(16),
            }

        elif protocol == "http_proxy":
            return {
                "username": user.username,
                "password": secrets.token_urlsafe(12),
            }

        return {}

    def get_user_credentials(self, user_id: int) -> Dict[str, UserCredentialV2]:
        """Get all credentials for a user."""
        creds = (
            self.db.query(UserCredentialV2)
            .filter(UserCredentialV2.user_id == user_id)
            .all()
        )
        return {c.protocol: c for c in creds}

    def delete_user_credentials(self, user_id: int) -> int:
        """Delete all credentials for a user. Returns count deleted."""
        count = (
            self.db.query(UserCredentialV2)
            .filter(UserCredentialV2.user_id == user_id)
            .delete()
        )
        self.db.commit()
        return count

    def _trojan_password(self, username: str) -> str:
        """Derive the trojan password from a username (stable, matches creation)."""
        secret = (
            settings.TROJAN_SECRET_KEY
            or settings.FLUXVPN_SECRET_KEY
            or "default_trojan_secret"
        )
        raw = f"{username}:{secret}"
        digest = hashlib.sha256(raw.encode()).digest()
        return base64.urlsafe_b64encode(digest[:24]).decode().rstrip("=")

    def reprovision_username(self, user: AdminUser) -> list[str]:
        """Rewrite username-dependent credential rows after a rename.

        ssh/http_proxy: set credential_data["username"] to the new username
        (password preserved). trojan: recompute the derived password.
        ss/vless/outline: untouched. Does NOT commit — caller owns the txn.
        Returns the list of protocols whose credential_data changed.
        """
        rows = (
            self.db.query(UserCredentialV2)
            .filter(UserCredentialV2.user_id == user.id)
            .all()
        )
        changed: list[str] = []
        for row in rows:
            data = dict(row.credential_data or {})
            if row.protocol in ("ssh", "http_proxy"):
                data["username"] = user.username
                row.credential_data = data
                changed.append(row.protocol)
            elif row.protocol == "trojan":
                data["password"] = self._trojan_password(user.username)
                row.credential_data = data
                changed.append(row.protocol)
        return changed
