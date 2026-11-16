from app.models.admin_routing_config import AdminRoutingConfig


def test_admin_routing_config_columns():
    cols = {c.name for c in AdminRoutingConfig.__table__.columns}
    assert cols == {"id", "admin_id", "is_enabled", "rules", "created_at", "updated_at"}
    assert AdminRoutingConfig.__tablename__ == "admin_routing_configs"


def test_admin_routing_config_admin_id_unique():
    constraints = {c.name for c in AdminRoutingConfig.__table__.constraints}
    assert "uq_admin_routing_configs_admin_id" in constraints
