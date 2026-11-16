"""Per-reseller routing rules service (mirrors FreeConfigService shape)."""

from typing import Dict, List

from sqlalchemy.orm import Session

from app.models.admin_routing_config import AdminRoutingConfig


class RoutingRulesService:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create(self, admin_id: int) -> AdminRoutingConfig:
        cfg = (
            self.db.query(AdminRoutingConfig)
            .filter(AdminRoutingConfig.admin_id == admin_id)
            .first()
        )
        if cfg is None:
            cfg = AdminRoutingConfig(admin_id=admin_id, is_enabled=False, rules={})
            self.db.add(cfg)
            self.db.commit()
            self.db.refresh(cfg)
        return cfg

    def replace(
        self,
        admin_id: int,
        is_enabled: bool,
        ban_domains: List[str],
        allow_domains: List[str],
        presets: Dict[str, bool],
    ) -> AdminRoutingConfig:
        cfg = self.get_or_create(admin_id)
        cfg.is_enabled = is_enabled
        cfg.rules = {
            "ban_domains": list(ban_domains),
            "allow_domains": list(allow_domains),
            "presets": dict(presets),
        }
        self.db.commit()
        self.db.refresh(cfg)
        return cfg

    def get_effective_rules(self, admin_id: int) -> dict:
        cfg = (
            self.db.query(AdminRoutingConfig)
            .filter(AdminRoutingConfig.admin_id == admin_id)
            .first()
        )
        if cfg is None or not cfg.is_enabled or not isinstance(cfg.rules, dict):
            return {}
        return cfg.rules
