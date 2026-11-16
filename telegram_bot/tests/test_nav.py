from bot.keyboards.nav import parent_of, nav_row


def test_parent_defaults_to_main_menu():
    assert parent_of("menu_users") == "main_menu"
    assert parent_of("unknown") == "main_menu"


def test_nav_row_back_and_home():
    row = nav_row("menu_users", "en")
    cbs = [b.callback_data for b in row]
    assert cbs == ["menu_users", "main_menu"]


def test_nav_row_home_only():
    row = nav_row(None, "en")
    cbs = [b.callback_data for b in row]
    assert cbs == ["main_menu"]
