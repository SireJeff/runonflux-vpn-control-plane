from app.services.bots.nav_registry import parent_of


def test_known_screen_parent():
    assert parent_of("topup") == "wallet"
    assert parent_of("wallet") == "main_menu"
    assert parent_of("country") == "connections"


def test_unknown_defaults_to_main_menu():
    assert parent_of("nonsense") == "main_menu"


def test_new_screens_registered():
    assert parent_of("guides") == "my_sub"
    assert parent_of("plans") == "buy"
    assert parent_of("payment") == "buy"
    assert parent_of("unknown") == "main_menu"
