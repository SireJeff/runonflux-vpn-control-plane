import math
import logging
from urllib.parse import urlparse, parse_qs

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from bot.api.client import get_api
from bot.i18n.translator import t
from bot.keyboards.common import (
    back_button,
    error_keyboard,
    make_button,
    make_keyboard,
    pagination_row,
)

logger = logging.getLogger(__name__)

PER_PAGE = 5


def parse_ssh_uri(uri: str) -> dict:
    """Parse an ssh:// URI into domain, port, username, password components."""
    parsed = urlparse(uri)
    params = parse_qs(parsed.query)
    return {
        "domain": parsed.hostname or "",
        "port": str(parsed.port or ""),
        "username": params.get("user", [""])[0],
        "password": params.get("password", [""])[0],
    }


def _format_user_row(user: dict, lang: str) -> str:
    """Format a single user as a one-line summary for the connections picker list."""
    username = user.get("username", "-")
    region = user.get("region_code", user.get("region", "-"))
    return f"{username} ({region})"


def _build_connections_user_list_text(users: list[dict], total: int, page: int, lang: str) -> str:
    """Build the full user list message text for connections picker."""
    title = t("connections_title", lang, username=t("menu_connections", lang))
    if not users:
        return f"{title}\n\n{t('users_empty', lang)}"
    lines = [title, ""]
    for u in users:
        lines.append(_format_user_row(u, lang))
    return "\n".join(lines)


def _build_connections_user_list_keyboard(total: int, page: int, lang: str) -> object:
    """Build inline keyboard for the user picker with pagination + back."""
    total_pages = max(1, math.ceil(total / PER_PAGE))
    rows = []

    if total_pages > 1:
        rows.append(pagination_row(page, total_pages, "conn"))

    rows.append([back_button("main_menu", lang)])
    return make_keyboard(rows)


async def _show_connections_user_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    """Shared helper to render the paginated user list for connections."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("language", "en")
    telegram_id = update.effective_user.id
    api = get_api()

    data = await api.list_users(telegram_id, page=page, per_page=PER_PAGE)

    if not data:
        await query.edit_message_text(
            t("error_general", lang),
            reply_markup=error_keyboard(lang),
        )
        return

    users = data.get("items", [])
    total = data.get("total", 0)
    current_page = data.get("page", page)
    per_page = data.get("per_page", PER_PAGE)

    text = _build_connections_user_list_text(users, total, current_page, lang)
    keyboard = _build_connections_user_list_keyboard(total, current_page, lang)

    await query.edit_message_text(text, reply_markup=keyboard)


def _build_connection_view_text(user_id: int, connections_data: dict, lang: str) -> str:
    """Build the formatted connection strings message for a user."""
    # Get username from the first available connection region key, or fallback
    connections = connections_data.get("connections", {})

    # Try to extract username from the connections structure
    # First region's first protocol's primary connection string
    username = "—"
    for region_data in connections.values():
        if isinstance(region_data, dict):
            for proto_data in region_data.values():
                if isinstance(proto_data, dict):
                    primary = proto_data.get("primary", "")
                    if primary:
                        parsed = parse_ssh_uri(primary) if primary.startswith("ssh://") else {}
                        username = parsed.get("username", "")
                        # Fallback: try to extract from vless URI
                        if not username:
                            try:
                                p = urlparse(primary)
                                username = (p.path or "").strip("/").split("@")[0]
                            except Exception:
                                pass
                        if username:
                            break
            if username:
                break

    title = t("connections_title", lang, username=username)
    lines = [f"━━ {title} ━━", ""]

    if not connections:
        lines.append(t("connections_empty", lang))
        return "\n".join(lines)

    for region_name, protocols in connections.items():
        if not isinstance(protocols, dict):
            continue

        region_label = t("connections_no_region", lang) if not region_name else region_name
        lines.append(f"Region: {region_label}")
        lines.append("")

        has_detail = False

        for protocol_name, proto_info in protocols.items():
            if not isinstance(proto_info, dict):
                continue

            primary = proto_info.get("primary", "")

            # SSH: parse URI and show detailed fields
            if protocol_name.lower() == "ssh" and primary.startswith("ssh://"):
                ssh = parse_ssh_uri(primary)
                lines.append(f"━━ SSH ━━")
                lines.append(f"Domain: {ssh['domain']}")
                lines.append(f"Port: {ssh['port']}")
                lines.append(f"Username: {ssh['username']}")
                lines.append(f"Password: {ssh['password']}")
                lines.append("")

                # Remark line if extractable from the URI fragment or fallback
                remark = f"FluxVPN-{region_name}" if region_name else "FluxVPN"
                lines.append(f"Remark: {remark}")
                lines.append("")
                has_detail = True
            elif primary:
                lines.append(f"━━ {protocol_name.upper()} ━━")
                lines.append(primary)
                lines.append("")
                has_detail = True

        # Collect all primary URIs for connection strings section
        all_primaries = []
        for proto_info in protocols.values():
            if isinstance(proto_info, dict) and proto_info.get("primary"):
                all_primaries.append(proto_info["primary"])

        if has_detail and all_primaries:
            lines.append("━━ Connection Strings ━━")
            for uri in all_primaries:
                lines.append(uri)
            lines.append("")

    return "\n".join(lines)


async def _render_connection_view(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    """Fetch and render the connection view for a specific user."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("language", "en")
    telegram_id = update.effective_user.id
    api = get_api()

    data = await api.get_connections(telegram_id, user_id)

    if not data:
        await query.edit_message_text(
            t("error_general", lang),
            reply_markup=error_keyboard(lang),
        )
        return

    text = _build_connection_view_text(user_id, data, lang)

    rows = [
        [
            make_button(t("connections_refresh", lang), f"conn_refresh_{user_id}", lang),
            back_button("menu_connections", lang),
        ],
    ]

    await query.edit_message_text(text, reply_markup=make_keyboard(rows))


