from app.models.user_orders import UserOrder


def test_user_order_has_macro_regions_column():
    assert "macro_regions" in UserOrder.__table__.columns
