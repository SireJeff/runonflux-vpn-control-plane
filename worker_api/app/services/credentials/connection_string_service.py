"""
FluxVPN Connection String Service
Generates protocol-specific connection string URLs using FDM DNS domains.
Maps AdminUser credentials to macro-region FDM domains across all countries.
"""

import base64
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.core.constants import MACRO_REGIONS, country_flag, get_country_name
from app.models.admin_users import AdminUser
from app.models.fdm import FdmDeployment, FdmDomain
from app.models.flux_app_registration import FluxAppRegistration
from app.models.ip_management import ProtocolInstance
from app.models.user_credentials_v2 import UserCredentialV2
from app.services.credentials.routing_presets import build_singbox_routing
from app.services.routing.routing_rules_service import RoutingRulesService

logger = logging.getLogger(__name__)

# Protocol iteration order (no hardcoded ports -- port comes from database)
PROTOCOL_ORDER = ["ssh", "ss", "vless", "trojan", "outline", "http_proxy"]

# Alternate names used in older deployments
PROTOCOL_ALIASES = {
    "ss": ["shadowsocks"],
    "http_proxy": ["http-proxy"],
}

# Display names for connection string fragments
PROTOCOL_DISPLAY_NAMES = {
    "ssh": "SSH",
    "ss": "SS",
    "vless": "VLESS",
    "trojan": "Trojan",
    "outline": "Outline",
    "http_proxy": "HTTP",
}

# Method used by deployment token service for SS/Outline containers
SS_DEPLOYMENT_METHOD = "chacha20-ietf-poly1305"


