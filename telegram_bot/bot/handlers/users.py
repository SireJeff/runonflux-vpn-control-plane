import math
import logging

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from bot.api.client import get_api
from bot.i18n.translator import t
from bot.keyboards.common import (
    back_to_main_keyboard,
    cancel_button,
    confirm_button,
    error_keyboard,
    make_button,
    make_keyboard,
    pagination_row,
)
from bot.keyboards.nav import nav_row

logger = logging.getLogger(__name__)

PER_PAGE = 5


def _format_traffic_gb(bytes_val: int | float | None) -> float:
    """Convert bytes to GB with 1 decimal."""
    if bytes_val is None:
        return 0.0
    return round(float(bytes_val) / (1024 ** 3), 1)


def _format_user_row(user: dict, lang: str) -> str:
    """Format a single user as a one-line summary for the list view."""
    username = user.get("username", "-")
    region = user.get("region_code", user.get("region", "-"))
    is_active = user.get("is_active", True)

    status_emoji = "✅" if is_active else "⏸️"

    used_gb = _format_traffic_gb(user.get("traffic_used"))
    limit_bytes = user.get("traffic_limit")
    if limit_bytes and int(limit_bytes) > 0:
        limit_gb = _format_traffic_gb(limit_bytes)
        traffic_str = f"{used_gb}/{limit_gb} GB"
    else:
        traffic_str = f"{used_gb} GB"

    status_label = t("status_active" if is_active else "status_suspended", lang)

    return f"{status_emoji} {username}    {region}    {traffic_str}    {status_label}"


def _build_users_list_text(users: list[dict], total: int, page: int, lang: str) -> str:
    """Build the full user list message text."""
    title = t("users_title", lang, total=total)
    if not users:
        return f"{title}\n\n{t('users_empty', lang)}"
    lines = [title, ""]
    for u in users:
        lines.append(_format_user_row(u, lang))
    return "\n".join(lines)


def _build_users_keyboard(total: int, page: int, lang: str) -> object:
    """Build inline keyboard for user list with pagination + back."""
    total_pages = max(1, math.ceil(total / PER_PAGE))
    rows = []

    # Pagination row (only if more than 1 page)
    if total_pages > 1:
        rows.append(pagination_row(page, total_pages, "users"))

    # Back to main menu
    rows.append([back_to_main_keyboard(lang).inline_keyboard[0][0]])
    return make_keyboard(rows)


async def _show_users_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    """Shared helper: answer() + fetch + render the paginated user list."""
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

    text = _build_users_list_text(users, total, current_page, lang)
    keyboard = _build_users_keyboard(total, current_page, lang)

    await query.edit_message_text(text, reply_markup=keyboard)


async def menu_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show paginated user list starting at page 1."""
    await _show_users_page(update, context, page=1)


async def users_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle pagination: users_page_{n}."""
    callback_data = update.callback_query.data
    try:
        page = int(callback_data.split("_")[-1])
    except (ValueError, IndexError):
        page = 1
    await _show_users_page(update, context, page=page)


