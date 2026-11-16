"""In-process registry of python-telegram-bot Application objects.

One Application per registered reseller bot. Lazily initialized on first
webhook hit. Cached as {bot_id: Application} so subsequent updates are
dispatched without re-paying Application startup cost.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Dict, Optional

from sqlalchemy.orm import Session

from app.core.crypto import decrypt_token
from app.core.database import SessionLocal
from app.models.admin_bots import AdminBot

if TYPE_CHECKING:
    from telegram.ext import Application

logger = logging.getLogger(__name__)


class BotInactiveError(Exception):
    """Raised when a webhook arrives for a bot marked inactive."""


@dataclass
class _BotSnapshot:
    """Detached copy of the AdminBot fields the manager needs.

    Returned by _load_bot_config so callers never touch a live/expired ORM
    instance after its short-lived session is closed.
    """

    id: int
    admin_id: int
    is_active: bool
    bot_token_enc: bytes


def _default_token_loader(bot: "_BotSnapshot") -> str:
    return decrypt_token(bot.bot_token_enc)


def _default_app_builder(token: str) -> "Application":
    from telegram.ext import ApplicationBuilder

    return ApplicationBuilder().token(token).updater(None).build()


class ResellerBotManager:
    """In-memory Application objects for active reseller bots."""

    def __init__(
        self,
        db: Session,
        *,
        session_factory: Optional[Callable[[], Session]] = None,
        token_loader: Callable[["_BotSnapshot"], str] = _default_token_loader,
        app_builder: Callable[[str], "Application"] = _default_app_builder,
        handler_registrar: Optional[Callable[["Application"], None]] = None,
    ):
        # ``db`` is retained for backward compatibility but is intentionally NOT
        # used for per-webhook lookups: a single long-lived Session pins one
        # pooled connection for the process lifetime and shares transaction
        # state across concurrent async webhooks. Each lookup instead gets its
        # own short session from ``session_factory`` (SessionLocal by default),
        # opened and closed within _load_bot_config.
        self.db = db
        self._session_factory = session_factory or SessionLocal
        self._apps: Dict[int, "Application"] = {}
        self._lock = asyncio.Lock()
        self._token_loader = token_loader
        self._app_builder = app_builder
        self._handler_registrar = handler_registrar

    def _load_bot_config(self, bot_id: int) -> Optional["_BotSnapshot"]:
        db = self._session_factory()
        try:
            bot = db.query(AdminBot).filter(AdminBot.id == bot_id).first()
            if bot is None:
                return None
            return _BotSnapshot(
                id=bot.id,
                admin_id=bot.admin_id,
                is_active=bot.is_active,
                bot_token_enc=bot.bot_token_enc,
            )
        finally:
            db.close()

    async def get_or_create_app(self, bot_id: int) -> "Application":
        if bot_id in self._apps:
            return self._apps[bot_id]

        async with self._lock:
            if bot_id in self._apps:
                return self._apps[bot_id]

            bot = self._load_bot_config(bot_id)
            if not bot or not bot.is_active:
                raise BotInactiveError(f"Bot {bot_id} not found or inactive")

            token = self._token_loader(bot)
            app = self._app_builder(token)
            app.bot_data["admin_id"] = bot.admin_id
            app.bot_data["bot_id"] = bot.id

            if self._handler_registrar:
                self._handler_registrar(app)

            await app.initialize()
            self._apps[bot_id] = app
            logger.info(f"Initialized Application for bot_id={bot_id}")
            return app

    async def evict(self, bot_id: int) -> None:
        app = self._apps.pop(bot_id, None)
        if app:
            try:
                await app.shutdown()
            except Exception as e:
                logger.warning(f"Error shutting down app for bot {bot_id}: {e}")

    async def refresh(self, bot_id: int) -> None:
        """Re-load a bot's Application in-place (used by /reactivate)."""
        async with self._lock:
            old = self._apps.pop(bot_id, None)
            if old:
                try:
                    await old.shutdown()
                except Exception as e:
                    logger.warning(f"Error shutting down app for bot {bot_id}: {e}")
            await self.get_or_create_app(bot_id)
