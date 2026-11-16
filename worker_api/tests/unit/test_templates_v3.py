"""Tests for v3 templates: country_detail, guides, reset_password (fa + en)."""
from app.services.notifications import templates_en as _EN
from app.services.notifications import templates_fa as _FA

# ---------------------------------------------------------------------------
# Country detail
# ---------------------------------------------------------------------------


def test_format_country_detail_fa_includes_ssh_fields_block():
    msg = _FA.format_country_detail(
        country_flag="🇳🇱",
        country_name_fa="هلند",
        protocols={
            "ssh": "ssh://u:p@h:1",
            "vless": "vless://u@h:2",
        },
        ssh_fields={"host": "h", "port": 1, "username": "u", "password": "p"},
    )
    assert "🇳🇱 هلند" in msg
    assert "ssh://u:p@h:1" in msg
    assert "vless://u@h:2" in msg
    # SSH field block
    assert "هاست" in msg or "Host" in msg  # fa uses هاست
    assert "پورت" in msg
    assert "رمز عبور" in msg


def test_format_country_detail_fa_without_ssh_fields():
    """If ssh_fields is None, no field block should be rendered."""
    msg = _FA.format_country_detail(
        country_flag="🇩🇪",
        country_name_fa="آلمان",
        protocols={"vless": "vless://u@h:2"},
        ssh_fields=None,
    )
    assert "🇩🇪 آلمان" in msg
    assert "vless://u@h:2" in msg
    assert "هاست" not in msg  # no SSH section


def test_format_country_detail_en_includes_ssh_fields_block():
    msg = _EN.format_country_detail(
        country_flag="🇳🇱",
        country_name_fa="Netherlands",
        protocols={"ssh": "ssh://u:p@h:1"},
        ssh_fields={"host": "h", "port": 1, "username": "u", "password": "p"},
    )
    assert "🇳🇱 Netherlands" in msg
    assert "ssh://u:p@h:1" in msg
    assert "Host" in msg
    assert "Port" in msg
    assert "Password" in msg


# ---------------------------------------------------------------------------
# Guides
# ---------------------------------------------------------------------------


def test_format_guide_android_fa_contains_download_urls():
    urls = {"throne": "https://t", "hiddify": "https://h", "nekobox": "https://n"}
    msg = _FA.format_guide_android(urls)
    assert "https://t" in msg
    assert "https://h" in msg
    assert "https://n" in msg
    assert "اندروید" in msg  # platform name in Persian


def test_format_guide_android_en_contains_download_urls():
    urls = {"throne": "https://t", "hiddify": "https://h", "nekobox": "https://n"}
    msg = _EN.format_guide_android(urls)
    assert "https://t" in msg
    assert "Android" in msg


def test_format_guide_ios_fa_and_en():
    urls = {"throne": "https://t", "hiddify": "https://h", "streisand": "https://s"}
    fa_msg = _FA.format_guide_ios(urls)
    en_msg = _EN.format_guide_ios(urls)
    assert "آیفون" in fa_msg
    assert "iOS" in en_msg
    assert "https://s" in fa_msg
    assert "https://s" in en_msg


def test_format_guide_windows_fa_and_en():
    urls = {"throne": "https://t", "nekoray": "https://n", "hiddify": "https://h"}
    fa_msg = _FA.format_guide_windows(urls)
    en_msg = _EN.format_guide_windows(urls)
    assert "ویندوز" in fa_msg
    assert "Windows" in en_msg
    assert "https://n" in fa_msg


# ---------------------------------------------------------------------------
# Guides — empty URL handling (Fix B: graceful when setting is "")
# ---------------------------------------------------------------------------


def test_render_apps_block_fa_skips_empty_urls():
    """Helper renders only non-empty URLs; label still shown for empty."""
    apps = [
        ("1️⃣", "Throne", ""),
        ("2️⃣", "Hiddify", "https://h"),
        ("3️⃣", "NekoBox", ""),
    ]
    result = _FA._render_apps_block(apps)
    assert "🔗 https://h" in result
    assert "Throne" in result
    assert "Hiddify" in result
    assert "NekoBox" in result
    # Only one 🔗 should appear (for Hiddify)
    assert result.count("🔗") == 1


def test_format_guide_android_fa_skips_empty_urls():
    """All-empty URLs → no 🔗 in apps block; labels still present."""
    urls = {"throne": "", "hiddify": "", "nekobox": ""}
    msg = _FA.format_guide_android(urls)
    assert "Throne" in msg
    assert "Hiddify" in msg
    assert "NekoBox" in msg
    # Zero non-empty URLs → zero 🔗 in the entire message
    assert "🔗" not in msg


def test_format_guide_android_en_partial_urls():
    """Mixed empty/populated URLs → only populated ones get 🔗 prefix."""
    urls = {"throne": "https://t", "hiddify": "", "nekobox": ""}
    msg = _EN.format_guide_android(urls)
    assert "🔗 https://t" in msg
    assert "Hiddify" in msg
    assert "NekoBox" in msg
    # Only 1 non-empty URL → exactly 1 🔗
    assert msg.count("🔗") == 1


def test_format_guide_ios_fa_all_empty_urls():
    urls = {"throne": "", "hiddify": "", "streisand": ""}
    msg = _FA.format_guide_ios(urls)
    assert "🔗" not in msg
    assert "Throne" in msg


def test_format_guide_windows_en_all_empty_urls():
    urls = {"throne": "", "nekoray": "", "hiddify": ""}
    msg = _EN.format_guide_windows(urls)
    assert "🔗" not in msg
    assert "Nekoray" in msg


# ---------------------------------------------------------------------------
# Reset password reply
# ---------------------------------------------------------------------------


def test_format_reset_password_reply_fa_contains_new_creds():
    msg = _FA.format_reset_password_reply(
        new_password="NewPass123",
        new_subscription_url="https://api.test/sub/newtoken",
    )
    assert "NewPass123" in msg
    assert "https://api.test/sub/newtoken" in msg
    assert "بازنشانی" in msg or "reset" in msg.lower()  # reset message wording


def test_format_reset_password_reply_en_contains_new_creds():
    msg = _EN.format_reset_password_reply(
        new_password="NewPass123",
        new_subscription_url="https://api.test/sub/newtoken",
    )
    assert "NewPass123" in msg
    assert "https://api.test/sub/newtoken" in msg
    assert "reset" in msg.lower() or "Reset" in msg
