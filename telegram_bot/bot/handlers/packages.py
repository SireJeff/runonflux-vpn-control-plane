"""Reseller package (plan-template) management handlers."""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes,
    ConversationHandler, MessageHandler, filters,
)

from bot.api.client import get_api
from bot.keyboards.nav import nav_row

logger = logging.getLogger(__name__)

P_NAME, P_TRAFFIC, P_DURATION, P_PRICE, P_REGIONS = range(5)


def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("↩️ لغو", callback_data="pkg_cancel")]])


async def menu_packages_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    api = get_api()
    packages = await api.list_packages(update.effective_user.id) or []
    if not packages:
        text = "شما هنوز پلنی ندارید."
    else:
        text = "═══ 📦 پلن‌های شما ═══\n" + "\n".join(
            f"• {p['name']} — {p['traffic_limit_gb']}GB / {p['duration_days']}d / "
            f"{'همه مناطق' if p['all_regions'] else str(p['region_count']) + ' منطقه'} — "
            f"{int(float(p['price_tomans'])):,} ت"
            for p in packages
        )
    rows = [
        [InlineKeyboardButton("➕ پلن جدید", callback_data="pkg_new")],
        [InlineKeyboardButton("♻️ بارگذاری پیش‌فرض‌ها", callback_data="pkg_load_defaults")],
        [InlineKeyboardButton("↩️ بازگشت", callback_data="main_menu")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows))


async def load_defaults_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    api = get_api()
    result = await api._post("/admin/packages/seed-defaults", update.effective_user.id)
    if result is not None:
        count = result.get("inserted", 0) if isinstance(result, dict) else 0
        msg = f"✅ {count} پلن پیش‌فرض بارگذاری شد." if count else "پلن‌های شما از قبل موجود است."
    else:
        msg = "❌ خطا در بارگذاری پیش‌فرض‌ها."
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([nav_row(None)]))


# --- create conversation ---
async def pkg_new_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    context.user_data["new_pkg"] = {}
    await update.callback_query.edit_message_text("نام پلن را وارد کنید:", reply_markup=_cancel_kb())
    return P_NAME


async def pkg_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_pkg"]["name"] = update.message.text.strip()
    await update.message.reply_text("حجم ترافیک (GB):", reply_markup=_cancel_kb())
    return P_TRAFFIC


async def pkg_traffic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data["new_pkg"]["traffic_limit_gb"] = float(update.message.text)
    except ValueError:
        await update.message.reply_text("عدد نامعتبر. حجم ترافیک (GB):")
        return P_TRAFFIC
    await update.message.reply_text("مدت (روز):", reply_markup=_cancel_kb())
    return P_DURATION


async def pkg_duration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data["new_pkg"]["duration_days"] = int(update.message.text)
    except ValueError:
        await update.message.reply_text("عدد نامعتبر. مدت (روز):")
        return P_DURATION
    await update.message.reply_text("قیمت (تومان):", reply_markup=_cancel_kb())
    return P_PRICE


async def pkg_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data["new_pkg"]["price_tomans"] = float(update.message.text)
    except ValueError:
        await update.message.reply_text("عدد نامعتبر. قیمت (تومان):")
        return P_PRICE
    await update.message.reply_text("تعداد مناطق (1-4) یا 'all' برای همه:", reply_markup=_cancel_kb())
    return P_REGIONS


async def pkg_regions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    val = update.message.text.strip().lower()
    if val == "all":
        context.user_data["new_pkg"]["all_regions"] = True
        context.user_data["new_pkg"]["region_count"] = 1
    else:
        try:
            n = int(val)
        except ValueError:
            await update.message.reply_text("عدد نامعتبر. تعداد مناطق (1-4) یا 'all':")
            return P_REGIONS
        if n < 1 or n > 4:
            await update.message.reply_text("تعداد مناطق باید بین ۱ تا ۴ باشد. دوباره وارد کنید:")
            return P_REGIONS
        context.user_data["new_pkg"]["region_count"] = n
        context.user_data["new_pkg"]["all_regions"] = False
    api = get_api()
    result = await api.create_package(update.effective_user.id, context.user_data["new_pkg"])
    context.user_data.pop("new_pkg", None)
    await update.message.reply_text("✅ پلن ساخته شد." if result else "❌ خطا در ساخت پلن.")
    return ConversationHandler.END


async def pkg_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("new_pkg", None)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("لغو شد.")
    elif update.message:
        await update.message.reply_text("لغو شد.")
    return ConversationHandler.END


def get_packages_handlers() -> list:
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(pkg_new_start, pattern="^pkg_new$")],
        states={
            P_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, pkg_name)],
            P_TRAFFIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, pkg_traffic)],
            P_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, pkg_duration)],
            P_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, pkg_price)],
            P_REGIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, pkg_regions)],
        },
        fallbacks=[
            CommandHandler("cancel", pkg_cancel),
            CallbackQueryHandler(pkg_cancel, pattern="^pkg_cancel$"),
            CallbackQueryHandler(pkg_cancel, pattern="^main_menu$"),
        ],
    )
    return [
        CallbackQueryHandler(menu_packages_callback, pattern="^menu_packages$"),
        CallbackQueryHandler(load_defaults_callback, pattern="^pkg_load_defaults$"),
        conv,
    ]
