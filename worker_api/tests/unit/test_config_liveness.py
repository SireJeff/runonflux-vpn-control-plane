"""FDM liveness config knobs: defaults + validators (Problem B)."""
import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _mk(**over):
    base = dict(SUPER_ADMIN_PASSWORD="dummy")
    base.update(over)
    return Settings(**base)


def test_liveness_defaults():
    s = _mk()
    assert s.FDM_LIVENESS_ENABLED is True
    assert s.FDM_LIVENESS_DEAD_CYCLES == 3
    assert s.FDM_LIVENESS_PORT_TIMEOUT == 4.0
    assert s.FDM_LIVENESS_MIN_INTERVAL == 300.0
    assert s.FDM_LIVENESS_MAX_DEAD_FRACTION == 0.5
    assert s.FDM_LIVENESS_CONCURRENCY == 20


def test_dead_cycles_must_be_at_least_one():
    with pytest.raises(ValidationError):
        _mk(FDM_LIVENESS_DEAD_CYCLES=0)


def test_max_dead_fraction_must_be_in_unit_interval():
    with pytest.raises(ValidationError):
        _mk(FDM_LIVENESS_MAX_DEAD_FRACTION=0)
    with pytest.raises(ValidationError):
        _mk(FDM_LIVENESS_MAX_DEAD_FRACTION=1.5)
    assert _mk(FDM_LIVENESS_MAX_DEAD_FRACTION=1.0).FDM_LIVENESS_MAX_DEAD_FRACTION == 1.0


def test_concurrency_must_be_at_least_one():
    with pytest.raises(ValidationError):
        _mk(FDM_LIVENESS_CONCURRENCY=0)
    assert _mk(FDM_LIVENESS_CONCURRENCY=1).FDM_LIVENESS_CONCURRENCY == 1
