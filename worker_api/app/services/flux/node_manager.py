"""
FluxCloud Node Manager
Manages deployment and lifecycle of VPN protocol instances on FluxCloud
"""

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, cast

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Protocol, ProtocolInstance
from app.services.auth.deployment_tokens import DeploymentTokenService
from app.services.flux.client import FluxCloudAPIException, FluxCloudClient
from app.services.flux.hybrid_client import FluxHybridClient

logger = logging.getLogger(__name__)

# =============================================================================
# HELPER CLASSES FOR FLUXCLOUD COMPLIANCE
# =============================================================================

from dataclasses import dataclass


class PortValidator:
    """
    Validates exposed ports against FluxCloud restrictions.

    FluxCloud restricts certain ports and port ranges:
    - Ranges: 16100-16299, 26100-26299, 30000-30099
    - Specific: 22, 23, 25, 123, 161, 512, 513, 3388, 3889, 4444,
    -           5800, 5900, 5901, 8384, 27017
    """

    RESTRICTED_PORTS = {
        22,
        23,
        25,
        123,
        161,
        512,
        513,
        3388,
        3889,
        4444,
        5800,
        5900,
        5901,
        8384,
        27017,
    }

    RESTRICTED_RANGES = [(16100, 16299), (26100, 26299), (30000, 30099)]

    @classmethod
    def is_port_restricted(cls, port: int) -> bool:
        """Check if a port is restricted by FluxCloud."""
        if port in cls.RESTRICTED_PORTS:
            return True
        for start, end in cls.RESTRICTED_RANGES:
            if start <= port <= end:
                return True
        return False

    @classmethod
    def validate_exposed_ports(cls, ports: List[int]) -> bool:
        """Validate that all ports are outside restricted ranges."""
        return all(not cls.is_port_restricted(p) for p in ports)


@dataclass
class ResourcePreset:
    """
    Resource allocation presets for different environments.

    Testing mode: Minimal resources for cost-effective development
    Production mode: Full resources for production performance
    """

    mode: str  # "testing" or "production"

    # Testing presets (minimal cost, 10x less resources)
    testing_cpu: float = 0.1
    testing_ram: int = 100
    testing_hdd: int = 1

    # Production presets (full performance)
    production_cpu: float = 1.0
    production_ram: int = 512
    production_hdd: int = 2

    # Per-protocol overrides for production
    production_ram_shadowsocks: int = 1024  # 1 GB
    production_ram_vless: int = 1024
    production_ram_trojan: int = 1024
    production_ram_outline: int = 1024
    production_hdd_shadowsocks: int = 5  # 5 GB
    production_hdd_vless: int = 5
    production_hdd_trojan: int = 5
    production_hdd_outline: int = 5

    def get_cpu(self, protocol: str) -> float:
        """Get CPU allocation for a protocol."""
        base = self.testing_cpu if self.mode == "testing" else self.production_cpu
        # Production uses slightly more CPU for some protocols
        if self.mode == "production" and protocol in [
            "shadowsocks",
            "vless",
            "trojan",
            "outline",
        ]:
            return 1.0
        return base

    def get_ram(self, protocol: str) -> int:
        """Get RAM allocation for a protocol."""
        if self.mode == "testing":
            return self.testing_ram

        # Production with per-protocol overrides
        overrides = {
            "shadowsocks": self.production_ram_shadowsocks,
            "vless": self.production_ram_vless,
            "trojan": self.production_ram_trojan,
            "outline": self.production_ram_outline,
        }
        return overrides.get(protocol, self.production_ram)

    def get_hdd(self, protocol: str) -> int:
        """Get HDD allocation for a protocol."""
        if self.mode == "testing":
            return 1 if protocol in ["ssh", "httpproxy"] else 2

        # Production with per-protocol overrides
        overrides = {
            "shadowsocks": self.production_hdd_shadowsocks,
            "vless": self.production_hdd_vless,
            "trojan": self.production_hdd_trojan,
            "outline": self.production_hdd_outline,
        }
        return overrides.get(protocol, 2)  # Default 2GB for production


