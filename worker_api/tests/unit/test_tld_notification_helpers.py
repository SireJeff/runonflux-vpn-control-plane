"""Unit tests for the Phase-3 TLD notification templates + purpose labels.

No DB, no Celery — pure string formatting. Safe to run in any pytest group.
"""


def test_en_template_contains_purpose_label_and_new_domain():
    from app.services.notifications.templates_en import format_tld_effective_changed

    msg = format_tld_effective_changed("subscription link", "sub.new.example")
    assert "subscription link" in msg
    assert "sub.new.example" in msg


def test_fa_template_contains_purpose_label_and_new_domain():
    from app.services.notifications.templates_fa import format_tld_effective_changed

    msg = format_tld_effective_changed("لینک اشتراک", "sub.new.example")
    assert "لینک اشتراک" in msg
    assert "sub.new.example" in msg


def test_en_purpose_labels_cover_all_four_purposes():
    from app.services.notifications.templates_en import TLD_PURPOSE_LABELS

    for p in ("fdm", "subscription", "dashboard", "admin_panel"):
        assert p in TLD_PURPOSE_LABELS
    assert TLD_PURPOSE_LABELS["subscription"] == "subscription link"
    assert TLD_PURPOSE_LABELS["admin_panel"] == "admin panel"


def test_fa_purpose_labels_cover_all_four_purposes():
    from app.services.notifications.templates_fa import TLD_PURPOSE_LABELS

    for p in ("fdm", "subscription", "dashboard", "admin_panel"):
        assert p in TLD_PURPOSE_LABELS
    assert TLD_PURPOSE_LABELS["subscription"] == "لینک اشتراک"
    assert TLD_PURPOSE_LABELS["admin_panel"] == "پنل مدیریت"


def test_template_for_resolves_labels_per_language():
    from app.services.notifications.templates_fa import template_for

    assert template_for("en").TLD_PURPOSE_LABELS["dashboard"] == "user panel"
    assert template_for("fa").TLD_PURPOSE_LABELS["dashboard"] == "پنل کاربر"
    # unknown language falls back to fa
    assert template_for("de").TLD_PURPOSE_LABELS["dashboard"] == "پنل کاربر"
