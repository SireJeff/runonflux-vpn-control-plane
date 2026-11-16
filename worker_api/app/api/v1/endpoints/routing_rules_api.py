"""Reseller routing rules API (ban list + website allow/direct)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth.role_dependencies import RoleChecker
from app.core.database import get_db
from app.schemas.routing_rules import RoutingRulesResponse, RoutingRulesUpdate
from app.services.routing.routing_rules_service import RoutingRulesService

router = APIRouter(prefix="/admin/routing-rules", tags=["Admin Routing Rules"])


def _to_response(cfg) -> RoutingRulesResponse:
    rules = cfg.rules if isinstance(cfg.rules, dict) else {}
    return RoutingRulesResponse(
        is_enabled=cfg.is_enabled,
        ban_domains=rules.get("ban_domains", []),
        allow_domains=rules.get("allow_domains", []),
        presets=rules.get("presets", {}),
    )


@router.get("", response_model=RoutingRulesResponse)
def get_routing_rules(
    current: dict = Depends(RoleChecker(["admin"])),
    db: Session = Depends(get_db),
):
    """Return the reseller's routing rules, creating a disabled default if absent."""
    cfg = RoutingRulesService(db).get_or_create(current["id"])
    return _to_response(cfg)


@router.put("", response_model=RoutingRulesResponse)
def update_routing_rules(
    payload: RoutingRulesUpdate,
    current: dict = Depends(RoleChecker(["admin"])),
    db: Session = Depends(get_db),
):
    """Replace the reseller's whole routing rule set."""
    cfg = RoutingRulesService(db).replace(
        current["id"],
        is_enabled=payload.is_enabled,
        ban_domains=payload.ban_domains,
        allow_domains=payload.allow_domains,
        presets=payload.presets,
    )
    return _to_response(cfg)
