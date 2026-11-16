"""Stateless pagination primitive for the reseller end-user bot.

The current page is carried in ``callback_data`` (e.g. ``pgplans:2``), so
paging survives bot restarts/redeploys and never shows stale data. Pure
helpers plus one inert ``noop`` handler for the disabled boundary/counter
buttons. Imports nothing from other bot modules (no import cycles).
"""

from telegram import InlineKeyboardButton, Update
from telegram.ext import ContextTypes


def paginate(items: list, page: int, per_page: int) -> tuple[list, int, int]:
    """Slice ``items`` for ``page``. Returns (page_items, page, total_pages).

    total_pages is at least 1 (an empty list is one empty page). page is
    clamped into [0, total_pages-1], so a stale/out-of-range callback (e.g. a
    button left over after the list shrank) renders the nearest valid page
    instead of raising.
    """
    total = len(items)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    return items[start : start + per_page], page, total_pages


def pagination_row(
    prefix: str, page: int, total_pages: int, lang: str = "fa"
) -> list[list[InlineKeyboardButton]]:
    """One-row [◀️][x/N][▶️] control, or [] when there is a single page.

    Boundary arrows (◀️ on the first page, ▶️ on the last) and the counter use
    callback_data='noop'. Active arrows carry f'{prefix}:{page-1}' /
    f'{prefix}:{page+1}'. Label is 1-indexed; callback_data is 0-indexed.
    """
    if total_pages <= 1:
        return []
    prev_cb = f"{prefix}:{page - 1}" if page > 0 else "noop"
    next_cb = f"{prefix}:{page + 1}" if page < total_pages - 1 else "noop"
    return [
        [
            InlineKeyboardButton("◀️", callback_data=prev_cb),
            InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop"),
            InlineKeyboardButton("▶️", callback_data=next_cb),
        ]
    ]


async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inert handler for disabled boundary/counter buttons: just ack the tap."""
    if update.callback_query is not None:
        await update.callback_query.answer()