class GeolocationBuilder:
    """
    Builds FluxCloud geolocation arrays with backup regions.

    FluxCloud API format: ["acNA_US_Missouri", "acNA_US_North Carolina", "acEU_ES"]
    """

    # Regional groups for backup regions
    REGION_GROUPS = {
        "US": ["acNA_US_Missouri", "acNA_US_North Carolina", "acNA_US_California"],
        "EU": ["acEU_ES", "acEU_DE", "acEU_NL", "acEU_FR"],
        "ASIA": ["acAS_SG", "acAS_JP", "acAS_KR"],
    }

    # Country code to region group mapping
    COUNTRY_TO_GROUP = {
        "US": "US",
        "USE": "US",
        "USW": "US",
        "USC": "US",
        "NL": "EU",
        "DE": "EU",
        "ES": "EU",
        "FR": "EU",
        "SG": "ASIA",
        "JP": "ASIA",
        "KR": "ASIA",
    }

    def __init__(self, regions: Optional[List[str]] = None):
        """
        Initialize with available regions.

        Args:
            regions: List of FluxCloud region codes (e.g., ["acNA_US_Missouri"])
        """
        self.available_regions = regions or [
            region for group in self.REGION_GROUPS.values() for region in group
        ]

    def build_for_country(
        self, country_code: str, include_backup: bool = True
    ) -> List[str]:
        """
        Build geolocation array for a country with optional backup regions.

        Args:
            country_code: Two-letter country code (e.g., "US", "NL")
            include_backup: Whether to include backup regions

        Returns:
            List of FluxCloud region codes in format: ["acNA_US_Missouri", ...]
        """
        # Map country code to FluxCloud region format
        # Must match all country codes in COUNTRY_TO_GROUP
        country_to_flux = {
            "US": "acNA_US_Missouri",
            "USE": "acNA_US_North Carolina",
            "USW": "acNA_US_California",
            "USC": "acNA_US_Chicago",
            "NL": "acEU_NL",  # Netherlands
            "DE": "acEU_DE",  # Germany
            "ES": "acEU_ES",  # Spain
            "FR": "acEU_FR",  # France
            "SG": "acAS_SG",  # Singapore
            "JP": "acAS_JP",  # Japan
            "KR": "acAS_KR",  # South Korea
        }

        # Get primary region
        primary_region = country_to_flux.get(country_code)

        if not primary_region:
            raise ValueError(f"Unknown country code: {country_code}")

        if not include_backup:
            return [primary_region]

        # Get backup regions from same group
        group = self.COUNTRY_TO_GROUP.get(country_code, "")
        backup_regions = self.REGION_GROUPS.get(group, [])[:2]  # Get up to 2 backups

        # Filter out the primary region from backups
        geolocation = [primary_region] + [
            r for r in backup_regions if r != primary_region
        ]

        return geolocation


class NodeDeploymentError(Exception):
    """Exception raised for node deployment errors"""

    pass


