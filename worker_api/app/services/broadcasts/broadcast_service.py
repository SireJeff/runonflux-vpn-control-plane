"""Reseller broadcast service: segments, audience, eligibility, validation."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.admin_bots import AdminBot
from app.models.admin_users import AdminUser
from app.models.admins import Admin
from app.models.broadcast import Broadcast

VALID_SEGMENTS: set[str] = {
    "all",
    "lang_fa",
    "lang_en",
    "active_paid",
    "expired_free",
}

# Sentinel end-user created by the free-config feature; never a broadcast target.
# (legacy ``__free__`` or per-reseller ``__free__<admin_id>``).
FREE_SENTINEL_PREFIX: str = "__free__"

MAX_TEXT_LEN = 4096
_ALLOWED_URL_SCHEMES = {"http", "https", "tg"}

# Telegram-supported HTML tag subset (sendMessage parse_mode=HTML).
_ALLOWED_TAGS = {
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
    "a", "code", "pre", "span", "tg-spoiler", "blockquote",
}


class _TagValidator(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.error: str | None = None

    def handle_starttag(self, tag, attrs):
        if tag not in _ALLOWED_TAGS:
            self.error = self.error or f"unsupported tag <{tag}>"
        else:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag not in _ALLOWED_TAGS:
            self.error = self.error or f"unsupported tag <{tag}/>"

    def handle_endtag(self, tag):
        if tag not in _ALLOWED_TAGS:
            self.error = self.error or f"unsupported tag </{tag}>"
        elif not self.stack or self.stack[-1] != tag:
            self.error = self.error or f"mismatched </{tag}>"
        else:
            self.stack.pop()


def _validate_html(text: str) -> None:
    parser = _TagValidator()
    parser.feed(text)
    parser.close()
    if parser.error:
        raise ValueError(f"Invalid message HTML: {parser.error}")
    if parser.stack:
        raise ValueError(f"Invalid message HTML: unclosed <{parser.stack[-1]}>")


def validate_content(
    message_text: str,
    button_label: str | None,
    button_url: str | None,
) -> None:
    """Raise ValueError if the broadcast content is invalid; else return None."""
    if not message_text or not message_text.strip():
        raise ValueError("Message text is required")
    if len(message_text) > MAX_TEXT_LEN:
        raise ValueError(f"Message exceeds {MAX_TEXT_LEN} characters")
    _validate_html(message_text)

    has_label = bool(button_label and button_label.strip())
    has_url = bool(button_url and button_url.strip())
    if has_label != has_url:
        raise ValueError("Button label and URL must both be provided or both omitted")
    if has_url:
        scheme = urlparse(button_url or "").scheme.lower()
        if scheme not in _ALLOWED_URL_SCHEMES:
            raise ValueError(f"Button URL scheme '{scheme}' not allowed")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _base_query(db: Session, admin_id: int):
    return db.query(AdminUser).filter(
        AdminUser.admin_id == admin_id,
        AdminUser.telegram_chat_id.isnot(None),
        ~AdminUser.username.startswith(FREE_SENTINEL_PREFIX, autoescape=True),
        AdminUser.status != "deleted",
    )


def _apply_segment(query, segment: str):
    if segment not in VALID_SEGMENTS:
        raise ValueError(f"Unknown segment: {segment}")
    if segment == "all":
        return query
    if segment == "lang_fa":
        return query.filter(AdminUser.language == "fa")
    if segment == "lang_en":
        return query.filter(AdminUser.language == "en")
    now = _now()
    if segment == "active_paid":
        return query.filter(
            AdminUser.status == "active",
            AdminUser.expires_at.isnot(None),
            AdminUser.expires_at > now,
        )
    # expired_free: explicitly expired, never purchased, or past expiry
    return query.filter(
        or_(
            AdminUser.status == "expired",
            AdminUser.expires_at.is_(None),
            AdminUser.expires_at <= now,
        )
    )


def count_audience(db: Session, admin_id: int, segment: str) -> int:
    return _apply_segment(_base_query(db, admin_id), segment).count()


def resolve_audience(db: Session, admin_id: int, segment: str) -> list[tuple[int, int]]:
    rows = _apply_segment(_base_query(db, admin_id), segment).all()
    return [(u.id, u.telegram_chat_id) for u in rows]


@dataclass
class BroadcastEligibility:
    ok: bool
    reason: str | None = None  # "disabled"|"no_bot"|"in_flight"|"rate_limited"


def can_broadcast(db: Session, admin_id: int) -> BroadcastEligibility:
    admin = db.query(Admin).filter(Admin.id == admin_id).first()
    if admin is None or not admin.broadcasts_enabled:
        return BroadcastEligibility(False, "disabled")

    bot = (
        db.query(AdminBot)
        .filter(AdminBot.admin_id == admin_id, AdminBot.is_active == True)  # noqa: E712
        .first()
    )
    if bot is None:
        return BroadcastEligibility(False, "no_bot")

    stale_before = _now() - timedelta(minutes=settings.BROADCAST_STALE_MINUTES)
    in_flight = (
        db.query(Broadcast)
        .filter(
            Broadcast.admin_id == admin_id,
            Broadcast.status.in_(("queued", "sending")),
            func.coalesce(Broadcast.started_at, Broadcast.created_at) > stale_before,
        )
        .first()
    )
    if in_flight is not None:
        return BroadcastEligibility(False, "in_flight")

    since = _now() - timedelta(hours=24)
    recent = (
        db.query(Broadcast)
        .filter(Broadcast.admin_id == admin_id, Broadcast.created_at > since)
        .count()
    )
    if recent >= settings.BROADCAST_MAX_PER_DAY:
        return BroadcastEligibility(False, "rate_limited")

    return BroadcastEligibility(True)
