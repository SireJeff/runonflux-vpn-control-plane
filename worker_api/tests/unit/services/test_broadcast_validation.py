import pytest

from app.services.broadcasts.broadcast_service import validate_content


def test_valid_plain_text_passes():
    validate_content("Hello everyone", None, None)


def test_valid_html_subset_passes():
    validate_content("<b>Bold</b> and <a href='https://x.io'>link</a>", None, None)


def test_empty_text_rejected():
    with pytest.raises(ValueError):
        validate_content("   ", None, None)


def test_overlong_text_rejected():
    with pytest.raises(ValueError):
        validate_content("x" * 4097, None, None)


def test_unsupported_tag_rejected():
    with pytest.raises(ValueError):
        validate_content("<script>alert(1)</script>", None, None)


def test_unbalanced_tag_rejected():
    with pytest.raises(ValueError):
        validate_content("<b>oops", None, None)


def test_half_button_rejected():
    with pytest.raises(ValueError):
        validate_content("hi", "Click", None)
    with pytest.raises(ValueError):
        validate_content("hi", None, "https://x.io")


def test_bad_button_url_scheme_rejected():
    with pytest.raises(ValueError):
        validate_content("hi", "Click", "javascript:alert(1)")


def test_valid_button_passes():
    validate_content("hi", "Open", "https://example.com")
