from unittest.mock import MagicMock

from app.services.subscriptions.package_seeder import (
    DEFAULT_PACKAGE_TEMPLATES,
    seed_default_packages,
)


def test_templates_are_single_region_or_all_regions_only():
    for t in DEFAULT_PACKAGE_TEMPLATES:
        if t["all_regions"]:
            assert t["region_count"] == 1  # ignored when all_regions
        else:
            assert t["region_count"] == 1  # spec §8.2: no 2-region variants seeded


def test_templates_have_required_fields():
    for t in DEFAULT_PACKAGE_TEMPLATES:
        assert {
            "name",
            "traffic_limit_gb",
            "duration_days",
            "price_tomans",
            "region_count",
            "all_regions",
        } <= set(t)


def test_seed_skips_when_admin_has_packages():
    db = MagicMock()
    db.query.return_value.filter.return_value.count.return_value = (
        3  # already has packages
    )
    inserted = seed_default_packages(db, admin_id=1)
    assert inserted == 0
    db.add.assert_not_called()


def test_seed_inserts_all_when_empty():
    db = MagicMock()
    db.query.return_value.filter.return_value.count.return_value = 0
    inserted = seed_default_packages(db, admin_id=1)
    assert inserted == len(DEFAULT_PACKAGE_TEMPLATES)
    assert db.add.call_count == len(DEFAULT_PACKAGE_TEMPLATES)
