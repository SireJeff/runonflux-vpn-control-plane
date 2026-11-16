"""Tests for the figure-based username generator (Task 6)."""

import re
from unittest.mock import MagicMock

from app.services.credentials.username_generator import (
    FIGURES,
    generate_unique_username,
)

FIGURE_RE = re.compile(r"^[a-z][a-z0-9]{1,13}$")


def test_every_figure_is_valid():
    assert len(FIGURES) >= 100
    for f in FIGURES:
        assert FIGURE_RE.match(f), f"invalid figure name: {f!r}"
        assert len(f) <= 14


def test_no_duplicate_figures():
    assert len(FIGURES) == len(set(FIGURES))


def test_generated_format():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    name = generate_unique_username(db, admin_id=5)
    figure, _, suffix = name.partition("_")
    assert figure in FIGURES
    assert re.fullmatch(r"[0-9a-f]{4}", suffix), name  # 4 hex chars


def test_retries_on_collision():
    db = MagicMock()
    # First candidate collides (truthy), second does not (None).
    db.query.return_value.filter.return_value.first.side_effect = [object(), None]
    name = generate_unique_username(db, admin_id=5)
    assert name.partition("_")[0] in FIGURES
    assert re.fullmatch(r"[0-9a-f]{4}", name.rsplit("_", 1)[1]), name
    # Prove the retry actually happened (two DB lookups, not one):
    assert db.query.return_value.filter.return_value.first.call_count == 2


def test_exhaustion_raises():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = (
        object()
    )  # always collides
    import pytest

    with pytest.raises(RuntimeError):
        generate_unique_username(db, admin_id=5, max_attempts=5)
