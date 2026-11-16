import logging
from dataclasses import dataclass, field

from app.core.crypto import decrypt_token
from app.models.free_config_global import FreeConfigGlobal

logger = logging.getLogger(__name__)

_JOINED = {"member", "administrator", "creator"}

# Telegram raises these from getChatMember when the queried user is definitively
# NOT a participant of the chat (common in broadcast channels, where a non-member
# cannot be resolved and yields "Participant_id_invalid" instead of status="left").
# These mean "not joined" — show the join screen — NOT an infra failure to fail
# closed on. Everything else (bot not admin, chat not found, network) stays
# unverifiable. Matched case-insensitively against the exception text.
_NOT_MEMBER_ERRORS = ("participant_id_invalid", "user_not_participant")


@dataclass
class VerificationResult:
    ok: bool
    missing: list = field(default_factory=list)
    unverifiable: list = field(default_factory=list)


class MembershipVerifier:
    """Checks whether a Telegram user is a member of all required channels."""

    def __init__(self, bot):
        self._bot = bot

    @classmethod
    def from_global(cls, db):
        g = db.query(FreeConfigGlobal).first()
        if not g or not g.verification_bot_token_enc:
            return None
        from telegram import Bot
        return cls(Bot(decrypt_token(g.verification_bot_token_enc)))

    @staticmethod
    def _is_joined(member) -> bool:
        status = getattr(member, "status", None)
        if status in _JOINED:
            return True
        if status == "restricted":
            return bool(getattr(member, "is_member", False))
        return False

    async def check(self, telegram_id: int, channels: list) -> VerificationResult:
        missing, unverifiable = [], []
        for ch in channels:
            target = ch.chat_id if ch.chat_id is not None else ch.username
            try:
                member = await self._bot.get_chat_member(target, telegram_id)
            except Exception as exc:  # bot not admin / chat not found / network / non-member
                msg = str(exc).lower()
                if any(marker in msg for marker in _NOT_MEMBER_ERRORS):
                    # Definitive "not a participant" — treat as not joined, not infra failure.
                    logger.info("membership check: user not a member of %s (%s)", target, exc)
                    missing.append(ch)
                else:
                    logger.warning("membership check unverifiable for %s: %s", target, exc)
                    unverifiable.append(ch)
                continue
            if not self._is_joined(member):
                missing.append(ch)
        ok = not missing and not unverifiable
        return VerificationResult(ok=ok, missing=missing, unverifiable=unverifiable)


async def validate_bot_token(token: str) -> str:
    """Return the bot's @username via getMe; raises on invalid token."""
    from telegram import Bot
    me = await Bot(token).get_me()
    return me.username


async def resolve_channel(bot, identifier: str) -> dict:
    """Resolve a channel handle/id to its chat_id/title and confirm bot is admin."""
    chat = await bot.get_chat(identifier)
    admins = await bot.get_chat_administrators(chat.id)
    bot_me = await bot.get_me()
    if not any(a.user.id == bot_me.id for a in admins):
        raise ValueError("verification bot is not an admin of this channel")
    return {
        "chat_id": chat.id,
        "title": chat.title or "",
        "username": (f"@{chat.username}" if chat.username else None),
        "invite_url": getattr(chat, "invite_link", None),
    }
