"""Persian inline keyboards for the end-user bot."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.bots.end_user_pagination import paginate, pagination_row

_LABELS = {
    "fa": {
        "buy": "📦 خرید اشتراک",
        "my_sub": "👤 اشتراک من",
        "connections": "🔗 اتصالات من",
        "support": "🎧 پشتیبانی",
        "wallet": "💰 کیف پول",
        "referral": "🎁 دعوت دوستان",
        "free_config": "🆓 کانفیگ رایگان",
        "settings": "⚙️ تنظیمات",
        "back": "🔙 بازگشت",
        "home": "🏠 منوی اصلی",
        "my_orders": "🧾 سفارش‌های من",
        "orders_title": "═══ 🧾 سفارش‌های من ═══",
        "orders_empty": "شما هنوز سفارشی ثبت نکرده‌اید.",
        "status_pending": "در انتظار",
        "status_approved": "تأیید شده",
        "status_rejected": "رد شده",
        "fc_join_title": "🎁 برای دریافت کانفیگ رایگان، در کانال‌های زیر عضو شوید:",
        "fc_check_again": "✅ عضو شدم — بررسی مجدد",
        "fc_unavailable": "کانفیگ رایگان موقتاً در دسترس نیست. کمی بعد دوباره تلاش کنید.",
        "fc_slots_full": "ظرفیت کانفیگ رایگان تکمیل است.",
        "fc_daily_label": "🎁 کانفیگ رایگان — {mb} مگابایت در روز",
    },
    "en": {
        "buy": "📦 Buy",
        "my_sub": "👤 My Subscription",
        "connections": "🔗 My Connections",
        "support": "🎧 Support",
        "wallet": "💰 Wallet",
        "referral": "🎁 Referral",
        "free_config": "🆓 Free Config",
        "settings": "⚙️ Settings",
        "back": "🔙 Back",
        "home": "🏠 Main Menu",
        "my_orders": "🧾 My Orders",
        "orders_title": "═══ 🧾 My Orders ═══",
        "orders_empty": "You have no orders yet.",
        "status_pending": "Pending",
        "status_approved": "Approved",
        "status_rejected": "Rejected",
        "fc_join_title": "🎁 Join these channels to unlock your free config:",
        "fc_check_again": "✅ I've joined — check again",
        "fc_unavailable": "Free config is temporarily unavailable. Please try again later.",
        "fc_slots_full": "Free config slots are full.",
        "fc_daily_label": "🎁 Free config — {mb} MB/day",
    },
}


def _L(lang: str, key: str) -> str:
    """Bilingual label lookup; falls back to English for unknown langs."""
    return _LABELS.get(lang, _LABELS["en"])[key]


def main_menu(
    lang: str = "fa", show_free_config: bool = False
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(_L(lang, "buy"), callback_data="buy"),
            InlineKeyboardButton(_L(lang, "my_sub"), callback_data="my_sub"),
        ],
        [
            InlineKeyboardButton(
                _L(lang, "connections"), callback_data="connections"
            ),
            InlineKeyboardButton(_L(lang, "support"), callback_data="support"),
        ],
        [
            InlineKeyboardButton(_L(lang, "wallet"), callback_data="wallet"),
            InlineKeyboardButton(_L(lang, "referral"), callback_data="referral"),
        ],
        [
            InlineKeyboardButton(_L(lang, "settings"), callback_data="settings"),
        ],
    ]
    if show_free_config:
        rows.append(
            [
                InlineKeyboardButton(
                    _L(lang, "free_config"), callback_data="free_config"
                ),
            ]
        )
    return InlineKeyboardMarkup(rows)


# Back-compat alias for any caller not yet updated.
def main_menu_fa() -> InlineKeyboardMarkup:
    return main_menu("fa")


def nav_footer(
    lang: str = "fa",
    back_to: str | None = None,
    quick_switch: str | None = None,
    screen: str | None = None,
) -> list[list[InlineKeyboardButton]]:
    """Standard navigation row appended to every screen's keyboard.

    Always includes [🏠 Main Menu]. Optionally a [🔙 Back] button (back_to =
    parent callback) and a quick-switch section button (quick_switch = a _LABELS
    key such as 'connections'). Returns a list of rows (one row) ready to
    extend a keyboard's row list.

    When both back_to and quick_switch are given, order is
    [🔙 Back, 🏠 Main Menu, <quick_switch>].

    If ``back_to`` is not passed but ``screen`` is, the back target is derived
    from the nav registry (``parent_of(screen)``). Passing ``back_to`` explicitly
    always wins for back-compat.
    """
    # Lazy import to avoid a circular import at module load time.
    from app.services.bots.nav_registry import parent_of

    if back_to is None and screen is not None:
        back_to = parent_of(screen)
    row = []
    if back_to:
        row.append(InlineKeyboardButton(_L(lang, "back"), callback_data=back_to))
    row.append(InlineKeyboardButton(_L(lang, "home"), callback_data="main_menu"))
    if quick_switch:
        row.append(
            InlineKeyboardButton(_L(lang, quick_switch), callback_data=quick_switch)
        )
    return [row]


def region_picker_fa() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🇪🇺 اروپا", callback_data="region:eu"),
                InlineKeyboardButton("🌏 آسیا", callback_data="region:as"),
            ],
            [
                InlineKeyboardButton("🇺🇸 آمریکا", callback_data="region:na"),
                InlineKeyboardButton("🌍 سایر", callback_data="region:row"),
            ],
            [InlineKeyboardButton("↩️ لغو", callback_data="main_menu")],
        ]
    )


def region_multiselect_keyboard(avail, selected, required):
    """avail: list of {"code","flag","name"} healthy macro-regions.
    selected: list[str] currently chosen. Renders a ✅/⬜ toggle per region
    plus a confirm button that shows progress.
    """
    rows = []
    for e in avail:
        mark = "✅" if e["code"] in selected else "⬜"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{mark} {e['flag']} {e['name']}",
                    callback_data=f"rtoggle:{e['code']}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                f"تأیید ({len(selected)}/{required})",
                callback_data="rconfirm",
            )
        ]
    )
    rows.append([InlineKeyboardButton("↩️ لغو", callback_data="main_menu")])
    return InlineKeyboardMarkup(rows)


def cancel_keyboard_fa() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("↩️ لغو", callback_data="main_menu")]]
    )


def language_picker(lang: str = "fa") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🇮🇷 فارسی", callback_data="lang:fa"),
                InlineKeyboardButton("🇬🇧 English", callback_data="lang:en"),
            ],
        ]
        + nav_footer(lang)
    )


def country_picker_keyboard(
    countries: list, lang: str = "fa", page: int = 0, per_page: int = 9
) -> InlineKeyboardMarkup:
    """3-per-row grid of country buttons (paginated) + reset-password + back-to-sub.

    countries: list of (code, flag, name) tuples.
    """
    page_items, page, total_pages = paginate(countries, page, per_page)
    rows = []
    current_row = []
    for code, flag, name in page_items:
        current_row.append(
            InlineKeyboardButton(f"{flag} {name}", callback_data=f"country:{code}")
        )
        if len(current_row) == 3:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)

    rows += pagination_row("pgcty", page, total_pages, lang)

    # Bottom action buttons
    reset_label = "🔄 بازنشانی رمز و لینک" if lang == "fa" else "🔄 Reset Password + Sub"
    sub_label = "📋 اشتراک من" if lang == "fa" else "📋 My Subscription"
    rows.append(
        [
            InlineKeyboardButton(reset_label, callback_data="reset_password"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(sub_label, callback_data="my_sub"),
        ]
    )
    rows.append([InlineKeyboardButton(_L(lang, "home"), callback_data="main_menu")])
    return InlineKeyboardMarkup(rows)