class FluxNodeManager:
    """
    Manages VPN protocol node deployments on FluxCloud

    Supports two deployment modes:
    1. Single-protocol apps (legacy): One protocol per Flux app
    2. Multi-protocol apps (new): All 6 protocols in one Flux app

    Default: Multi-protocol mode for cost efficiency
    """

    # Geographic distribution for deployments
    GEO_DISTRIBUTION = {
        # US Regions for 3-instance test deployment
        "USE": {"name": "United States", "city": "New York", "region": "US-East"},
        "USW": {"name": "United States", "city": "Los Angeles", "region": "US-West"},
        "USC": {"name": "United States", "city": "Chicago", "region": "US-Central"},
        # Original countries (kept for future use)
        "NL": {"name": "Netherlands", "city": "Amsterdam"},
        "US": {"name": "United States", "city": "New York"},
        "DE": {"name": "Germany", "city": "Frankfurt"},
        "SG": {"name": "Singapore", "city": "Singapore"},
        "JP": {"name": "Japan", "city": "Tokyo"},
    }

    # Protocol specifications with FluxCloud-compliant ports
    # FluxCloud exposed port requirements:
    #   - Must be 1024-65535
    #   - Restricted: 16100-16299, 26100-26299, 30000-30099, 22, 23, 25, 123, 161, 512, 513, 3388, 3889, 4444, 5800, 5900, 5901, 8384, 27017
    # Container ports can be any port (internal)
    PROTOCOL_SPECS = {
        "vless": {
            "docker_image": "sandmanshiri/vless:latest",  # Changed from fluxvpn/vless
            "cpu": 0.1,  # Minimum for testing
            "ram": 100,  # Minimum for testing
            "hdd": 2,  # Reduced for testing
            "ports": [31443, 31080],  # Exposed ports (FluxCloud)
            "container_ports": [443, 80],  # Internal container ports
        },
        "ssh": {
            "docker_image": "sandmanshiri/ssh:latest",  # Changed from fluxvpn/ssh
            "cpu": 0.1,  # Minimum for testing
            "ram": 100,  # Minimum for testing
            "hdd": 1,  # Reduced for testing
            "ports": [
                31023,
                32023,
            ],  # Exposed ports (FluxCloud) - Fixed: 22 is restricted!
            "container_ports": [22, 2222],  # Internal container ports
        },
        "shadowsocks": {
            "docker_image": "sandmanshiri/shadowsocks:latest",  # Changed from fluxvpn/shadowsocks
            "cpu": 0.1,  # Minimum for testing
            "ram": 100,  # Minimum for testing
            "hdd": 2,  # Reduced for testing
            "ports": [
                38390,
                38400,
            ],  # Exposed ports (FluxCloud) - Fixed: near 8384 restricted!
            "container_ports": [8388, 8389],  # Internal container ports
        },
        "trojan": {
            "docker_image": "sandmanshiri/trojan:latest",  # Changed from fluxvpn/trojan
            "cpu": 0.1,  # Minimum for testing
            "ram": 100,  # Minimum for testing
            "hdd": 2,  # Reduced for testing
            "ports": [38443, 38444],  # Exposed ports (FluxCloud)
            "container_ports": [443, 80],  # Internal container ports
        },
        "outline": {
            "docker_image": "sandmanshiri/outline:latest",  # Changed from fluxvpn/outline
            "cpu": 0.1,  # Minimum for testing
            "ram": 100,  # Minimum for testing
            "hdd": 2,  # Reduced for testing
            "ports": [39443, 39081],  # Exposed ports (FluxCloud)
            "container_ports": [443, 8081],  # Internal container ports
        },
        "httpproxy": {
            "docker_image": "sandmanshiri/http-proxy:latest",  # Changed from fluxvpn/http-proxy
            "cpu": 0.1,  # Minimum for testing
            "ram": 100,  # Minimum for testing
            "hdd": 1,  # Reduced for testing
            "ports": [33128],  # Exposed ports (FluxCloud)
            "container_ports": [3128],  # Internal container ports
        },
    }

    def __init__(self, flux_client: Optional[FluxHybridClient] = None):
        """
        Initialize Node Manager

        Args:
            flux_client: FluxHybridClient (creates new one if not provided)
                         Can also accept FluxCloudClient for backward compatibility
        """
        # Support both FluxHybridClient and legacy FluxCloudClient
        if flux_client is None:
            self.flux_client = FluxHybridClient()
        elif isinstance(flux_client, FluxCloudClient):
            # Wrap legacy client in hybrid client for consistency
            self.flux_client = FluxHybridClient(api_client=flux_client)
        else:
            self.flux_client = flux_client

        # Initialize FluxCloud compliance helpers
        self.resource_preset = ResourcePreset(
            mode=getattr(settings, "FLUX_RESOURCE_MODE", "testing")
        )
        self.geo_builder = GeolocationBuilder()

        # Initialize deployment token service if configured
        self.token_service = None
        if settings.FLUXVPN_SECRET_KEY:
            try:
                self.token_service = DeploymentTokenService()
            except Exception as e:
                logger.warning(f"Could not initialize deployment token service: {e}")

    def _require_token_service(self) -> None:
        """
        Ensure deployment token service is available.

        Protocol containers enforce bootstrap token validation at startup.
        Deploying without a token guarantees container startup failure.
        """
        if self.token_service is None:
            raise NodeDeploymentError(
                "Deployment token service is not configured. "
                "Set FLUXVPN_SECRET_KEY so FLUXVPN_AUTH_TOKEN can be injected."
            )

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()

    # =========================================================================
    # MULTI-PROTOCOL DEPLOYMENT (NEW - RECOMMENDED)
    # =========================================================================

    async def deploy_multi_protocol_instance(
        self,
        db: Session,
        country_code: str,
        instance_number: int = 1,
        protocols: Optional[List[str]] = None,
    ) -> List[ProtocolInstance]:
        """
        Deploy a single Flux app with all VPN protocol components

        This creates ONE Flux app containing multiple protocol containers,
        all sharing the same IP address. More cost-efficient than separate apps.

        Args:
            db: Database session
            country_code: Two-letter country code (e.g., "NL", "US")
            instance_number: Instance number for this country (default: 1)
            protocols: List of protocol slugs to deploy (default: all 6)

        Returns:
            List of created ProtocolInstance models (one per protocol)

        Raises:
            NodeDeploymentError: If deployment fails
        """
        if country_code not in self.GEO_DISTRIBUTION:
            raise NodeDeploymentError(f"Unknown country code: {country_code}")

        # Default to all protocols
        if protocols is None:
            protocols = list(self.PROTOCOL_SPECS.keys())

        geo_info = self.GEO_DISTRIBUTION[country_code]
        # FluxCloud app naming: only a-zA-Z0-9, cannot start with 'flux'
        app_name = f"vpnservice{country_code.upper()}{instance_number:02d}"

        logger.info(
            f"Deploying multi-protocol app: {app_name} with {len(protocols)} protocols"
        )

        # Validate all exposed ports before deployment
        for protocol_slug in protocols:
            if protocol_slug in self.PROTOCOL_SPECS:
                ports = cast(List[int], self.PROTOCOL_SPECS[protocol_slug]["ports"])
                if not PortValidator.validate_exposed_ports(ports):
                    raise NodeDeploymentError(
                        f"Invalid exposed ports for {protocol_slug}: {ports}. "
                        f"FluxCloud restricts ports {PortValidator.RESTRICTED_PORTS} "
                        f"and ranges {PortValidator.RESTRICTED_RANGES}"
                    )

        try:
            # Build components list
            components = []
            for protocol_slug in protocols:
                if protocol_slug not in self.PROTOCOL_SPECS:
                    logger.warning(f"Unknown protocol: {protocol_slug}, skipping")
                    continue

                specs = self.PROTOCOL_SPECS[protocol_slug]
                ports = cast(List[int], specs["ports"])
                container_ports = cast(List[int], specs.get("container_ports", ports))
                env_params = self._build_env_params(protocol_slug, app_name)
                logger.info(
                    "Flux deploy debug: prepared component payload "
                    "name=%s image=%s ports=%s container_ports=%s env_param_count=%d",
                    protocol_slug,
                    specs["docker_image"],
                    ports,
                    container_ports,
                    len(env_params),
                )

                components.append(
                    {
                        "name": protocol_slug,
                        "description": f"FluxVPN {protocol_slug.upper()}",
                        "repotag": specs["docker_image"],
                        "ports": ports,  # Exposed ports (1024-65535)
                        "containerPorts": container_ports,  # Internal ports
                        "domains": [""] * len(ports),  # Empty domains for each port
                        "cpu": self.resource_preset.get_cpu(protocol_slug),
                        "ram": self.resource_preset.get_ram(protocol_slug),
                        "hdd": self.resource_preset.get_hdd(protocol_slug),
                        "environmentParameters": env_params,
                    }
                )

            if not components:
                raise NodeDeploymentError("No valid protocols to deploy")

            logger.info(
                "Flux deploy debug: submitting app=%s components=%s",
                app_name,
                ",".join([cast(str, comp["name"]) for comp in components]),
            )

            # Deploy to FluxCloud (minimum 3 instances required)
            # Build geolocation array with backup regions for redundancy
            geolocation_array = self.geo_builder.build_for_country(
                country_code, include_backup=True
            )

            deployment_response = await self.flux_client.deploy_multi_component_app(
                app_name=app_name,
                components=components,
                geolocation=geolocation_array[0] if geolocation_array else None,
                instances=3,
            )

            logger.info(f"FluxCloud deployment response: {deployment_response}")

            # Extract IP from response
            node_ip = self._extract_ip_from_deployment(deployment_response)

            # Create database records for each protocol component
            instances = []
            for protocol_slug in protocols:
                if protocol_slug not in self.PROTOCOL_SPECS:
                    continue

                # Get protocol from database
                protocol = db.query(Protocol).filter_by(slug=protocol_slug).first()
                if not protocol:
                    logger.warning(
                        f"Protocol {protocol_slug} not found in database, skipping"
                    )
                    continue

                instance = ProtocolInstance(
                    protocol_id=protocol.id,
                    flux_app_name=app_name,
                    component_name=protocol_slug,
                    instance_number=instance_number,
                    flux_node_name=deployment_response.get(
                        "node_name", f"{country_code.lower()}-node-{instance_number}"
                    ),
                    ip_address=node_ip,
                    country_code=country_code,
                    country_name=geo_info["name"],
                    city=geo_info["city"],
                    last_health_check=datetime.now(),
                    health_status="deploying",
                    is_active=True,
                )

                db.add(instance)
                instances.append(instance)

            db.commit()

            for inst in instances:
                db.refresh(inst)

            logger.info(
                f"Successfully deployed {app_name} with {len(instances)} protocol components at {node_ip}"
            )
            return instances

        except FluxCloudAPIException as e:
            logger.error(f"FluxCloud API error deploying {app_name}: {str(e)}")
            db.rollback()
            raise NodeDeploymentError(f"FluxCloud deployment failed: {str(e)}")

        except Exception as e:
            logger.error(f"Unexpected error deploying {app_name}: {str(e)}")
            db.rollback()
            raise NodeDeploymentError(f"Deployment error: {str(e)}")

    async def deploy_all_countries(
        self,
        db: Session,
        countries: Optional[List[str]] = None,
        protocols: Optional[List[str]] = None,
    ) -> Dict[str, List[ProtocolInstance]]:
        """
        Deploy multi-protocol apps to all specified countries

        Args:
            db: Database session
            countries: List of country codes (default: all 5)
            protocols: List of protocol slugs (default: all 6)

        Returns:
            Dict mapping country code to list of ProtocolInstance models
        """
        if countries is None:
            countries = list(self.GEO_DISTRIBUTION.keys())

        results = {}
        for country_code in countries:
            try:
                logger.info(f"Deploying to {country_code}...")
                instances = await self.deploy_multi_protocol_instance(
                    db=db,
                    country_code=country_code,
                    instance_number=1,
                    protocols=protocols,
                )
                results[country_code] = instances

                # Delay between deployments to avoid rate limiting
                await asyncio.sleep(2)

            except NodeDeploymentError as e:
                logger.error(f"Failed to deploy to {country_code}: {e}")
                results[country_code] = []

        return results

    @staticmethod
    def _env_params_to_dict(env_params: List[str]) -> Dict[str, str]:
        """
        Convert Flux env parameter list into a key/value map.

        Input format: ["KEY=VALUE", ...]
        """
        env_values: Dict[str, str] = {}
        for env_param in env_params:
            if "=" not in env_param:
                continue
            key, value = env_param.split("=", 1)
            env_values[key] = value
        return env_values

    def _log_env_debug_summary(
        self, component_name: str, env_values: Dict[str, str]
    ) -> None:
        """
        Log non-secret diagnostics for deployment environment variables.

        This helps diagnose missing runtime env vars without exposing secrets.
        """
        required_keys = ("FLUXVPN_AUTH_TOKEN", "FLUXVPN_API_URL", "FLUXVPN_INSTANCE_ID")
        missing_required = [key for key in required_keys if not env_values.get(key)]
        auth_token = env_values.get("FLUXVPN_AUTH_TOKEN", "")

        logger.info(
            "Flux deploy debug: component=%s env_keys=%s missing_required=%s "
            "token_len=%d token_parts=%d token_has_whitespace=%s token_has_newline=%s "
            "instance_id=%s api_url=%s",
            component_name,
            ",".join(sorted(env_values.keys())),
            ",".join(missing_required) if missing_required else "none",
            len(auth_token),
            len(auth_token.split(".")) if auth_token else 0,
            auth_token != auth_token.strip(),
            "\n" in auth_token or "\r" in auth_token,
            env_values.get("FLUXVPN_INSTANCE_ID", "<missing>"),
            env_values.get("FLUXVPN_API_URL", "<missing>"),
        )

    def _build_env_params(self, protocol_slug: str, app_name: str) -> List[str]:
        """
        Build environment parameters for a protocol component

        Args:
            protocol_slug: Protocol identifier (e.g., "vless")
            app_name: Parent app name (e.g., "fluxvpn-nl-01")

        Returns:
            List of "KEY=VALUE" strings
        """
        import uuid

        self._require_token_service()
        token_service = self.token_service
        assert token_service is not None

        component_instance_id = f"{app_name}-{protocol_slug}"
        env_params = [
            f"PROTOCOL={protocol_slug}",
            f"FLUXVPN_INSTANCE_ID={component_instance_id}",
            f"FLUXVPN_APP_NAME={app_name}",
            f"FLUXVPN_COMPONENT={protocol_slug}",
            f"FLUXVPN_API_URL={settings.FLUXVPN_API_URL}",
        ]

        deployment_id = str(uuid.uuid4())
        auth_token = token_service.generate_token(
            deployment_id=deployment_id,
            protocol=protocol_slug,
            instance_id=component_instance_id,
        )
        env_params.append(f"FLUXVPN_AUTH_TOKEN={auth_token}")
        self._log_env_debug_summary(
            component_instance_id,
            self._env_params_to_dict(env_params),
        )

        return env_params

    # =========================================================================
    # SINGLE-PROTOCOL DEPLOYMENT (LEGACY)
    # =========================================================================

    async def deploy_protocol_instances(
        self, db: Session, protocol: Protocol, count: int = 40
    ) -> List[ProtocolInstance]:
        """
        Deploy single-protocol instances across geographic locations (legacy method)

        Args:
            db: Database session
            protocol: Protocol model to deploy
            count: Number of instances to deploy (default: 40)

        Returns:
            List of created ProtocolInstance models

        Raises:
            NodeDeploymentError: If deployment fails
        """
        logger.info(f"Deploying {count} instances for protocol: {protocol.name}")

        protocol_slug = cast(str, protocol.slug or protocol.name.lower())
        if protocol_slug not in self.PROTOCOL_SPECS:
            raise NodeDeploymentError(f"Unknown protocol: {protocol.name}")

        specs = self.PROTOCOL_SPECS[protocol_slug]
        instances = []

        # Validate exposed ports before deployment
        if not PortValidator.validate_exposed_ports(cast(List[int], specs["ports"])):
            raise NodeDeploymentError(
                f"Invalid exposed ports for {protocol_slug}: {specs['ports']}. "
                f"FluxCloud restricts ports {PortValidator.RESTRICTED_PORTS} "
                f"and ranges {PortValidator.RESTRICTED_RANGES}"
            )

        try:
            instance_number = 1
            instances_per_country = max(1, count // len(self.GEO_DISTRIBUTION))

            for country_code, geo_info in self.GEO_DISTRIBUTION.items():
                for i in range(instances_per_country):
                    if instance_number > count:
                        break

                    instance = await self._deploy_single_instance(
                        db=db,
                        protocol=protocol,
                        instance_number=instance_number,
                        country_code=country_code,
                        country_name=geo_info["name"],
                        specs=specs,
                    )

                    instances.append(instance)
                    instance_number += 1

                    await asyncio.sleep(0.5)

                if instance_number > count:
                    break

            logger.info(
                f"Successfully deployed {len(instances)} instances for {protocol.name}"
            )
            return instances

        except Exception as e:
            logger.error(f"Failed to deploy protocol instances: {str(e)}")
            raise NodeDeploymentError(f"Deployment failed: {str(e)}")

    async def _deploy_single_instance(
        self,
        db: Session,
        protocol: Protocol,
        instance_number: int,
        country_code: str,
        country_name: str,
        specs: Dict,
    ) -> ProtocolInstance:
        """Deploy a single protocol instance (legacy single-app mode)"""
        import uuid

        protocol_slug = cast(str, protocol.slug or protocol.name.lower())
        # FluxCloud app naming: only a-zA-Z0-9, cannot start with 'flux'
        app_name = f"vpn{protocol_slug}{country_code.upper()}{instance_number:02d}"

        logger.info(f"Deploying instance: {app_name}")

        try:
            self._require_token_service()
            token_service = self.token_service
            assert token_service is not None
            deployment_id = str(uuid.uuid4())

            env_vars: Dict[str, str] = {
                "PROTOCOL": protocol_slug,
                "INSTANCE_NUMBER": str(instance_number),
                "COUNTRY_CODE": country_code,
                "FLUXVPN_INSTANCE_ID": app_name,
                "FLUXVPN_API_URL": str(settings.FLUXVPN_API_URL or ""),
            }

            auth_token = token_service.generate_token(
                deployment_id=deployment_id,
                protocol=protocol_slug,
                instance_id=app_name,
            )
            env_vars["FLUXVPN_AUTH_TOKEN"] = str(auth_token)
            self._log_env_debug_summary(app_name, env_vars)
            logger.info(
                "Flux deploy debug: single-instance payload app=%s image=%s "
                "ports=%s env_var_count=%d",
                app_name,
                specs["docker_image"],
                specs["ports"],
                len(env_vars),
            )

            deployment_response = await self.flux_client.deploy_app(
                app_name=app_name,
                docker_image=specs["docker_image"],
                ports=cast(List[int], specs["ports"]),
                cpu=self.resource_preset.get_cpu(protocol_slug),
                ram=self.resource_preset.get_ram(protocol_slug),
                hdd=self.resource_preset.get_hdd(protocol_slug),
                tiered=True,
                environment_variables=env_vars,
            )

            node_ip = self._extract_ip_from_deployment(deployment_response)

            instance = ProtocolInstance(
                protocol_id=protocol.id,
                flux_app_name=app_name,
                component_name=protocol_slug,
                instance_number=instance_number,
                flux_node_name=deployment_response.get(
                    "node_name", f"{country_code.lower()}-node-{instance_number}"
                ),
                ip_address=node_ip,
                country_code=country_code,
                country_name=country_name,
                city=self.GEO_DISTRIBUTION.get(country_code, {}).get("city"),
                last_health_check=datetime.now(),
                is_active=True,
            )

            db.add(instance)
            db.commit()
            db.refresh(instance)

            logger.info(f"Successfully deployed {app_name} at {node_ip}")
            return instance

        except FluxCloudAPIException as e:
            logger.error(f"FluxCloud deployment failed for {app_name}: {str(e)}")
            raise NodeDeploymentError(f"FluxCloud deployment failed: {str(e)}")

        except Exception as e:
            logger.error(f"Unexpected error deploying {app_name}: {str(e)}")
            db.rollback()
            raise NodeDeploymentError(f"Deployment error: {str(e)}")

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def _extract_ip_from_deployment(self, deployment_response: Dict) -> str:
        """
        Extract IP address from deployment response

        Args:
            deployment_response: FluxCloud deployment response

        Returns:
            IP address string
        """
        # Try common locations for IP in FluxCloud responses
        ip = (
            deployment_response.get("ip")
            or deployment_response.get("ip_address")
            or deployment_response.get("public_ip")
            or deployment_response.get("data", {}).get("ip")
            or deployment_response.get("data", {}).get("ip_address")
            or
            # FluxCloud may return node info with IP
            deployment_response.get("node", {}).get("ip")
            or
            # nosec: B104 - 0.0.0.0 is used as a fallback local IP, not for binding
            "0.0.0.0"
        )

        if ip == "0.0.0.0":
            logger.warning(
                "Could not extract IP from deployment response, using fallback"
            )

        return ip

    async def scale_protocol(
        self, db: Session, protocol: Protocol, target_count: int
    ) -> Tuple[List[ProtocolInstance], List[ProtocolInstance]]:
        """Scale protocol instances to target count"""
        current_instances = (
            db.query(ProtocolInstance)
            .filter_by(protocol_id=protocol.id, is_active=True)
            .all()
        )

        current_count = len(current_instances)

        logger.info(
            f"Scaling {protocol.name}: {current_count} → {target_count} instances"
        )

        added = []
        removed = []

        if target_count > current_count:
            additional_needed = target_count - current_count
            added = await self.deploy_protocol_instances(
                db, protocol, additional_needed
            )

        elif target_count < current_count:
            remove_count = current_count - target_count
            instances_to_remove = current_instances[:remove_count]

            for instance in instances_to_remove:
                await self.remove_instance(db, instance)
                removed.append(instance)

        return (added, removed)

    async def remove_instance(self, db: Session, instance: ProtocolInstance) -> bool:
        """Remove a protocol instance"""
        logger.info(f"Removing instance: {instance.flux_app_name}")

        try:
            await self.flux_client.delete_app(cast(str, instance.flux_app_name))
            cast(Any, instance).is_active = False
            db.commit()
            logger.info(f"Successfully removed {instance.flux_app_name}")
            return True

        except FluxCloudAPIException as e:
            logger.error(f"Failed to remove {instance.flux_app_name}: {str(e)}")
            return False

    async def restart_instance(self, instance: ProtocolInstance) -> bool:
        """Restart a protocol instance"""
        logger.info(f"Restarting instance: {instance.flux_app_name}")

        try:
            await self.flux_client.restart_app(cast(str, instance.flux_app_name))
            logger.info(f"Successfully restarted {instance.flux_app_name}")
            return True

        except FluxCloudAPIException as e:
            logger.error(f"Failed to restart {instance.flux_app_name}: {str(e)}")
            return False

    async def get_instance_logs(
        self, instance: ProtocolInstance, lines: int = 100
    ) -> str:
        """Get logs for a protocol instance"""
        try:
            logs_response = await self.flux_client.get_app_logs(
                cast(str, instance.flux_app_name), lines=lines
            )
            return logs_response or ""

        except FluxCloudAPIException as e:
            logger.error(f"Failed to get logs for {instance.flux_app_name}: {str(e)}")
            return f"Error retrieving logs: {str(e)}"

    async def estimate_deployment_cost(
        self,
        protocol_name: Optional[str] = None,
        instance_count: int = 5,
        multi_protocol: bool = True,
    ) -> Decimal:
        """
        Estimate cost to deploy instances

        Args:
            protocol_name: Protocol to deploy (ignored if multi_protocol=True)
            instance_count: Number of instances (countries if multi_protocol=True)
            multi_protocol: Whether using multi-protocol mode

        Returns:
            Estimated cost in USD
        """
        specs: Dict[str, Any]
        if multi_protocol:
            # Calculate total resources for all protocols in one app
            total_cpu = sum(
                (float(str(s.get("cpu", 0))) for s in self.PROTOCOL_SPECS.values()), 0.0
            )
            total_ram = sum(
                (float(str(s.get("ram", 0))) for s in self.PROTOCOL_SPECS.values()), 0.0
            )
            total_hdd = sum(
                (float(str(s.get("hdd", 0))) for s in self.PROTOCOL_SPECS.values()), 0.0
            )

            specs = {"cpu": total_cpu, "ram": total_ram, "hdd": total_hdd}
        else:
            if protocol_name is None:
                raise ValueError("protocol_name is required when multi_protocol=False")
            if protocol_name not in self.PROTOCOL_SPECS:
                raise ValueError(f"Unknown protocol: {protocol_name}")
            specs = self.PROTOCOL_SPECS[protocol_name]

        try:
            pricing_response = await self.flux_client.get_pricing(specs)
            monthly_cost = Decimal(str(pricing_response.get("monthly_cost", 0)))
            total_cost = monthly_cost * instance_count

            logger.info(
                f"Estimated cost for {instance_count} instances: ${total_cost}/month"
            )
            return total_cost

        except FluxCloudAPIException as e:
            logger.error(f"Failed to get pricing estimate: {str(e)}")
            # Fallback estimation based on resources
            if multi_protocol:
                return Decimal("15.00") * instance_count  # ~$15/app for 6 protocols
            else:
                return Decimal("3.00") * instance_count

    async def close(self):
        """Close the FluxCloud client connection"""
        await self.flux_client.close()