async def user_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user detail: user_view_{id}."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("language", "en")
    telegram_id = update.effective_user.id
    api = get_api()

    # Extract user_id from callback data
    callback_data = query.data
    try:
        user_id = int(callback_data.split("_")[-1])
    except (ValueError, IndexError):
        await query.edit_message_text(
            t("error_general", lang),
            reply_markup=error_keyboard(lang),
        )
        return

    user = await api.get_user(telegram_id, user_id)

    if not user:
        await query.edit_message_text(
            t("error_general", lang),
            reply_markup=error_keyboard(lang),
        )
        return

    username = user.get("username", "-")
    is_active = user.get("is_active", True)
    region = user.get("region_code", user.get("region", "-"))
    region_display = user.get("region_display", region)

    # Status line
    status_emoji = "✅" if is_active else "⏸️"
    status_label = t("status_active" if is_active else "status_suspended", lang)
    status_line = t("users_detail_status", lang, status=f"{status_emoji} {status_label}")

    # Region line
    region_line = t("users_detail_region", lang, region=f"{region_display} ({region})")

    # Traffic line
    used_gb = _format_traffic_gb(user.get("traffic_used"))
    limit_bytes = user.get("traffic_limit")
    if limit_bytes and int(limit_bytes) > 0:
        limit_gb = _format_traffic_gb(limit_bytes)
        if limit_gb > 0:
            percentage = min(100, round(used_gb / limit_gb * 100))
        else:
            percentage = 0
        traffic_line = t(
            "users_detail_traffic", lang,
            used=used_gb, limit=limit_gb, percentage=percentage,
        )
    else:
        traffic_line = t("users_detail_traffic_unlimited", lang, used=used_gb)

    # Created line
    created_at = user.get("created_at", "-")
    # Truncate to date only if it includes time
    if isinstance(created_at, str) and "T" in created_at:
        created_at = created_at.split("T")[0]
    created_line = t("users_detail_created", lang, date=created_at)

    # Build message
    title = t("users_detail_title", lang, username=username)
    text = f"━━ {title} ━━\n\n{status_line}\n{region_line}\n{traffic_line}\n{created_line}"

    # Action buttons: Suspend/Resume + Back to Users
    action_label = t("btn_suspend" if is_active else "btn_resume", lang)
    rows = [
        [
            make_button(action_label, f"user_toggle_{user_id}", lang),
            make_button(t("btn_back_to_users", lang), "back_to_users", lang),
        ],
        [
            make_button("➕ ۳۰ روز", f"user_extend_{user_id}", lang),
            make_button("🌍 مناطق", f"user_regions_{user_id}", lang),
        ],
        nav_row(None, lang),
    ]

    await query.edit_message_text(text, reply_markup=make_keyboard(rows))


async def user_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show confirmation dialog for suspend/resume: user_toggle_{id}."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("language", "en")
    telegram_id = update.effective_user.id
    api = get_api()

    # Extract user_id from callback data
    callback_data = query.data
    try:
        user_id = int(callback_data.split("_")[-1])
    except (ValueError, IndexError):
        await query.edit_message_text(
            t("error_general", lang),
            reply_markup=error_keyboard(lang),
        )
        return

    user = await api.get_user(telegram_id, user_id)

    if not user:
        await query.edit_message_text(
            t("error_general", lang),
            reply_markup=error_keyboard(lang),
        )
        return

    username = user.get("username", "-")
    is_active = user.get("is_active", True)
    action = "suspend" if is_active else "resume"

    text = f"Are you sure you want to {action} user {username}?"
    rows = [
        [confirm_button(lang), cancel_button()],
    ]
    await query.edit_message_text(text, reply_markup=make_keyboard(rows))


async def confirm_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Execute suspend/resume toggle: confirm_toggle_{id}."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("language", "en")
    telegram_id = update.effective_user.id
    api = get_api()

    # Extract user_id from callback data
    callback_data = query.data
    try:
        user_id = int(callback_data.split("_")[-1])
    except (ValueError, IndexError):
        await query.edit_message_text(
            t("error_general", lang),
            reply_markup=error_keyboard(lang),
        )
        return

    result = await api.toggle_user(telegram_id, user_id)

    if not result:
        await query.edit_message_text(
            t("error_general", lang),
            reply_markup=error_keyboard(lang),
        )
        return

    username = result.get("username", "-")
    is_active = result.get("is_active", True)

    if is_active:
        text = t("users_resumed", lang, username=username)
    else:
        text = t("users_suspended", lang, username=username)

    rows = [
        [make_button(t("btn_back_to_users", lang), "back_to_users", lang)],
        nav_row(None, lang),
    ]
    await query.edit_message_text(text, reply_markup=make_keyboard(rows))


