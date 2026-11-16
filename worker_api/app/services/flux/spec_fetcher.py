"""FluxSpecFetcher: read a Flux app's declared specification (Phase 3.2).

GET /apps/appspecifications/{app} is PUBLIC (no auth). The snapshot lets FDM
size domain pools to the app's declared instance count and surface an
expected-vs-actual gap (Goal 1). Uses FluxCloudClient's bare `_request` (NOT
the resilience-wrapped `_request_with_resilience`) so a transient Flux error
degrades to None immediately rather than blocking the sync cycle with retry
backoff -- the snapshot refreshes on the next sync cycle, and the last known
expected_instances is retained on FluxAppRegistration until a successful fetch.
"""
import logging
from typing import Any, Dict, Optional

from app.services.flux.client import FluxCloudClient

logger = logging.getLogger(__name__)


class FluxSpecFetcher:
    """Fetch + parse a Flux app's appspecifications into a typed dict."""

    def __init__(self, client: FluxCloudClient):
        self._client = client

    async def fetch_spec(self, app_name: str) -> Optional[Dict[str, Any]]:
        """Return {'instances', 'components', 'geolocation', 'raw'} or None.

        - instances: declared instance count (int) or None if absent.
        - components: list of {name, ram, cpu, hdd, ports} from compose[].
        - geolocation: the raw geolocation list.
        - raw: the unwrapped payload. DIAGNOSTICS ONLY -- never persist or log;
          carries live auth tokens (see SECURITY note at the return statement).

        Returns None on any fetch/parse error (never raises to the caller).
        """
        try:
            response = await self._client._request(
                "GET",
                f"/apps/appspecifications/{app_name}",
                authenticated=False,
                redact=True,
            )
        except Exception as e:  # noqa: BLE001 -- degrade, never raise
            logger.warning(f"FluxSpecFetcher: fetch failed for {app_name}: {e}")
            return None

        payload = response.get("data") if isinstance(response, dict) else response
        if not isinstance(payload, dict):
            logger.warning(f"FluxSpecFetcher: unexpected payload shape for {app_name}")
            return None

        try:
            instances = payload.get("instances")
            if instances is not None:
                instances = int(instances)
            components = [
                {
                    "name": c.get("name"),
                    "ram": c.get("ram"),
                    "cpu": c.get("cpu"),
                    "hdd": c.get("hdd"),
                    "ports": c.get("ports") or [],
                }
                for c in (payload.get("compose") or [])
            ]
            # SECURITY: `raw` is the full unwrapped payload; its compose[].environmentParameters
            # carry live FLUXVPN_AUTH_TOKEN JWTs (10-yr expiry) in the PUBLIC endpoint response.
            # Persist/log ONLY the normalized instances/components/geolocation above (components
            # already excludes environmentParameters). Never store `raw` downstream (Task 3.3).
            return {
                "instances": instances,
                "components": components,
                "geolocation": payload.get("geolocation") or [],
                "raw": payload,
            }
        except Exception as e:  # noqa: BLE001
            logger.warning(f"FluxSpecFetcher: parse failed for {app_name}: {e}")
            return None
