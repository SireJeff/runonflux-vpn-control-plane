"""Region availability — the single source of truth for which macro-regions
currently have healthy FDM capacity. Consumed by the admin API endpoint and by
the in-process purchase bot (both run inside worker_api with direct DB access).
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.constants import MACRO_REGIONS, country_flag, get_country_name


def _healthy_country_counts(db: Session) -> dict[str, int]:
    """Uppercase country code -> count of healthy FDM domains."""
    from app.models.fdm import FdmDeployment, FdmDomain

    return dict(
        db.query(
            func.upper(FdmDeployment.region).label("code"),
            func.count(func.distinct(FdmDomain.id)).label("healthy"),
        )
        .join(FdmDomain, FdmDomain.deployment_id == FdmDeployment.id)
        .filter(
            FdmDeployment.is_active == True,  # noqa: E712
            FdmDomain.health_status == "healthy",
        )
        .group_by(func.upper(FdmDeployment.region))
        .all()
    )


def macro_region_availability(db: Session) -> list[dict]:
    counts = _healthy_country_counts(db)
    out = []
    for macro_code, info in MACRO_REGIONS.items():
        countries = [
            {
                "code": c,
                "name": get_country_name(c),
                "flag": country_flag(c),
                "healthy_instances": counts.get(c, 0),
            }
            for c in info["countries"]
            if counts.get(c, 0) > 0
        ]
        out.append(
            {
                "code": macro_code,
                "name": info["name"],
                "flag": info["flag"],
                "healthy_instances": sum(counts.get(c, 0) for c in info["countries"]),
                "countries": countries,
            }
        )
    return out


def healthy_macro_codes(db: Session) -> set[str]:
    return {
        e["code"] for e in macro_region_availability(db) if e["healthy_instances"] > 0
    }
