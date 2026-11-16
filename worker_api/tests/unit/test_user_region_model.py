from app.models.admin_users import AdminUser
from app.models.user_regions import UserRegion


def test_user_region_has_status_and_region_expiry_columns():
    cols = UserRegion.__table__.columns
    assert "status" in cols
    assert "region_expires_at" in cols


def test_user_region_unique_is_user_plus_macro():
    names = {c.name for c in UserRegion.__table__.constraints}
    assert "uq_user_region_user_macro" in names
    # the old single-column unique must be gone
    user_id_col = UserRegion.__table__.columns["user_id"]
    assert user_id_col.unique is not True


def test_admin_user_has_regions_collection_and_primary_scalar():
    assert AdminUser.regions.property.uselist is True
    assert AdminUser.region.property.uselist is False
