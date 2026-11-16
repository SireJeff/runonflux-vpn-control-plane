from app.services.bots.end_user_keyboards import main_menu


def _callbacks(markup):
    return {b.callback_data for row in markup.inline_keyboard for b in row}


def test_free_config_button_hidden_by_default():
    assert "free_config" not in _callbacks(main_menu("fa"))


def test_free_config_button_shown_when_enabled():
    assert "free_config" in _callbacks(main_menu("fa", show_free_config=True))
