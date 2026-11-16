import pytest
from pydantic import ValidationError

from app.schemas.admin_packages import PackageCreateRequest


def _base(**over):
    data = dict(name="Test", traffic_limit_gb=10, duration_days=30, price_tomans=150000)
    data.update(over)
    return data


def test_region_count_defaults_to_one():
    req = PackageCreateRequest(**_base())
    assert req.region_count == 1
    assert req.all_regions is False


def test_region_count_accepts_valid_bounds():
    assert PackageCreateRequest(**_base(region_count=4)).region_count == 4


def test_region_count_rejects_zero():
    with pytest.raises(ValidationError):
        PackageCreateRequest(**_base(region_count=0))


def test_region_count_rejects_above_four():
    with pytest.raises(ValidationError):
        PackageCreateRequest(**_base(region_count=5))


def test_all_regions_flag_parses():
    assert PackageCreateRequest(**_base(all_regions=True)).all_regions is True
