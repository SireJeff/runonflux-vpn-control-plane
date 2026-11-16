"""
Synchronous Telegram alert helper for non-async contexts.

Unlike the async NotificationClient (which expects User model objects with
telegram_user_id), this is a lightweight helper that sends Telegram messages
directly by chat_id.  Intended for use inside synchronous services such as
TrafficBillingService.
"""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

TELEGRAM_TEXT_LIMIT = 4096


def _chunk_message(message: str, max_len: int = TELEGRAM_TEXT_LIMIT) -> list[str]:
    """Split a long message into chunks at line boundaries.

    Each returned chunk is at most max_len chars. Tries to break on newlines;
    if a single line exceeds max_len it is hard-split.
    """
    if len(message) <= max_len:
        return [message]

    chunks: list[str] = []
    current_lines: list[str] = []
    current_len = 0

    for line in message.split("\n"):
        # Hard-split lines longer than max_len
        while len(line) > max_len:
            if current_lines:
                chunks.append("\n".join(current_lines))
                current_lines = []
                current_len = 0
            chunks.append(line[:max_len])
            line = line[max_len:]

        line_len = len(line) + 1  # +1 for the "\n" join
        if current_len + line_len > max_len and current_lines:
            chunks.append("\n".join(current_lines))
            current_lines = []
            current_len = 0
        current_lines.append(line)
        current_len += line_len

    if current_lines:
        chunks.append("\n".join(current_lines))

    return chunks


def send_telegram_alert(chat_id: int | str, message: str) -> bool:
    """Send a Telegram message directly to a chat_id. Synchronous.

    Auto-chunks messages longer than Telegram's 4096-char text limit and
    sends each chunk as a separate sendMessage. Returns True only if all
    chunks deliver.

    Args:
        chat_id: Target Telegram chat ID.
        message: Plain-text message body.

    Returns:
        True if the message was delivered, False otherwise.
    """
    if not settings.TELEGRAM_BOT_TOKEN or not chat_id:
        return False

    chunks = _chunk_message(message)
    try:
        with httpx.Client(timeout=15) as client:
            for chunk in chunks:
                response = client.post(
                    f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": chunk,
                    },
                )
                response.raise_for_status()
        return True
    except Exception as e:
        logger.error(
            f"Failed to send Telegram alert to {chat_id} "
            f"({len(chunks)} chunk(s), {len(message)} chars): {e}"
        )
        return False
