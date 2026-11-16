"""
Configuration settings for FluxVPN Worker/API Service
"""

from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

FDM_SYNC_INTERVAL_FLOOR_SECONDS = 300.0  # Phase 4.5: minimum allowed FDM cadence


class Settings(BaseSettings):
    """Application settings"""

    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Redis (optional - set to empty string to disable)
    REDIS_URL: Optional[str] = None

    # Traffic-report anti-inflation guards (Layer 1).
    # A VPN container is supposed to POST a per-cycle DELTA; a broken container
    # delta-state re-sends the whole cumulative counter (or an identical value)
    # every cycle, and the backend's `traffic_used_bytes +=` over-bills users
    # N-fold (see memory traffic_overbilling_rootcause_2026-07-25).
    # - CEILING: reject any single report implying more than this line-rate over
    #   the report window (default 125 MB/s ~ 1 Gbps -> ~7.5 GB per 60s report).
    TRAFFIC_MAX_BYTES_PER_SECOND: int = 131_072_000
    # - DUP SUPPRESSION: skip an identical consecutive (bytes_in, bytes_out) for
    #   the same (user, protocol, instance) within this TTL. Only applies to
    #   reports >= TRAFFIC_DUP_MIN_BYTES (tiny identical keepalives are harmless).
    TRAFFIC_DUP_MIN_BYTES: int = 1_048_576
    TRAFFIC_DUP_TTL_SECONDS: int = 1_800

    # FluxCloud (Multi-wallet authentication - API v6.6.1)
    #
    # SECURITY: NEVER use private keys directly!
    # Use the ZelCore authentication flow with external signing.
    #
    # Authentication Flow:
    # 1. Get login phrase from FluxCloud API (15 min validity)
    # 2. Sign phrase EXTERNALLY with ZelCore wallet software
    # 3. Provide signature to FluxClient via set_signature()
    #
    # Documentation: docs/fluxcloud/api/authentication.md
    #
    FLUX_API_URL: str = "https://api.runonflux.io"
    FLUX_WALLET_ADDRESS: Optional[str] = None  # Your Zelcore wallet address

    # WARNING: Handle with extreme care - private keys should ideally use ZelCore external signing
    # For deployment scripts, private key can be used but ensure proper security measures
    FLUX_WALLET_PRIVATE_KEY: Optional[
        str
    ] = None  # Set via environment variable for deployment scripts

    # FluxCloud API Resilience Settings
    FLUX_RETRY_MAX_ATTEMPTS: int = 3  # Max retry attempts for transient failures
    FLUX_RETRY_MIN_WAIT: float = 2.0  # Min wait between retries (seconds)
    FLUX_RETRY_MAX_WAIT: float = 60.0  # Max wait between retries (seconds)
    FLUX_CIRCUIT_FAILURE_THRESHOLD: int = 5  # Failures before opening circuit
    FLUX_CIRCUIT_RECOVERY_TIMEOUT: float = 120.0  # Seconds before testing recovery

    # FluxCloud Resource Allocation Mode
    # Controls resource presets for VPN protocol deployments
    # - "testing": Minimal resources for development (0.1 CPU, 100 MB RAM, 1-2 GB HDD)
    # - "production": Full resources for production (1 CPU, 512-1024 MB RAM, 2-5 GB HDD)
    FLUX_RESOURCE_MODE: str = "testing"  # "testing" or "production"

    # ============================================================================
    # FLUX NODE-BASED QUERY SETTINGS (Hybrid Client)
    # ============================================================================
    #
    # The FluxVPN system uses a hybrid approach for Flux API interactions:
    # - Read operations: Query nodes directly with consensus → fallback to API
    # - Write operations: Use centralized API (requires authentication)
    #
    # FLUX_NODE_DISCOVERY_ENABLED: Enable node-first queries (default: True)
    # FLUX_NODE_CACHE_TTL_HOURS: Node list cache TTL (default: 24)
    # FLUX_NODE_MIN_CONSENSUS: Minimum nodes for consensus (default: 3)
    # FLUX_NODE_API_PORT: Flux node API port (default: 16127)
    # FLUX_NODE_TIMEOUT: Timeout for node queries in seconds (default: 10.0)
    # FLUX_INITIAL_NODES: Static fallback nodes if API fetch fails
    #
    # To disable node queries and use only API: FLUX_NODE_DISCOVERY_ENABLED=false
    #

    FLUX_NODE_DISCOVERY_ENABLED: bool = True  # Enable node-first queries
    FLUX_NODE_CACHE_TTL_HOURS: int = 24  # Node list cache TTL
    FLUX_NODE_MIN_CONSENSUS: int = 3  # Minimum nodes for consensus
    FLUX_NODE_API_PORT: int = 16127  # Flux node API port
    FLUX_NODE_TIMEOUT: float = 10.0  # Node query timeout (seconds)

    # Initial static nodes (fallback if API fetch fails)
    FLUX_INITIAL_NODES: List[str] = [
        "65.109.90.8",
        "65.109.23.3",
        "65.109.90.29",
        "95.217.146.187",
        "65.108.72.81",
    ]

    # FDM discovery: how many healthy Flux nodes to query for consensus per app per
    # cycle. Sourced from the dynamic NodeDiscoveryService pool; the static
    # FLUX_INITIAL_NODES list is the fallback. Read via getattr-with-default in
    # flux_discovery._resolve_discovery_nodes, so deploying this attr is optional.
    # (Phase 4.2)
    FLUX_FDM_DISCOVERY_NODE_COUNT: int = 10

    # Security (JWT_SECRET_KEY is REQUIRED - no default for security)
    JWT_SECRET_KEY: str  # Must be set via environment variable
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24
    JWT_REFRESH_EXPIRATION_DAYS: int = 30  # Refresh tokens valid for 30 days

    # FluxVPN Deployment Security
    # Secret key for signing deployment tokens (256-bit minimum recommended)
    FLUXVPN_SECRET_KEY: Optional[str] = None  # Must be set for production
    DEPLOYMENT_TOKEN_EXPIRY: int = 3600  # 1 hour bootstrap window
    FLUXVPN_API_URL: str = (
        "https://api.operator7.example.invalid"  # Worker API URL for container callbacks
    )

    # Internal Service Authentication
    # Required for Telegram Bot → Worker API communication
    # Must be the same value in both services
    INTERNAL_API_KEY: Optional[str] = None  # Set this to secure internal endpoints

    # Telegram Bot Integration
    TELEGRAM_BOT_TOKEN: Optional[str] = None  # Telegram bot token for notifications

    # API Rate Limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 60  # seconds

    # CORS
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://admin.operator7.example.invalid",
        "https://operator7.example.invalid",
        "https://www.operator7.example.invalid",
        "https://panel.operator5.example.invalid",
    ]

    # User-facing portal URL (for end-user notifications)
    USER_PORTAL_URL: str = "https://panel.operator5.example.invalid"

    # Client download URLs for setup guides (configurable per deployment).
    # Empty string means "to be configured" — bot will show the URL as-is.
    THRONE_ANDROID_URL: str = ""
    THRONE_IOS_URL: str = ""
    THRONE_WINDOWS_URL: str = ""
    HIDDIFY_ANDROID_URL: str = ""
    HIDDIFY_IOS_URL: str = ""
    HIDDIFY_WINDOWS_URL: str = ""
    NEKOBOX_ANDROID_URL: str = ""
    NEKORAY_WINDOWS_URL: str = ""
    STREISAND_IOS_URL: str = ""

    # Payment Gateways
    ZARINPAL_MERCHANT_ID: Optional[str] = None
    ZARINPAL_SANDBOX: bool = True
    NOWPAYMENTS_API_KEY: Optional[str] = None
    NOWPAYMENTS_IPN_SECRET: Optional[str] = None
    NOWPAYMENTS_SANDBOX: bool = True
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_PUBLISHABLE_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None

    # Email
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_USE_TLS: bool = True
    FROM_EMAIL: str = "noreply@operator7.example.invalid"

    # Monitoring
    SENTRY_DSN: Optional[str] = None
    LOG_LEVEL: str = "INFO"

    # Feature Flags
    ENABLE_FREE_TRIAL: bool = True
    ENABLE_REFERRAL_PROGRAM: bool = True
    ENABLE_WALLET_WITHDRAWALS: bool = True
    ENABLE_IP_CHANGES: bool = True
    TRIAL_DURATION_DAYS: int = 3
    ENABLE_MVP_PUBLIC_DEPLOY: bool = False  # P0-02: Lock down public MVP deployment

    # Compliance / account lifecycle
    USER_DELETION_RETENTION_DAYS: int = 30

    # Reseller broadcast messaging
    BROADCAST_MAX_PER_DAY: int = 5
    BROADCAST_STALE_MINUTES: int = 30

    # Admin health telemetry (low-overhead buffered flush)
    ADMIN_METRICS_FLUSH_INTERVAL_SECONDS: int = 60
    ADMIN_METRICS_MIN_FLUSH_REQUESTS: int = 25
    ADMIN_METRICS_MAX_RESPONSE_TIME_MS: int = 120000

    # Exchange Rate API
    EXCHANGE_RATE_API_URL: str = "https://api.bonbast.com/v1/currencies"

    # Reseller Platform Auth
    SUPER_ADMIN_USERNAME: str = "superadmin"
    SUPER_ADMIN_PASSWORD: str
    TROJAN_SECRET_KEY: str = ""  # Defaults to FLUXVPN_SECRET_KEY if empty

    # Cloudflare DNS API (for FDM - Flux DNS Manager)
    # Replaces ArvanCloud for DNS management
    CLOUDFLARE_API_TOKEN: Optional[str] = None  # Cloudflare API token
    CLOUDFLARE_ZONE_ID: Optional[str] = None  # Cloudflare zone ID
    CLOUDFLARE_DOMAIN: str = "operator3.example.invalid"  # Domain managed by Cloudflare

    # ArvanCloud DNS API (for multi-TLD support)
    ARVAN_API_KEY: Optional[str] = None  # ArvanCloud API key (Machine User key)
    FDM_ARVAN_RATE_LIMIT_MAX_CALLS: int = (
        # Kept at 30 deliberately. Production logs show real ArvanCloud 429s
        # already occur at this ceiling (free Basic plan + bursty concurrent
        # writes), so raising it would only enlarge the pre-cap 429 burst
        # without buying throughput (Arvan rejects the excess). The pool now
        # converges via skip-already-converged in fdm_sync_service
        # (_update_dns_records_v2), which stops wasting this budget re-writing
        # healthy domains -- not by raising the ceiling.
        30  # max ArvanCloud calls per window
    )
    FDM_ARVAN_RATE_LIMIT_WINDOW_SECONDS: int = 60  # Phase 4.4: window length in seconds

    # FDM (Flux DNS Manager) sync cadence
    FDM_SYNC_INTERVAL_SECONDS: float = 600.0  # Phase 4.5: FDM beat cadence

    @field_validator("SUPER_ADMIN_PASSWORD")
    @classmethod
    def _reject_weak_super_admin_password(cls, v: str) -> str:
        if not v or v == "change_me_in_production":
            raise ValueError(
                "SUPER_ADMIN_PASSWORD must be set to a real secret "
                "(empty or the placeholder 'change_me_in_production' is not allowed)"
            )
        return v

    @field_validator("FDM_SYNC_INTERVAL_SECONDS")
    @classmethod
    def _reject_fdm_sync_interval_below_floor(cls, v: float) -> float:
        if v < FDM_SYNC_INTERVAL_FLOOR_SECONDS:
            raise ValueError(
                f"FDM_SYNC_INTERVAL_SECONDS must be >= "
                f"{FDM_SYNC_INTERVAL_FLOOR_SECONDS} seconds (got {v}) — lower "
                f"values risk hammering ArvanCloud/Flux with back-to-back syncs"
            )
        return v

    # Max excess domains one deployment prunes per sync cycle (each prune is a
    # DNS delete; a big shrink drains over cycles within the ArvanCloud budget).
    FDM_RIGHTSIZE_MAX_PRUNE_PER_CYCLE: int = 10

    # FDM endpoint liveness gating (Problem B)
    FDM_LIVENESS_ENABLED: bool = (
        True  # master kill switch; False = today's all_ips behavior
    )
    FDM_LIVENESS_DEAD_CYCLES: int = 3  # consecutive dead cycles before demotion
    FDM_LIVENESS_PORT_TIMEOUT: float = 4.0  # per-port TCP connect timeout (seconds)
    FDM_LIVENESS_MIN_INTERVAL: float = (
        300.0  # min seconds between probes for same (app, ip)
    )
    FDM_LIVENESS_MAX_DEAD_FRACTION: float = (
        0.5  # fail-safe: skip demotion above this fraction
    )
    FDM_LIVENESS_CONCURRENCY: int = (
        20  # max IPs probed at once per app (bounds serial-probe latency)
    )

    # FDM Iran reachability (check-host.net Iranian probe nodes). The liveness
    # gate probes from Dallas and can't see Iranian filtering; this excludes IPs
    # that Iran blocks. See app/services/fdm/iran_reach.py.
    FDM_IRAN_REACH_ENABLED: bool = True  # kill switch for the task AND the filter
    FDM_IRAN_REACH_NODES: str = "ir1,ir2,ir3,ir4,ir5,ir7"  # check-host node ids
    FDM_IRAN_REACH_CONTROL_NODE: str = "de1"  # must connect for a BLOCKED verdict
    FDM_IRAN_REACH_MIN_NODES: int = 4  # Iranian answers needed for BLOCKED
    FDM_IRAN_REACH_BLOCKED_CHECKS: int = 2  # consecutive BLOCKED verdicts to exclude
    FDM_IRAN_REACH_RUN_INTERVAL: float = 600.0  # beat interval of the check task
    FDM_IRAN_REACH_INTERVAL: float = 3600.0  # re-check period per reachable IP
    FDM_IRAN_REACH_SUSPECT_INTERVAL: float = 600.0  # re-check period once suspect
    FDM_IRAN_REACH_MAX_CHECKS_PER_RUN: int = 6  # check-host submits per task run
    FDM_IRAN_REACH_RESULT_DELAY: float = 30.0  # min age before collecting a result
    FDM_IRAN_REACH_RESULT_TTL: float = 1800.0  # give up on a pending result after
    FDM_IRAN_REACH_STALE_AFTER: float = 21600.0  # ignore a block not re-confirmed
    FDM_IRAN_REACH_CANDIDATE_WINDOW: float = 3600.0  # IPs FDM probed this recently
    FDM_IRAN_REACH_MAX_BLOCKED_FRACTION: float = 0.5  # above this, exclude nothing
    FDM_IRAN_REACH_HTTP_TIMEOUT: float = 15.0  # per check-host HTTP call (seconds)

    @field_validator("FDM_IRAN_REACH_MIN_NODES", "FDM_IRAN_REACH_BLOCKED_CHECKS")
    @classmethod
    def _reject_non_positive_iran_counts(cls, v: int) -> int:
        if v < 1:
            raise ValueError("FDM_IRAN_REACH counts must be >= 1")
        return v

    @field_validator("FDM_IRAN_REACH_MAX_BLOCKED_FRACTION")
    @classmethod
    def _reject_out_of_range_blocked_fraction(cls, v: float) -> float:
        if not (0 < v <= 1):
            raise ValueError("FDM_IRAN_REACH_MAX_BLOCKED_FRACTION must be in (0, 1]")
        return v

    @field_validator("FDM_LIVENESS_DEAD_CYCLES")
    @classmethod
    def _reject_non_positive_dead_cycles(cls, v: int) -> int:
        if v < 1:
            raise ValueError("FDM_LIVENESS_DEAD_CYCLES must be >= 1")
        return v

    @field_validator("FDM_LIVENESS_MAX_DEAD_FRACTION")
    @classmethod
    def _reject_out_of_range_dead_fraction(cls, v: float) -> float:
        if not (0 < v <= 1):
            raise ValueError("FDM_LIVENESS_MAX_DEAD_FRACTION must be in (0, 1]")
        return v

    @field_validator("FDM_LIVENESS_CONCURRENCY")
    @classmethod
    def _reject_non_positive_concurrency(cls, v: int) -> int:
        if v < 1:
            raise ValueError("FDM_LIVENESS_CONCURRENCY must be >= 1")
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="allow",  # Allow extra environment variables that aren't defined in the Settings class
    )


# Create global settings instance
settings = Settings()
