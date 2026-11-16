"""Pydantic v2 schemas for per-reseller routing rules."""

import re
from typing import Dict, List

from pydantic import BaseModel, ConfigDict, field_validator

from app.services.credentials.routing_presets import PRESET_KEYS

# Hostname (domain) validation: labels of a-z0-9-, dot-separated, no scheme/path.
HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$"
)


def _normalize_domains(values: List[str]) -> List[str]:
    seen: set = set()
    out: List[str] = []
    for v in values or []:
        d = (v or "").strip().lower()
        if not d:
            continue
        if not HOSTNAME_RE.match(d):
            raise ValueError(f"Invalid domain: '{v}'. Use a bare hostname like example.com")
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


class RoutingRulesUpdate(BaseModel):
    is_enabled: bool
    ban_domains: List[str] = []
    allow_domains: List[str] = []
    presets: Dict[str, bool] = {}

    @field_validator("ban_domains", "allow_domains")
    @classmethod
    def _validate_domains(cls, v: List[str]) -> List[str]:
        return _normalize_domains(v)

    @field_validator("presets")
    @classmethod
    def _validate_presets(cls, v: Dict[str, bool]) -> Dict[str, bool]:
        unknown = set(v) - set(PRESET_KEYS)
        if unknown:
            raise ValueError(
                f"Unknown preset key(s): {', '.join(sorted(unknown))}. "
                f"Valid: {', '.join(sorted(PRESET_KEYS))}"
            )
        return v


class RoutingRulesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    is_enabled: bool
    ban_domains: List[str] = []
    allow_domains: List[str] = []
    presets: Dict[str, bool] = {}
