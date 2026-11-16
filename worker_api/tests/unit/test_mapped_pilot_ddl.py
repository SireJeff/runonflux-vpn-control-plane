"""Track (ii) DDL-identity guard: the compiled CREATE TABLE DDL for every
model table must not change as models migrate from Column(...) to
mapped_column(...). The fixture was generated from the models on branch
chore/mypy-mapped-pilot; because mapped_column keeps all DDL-affecting
arguments verbatim, the converted DDL is byte-identical to the original.

If this test goes red, a mapped_column argument was altered — fix the model,
do NOT regenerate the fixture to match."""

from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

import app.models  # noqa: F401  # populates Base.metadata with every table
from app.core.database import Base

_FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "mapped_pilot_ddl_before.sql"
)


def _all_tables():
    # Deterministic order: sort by table name so the fixture is stable.
    return sorted(Base.metadata.tables.values(), key=lambda t: t.name)


def _ddl() -> str:
    parts = [
        str(CreateTable(t).compile(dialect=postgresql.dialect())).strip()
        for t in _all_tables()
    ]
    return "\n\n".join(parts)


def test_all_models_import():
    # Import smoke: metadata is populated and every table is reflected.
    assert len(Base.metadata.tables) > 0


def test_all_models_ddl_unchanged():
    expected = _FIXTURE.read_text()
    assert _ddl() == expected, (
        "Compiled DDL for a model table changed — the Mapped[] migration is NOT "
        "byte-identical. Diff _ddl() against tests/fixtures/mapped_pilot_ddl_before.sql "
        "to find the altered mapped_column argument."
    )
