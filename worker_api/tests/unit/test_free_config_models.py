from app.models.admin_free_config import AdminFreeConfig
from app.models.free_config_channel import FreeConfigChannel
from app.models.free_config_global import FreeConfigGlobal
from app.models.free_config_enrollment import FreeConfigEnrollment
from app.core.database import Base


def test_new_columns_and_tables_exist():
    afc = AdminFreeConfig.__table__.columns
    assert "daily_limit_mb" in afc
    assert "max_free_users" in afc
    assert "free_config_channels" in Base.metadata.tables
    assert "free_config_global" in Base.metadata.tables
    assert "free_config_enrollments" in Base.metadata.tables
    ch = Base.metadata.tables["free_config_channels"].columns
    assert ch["admin_id"].nullable is True  # NULL == global scope
    enr = Base.metadata.tables["free_config_enrollments"].columns
    assert enr["user_id"].unique or any(
        "user_id" in c.columns for c in Base.metadata.tables["free_config_enrollments"].constraints if hasattr(c, "columns")
    )
