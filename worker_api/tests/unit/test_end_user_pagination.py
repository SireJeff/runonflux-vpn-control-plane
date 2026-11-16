"""Unit tests for the stateless pagination primitive."""

import app.services.bots.end_user_pagination as _mod

paginate = _mod.paginate
pagination_row = _mod.pagination_row


def test_paginate_basic_slice():
    items = list(range(0, 20))
    page_items, page, total = paginate(items, 1, 6)
    assert page_items == [6, 7, 8, 9, 10, 11]
    assert page == 1
    assert total == 4  # ceil(20/6)


def test_paginate_empty_is_one_page():
    page_items, page, total = paginate([], 0, 6)
    assert page_items == []
    assert page == 0
    assert total == 1


def test_paginate_exact_multiple():
    _, _, total = paginate(list(range(12)), 0, 6)
    assert total == 2


def test_paginate_clamps_out_of_range_high():
    page_items, page, total = paginate(list(range(10)), 99, 6)
    assert page == 1  # last page (0-indexed)
    assert total == 2
    assert page_items == [6, 7, 8, 9]


def test_paginate_clamps_negative():
    _, page, _ = paginate(list(range(10)), -5, 6)
    assert page == 0


def test_pagination_row_hidden_single_page():
    assert pagination_row("pgplans", 0, 1) == []


def test_pagination_row_first_page_prev_is_noop():
    row = pagination_row("pgplans", 0, 3)[0]
    assert row[0].callback_data == "noop"  # prev inert on first page
    assert row[1].text == "1/3"
    assert row[1].callback_data == "noop"  # counter inert
    assert row[2].callback_data == "pgplans:1"  # next active


def test_pagination_row_last_page_next_is_noop():
    row = pagination_row("pgorders", 2, 3)[0]
    assert row[0].callback_data == "pgorders:1"
    assert row[2].callback_data == "noop"


def test_pagination_row_interior_both_active():
    row = pagination_row("pgcty", 1, 3)[0]
    assert row[0].callback_data == "pgcty:0"
    assert row[1].text == "2/3"
    assert row[2].callback_data == "pgcty:2"
