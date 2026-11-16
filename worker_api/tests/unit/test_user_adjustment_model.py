def test_user_adjustment_model_shape():
    from app.models.user_adjustments import UserAdjustment

    cols = UserAdjustment.__table__.columns
    for name in (
        "id",
        "user_id",
        "admin_id",
        "action",
        "details",
        "reason",
        "created_at",
    ):
        assert name in cols
    assert UserAdjustment.__tablename__ == "user_adjustments"


def test_user_adjustment_registered_in_models_package():
    import app.models as m

    assert hasattr(m, "UserAdjustment")