async def back_to_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Go back to user list (page 1)."""
    await _show_users_page(update, context, page=1)


async def user_extend_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Quick +30 days renewal: user_extend_{id}."""
    query = update.callback_query
    user_id = int(query.data.rsplit("_", 1)[1])
    api = get_api()
    result = await api.renew_user(update.effective_user.id, user_id, {"extend_days": 30})
    await query.answer("✅ ۳۰ روز اضافه شد." if result else "❌ خطا.", show_alert=True)


def _regedit_kb(user_id, regions, selected):
    rows = []
    for r in regions:
        if r["healthy_instances"] <= 0:
            continue
        mark = "✅" if r["code"] in selected else "⬜"
        rows.append([make_button(
            f"{mark} {r['flag']} {r['name']}", f"uregtoggle_{user_id}_{r['code']}",
        )])
    rows.append([make_button("💾 ذخیره", f"uregsave_{user_id}")])
    rows.append([make_button("↩️ بازگشت", f"user_view_{user_id}")])
    rows.append(nav_row(None))
    return make_keyboard(rows)


async def user_regions_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Open the region multi-select editor for a user: user_regions_{id}."""
    query = update.callback_query
    await query.answer()
    user_id = int(query.data.rsplit("_", 1)[1])
    api = get_api()
    user = await api.get_user(update.effective_user.id, user_id) or {}
    context.user_data[f"regedit_{user_id}"] = list(user.get("macro_regions", []))
    regions = await api.get_available_regions(update.effective_user.id) or []
    await query.edit_message_text(
        "مناطق را انتخاب کنید:",
        reply_markup=_regedit_kb(user_id, regions, context.user_data[f"regedit_{user_id}"]),
    )


async def user_regtoggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle a region in the editor: uregtoggle_{uid}_{macro}."""
    query = update.callback_query
    await query.answer()
    _, uid, macro = query.data.split("_", 2)
    user_id = int(uid)
    key = f"regedit_{user_id}"
    sel = context.user_data.get(key, [])
    context.user_data[key] = [m for m in sel if m != macro] if macro in sel else sel + [macro]
    api = get_api()
    regions = await api.get_available_regions(update.effective_user.id) or []
    await query.edit_message_reply_markup(_regedit_kb(user_id, regions, context.user_data[key]))


async def user_regsave_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Persist the edited region set: uregsave_{uid}."""
    query = update.callback_query
    user_id = int(query.data.rsplit("_", 1)[1])
    sel = context.user_data.get(f"regedit_{user_id}", [])
    if not sel:
        await query.answer("حداقل یک منطقه لازم است.", show_alert=True)
        return
    api = get_api()
    result = await api.set_user_regions(update.effective_user.id, user_id, sel)
    if result:
        context.user_data.pop(f"regedit_{user_id}", None)  # FIX 2: cleanup on success
    await query.answer("✅ ذخیره شد." if result else "❌ خطا.", show_alert=True)


def get_users_handlers() -> list:
    return [
        CallbackQueryHandler(menu_users_callback, pattern="^menu_users$"),
        CallbackQueryHandler(users_page_callback, pattern=r"^users_page_(\d+)$"),
        CallbackQueryHandler(user_view_callback, pattern=r"^user_view_(\d+)$"),
        CallbackQueryHandler(user_toggle_callback, pattern=r"^user_toggle_(\d+)$"),
        CallbackQueryHandler(confirm_toggle_callback, pattern=r"^confirm_toggle_(\d+)$"),
        CallbackQueryHandler(back_to_users_callback, pattern="^back_to_users$"),
        CallbackQueryHandler(user_extend_callback, pattern=r"^user_extend_\d+$"),
        CallbackQueryHandler(user_regions_callback, pattern=r"^user_regions_\d+$"),
        CallbackQueryHandler(user_regtoggle_callback, pattern=r"^uregtoggle_\d+_\w+$"),
        CallbackQueryHandler(user_regsave_callback, pattern=r"^uregsave_\d+$"),
    ]
