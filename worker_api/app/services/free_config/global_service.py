"""Superadmin global free-config service (Task 9).

Owns the FreeConfigGlobal singleton: the global toggle, per-user daily
ceiling, max-free-users cap, and the WRITE-ONLY verification-bot token.
`set_token` validates the token via getMe (validate_bot_token, which
RAISES on an invalid token) before storing its encrypted form + username.
"""

import asyncio

from sqlalchemy.orm import Session

from app.core.crypto import encrypt_token
from app.models.free_config_global import FreeConfigGlobal


class GlobalConfigService:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create(self) -> FreeConfigGlobal:
        row = self.db.query(FreeConfigGlobal).first()
        if row is None:
            row = FreeConfigGlobal(is_enabled=False, default_daily_limit_mb=200)
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)
        return row

    def update(self, **fields) -> FreeConfigGlobal:
        row = self.get_or_create()
        for k in ("is_enabled", "default_daily_limit_mb", "default_max_free_users"):
            if fields.get(k) is not None:
                setattr(row, k, fields[k])
        self.db.commit()
        self.db.refresh(row)
        return row

    def set_token(self, token: str) -> str:
        # Patched in the source module at call time -> re-import here.
        from app.services.free_config.membership_verifier import validate_bot_token

        username = asyncio.run(validate_bot_token(token))  # raises on invalid
        row = self.get_or_create()
        row.verification_bot_token_enc = encrypt_token(token)
        row.verification_bot_username = username
        self.db.commit()
        return username
