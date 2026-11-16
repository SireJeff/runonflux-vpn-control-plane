"""Dynamic Traefik router provisioning for onboarded TLDs.

Traefik's *static* config (docker labels in docker-compose.prod.yml) routes only
a fixed set of hostnames — ``api.``/``admin.``/``panel.``/``flower.``. A newly
onboarded subscription/dashboard/admin_panel TLD therefore ends up with DNS
pointing at the server but **no Traefik router and no TLS certificate**, so its
URLs 404 / cert-fail even though the DB assignment "sticks". That is the
infrastructure half of the 2026-08-19 "reassignment sticks but the domain
doesn't work" audit.

This module writes a per-TLD Traefik **file-provider** config so activation
provisions a working HTTPS host end-to-end. HTTP-01 ACME succeeds because the
A-record already resolves to this server by the time the router appears. The
file provider is enabled in compose via
``--providers.file.directory=${TRAEFIK_DYNAMIC_DIR}`` + ``--providers.file.watch``,
with the directory shared between the worker-api (writer) and traefik (reader)
via the ``traefik_dynamic`` volume.

Only HTTP purposes get a router:
  - subscription  -> worker-api  (serves /api/v1/user/sub/<token>)
  - dashboard     -> admin-dashboard
  - admin_panel   -> admin-dashboard
``fdm`` domains are VPN endpoints on Flux instances, not served by this proxy,
so they are skipped.

Fail-open by design: if the dynamic directory is not configured/mounted (dev,
tests, or a host without the volume) every operation is a logged no-op — never
an exception — so a missing proxy layer can never block a TLD activation.
"""

import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

# purpose -> internal backend URL the generated router forwards to. Overridable
# by env for non-standard topologies; defaults match docker-compose.prod.yml
# service names + ports.
_BACKEND_URLS = {
    "subscription": os.getenv("TRAEFIK_SUBSCRIPTION_BACKEND", "http://worker-api:8080"),
    "dashboard": os.getenv("TRAEFIK_DASHBOARD_BACKEND", "http://admin-dashboard:3000"),
    "admin_panel": os.getenv(
        "TRAEFIK_ADMIN_PANEL_BACKEND", "http://admin-dashboard:3000"
    ),
}

# Purposes that are served over HTTP by this proxy (get a dynamic router).
HTTP_PURPOSES = frozenset(_BACKEND_URLS.keys())

_CERT_RESOLVER = os.getenv("TRAEFIK_CERT_RESOLVER", "letsencrypt")
_SECURE_ENTRYPOINT = os.getenv("TRAEFIK_SECURE_ENTRYPOINT", "websecure")


def _dynamic_dir() -> Optional[str]:
    """Directory Traefik's file provider watches (shared volume). Empty/unset
    disables dynamic routing (fail-open no-op)."""
    d = os.getenv("TRAEFIK_DYNAMIC_DIR", "").strip()
    return d or None


def _slug(domain: str) -> str:
    """Stable, filesystem/Traefik-safe router+service name for a domain."""
    base = re.sub(r"[^a-z0-9]+", "-", domain.lower()).strip("-")
    return f"tld-{base}"


def _config_path(dynamic_dir: str, domain: str) -> str:
    return os.path.join(dynamic_dir, f"{_slug(domain)}.yml")


def render_router_config(domain: str, purpose: str) -> str:
    """Render the Traefik file-provider YAML for one TLD's HTTPS router.

    Pure/deterministic (no PyYAML dependency) so it is trivially unit-testable
    and diffable. Raises KeyError for a non-HTTP purpose — callers gate on
    HTTP_PURPOSES first.
    """
    backend = _BACKEND_URLS[purpose]
    name = _slug(domain)
    return (
        f"# Managed by FluxVPN TldRouterManager — {domain} ({purpose}).\n"
        f"# Auto-generated; do not edit by hand. Removed on deactivate/delete.\n"
        "http:\n"
        "  routers:\n"
        f"    {name}:\n"
        f'      rule: "Host(`{domain}`)"\n'
        "      entryPoints:\n"
        f"        - {_SECURE_ENTRYPOINT}\n"
        f"      service: {name}\n"
        "      tls:\n"
        f"        certResolver: {_CERT_RESOLVER}\n"
        "  services:\n"
        f"    {name}:\n"
        "      loadBalancer:\n"
        "        servers:\n"
        f'          - url: "{backend}"\n'
    )


def register_route(domain: str, purpose: str) -> bool:
    """Provision (or refresh) the dynamic Traefik router for ``domain``.

    Returns True if a config file was written, False if skipped (non-HTTP
    purpose, dynamic routing disabled, or a write error — all logged, never
    raised). Idempotent: re-writing an identical config is harmless and Traefik
    hot-reloads via ``--providers.file.watch``.
    """
    if purpose not in HTTP_PURPOSES:
        return False  # fdm (and anything else) is not proxy-served
    dynamic_dir = _dynamic_dir()
    if not dynamic_dir or not os.path.isdir(dynamic_dir):
        logger.info(
            "Traefik dynamic dir %r unavailable; skipping proxy route for %s "
            "(the domain will not be HTTPS-served until the file provider is "
            "mounted)",
            dynamic_dir,
            domain,
        )
        return False
    path = _config_path(dynamic_dir, domain)
    tmp = f"{path}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(render_router_config(domain, purpose))
        os.replace(tmp, path)  # atomic swap so the watcher never sees a partial
        logger.info("Registered Traefik route for %s (%s) -> %s", domain, purpose, path)
        return True
    except OSError as e:
        logger.error("Failed to write Traefik route for %s: %s", domain, e)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return False


def deregister_route(domain: str) -> bool:
    """Remove the dynamic Traefik router for ``domain`` (deactivate/delete).

    Returns True if a file was removed, False if there was nothing to remove or
    dynamic routing is disabled. Never raises.
    """
    dynamic_dir = _dynamic_dir()
    if not dynamic_dir or not os.path.isdir(dynamic_dir):
        return False
    path = _config_path(dynamic_dir, domain)
    try:
        if os.path.exists(path):
            os.remove(path)
            logger.info("Deregistered Traefik route for %s (%s)", domain, path)
            return True
        return False
    except OSError as e:
        logger.error("Failed to remove Traefik route for %s: %s", domain, e)
        return False