class ConnectionStringService:
    """Generates protocol-specific connection strings using FDM DNS domains."""

    def __init__(self, db: Session):
        self.db = db

    def generate_connection_strings(
        self, user: AdminUser, macro_region: str, *, increment_load: bool = True
    ) -> Dict[str, Dict[str, dict]]:
        """Generate connection strings for ALL countries in user's macro region.

        Returns: {country_code: {protocol: {primary: str, fallbacks: list[str]}}}
        """
        countries = MACRO_REGIONS[macro_region]["countries"]
        creds = (
            self.db.query(UserCredentialV2)
            .filter(UserCredentialV2.user_id == user.id)
            .all()
        )
        cred_map = {c.protocol: c.credential_data for c in creds}

        # Phase 4: resolve the admin's effective fdm TLD once per generate
        # call. None = no active fdm TLD / legacy -> unfiltered (safe).
        effective_tld_id = self._resolve_fdm_effective(admin_id=user.admin_id)

        # On refresh (increment_load=True), decrement old domain and rotate
        # to a different IP so the user gets genuinely new connections.
        previous_domain_name = None
        if increment_load and user.assigned_domain_id:
            prev_domain = (
                self.db.query(FdmDomain)
                .filter(FdmDomain.id == user.assigned_domain_id)
                .first()
            )
            if prev_domain:
                previous_domain_name = prev_domain.domain_name
                from app.services.fdm.fdm_domain_service import FdmDomainService

                FdmDomainService(self.db).decrement_domain_load(prev_domain)

        result = {}
        for country in countries:
            country_connections = {}
            for protocol in PROTOCOL_ORDER:
                if protocol not in cred_map:
                    continue
                domains = self._get_domains_for_country(
                    country,
                    protocol,
                    effective_tld_id=effective_tld_id,
                )
                if not domains:
                    continue

                # Rotate away from previous primary if possible
                primary = domains[0]
                if (
                    previous_domain_name
                    and len(domains) > 1
                    and primary[0] == previous_domain_name
                ):
                    primary = domains[1]

                primary_url = self._format_connection_string(
                    user,
                    protocol,
                    cred_map[protocol],
                    primary[0],
                    primary[1],
                    country,
                )
                if not primary_url:
                    continue

                # Fallbacks: all OTHER domains (IP-deduplicated already)
                fallback_urls = []
                for domain, port, _ in domains:
                    if domain == primary[0]:
                        continue
                    url = self._format_connection_string(
                        user,
                        protocol,
                        cred_map[protocol],
                        domain,
                        port,
                        country,
                    )
                    if url:
                        fallback_urls.append(url)

                country_connections[protocol] = {
                    "primary": primary_url,
                    "fallbacks": fallback_urls,
                }

                if increment_load:
                    self._increment_domain_load(primary[0])

                    primary_domain = (
                        self.db.query(FdmDomain)
                        .filter(FdmDomain.domain_name == primary[0])
                        .first()
                    )
                    if primary_domain:
                        user.assigned_domain_id = primary_domain.id
                        self.db.commit()

            if country_connections:
                result[country] = country_connections

        return result

    def generate_all_region_connections(
        self, user: AdminUser, *, increment_load: bool = True
    ) -> Dict[str, Dict[str, dict]]:
        """Generate connection strings across ALL of the user's active macro-regions.

        Returns {country_code: {protocol: {primary: str, fallbacks: list[str]}}}
        merged across every region the user holds whose status is "active".
        Macro-regions own disjoint country sets, so per-region dicts merge
        without key collisions. Suspended (unpaid) non-primary regions are
        excluded so a suspension actually removes access.
        """
        from app.models.user_regions import UserRegion

        regions = (
            self.db.query(UserRegion)
            .filter(
                UserRegion.user_id == user.id,
                UserRegion.status == "active",
            )
            .all()
        )
        if not regions:
            return {}

        merged: Dict[str, Dict[str, dict]] = {}
        for region in regions:
            merged.update(
                self.generate_connection_strings(
                    user, region.macro_region, increment_load=increment_load
                )
            )
        return merged

    def generate_all_region_singbox_outbounds(self, user: AdminUser) -> list[dict]:
        """sing-box outbounds across ALL of the user's active macro-regions.

        The singbox analogue of generate_all_region_connections: one call per
        active macro-region, concatenated. Macro-regions own disjoint country
        sets so outbounds never collide. Suspended (unpaid) non-primary regions
        are excluded so a suspension actually removes access.
        """
        from app.models.user_regions import UserRegion

        regions = (
            self.db.query(UserRegion)
            .filter(
                UserRegion.user_id == user.id,
                UserRegion.status == "active",
            )
            .all()
        )
        outbounds: list[dict] = []
        seen_macros: set = set()
        for region in regions:
            if region.macro_region in seen_macros:
                continue
            seen_macros.add(region.macro_region)
            outbounds.extend(self.generate_singbox_outbounds(user, region.macro_region))
        return outbounds

    def generate_singbox_full_config(self, user: "AdminUser"):
        """Return (is_full, payload) for the sing-box subscription.

        No effective rules → (False, bare_outbounds_list) — unchanged behavior.
        Rules present → (True, {"outbounds": [...], "route": {...}}).
        """
        outbounds = self.generate_all_region_singbox_outbounds(user)
        rules = RoutingRulesService(self.db).get_effective_rules(user.admin_id)
        proxy_tags = [o["tag"] for o in outbounds if "tag" in o]
        extra, route = build_singbox_routing(rules, proxy_tags)

        # Info node is display-only: built AFTER proxy_tags/route so it can
        # never enter a selector or route rule. Prepended so clients list it first.
        from app.services.credentials.info_node import (
            format_info_node_label,
            info_singbox_outbound,
        )

        label = format_info_node_label(
            getattr(user, "traffic_limit_bytes", None),
            getattr(user, "traffic_used_bytes", None),
            getattr(user, "expires_at", None),
            getattr(user, "language", "fa") or "fa",
        )
        prefix = [info_singbox_outbound(label)] if label else []

        if route is None:
            return False, prefix + outbounds
        return True, {"outbounds": prefix + outbounds + extra, "route": route}

    def generate_telegram_proxy_links(self, user: AdminUser) -> Dict[str, str]:
        """Generate tg://socks deep links for Telegram proxy, one per country.

        Returns {country_code: "tg://socks?server=...&port=...&user=...&pass=..."}
        """
        # Phase 4: resolve the admin's effective fdm TLD once.
        effective_tld_id = self._resolve_fdm_effective(admin_id=user.admin_id)

        from app.models.user_regions import UserRegion

        user_region = (
            self.db.query(UserRegion).filter(UserRegion.user_id == user.id).first()
        )
        if not user_region:
            return {}

        countries = MACRO_REGIONS[user_region.macro_region]["countries"]

        creds = (
            self.db.query(UserCredentialV2)
            .filter(UserCredentialV2.user_id == user.id)
            .filter(UserCredentialV2.protocol.in_(["ss", "shadowsocks"]))
            .first()
        )
        if not creds:
            return {}

        cred = creds.credential_data
        socks_user = user.username
        socks_pass = cred.get("password", "")

        result = {}
        for country in countries:
            clauses = [
                func.upper(FdmDeployment.region) == country.upper(),
                FdmDeployment.is_active == True,
                FdmDomain.health_status == "healthy",
                ProtocolInstance.is_active == True,
            ]
            if effective_tld_id is not None:
                clauses.append(
                    (FdmDomain.tld_id == effective_tld_id)
                    | (FdmDomain.tld_id.is_(None))
                )
            row = (
                self.db.query(FdmDomain, FdmDeployment)
                .join(FdmDeployment, FdmDomain.deployment_id == FdmDeployment.id)
                .join(
                    ProtocolInstance,
                    ProtocolInstance.ip_address == FdmDomain.current_ip,
                )
                .filter(*clauses)
                .order_by(FdmDomain.assigned_users_count.asc())
                .first()
            )
            if not row:
                continue

            domain = row.FdmDomain.domain_name

            # Resolve SOCKS5 port from FluxAppRegistration
            app_reg = (
                self.db.query(FluxAppRegistration)
                .filter(FluxAppRegistration.app_name == row.FdmDeployment.flux_app_name)
                .first()
            )
            socks_port = (
                app_reg.protocol_ports.get("socks5")
                if app_reg and app_reg.protocol_ports
                else None
            )
            port = socks_port or row.FdmDeployment.socks5_port
            if not port:
                continue

            link = (
                f"tg://socks?server={domain}&port={port}"
                f"&user={quote(socks_user)}&pass={quote(socks_pass)}"
            )
            result[country] = link

        return result

    def _resolve_fdm_effective(self, admin_id: int) -> int | None:
        """Resolve the admin's effective fdm TLD id for connection-string scoping.

        Returns None on NoActiveTld or any error so the caller falls back to
        the legacy unfiltered query (gradual rollout; never breaks users).
        Lazy import avoids circular imports (selection.py -> models -> ...).
        """
        try:
            from app.services.tlds.selection import NoActiveTld, TldSelectionService

            tld = TldSelectionService(self.db).resolve_effective(admin_id, "fdm")
            return tld.id
        except NoActiveTld:
            logger.warning(
                f"No active fdm TLD for admin {admin_id}; connection strings unfiltered"
            )
            return None
        except Exception as exc:
            logger.warning(
                f"fdm effective-TLD resolution failed for admin {admin_id}: {exc}; "
                f"connection strings unfiltered"
            )
            return None

    def _get_domains_for_country(
        self,
        country: str,
        protocol: str,
        effective_tld_id: int | None = None,
    ) -> List[tuple]:
        """
        Get protocol-agnostic domains for a country, ordered by load.

        Returns one domain per unique IP (deduplicated), ensuring fallbacks
        point to genuinely distinct servers. Port is resolved from
        FluxAppRegistration.protocol_ports[protocol].

        Args:
            country: ISO country code (e.g., 'CH')
            protocol: Protocol name (e.g., 'ssh', 'vless')
            effective_tld_id: Phase 4 — restrict to the admin's effective fdm
                TLD. When set, domains are filtered to
                ``(tld_id == effective_tld_id) OR (tld_id IS NULL)`` so
                backfilled rows match and legacy/4b-transition NULL rows still
                resolve under single-active. None = legacy unfiltered.

        Returns:
            List of (domain_name, port, deployment_id) tuples, one per unique IP
        """
        country_upper = country.upper()

        # Query all healthy domains for this country with their IPs.
        # JOIN ProtocolInstance to exclude domains whose current_ip is not
        # in any active protocol instance (stale-IP defense at SQL level).
        clauses = [
            func.upper(FdmDeployment.region) == country_upper,
            FdmDeployment.is_active == True,
            FdmDomain.health_status == "healthy",
            FdmDomain.current_ip.isnot(None),
            ProtocolInstance.is_active == True,
        ]
        # Phase 4: scope to the admin's effective fdm TLD. NULL tld_id rows
        # (legacy + 4b-transition) are included so single-active stays correct.
        if effective_tld_id is not None:
            clauses.append(
                (FdmDomain.tld_id == effective_tld_id) | (FdmDomain.tld_id.is_(None))
            )

        rows = (
            self.db.query(
                FdmDomain.domain_name,
                FdmDomain.current_ip,
                FdmDeployment.id,
                FdmDeployment.flux_app_name,
                FdmDomain.assigned_users_count,
            )
            .join(FdmDeployment, FdmDomain.deployment_id == FdmDeployment.id)
            .join(ProtocolInstance, ProtocolInstance.ip_address == FdmDomain.current_ip)
            .filter(*clauses)
            .order_by(FdmDomain.assigned_users_count.asc())
            .all()
        )

        if not rows:
            return []

        # Resolve port from FluxAppRegistration.protocol_ports
        app_cache: Dict[str, Optional[dict]] = {}
        seen_ips = set()
        result = []

        for domain_name, current_ip, deployment_id, flux_app_name, load in rows:
            # Deduplicate by IP — one domain per server
            ip_str = str(current_ip)
            if ip_str in seen_ips:
                continue
            seen_ips.add(ip_str)

            if flux_app_name not in app_cache:
                app_reg = (
                    self.db.query(FluxAppRegistration)
                    .filter(FluxAppRegistration.app_name == flux_app_name)
                    .first()
                )
                app_cache[flux_app_name] = app_reg.protocol_ports if app_reg else None

            ports = app_cache[flux_app_name]
            if not ports:
                continue

            port = ports.get(protocol)
            if not port:
                continue

            result.append((domain_name, port, deployment_id))

        return result

    def _format_connection_string(
        self,
        user: AdminUser,
        protocol: str,
        cred: dict,
        domain: str,
        port: int,
        country_code: str,
    ) -> Optional[str]:
        """Format a connection string with country flag emoji prefix in fragment."""
        display_label = user.display_name if user.display_name else user.username
        proto_display = PROTOCOL_DISPLAY_NAMES.get(protocol, protocol.upper())
        flag = country_flag(country_code)

        # Fragment: CH-DisplayLabel-SSH (URL-encoded for client compatibility)
        fragment = quote(f"{flag}-{display_label}-{proto_display}", safe="-")

        if protocol == "ssh":
            # Standard ssh://userinfo@host:port form (RFC 3986).
            # URL-encode user/pass so special chars (&, #, ?, =, space) don't
            # break the URI. Parses cleanly with urllib.parse.urlparse.
            ssh_user = quote(str(cred["username"]), safe="")
            ssh_pw = quote(str(cred["password"]), safe="")
            return f"ssh://{ssh_user}:{ssh_pw}@{domain}:{port}#{fragment}"

        elif protocol == "ss":
            password = cred["password"]
            method = SS_DEPLOYMENT_METHOD
            raw = f"{method}:{password}"
            encoded = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
            return f"ss://{encoded}@{domain}:{port}#{fragment}"

        elif protocol == "vless":
            return (
                f"vless://{cred['uuid']}@{domain}:{port}"
                f"?encryption=none&security=none&type=ws"
                f"&host={domain}&path=/vless"
                f"&packetEncoding=xudp"
                f"#{fragment}"
            )

        elif protocol == "trojan":
            return (
                f"trojan://{cred['password']}@{domain}:{port}"
                f"?security=tls&sni={domain}&type=tcp"
                f"&allowInsecure=true#{fragment}"
            )

        elif protocol == "outline":
            password = cred["password"]
            method = SS_DEPLOYMENT_METHOD
            raw = f"{method}:{password}"
            encoded = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
            return f"ss://{encoded}@{domain}:{port}#{fragment}"

        elif protocol == "http_proxy":
            return (
                f"http://{cred['username']}:{cred['password']}@{domain}:{port}"
                f"#{fragment}"
            )

        return None

    def generate_singbox_outbounds(
        self, user: AdminUser, macro_region: str
    ) -> list[dict]:
        """Generate sing-box outbound JSON configs for ALL countries in macro region.

        Unlike URI share links, the JSON outbound format supports all protocols
        including SSH and HTTP proxy — no URI scheme standardization needed.
        """
        countries = MACRO_REGIONS[macro_region]["countries"]
        creds = (
            self.db.query(UserCredentialV2)
            .filter(UserCredentialV2.user_id == user.id)
            .all()
        )
        cred_map = {c.protocol: c.credential_data for c in creds}
        effective_tld_id = self._resolve_fdm_effective(admin_id=user.admin_id)

        outbounds = []
        for country in countries:
            for protocol in PROTOCOL_ORDER:
                if protocol not in cred_map:
                    continue
                domains = self._get_domains_for_country(
                    country,
                    protocol,
                    effective_tld_id=effective_tld_id,
                )
                if not domains:
                    continue
                domain, port, _ = domains[0]
                outbound = self._format_singbox_outbound(
                    user, protocol, cred_map[protocol], domain, port, country
                )
                if outbound:
                    outbounds.append(outbound)

        return outbounds

    def _format_singbox_outbound(
        self,
        user: AdminUser,
        protocol: str,
        cred: dict,
        domain: str,
        port: int,
        country_code: str,
    ) -> Optional[dict]:
        """Build a sing-box outbound JSON object for the given protocol."""
        display_label = user.display_name if user.display_name else user.username
        proto_display = PROTOCOL_DISPLAY_NAMES.get(protocol, protocol.upper())
        flag = country_flag(country_code)
        tag = f"{flag} {display_label} {proto_display}"

        if protocol == "ssh":
            return {
                "type": "ssh",
                "tag": tag,
                "server": domain,
                "server_port": port,
                "user": cred["username"],
                "password": cred["password"],
            }

        elif protocol == "ss":
            return {
                "type": "shadowsocks",
                "tag": tag,
                "server": domain,
                "server_port": port,
                "method": SS_DEPLOYMENT_METHOD,
                "password": cred["password"],
            }

        elif protocol == "vless":
            return {
                "type": "vless",
                "tag": tag,
                "server": domain,
                "server_port": port,
                "uuid": cred["uuid"],
                "transport": {
                    "type": "ws",
                    "path": "/vless",
                    "headers": {"Host": domain},
                },
                "packet_encoding": "xudp",
            }

        elif protocol == "trojan":
            return {
                "type": "trojan",
                "tag": tag,
                "server": domain,
                "server_port": port,
                "password": cred["password"],
                "tls": {
                    "enabled": True,
                    "server_name": domain,
                    "insecure": True,
                },
            }

        elif protocol == "outline":
            return {
                "type": "shadowsocks",
                "tag": tag,
                "server": domain,
                "server_port": port,
                "method": SS_DEPLOYMENT_METHOD,
                "password": cred["password"],
            }

        elif protocol == "http_proxy":
            return {
                "type": "http",
                "tag": tag,
                "server": domain,
                "server_port": port,
                "username": cred["username"],
                "password": cred["password"],
            }

        return None

    def _increment_domain_load(self, domain_name: str) -> None:
        """Atomic increment of assigned_users_count for a domain."""
        stmt = (
            update(FdmDomain)
            .where(FdmDomain.domain_name == domain_name)
            .values(
                assigned_users_count=FdmDomain.assigned_users_count + 1,
                updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        self.db.execute(stmt)
        self.db.commit()

    def decrement_domain_on_user_change(self, user_id: int) -> None:
        """
        Decrement domain load when user is deactivated, deleted, or changes region.
        Looks up user's assigned_domain_id and decrements that domain.
        """
        user = self.db.query(AdminUser).filter(AdminUser.id == user_id).first()
        if not user or not user.assigned_domain_id:
            return

        domain = (
            self.db.query(FdmDomain)
            .filter(FdmDomain.id == user.assigned_domain_id)
            .first()
        )
        if not domain:
            return

        from app.services.fdm.fdm_domain_service import FdmDomainService

        domain_service = FdmDomainService(self.db)
        domain_service.decrement_domain_load(domain)

        user.assigned_domain_id = None
        self.db.commit()

    def generate_country_breakdown(self, user, macro_region: str) -> dict:
        """Return connections dict keyed by country code.

        Thin wrapper around generate_connection_strings that documents the
        intent (display only -- no load incrementing). Used by both the bot's
        per-country view and the website's country grid.
        """
        return (
            self.generate_connection_strings(
                user,
                macro_region,
                increment_load=False,
            )
            or {}
        )


def parse_ssh_fields(ssh_uri: str) -> dict:
    """Parse an ssh:// URI into its component fields.

    Returns dict with keys: host, port, username, password.
    Useful for PuTTY/Termius/CLI users who need each field separately
    to fill form inputs.

    Raises ValueError if URI is not an ssh:// scheme.
    """
    from urllib.parse import unquote, urlparse

    if not ssh_uri.startswith("ssh://"):
        raise ValueError(f"Not an ssh:// URI: {ssh_uri[:30]}...")

    parsed = urlparse(ssh_uri)
    return {
        "host": parsed.hostname or "",
        "port": parsed.port or 22,
        "username": unquote(parsed.username) if parsed.username else "",
        "password": unquote(parsed.password) if parsed.password else "",
    }
