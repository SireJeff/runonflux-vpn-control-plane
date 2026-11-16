"""Persist receipt photos locally so dashboard can serve them via auth.

Telegram file URLs expire ~1 hour; our dashboard needs to show receipts
days/weeks later. On upload we download the photo to /data/receipts/
{order_id}.jpg and serve via an authenticated endpoint.
"""

import logging
import os
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

RECEIPTS_DIR = Path(os.environ.get("RECEIPTS_DIR", "/data/receipts"))


def ensure_dir() -> None:
    """Create the receipts directory if missing. Called lazily to allow tests
    to override RECEIPTS_DIR via env var before first write."""
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)


async def download_and_store(bot_token: str, file_id: str, order_id: int) -> str:
    """Download Telegram file to local disk. Returns absolute path.

    Raises RuntimeError if Telegram returns non-ok response or network fails.
    """
    ensure_dir()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram getFile failed: {data}")
        file_path = data["result"]["file_path"]

        url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        content_resp = await client.get(url)
        content_resp.raise_for_status()

    dest = RECEIPTS_DIR / f"{order_id}.jpg"
    dest.write_bytes(content_resp.content)
    logger.info(f"Stored receipt for order {order_id} -> {dest}")
    return str(dest)


def persist_path(order_id: int, path: str) -> None:
    """Update UserOrder.receipt_local_path using a fresh session."""
    from app.core.database import SessionLocal
    from app.models.user_orders import UserOrder

    db = SessionLocal()
    try:
        db.query(UserOrder).filter(UserOrder.id == order_id).update(
            {UserOrder.receipt_local_path: path}
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