# ── Callback Handlers ──────────────────────────────────────────────────────────


async def menu_connections_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show paginated user list so the admin picks which user to view connections for."""
    await _show_connections_user_list(update, context, page=1)


async def conn_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle pagination: conn_page_{n}."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("language", "en")
    telegram_id = update.effective_user.id
    api = get_api()

    callback_data = query.data
    try:
        page = int(callback_data.split("_")[-1])
    except (ValueError, IndexError):
        page = 1

    data = await api.list_users(telegram_id, page=page, per_page=PER_PAGE)

    if not data:
        await query.edit_message_text(
            t("error_general", lang),
            reply_markup=error_keyboard(lang),
        )
        return

    users = data.get("items", [])
    total = data.get("total", 0)
    current_page = data.get("page", page)
    per_page = data.get("per_page", PER_PAGE)

    text = _build_connections_user_list_text(users, total, current_page, lang)
    keyboard = _build_connections_user_list_keyboard(total, current_page, lang)

    await query.edit_message_text(text, reply_markup=keyboard)


async def conn_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show connection strings for a user: conn_view_{user_id}."""
    query = update.callback_query

    callback_data = query.data
    try:
        user_id = int(callback_data.split("_")[-1])
    except (ValueError, IndexError):
        await query.answer()
        lang = context.user_data.get("language", "en")
        await query.edit_message_text(
            t("error_general", lang),
            reply_markup=error_keyboard(lang),
        )
        return

    await _render_connection_view(update, context, user_id)


async def conn_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Refresh connections for a user: conn_refresh_{user_id}."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("language", "en")
    telegram_id = update.effective_user.id
    api = get_api()

    callback_data = query.data
    try:
        user_id = int(callback_data.split("_")[-1])
    except (ValueError, IndexError):
        await query.edit_message_text(
            t("error_general", lang),
            reply_markup=error_keyboard(lang),
        )
        return

    # Show loading
    await query.edit_message_text(t("loading", lang))

    result = await api.refresh_connections(telegram_id, user_id)

    if not result:
        # The API returns None on non-2xx responses (logged by client).
        # Check if the raw response had rate-limit info — the client swallows it,
        # so we show a generic rate-limit message as a fallback.
        await query.edit_message_text(
            t("connections_rate_limited", lang, hours=0, minutes=5),
            reply_markup=make_keyboard([[
                back_button("menu_connections", lang),
            ]]),
        )
        return

    # If the response contains rate limit info (e.g. a "retry_after" or "rate_limited" key)
    if result.get("rate_limited") or result.get("retry_after"):
        retry_after = result.get("retry_after", 300)  # seconds, default 5 min
        hours = retry_after // 3600
        minutes = (retry_after % 3600) // 60
        await query.edit_message_text(
            t("connections_rate_limited", lang, hours=hours, minutes=minutes),
            reply_markup=make_keyboard([[
                back_button("menu_connections", lang),
            ]]),
        )
        return

    # Success — re-render the connections view
    await _render_connection_view(update, context, user_id)


def get_connections_handlers() -> list:
    return [
        CallbackQueryHandler(menu_connections_callback, pattern="^menu_connections$"),
        CallbackQueryHandler(conn_page_callback, pattern=r"^conn_page_(\d+)$"),
        CallbackQueryHandler(conn_view_callback, pattern=r"^conn_view_(\d+)$"),
        CallbackQueryHandler(conn_refresh_callback, pattern=r"^conn_refresh_(\d+)$"),
    ]
