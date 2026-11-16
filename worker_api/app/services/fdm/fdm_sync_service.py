"""
Flux DNS Manager (FDM) Sync Service
Main orchestration service for FDM sync operations.

This service coordinates the complete DNS synchronization workflow:
1. Discover Flux VPN instances using FluxDiscoveryService
2. Ensure domain records exist in the database
3. Calculate distribution of domains across instances
4. Update DNS records on Cloudflare

Architecture:
- Orchestrates FluxDiscoveryService for instance discovery
- Uses FdmDomainService for domain management and distribution
- Integrates with CloudflareDnsClient for DNS record updates
- Tracks sync operations in FdmSyncLog for observability
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.overlap_lock import overlap_lock
from app.models import ProtocolInstance
from app.models.fdm import FdmDeployment, FdmDomain, FdmSyncLog
from app.services.flux.client import FluxCloudClient
from app.services.flux.spec_fetcher import FluxSpecFetcher

from .arvancloud_client import ArvanCloudRateLimitBudgetExceeded
from .dns_provider import create_dns_client
from .fdm_domain_service import FdmDomainService
from .flux_discovery import FluxDiscoveryService
from .iran_reach import iran_blocked_ips
from .liveness import LivenessGate

if TYPE_CHECKING:
    from app.models.registered_tld import RegisteredTld

logger = logging.getLogger(__name__)


def _release_savepoint(savepoint: Any) -> None:
    """Release a SAVEPOINT that a success path (return/continue/fall-through)
    left open. A no-op after rollback() or an enclosing commit() closed it.

    The `savepoint = begin_nested(); try: ... except: savepoint.rollback()`
    pattern only ever closed it on error. In a loop every item then nested
    one level deeper, and with 635 healthy domains the next commit() hit
    "maximum recursion depth exceeded" (prod, 2026-10-24).
    """
    if savepoint.is_active:
        savepoint.commit()


class FdmSyncServiceError(Exception):
    """Base exception for FDM Sync Service errors."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class _StubIP:
    """Adapter for reusing _resolve_one_instance which expects an instance with .ip_address."""

    def __init__(self, ip: str):
        self.ip_address = ip


@dataclass(frozen=True)
class _DiscoveryResult:
    """Phase 4.1: one discovery outcome per (app, port) per cycle. Distinguishes
    discovery-FAILURE (ok=False) from discovery-SUCCESS-with-zero-healthy
    (ok=True, healthy_ips=[]) so callers can tell Flux-down from app-down — the
    split _app_healthy_ip_count collapsed into a single 0 (3.4-a root cause)."""

    all_ips: List[str]
    healthy_ips: List[str]
    ok: bool
    error: Optional[str]


class FdmSyncService:
    """
    Main orchestration service for FDM sync operations.

    This service coordinates the complete workflow for syncing
    Flux VPN instance IPs to Cloudflare DNS records.

    Responsibilities:
    - Discovering Flux VPN instances
    - Managing domain records in database
    - Calculating load distribution across instances
    - Updating DNS records on Cloudflare
    - Tracking sync history and errors
    """

    SPEC_GAP_THRESHOLD = 3  # consecutive short cycles before alerting
    SPEC_GAP_COOLDOWN_HOURS = 6
    POOL_CAP = 25  # grid ceiling for domain pool sizing
    MIN_POOL = 2
    SYNC_CONCURRENCY = 4  # Phase 4.6: bounded per-deployment sync fan-out
    DNS_CONCURRENCY = 6  # bounded per-domain DNS-call fan-out within a deployment
    STALE_DELETE_CAP = 10  # max stale-domain DNS deletes per deployment per cycle
    # _validate_domain_ips_against_instances: an app/IP the liveness gate probed
    # this recently (and has not demoted) is still in that app's Flux consensus.
    LIVENESS_FRESH_SECONDS = 1800

    def __init__(self, db: Session):
        """
        Initialize the FDM Sync Service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        self.domain_service = FdmDomainService(db)
        # Phase 3.3: intra-cycle cache of app -> expected_instances, populated by
        # _fetch_and_persist_app_specs and consumed by _spec_pool_target (3.5).
        # Phase 4.1 generalizes this into the per-app discovery cache.
        self._spec_expected: Dict[str, int] = {}
        # Phase 3.4 Option B: intra-cycle cache of app -> {expected, actual} for
        # apps with a spec gap THIS cycle. Reset by _detect_spec_gap each cycle;
        # consumed by _sync_deployment via _inject_spec_gap_into_log. Empty on
        # the on-demand reconcile_app path -> injection is a no-op (zero regression).
        self._spec_gap_by_app: Dict[str, dict] = {}
        # Phase 4.1: per-cycle discovery cache keyed by (app_name, port). Stores
        # BOTH success and the ok=False failure sentinel, so each (app,port) is
        # fetched exactly once per cycle even under outage. FdmSyncService is
        # cycle-fresh (reinstantiated each beat), so this resets every cycle free.
        self._discovery_cache: Dict[Tuple[str, int], "_DiscoveryResult"] = {}

    def _spec_pool_target(self, deployment: FdmDeployment, live_count: int) -> int:
        """Spec-aware pool target:
        max(live_count, MIN_POOL, min(ceil(expected / active_regions), POOL_CAP)).

        expected comes from the intra-cycle _spec_expected cache (populated by
        _fetch_and_persist_app_specs), falling back to a FluxAppRegistration
        query, then MIN_POOL. DNS still points only at live IPs: round-robin in
        _update_dns_records_v2 (ip = healthy_ips[i % len(healthy_ips)]) assigns
        every domain a healthy IP, so a pool larger than live_count yields N
        domains sharing the live IPs (CDN-style) -- never a dead A-record.

        The floor is the app's expected instances split across its ACTIVE
        region deployments. All regions share 99 names per TLD
        (generate_domain_names); using the app total for every region made
        ch01 (18 instances, 6 regions) claim ~90 of them and starved other
        regions out of every subscription (2026-10-24).
        """
        expected = self._spec_expected.get(deployment.flux_app_name)
        if expected is None:
            from app.models.flux_app_registration import FluxAppRegistration

            app = (
                self.db.query(FluxAppRegistration)
                .filter(FluxAppRegistration.app_name == deployment.flux_app_name)
                .first()
            )
            expected = getattr(app, "expected_instances", None) if app else None
            if expected is not None:
                self._spec_expected[deployment.flux_app_name] = expected
        if not expected:
            return max(live_count, self.MIN_POOL)
        regions = int(
            self.db.query(FdmDeployment)
            .filter(
                FdmDeployment.flux_app_name == deployment.flux_app_name,
                FdmDeployment.is_active.is_(True),
            )
            .count()
        )
        per_region = -(-expected // max(regions, 1))  # ceil division
        floor = max(self.MIN_POOL, min(per_region, self.POOL_CAP))
        return max(live_count, floor)

    async def _apply_liveness_gate(
        self, deployment: FdmDeployment, all_ips: List[str]
    ) -> List[str]:
        """Return the candidate IPs with confirmed-dead IPs excluded via the
        liveness gate (Problem B).

        Fail-open: on ANY gate error, serve all_ips unchanged and roll back the
        shared session. LivenessGate.gate() commits on self.db, so a failed
        commit/flush leaves the Session needing a rollback before the rest of
        sync_deployment can query it — without this, a probe-side DB error would
        cascade into a full sync failure instead of fail-open behavior.
        """
        if not (settings.FDM_LIVENESS_ENABLED and all_ips):
            return all_ips
        try:
            dead_ips = await LivenessGate(self.db).gate(
                deployment.flux_app_name, all_ips
            )
        except Exception as e:  # fail-open: never break sync on probe error
            self.db.rollback()
            logger.warning(
                "Liveness gate error for %s (serving all_ips): %s",
                deployment.flux_app_name,
                e,
                exc_info=True,
            )
            return all_ips
        if dead_ips:
            logger.info(
                "Liveness gate excluded %d dead IP(s) for %s: %s",
                len(dead_ips),
                deployment.flux_app_name,
                sorted(dead_ips),
            )
            return [ip for ip in all_ips if ip not in dead_ips]
        return all_ips

    def _apply_iran_reach_filter(
        self, deployment: FdmDeployment, all_ips: List[str], target_ips: List[str]
    ) -> List[str]:
        """Drop IPs confirmed blocked from Iran (fdm.check_iran_reachability)
        from a deployment's region-filtered target_ips.

        Fails toward serving: kill switch off, a state-read error (undone via
        its own SAVEPOINT), more than FDM_IRAN_REACH_MAX_BLOCKED_FRACTION of the
        app's IPs "blocked" at once (check-host's Iranian nodes more likely
        broken than Iran blocking most of the fleet), or every IP of the region
        blocked (still useful outside Iran) all return target_ips unchanged.
        ProtocolInstance.is_active is not touched: the node itself is healthy.
        """
        if not (settings.FDM_IRAN_REACH_ENABLED and target_ips):
            return target_ips
        app = deployment.flux_app_name
        try:
            # SAVEPOINT, not a full rollback on failure: sync_log's counts are
            # still uncommitted here and a rollback would expire them.
            with self.db.begin_nested():
                blocked = iran_blocked_ips(self.db, app, all_ips)
        except Exception as e:  # fail-open: never break sync on this filter
            logger.warning(
                "Iran reachability read failed for %s (serving all): %s", app, e
            )
            return target_ips
        dropped = [ip for ip in target_ips if ip in blocked]
        if not dropped:
            return target_ips
        if len(blocked) / max(len(all_ips), 1) > (
            settings.FDM_IRAN_REACH_MAX_BLOCKED_FRACTION
        ):
            logger.warning(
                "Iran reachability fail-safe for %s: %d/%d IPs marked blocked, "
                "excluding none",
                app,
                len(blocked),
                len(all_ips),
            )
            return target_ips
        kept = [ip for ip in target_ips if ip not in blocked]
        if not kept:
            logger.warning(
                "Iran reachability: every %s/%s IP is blocked from Iran %s, "
                "serving them anyway",
                app,
                deployment.region,
                sorted(dropped),
            )
            return target_ips
        logger.info(
            "Iran reachability excluded %d Iran-blocked IP(s) for %s/%s: %s",
            len(dropped),
            app,
            deployment.region,
            sorted(dropped),
        )
        return kept

    async def sync_deployment(
        self,
        deployment: FdmDeployment,
    ) -> FdmSyncLog:
        """
        Sync a single protocol-agnostic FDM deployment with DNS.

        Steps:
        1. Discover instances using FluxDiscoveryService
        2. Filter IPs by deployment region
        3. Ensure one domain per healthy IP (CDN-style naming)
        4. Map domains to IPs (1:1 assignment)
        5. Update DNS A records

        Args:
            deployment: FdmDeployment to sync (protocol-agnostic)

        Returns:
            FdmSyncLog with sync results
        """
        sync_log = FdmSyncLog(
            deployment_id=deployment.id,
            sync_started_at=datetime.now(timezone.utc).replace(tzinfo=None),
            status="running",
            errors=[],
        )
        self.db.add(sync_log)
        self.db.commit()

        logger.info(
            f"Starting sync for deployment {deployment.flux_app_name}/{deployment.region}"
        )

        errors = []

        try:
            # Step 1: Discover instances
            all_ips, healthy_ips = await self._discover_instances(
                deployment, protocol_port=deployment.health_check_port or 443
            )

            # Any-port-alive liveness gating (Problem B): exclude confirmed-dead
            # IPs from the candidate set. Kill-switch + fail-open live in the
            # helper (a gate error serves all_ips and rolls back the session).
            target_ips = await self._apply_liveness_gate(deployment, all_ips)

            # Recorded AFTER the gate on purpose: the gate's fail-open path rolls
            # back the shared session on a probe error, which would discard these
            # two counts if they were assigned before it — they'd revert to the
            # NULL the initial running-row was inserted with and this cycle would
            # log NULL instances_found/healthy. Assigning post-gate keeps them on
            # the session through to the finalize commit.
            sync_log.instances_found = len(all_ips)
            sync_log.instances_healthy = len(healthy_ips)

            # Step 2: Filter by region (skip for catch-all "XX")
            if deployment.region and deployment.region.upper() != "XX" and target_ips:
                target_ips = await self._filter_ips_by_region(
                    target_ips, deployment.region.upper()
                )

            # Drop IPs Iran blocks (check-host.net verdicts). After the region
            # filter so its never-empty guard applies per region.
            target_ips = self._apply_iran_reach_filter(deployment, all_ips, target_ips)

            # Auto-detect region if placeholder "XX"
            if deployment.region == "XX" and target_ips:
                from app.models.ip_management import ProtocolInstance

                instance = (
                    self.db.query(ProtocolInstance)
                    .filter(ProtocolInstance.ip_address.in_(target_ips))
                    .first()
                )
                if instance and instance.country_code:
                    deployment.region = instance.country_code.upper()
                    self.db.commit()

            # Manage domain lifecycle (mark unhealthy, cleanup, replenish)
            if target_ips:
                await self._manage_domain_lifecycle(deployment, target_ips)

            # Step 3: Ensure domains exist (1 per IP)
            domains = self._ensure_domains_exist(
                deployment, healthy_ip_count=len(target_ips) if target_ips else 0
            )

            if not domains:
                errors.append({"step": "domains", "error": "No domains available"})
            elif not target_ips:
                errors.append({"step": "discovery", "error": "No instances found"})

            # Step 4: Update DNS records (1:1 domain-to-IP mapping)
            domains_updated = 0
            dns_errors: List[dict] = []
            if domains and target_ips:
                domains_updated, dns_errors = await self._update_dns_records_v2(
                    deployment=deployment,
                    domains=domains,
                    healthy_ips=target_ips,
                )

            sync_log.domains_updated = domains_updated
            # Per-TLD DNS failures are now queryable in fdm_sync_logs.errors
            # (spec §4.2), not log-grep-only. They flow into sync_log.errors at
            # the existing `if errors: sync_log.errors = errors` line below.
            errors.extend(dns_errors)

            # De-duped superadmin alert for fdm TLDs fully DNS-dark this cycle
            # (spec §4.3). Fires at most once per TLD per 6h (platform_settings).
            if dns_errors:
                await self._alert_dns_dark_tlds(dns_errors)

            if not errors and domains_updated == len(domains):
                sync_log.status = "success"
                deployment.last_sync_status = "success"
                deployment.consecutive_failures = 0
                # Shrink pool if IPs dropped since last sync
                await self._rightsize_domain_pool(deployment, len(target_ips))
            elif domains_updated > 0:
                sync_log.status = "partial"
                deployment.last_sync_status = "partial"
                deployment.consecutive_failures = 0
                # Shrink pool if IPs dropped since last sync (also on partial —
                # pool sizing is independent of DNS update status)
                await self._rightsize_domain_pool(deployment, len(target_ips))
            else:
                sync_log.status = "failed"
                deployment.last_sync_status = "failed"
                # Only a phantom when discovery found IPs but none live in this
                # region. instances_found == 0 is a transient Flux API outage; a
                # region WITH live IPs that failed on domains/DNS (e.g. "No
                # domains available" under name starvation) is not a phantom
                # either, and counting it would deactivate a live region.
                if sync_log.instances_found > 0 and not target_ips:
                    deployment.consecutive_failures = (
                        getattr(deployment, "consecutive_failures", 0) or 0
                    ) + 1
                    logger.info(
                        f"Deployment {deployment.flux_app_name}/{deployment.region} "
                        f"failure streak: {deployment.consecutive_failures}"
                    )

            if errors:
                sync_log.errors = errors

        except Exception as e:
            logger.exception(f"Unexpected sync error: {e}")
            sync_log.status = "failed"
            deployment.last_sync_status = "failed"
            sync_log.errors = [{"step": "sync", "error": str(e)}]
            # Intentionally not incrementing consecutive_failures here:
            # exceptions often mean Flux API/Cloudflare outages (instances_found=0),
            # and incrementing would violate the instances_found > 0 safety guard.

        # Capture this cycle's real sync-outcome decisions as plain local
        # values BEFORE the finalize tail below. If the finalize commit fails
        # and the recovery path below calls self.db.rollback(), SQLAlchemy
        # expires deployment's uncommitted attributes -- re-reading
        # deployment.last_sync_status after a rollback would silently return
        # the STALE pre-cycle value from the DB, not what this cycle decided.
        outcome_last_sync_status = deployment.last_sync_status
        outcome_consecutive_failures = deployment.consecutive_failures

        # Phase 3.4 Option B: record owning-app spec gap in the sync-log errors
        # for DB-queryability (design §3.3). AFTER status computation so a
        # healthy sync of an under-provisioned app stays status="success".
        #
        # Phase 4.7a: this whole tail is now guarded. If it raises (e.g. a
        # transient DB error on the commit itself), the sync_log row would
        # otherwise be left permanently stuck at status="running" -- the only
        # write that had landed was the initial one at the top of this
        # method. This mirrors the failure-recovery pattern already shipped
        # and live-verified in Phase 4.6's _sync_deployment_isolated.
        try:
            self._inject_spec_gap_into_log(deployment, sync_log)
            sync_log.sync_completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            deployment.last_sync_at = datetime.now(timezone.utc).replace(tzinfo=None)
            self.db.add(deployment)
            self.db.add(sync_log)
            self.db.commit()
        except Exception as e:
            logger.exception(
                f"Failed to finalize sync log for "
                f"{deployment.flux_app_name}/{deployment.region}: {e}"
            )
            try:
                self.db.rollback()
                # Phase 4.7a review fix: rollback() above expires deployment's
                # uncommitted last_sync_status/consecutive_failures/last_sync_at
                # -- re-apply this cycle's real decision (captured before the
                # finalize tail started) so a transient finalize-commit
                # failure doesn't silently revert deployment bookkeeping to
                # last cycle's stale values.
                deployment.last_sync_status = outcome_last_sync_status
                deployment.consecutive_failures = outcome_consecutive_failures
                deployment.last_sync_at = datetime.now(timezone.utc).replace(
                    tzinfo=None
                )
                sync_log.status = "failed"
                sync_log.errors = (sync_log.errors or []) + [
                    {"step": "finalize", "error": str(e)}
                ]
                sync_log.sync_completed_at = datetime.now(timezone.utc).replace(
                    tzinfo=None
                )
                self.db.add(deployment)
                self.db.add(sync_log)
                self.db.commit()
            except Exception:
                logger.exception(
                    f"Failed to persist failure status for "
                    f"{deployment.flux_app_name}/{deployment.region} after "
                    f"finalize failure -- sync_log id={sync_log.id} may be "
                    f"stuck at status='running'"
                )

        return sync_log

    async def _discover_instances(
        self,
        deployment: FdmDeployment,
        protocol_port: int = 443,
    ) -> Tuple[List[str], List[str]]:
        """
        Discover Flux VPN instances for the deployment.

        Args:
            deployment: FdmDeployment to discover instances for
            protocol_port: Port for health checks

        Returns:
            Tuple of (all_ips, healthy_ips)

        Raises:
            FdmSyncServiceError: If discovery fails
        """
        res = await self._get_cached_instances(
            app_name=deployment.flux_app_name, port=protocol_port
        )
        if not res.ok:
            logger.error(
                f"Instance discovery failed for {deployment.flux_app_name}: {res.error}"
            )
            raise FdmSyncServiceError(f"Instance discovery failed: {res.error}")
        return res.all_ips, res.healthy_ips

    def _active_fdm_tlds(self) -> List["RegisteredTld"]:
        """Active, non-deleted fdm TLDs, ordered by id (deterministic; matches
        TldSelectionService's min((count, id)) tie-break).

        Phase 4b.1: under single-active this is a 1-element list — the one
        active fdm TLD — so every per-TLD loop iterates exactly once,
        preserving today's behavior while populating FdmDomain.tld_id.
        """
        from app.models.registered_tld import RegisteredTld

        return (
            self.db.query(RegisteredTld)
            .filter(
                RegisteredTld.purpose == "fdm",
                RegisteredTld.is_active == True,
                RegisteredTld.deleted_at.is_(None),
            )
            .order_by(RegisteredTld.id)
            .all()
        )

    def _create_domains_for_tld(
        self,
        deployment: FdmDeployment,
        tld: "RegisteredTld",
        count: int,
        seed_ip: Optional[str] = None,
    ) -> int:
        """Generate + insert `count` new FdmDomain rows for THIS tld.

        Per-TLD generation (Phase 4b.1): subdomain suffix = tld.domain; the
        dedup set is suffix-scoped: all names ending '.{tld.domain}' incl.
        legacy tld_id=NULL rows (the unique constraint is GLOBAL on
        domain_name, so the same
        slug can be reused across TLDs — domain_name stays globally unique
        because the suffix differs); every new row carries tld_id.

        Returns the number of rows created (0..count).
        """
        if count <= 0:
            return 0
        # SUFFIX-aware dedup (not tld_id-scoped). The unique constraint is
        # GLOBAL on domain_name (= "{domain_id}.{tld.domain}"), so a collision
        # is ANY existing name sharing this suffix -- owned rows (tld_id ==
        # tld.id) AND legacy tld_id=NULL rows. The old .filter(tld_id ==
        # tld.id) was blind to NULL rows -> generate re-emitted their slug ->
        # IntegrityError -> poisoned session -> sync died (crashloop 2026-06-27).
        suffix = "." + tld.domain
        used_ids = {
            d.domain_id
            for d in self.db.query(FdmDomain.domain_id)
            .filter(FdmDomain.domain_name.like("%" + suffix))
            .all()
        }
        new_names = FdmDomainService.generate_domain_names(
            base_domain=tld.domain,
            count=count,
            existing_domain_ids=used_ids,
        )
        for domain_name, domain_id in new_names:
            self.db.add(
                FdmDomain(
                    deployment_id=deployment.id,
                    tld_id=tld.id,
                    domain_name=domain_name,
                    domain_id=domain_id,
                    current_ip=seed_ip,
                    health_status="unknown",
                )
            )
        self.db.commit()
        return len(new_names)

    def _ensure_domains_exist(
        self,
        deployment: FdmDeployment,
        healthy_ip_count: int = 0,
    ) -> List[FdmDomain]:
        """Ensure protocol-agnostic domain records exist for the deployment,
        one pool of `_spec_pool_target(deployment, healthy_ip_count)` domains PER active fdm TLD (spec-aware floor; defaults to max(healthy_ip_count, 2) when no spec is known).

        Phase 4b.1 (per-TLD generation): for each active fdm TLD, ensure the
        deployment has >= target_count domains tagged with that TLD. Under
        single-active (one active fdm TLD) this is byte-for-byte today's
        behavior: one pool of target_count domains, tld.domain ==
        deployment.base_domain (activate rewrites base_domain), and the dedup
        set equals today's global set (all rows share this tld_id). The new
        dimension (tld_id) is simply populated.

        Args:
            deployment: FdmDeployment to ensure domains for
            healthy_ip_count: Number of healthy IPs (determines per-TLD pool size)

        Returns:
            All FdmDomain records for this deployment (every active TLD's pool).
        """
        target_count = self._spec_pool_target(deployment, healthy_ip_count)
        tlds = self._active_fdm_tlds()

        if not tlds:
            # No active fdm TLD (should not happen — last-active guard).
            # Return existing rows rather than generate tld_id-less domains
            # that would muddy the multi-active read filter later.
            logger.warning(
                f"No active fdm TLD; skipping domain generation for "
                f"{deployment.flux_app_name}/{deployment.region}"
            )
            return (
                self.db.query(FdmDomain)
                .filter(FdmDomain.deployment_id == deployment.id)
                .order_by(FdmDomain.domain_name)
                .all()
            )

        for tld in tlds:
            # Count this TLD's pool INCLUDING legacy tld_id=NULL rows. A NULL
            # tld_id resolves to the active TLD at READ time (mirrors the 4a
            # read filter's `(tld_id == effective) OR (tld_id IS NULL)`), so it
            # is capacity for THIS active TLD and must count toward its target —
            # otherwise we'd top up past target_count whenever an earlier phase
            # (e.g. _manage_domain_lifecycle replenish) created NULL rows.
            # Under single-active (4b.1 invariant) there is exactly one active
            # TLD, so a NULL row is counted exactly once. 4b.2 revisits this
            # for multi-active.
            existing = (
                self.db.query(FdmDomain)
                .filter(
                    FdmDomain.deployment_id == deployment.id,
                    (FdmDomain.tld_id == tld.id) | (FdmDomain.tld_id.is_(None)),
                )
                .count()
            )
            needed = max(0, target_count - existing)
            if needed:
                self._create_domains_for_tld(deployment, tld, needed)

        return (
            self.db.query(FdmDomain)
            .filter(FdmDomain.deployment_id == deployment.id)
            .order_by(FdmDomain.domain_name)
            .all()
        )

    def _count_healthy_domains(self, tld_id: int) -> int:
        """Number of healthy FdmDomain rows for a TLD (the dns-dark test)."""
        from app.models.fdm import FdmDomain

        return (
            self.db.query(FdmDomain)
            .filter(
                FdmDomain.tld_id == tld_id,
                FdmDomain.health_status == "healthy",
            )
            .count()
        )

    async def _alert_dns_dark_tlds(self, dns_errors: List[dict]) -> None:
        """De-duped superadmin alert for fdm TLDs fully DNS-dark this cycle
        (in dns_errors AND 0 healthy domains). De-dupe via platform_settings
        key tld_dns_alert:{id}: skip if alerted < 6h ago. Spec §4.3.

        Called per-deployment in the sync orchestrator; the 6h stamp suppresses
        cross-deployment/cross-cycle repeats (a TLD spans deployments).
        send_to_super_admin is synchronous (httpx) — matches the existing
        blocking-in-async pattern in this service (_broadcast_tld_change)."""
        from datetime import datetime, timedelta, timezone

        from app.models.platform_settings import PlatformSetting
        from app.services.notifications.router import NotificationRouter
        from app.services.notifications.templates import format_dns_dark_tld_alert

        COOLDOWN = timedelta(hours=6)
        now = datetime.now(timezone.utc)
        router = NotificationRouter(self.db)
        for err in dns_errors:
            tld_id = err.get("tld_id")
            if tld_id is None:
                continue
            if self._count_healthy_domains(tld_id) > 0:
                continue  # partial failure, not fully dark -> no alert
            key = f"tld_dns_alert:{tld_id}"
            row = (
                self.db.query(PlatformSetting)
                .filter(PlatformSetting.key == key)
                .first()
            )
            if row and row.value:
                try:
                    if now - datetime.fromisoformat(row.value) < COOLDOWN:
                        continue  # cooled down
                except ValueError:
                    pass  # corrupt stamp -> fall through and re-alert
            sent = router.send_to_super_admin(
                format_dns_dark_tld_alert(
                    tld_domain=err.get("tld_domain") or "",
                    provider=err.get("provider") or "",
                    failed=int(err.get("failed") or 0),
                    sample=err.get("sample") or "",
                )
            )
            if sent:
                if row is None:
                    self.db.add(PlatformSetting(key=key, value=now.isoformat()))
                else:
                    row.value = now.isoformat()
                self.db.flush()

    async def _update_dns_records_v2(
        self,
        deployment: FdmDeployment,
        domains: List[FdmDomain],
        healthy_ips: List[str],
    ) -> Tuple[int, List[dict]]:
        """Update DNS records 1:1, routing each domain through its OWN tld's
        DNS provider/zone (multi-active). Legacy tld_id=NULL rows resolve to an
        active TLD (mirrors the 4a read filter + _delete_dns_record_for_domain).

        Each domain -> exactly one IP (round-robin across healthy_ips); extra
        domains without an IP slot are marked unhealthy.

        Returns (domains_updated, dns_errors). dns_errors is one entry per TLD
        bucket that had >=1 per-domain failure: {"step":"dns","tld_id":..,
        "tld_domain":..,"provider":..,"failed":n,"sample":str}. The orchestrator
        persists these into fdm_sync_logs.errors (spec §4.2) so a dead zone is
        DB-queryable, not log-grep-only. Domains are still marked unhealthy and
        the per-bucket commit is unchanged.
        """
        if not domains or not healthy_ips:
            return 0, []

        from collections import defaultdict

        active = {t.id: t for t in self._active_fdm_tlds()}
        if not active:
            logger.error("No active FDM TLD found; skipping DNS updates")
            return 0, []

        # Bucket each domain by its tld. Three cases:
        #  - tld_id IS NULL  : legacy row -> first active TLD (fallback; mirrors
        #    the 4a read filter where NULL means "belongs to active").
        #  - tld_id in active : own bucket (per-TLD DNS provider/zone).
        #  - else (orphan)   : tld_id points at a deactivated/deleted TLD. Leave
        #    its DNS untouched -- D8 deactivate preserves rows for re-activation,
        #    and re-routing an orphan through a live TLD's provider would push a
        #    stray record into the wrong zone and overwrite its dns_record_id.
        fallback = next(iter(active.values()))
        buckets: dict = defaultdict(list)
        for d in domains:
            if d.tld_id is None:
                buckets[fallback.id].append(d)
            elif d.tld_id in active:
                buckets[d.tld_id].append(d)
            else:
                logger.debug(
                    f"Skipping DNS update for orphan domain {d.domain_name} "
                    f"(tld_id={d.tld_id} not in active set)"
                )

        domains_updated = 0
        healthy_ip_set = set(healthy_ips)
        bucket_err: dict = {}  # tld_id -> {"failed": int, "sample": str|None}
        for tld_id, tld_domains in buckets.items():
            tld = active[tld_id]
            try:
                client = create_dns_client(
                    provider=tld.dns_provider,
                    domain=tld.domain,
                    zone_id=tld.zone_id,
                )
            except Exception as e:
                logger.error(f"DNS client creation failed for tld {tld.domain}: {e}")
                sample = str(e)[:200]
                be = bucket_err.setdefault(
                    tld_id, {"failed": 0, "sample": None, "skipped": 0}
                )
                be["failed"] += len(tld_domains)
                if be["sample"] is None:
                    be["sample"] = sample
                for d in tld_domains:
                    d.health_status = "unhealthy"
                    self.db.add(d)
                continue

            async with client:
                # Serial DB prep, then fan out only the network calls. A degraded
                # DNS provider made this loop O(N * per-call timeout) *serially*,
                # so one deployment's DNS phase could exceed the Celery hard limit
                # and the overlap-lock window -> the whole sync never completed
                # (2026-08-16 region freeze). ensure_record_exists is network-only
                # on the prebuilt client, so it is safe to gather; the shared DB
                # session is only touched serially (prep above, apply below).
                prepped = []
                for i, domain in enumerate(tld_domains):
                    # Skip domains that are already converged: healthy, pointing
                    # at a still-healthy IP, and with a known DNS record id.
                    # Re-writing them spends the shared ArvanCloud rate-limit
                    # budget (30/60s across ALL Arvan TLDs) on a no-op, which
                    # starves un-provisioned domains so the pool never converges
                    # (root cause of resellers seeing only a handful of
                    # countries). Count as up-to-date and make no API call.
                    if (
                        domain.health_status == "healthy"
                        and domain.current_ip in healthy_ip_set
                        and domain.dns_record_id
                    ):
                        domains_updated += 1
                        continue
                    ip = healthy_ips[i % len(healthy_ips)]
                    instance = self._get_or_create_instance(
                        deployment=deployment,
                        ip=ip,
                        instance_number=(i % len(healthy_ips)) + 1,
                    )
                    subdomain = self._extract_subdomain(domain.domain_name)
                    prepped.append((domain, ip, instance, subdomain))

                sem = asyncio.Semaphore(self.DNS_CONCURRENCY)

                async def _ensure(subdomain, ip, existing_record_id):
                    async with sem:
                        return await client.ensure_record_exists(
                            name=subdomain,
                            ip=ip,
                            existing_record_id=existing_record_id,
                        )

                records = await asyncio.gather(
                    *[
                        _ensure(subdomain, ip, domain.dns_record_id)
                        for (domain, ip, instance, subdomain) in prepped
                    ],
                    return_exceptions=True,
                )

                for (domain, ip, instance, subdomain), record in zip(prepped, records):
                    if isinstance(record, ArvanCloudRateLimitBudgetExceeded):
                        logger.warning(
                            f"ArvanCloud rate-limit budget exhausted, deferring "
                            f"{domain.domain_name} to next cycle: {record}"
                        )
                        be = bucket_err.setdefault(
                            tld_id, {"failed": 0, "sample": None, "skipped": 0}
                        )
                        be["skipped"] += 1
                    elif isinstance(record, BaseException):
                        logger.error(
                            f"DNS update failed for {domain.domain_name}: {record}"
                        )
                        be = bucket_err.setdefault(
                            tld_id, {"failed": 0, "sample": None, "skipped": 0}
                        )
                        be["failed"] += 1
                        if be["sample"] is None:
                            be["sample"] = str(record)[:200]
                        domain.health_status = "unhealthy"
                        self.db.add(domain)
                    else:
                        domain.current_ip = ip
                        domain.current_instance_id = instance.id if instance else None
                        rid = record.get("id") if record else None
                        if rid:
                            domain.dns_record_id = rid
                        domain.health_status = "healthy"
                        domain.last_health_check = datetime.now(timezone.utc).replace(
                            tzinfo=None
                        )
                        self.db.add(domain)
                        domains_updated += 1
                self.db.commit()

        dns_errors = [
            {
                "step": "dns",
                "tld_id": tld_id,
                "tld_domain": active[tld_id].domain,
                "provider": active[tld_id].dns_provider,
                "failed": v["failed"],
                "sample": v["sample"] or "",
                "skipped": v.get("skipped", 0),
            }
            for tld_id, v in bucket_err.items()
            if v["failed"] > 0
        ]
        return domains_updated, dns_errors

    async def _manage_domain_lifecycle(
        self, deployment: FdmDeployment, healthy_ips: List[str]
    ) -> None:
        """
        Manage domain lifecycle: mark unhealthy, cleanup stale, replenish pool.

        Rules:
        - Domains pointing to dead IPs are marked unhealthy
        - Unhealthy domains older than 30 minutes are deleted (name recycled)
        - If pool drops below target, create new domains on healthy IPs
        """
        from datetime import timedelta

        all_domains = (
            self.db.query(FdmDomain)
            .filter(FdmDomain.deployment_id == deployment.id)
            .all()
        )

        healthy_ip_set = set(healthy_ips)
        target_pool = self._spec_pool_target(deployment, len(healthy_ips))

        # Mark domains with dead IPs as unhealthy
        for domain in all_domains:
            if domain.health_status == "healthy" and domain.current_ip:
                if str(domain.current_ip) not in healthy_ip_set:
                    domain.health_status = "unhealthy"
                    logger.info(
                        f"Marked {domain.domain_name} unhealthy (IP {domain.current_ip} dead)"
                    )

        unhealthy_domains = [d for d in all_domains if d.health_status == "unhealthy"]

        # Delete stale unhealthy domains (30+ minutes old)
        stale_threshold = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            minutes=30
        )
        # Cap deletes per cycle. Each delete is a serial DNS-provider call
        # (_delete_dns_record_for_domain reads the shared DB session to resolve
        # the owning TLD, so it can't be safely gathered on one session); on a
        # degraded/slow provider an unbounded backlog of stale domains — e.g. a
        # region that just churned all its IPs — would make this loop dominate a
        # deployment's sync and blow the overlap-lock window. Bounding it lets the
        # cycle finish; the remainder is recycled over subsequent cycles.
        stale_domains = [
            d
            for d in unhealthy_domains
            if d.updated_at and d.updated_at < stale_threshold
        ]
        for domain in stale_domains[: self.STALE_DELETE_CAP]:
            logger.info(f"Deleting stale domain {domain.domain_name}")
            await self._delete_dns_record_for_domain(domain)
            self.db.delete(domain)

        self.db.commit()

        # Re-query after cleanup
        surviving_healthy = (
            self.db.query(FdmDomain)
            .filter(
                FdmDomain.deployment_id == deployment.id,
                FdmDomain.health_status == "healthy",
            )
            .count()
        )

        # Replenish pool if needed
        if surviving_healthy < target_pool:
            # Phase 4b.1: top up each active fdm TLD's HEALTHY pool to
            # target_pool (was: one global pool off base_domain). New rows
            # carry tld_id + tld.domain suffix + the seed IP. Under
            # single-active this is exactly today's behavior (one TLD;
            # base_domain == tld.domain; per-TLD healthy count == global
            # surviving_healthy). The NULL clause counts legacy tld_id=NULL
            # healthy rows toward the active TLD (mirrors the 4a read filter +
            # _ensure_domains_exist's count) so we top up rather than
            # over-create during the transition.
            seed_ip = healthy_ips[0] if healthy_ips else None
            for tld in self._active_fdm_tlds():
                tld_healthy = (
                    self.db.query(FdmDomain)
                    .filter(
                        FdmDomain.deployment_id == deployment.id,
                        (FdmDomain.tld_id == tld.id) | (FdmDomain.tld_id.is_(None)),
                        FdmDomain.health_status == "healthy",
                    )
                    .count()
                )
                if tld_healthy < target_pool:
                    created = self._create_domains_for_tld(
                        deployment,
                        tld,
                        target_pool - tld_healthy,
                        seed_ip=seed_ip,
                    )
                    if created:
                        logger.info(
                            f"Replenished {created} domains for "
                            f"{deployment.flux_app_name}/{deployment.region} "
                            f"tld={tld.domain}"
                        )

    async def _prune_inactive_deployment_domains(
        self,
        grace_minutes: int = 30,
        app_name: Optional[str] = None,
    ) -> int:
        """Global reaper: delete domains under DEACTIVATED deployments.

        grace_minutes=30 (default) protects a deployment that _detect_new_countries
        is about to reactivate in the same window. grace_minutes=0 is for
        operator-driven actions (toggle/delete via reconcile_app) where the
        deactivation is explicit and must take effect immediately.

        app_name scopes the reaper to one app's deployments (used by reconcile_app).
        A NULL updated_at (never refreshed) is treated as stale. User pins
        (AdminUser.assigned_domain_id) are cleared by the FK's ON DELETE SET NULL.
        """
        from datetime import timedelta

        stale_threshold = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            minutes=grace_minutes
        )
        q = (
            self.db.query(FdmDomain)
            .join(FdmDeployment, FdmDomain.deployment_id == FdmDeployment.id)
            .filter(FdmDeployment.is_active == False)
        )
        if app_name is not None:
            q = q.filter(FdmDeployment.flux_app_name == app_name)
        orphans = q.all()
        pruned = 0
        for domain in orphans:
            if (
                grace_minutes > 0
                and domain.updated_at is not None
                and domain.updated_at >= stale_threshold
            ):
                continue
            await self._delete_dns_record_for_domain(domain)
            self.db.delete(domain)
            pruned += 1
        if pruned:
            self.db.commit()
            logger.info(f"Pruned {pruned} domain(s) under inactive deployments")
        return pruned

    def _get_or_create_instance(
        self,
        deployment: FdmDeployment,
        ip: str,
        instance_number: int,
    ) -> Optional[ProtocolInstance]:
        """
        Get or create a ProtocolInstance row for an IP.

        Uses protocol_id=0 (the 'multi-protocol' sentinel from migration
        20260616_001) for protocol-agnostic deployments (NULL protocol_name).
        For named protocols, looks up the protocol_id via the protocol_map.

        Failure mode: returns None on exception. The caller (_update_dns_records_v2)
        still sets domain.current_ip but skips domain.current_instance_id. The
        next sync cycle's _ensure_pi_for_fdm_domains phase will retry creating
        the PI row, so the gap is self-healing rather than permanent.
        """
        from app.models.ip_management import ProtocolInstance as PI

        savepoint = self.db.begin_nested()
        try:
            # 1. Lookup by IP — if PI row exists for this IP, reuse it
            instance = (
                self.db.query(PI)
                .filter(PI.ip_address == ip, PI.is_active == True)
                .first()
            )
            if instance:
                return instance

            country_code, country_name, city = self._lookup_geoip(ip)
            protocol_id, component_name = self._resolve_protocol_id(deployment)

            # 2. Lookup by slot — if (flux_app_name, component_name, instance_number)
            # already exists, the IP rotated through this slot. Update the row's
            # IP + geo rather than failing on the UNIQUE constraint. The lookup
            # MUST NOT filter on is_active: uq_app_component_instance ignores
            # is_active, so an INACTIVE row squatting this slot (a deactivated
            # stale IP) would be missed here yet still collide on the INSERT
            # below. Reuse and REACTIVATE it instead.
            slot_instance = (
                self.db.query(PI)
                .filter(
                    PI.flux_app_name == deployment.flux_app_name,
                    PI.component_name == component_name,
                    PI.instance_number == instance_number,
                )
                .first()
            )
            if slot_instance:
                old_ip = slot_instance.ip_address
                was_inactive = not slot_instance.is_active
                slot_instance.ip_address = ip
                slot_instance.country_code = country_code
                slot_instance.country_name = country_name
                slot_instance.city = city
                slot_instance.health_status = "healthy"
                slot_instance.is_active = True
                self.db.flush()
                logger.info(
                    f"Updated PI slot ({deployment.flux_app_name}, {component_name}, "
                    f"{instance_number}) ip {old_ip} -> {ip} ({country_code})"
                    + (" [reactivated]" if was_inactive else "")
                )
                return slot_instance

            # 3. No existing IP or slot — insert new row
            new_instance = PI(
                protocol_id=protocol_id,
                flux_app_name=deployment.flux_app_name,
                component_name=component_name,
                instance_number=instance_number,
                ip_address=ip,
                country_code=country_code,
                country_name=country_name,
                city=city,
                health_status="healthy",
                is_active=True,
            )
            self.db.add(new_instance)
            self.db.flush()
            logger.info(
                f"Created ProtocolInstance: ip={ip} proto={component_name} "
                f"region={country_code} for {deployment.flux_app_name}"
            )
            return new_instance

        except Exception as e:
            savepoint.rollback()
            logger.error(
                f"PI creation failed for ip={ip} "
                f"flux_app_name={deployment.flux_app_name} "
                f"protocol_name={deployment.protocol_name!r}: {e}",
                exc_info=True,
            )
            return None
        finally:
            _release_savepoint(savepoint)

    @staticmethod
    def _lookup_geoip(ip: str) -> tuple:
        """Resolve IP to (country_code, country_name, city). Falls back to XX/Unknown/None."""
        import json as _json
        import urllib.request

        try:
            resp = urllib.request.urlopen(
                f"http://ip-api.com/json/{ip}?fields=countryCode,country,city",
                timeout=3,
            )
            geo = _json.loads(resp.read())
            return (
                geo.get("countryCode", "XX"),
                geo.get("country", "Unknown"),
                geo.get("city"),
            )
        except Exception as e:
            logger.warning(f"GeoIP failed for {ip}: {e}")
            return ("XX", "Unknown", None)

    @staticmethod
    def _resolve_protocol_id(deployment) -> tuple:
        """Map deployment.protocol_name to (protocol_id, component_name).

        Returns (0, 'multi-protocol') for protocol-agnostic deployments.
        """
        protocol_map = {
            "ssh": (1, "ssh"),
            "shadowsocks": (2, "shadowsocks"),
            "ss": (2, "shadowsocks"),
            "vless": (3, "vless"),
            "trojan": (4, "trojan"),
            "outline": (5, "outline"),
            "http_proxy": (6, "http-proxy"),
            "http-proxy": (6, "http-proxy"),
        }
        if deployment.protocol_name:
            proto_info = protocol_map.get(deployment.protocol_name)
            if proto_info:
                return proto_info
        return (0, "multi-protocol")

    @staticmethod
    def _extract_subdomain(domain_name: str) -> str:
        """
        Extract the subdomain part without the base domain.

        Args:
            domain_name: Full domain name (e.g., 'us-01-a1.operator6.example.invalid')

        Returns:
            Subdomain part (e.g., 'us-01-a1')

        Example:
            >>> FdmSyncService._extract_subdomain('us-01-a1.operator6.example.invalid')
            'us-01-a1'
        """
        parts = domain_name.split(".")
        if len(parts) >= 3:
            return parts[0]  # Just the first part: 'us-01-a1'
        return domain_name

    @staticmethod
    def _fdm_instance_number_for_ip(ip: str) -> int:
        """Deterministic instance_number for FDM-discovered IPs.

        Range 10000-99999 to avoid collision with real per-protocol instances
        (typically 1-50). Same IP always maps to same instance_number, so
        retries are idempotent.
        """
        import hashlib

        h = hashlib.md5(ip.encode()).hexdigest()
        return 10000 + (int(h, 16) % 90000)

    def _create_pi_row_for_ip(
        self, ip: str, country_code: str, country_name: str, city
    ) -> None:
        """Insert a PI row for an IP discovered via FDM. Uses multi-protocol sentinel."""
        from app.models.ip_management import ProtocolInstance as PI

        inst_no = self._fdm_instance_number_for_ip(ip)
        savepoint = self.db.begin_nested()
        try:
            existing = (
                self.db.query(PI)
                .filter(PI.ip_address == ip, PI.is_active == True)
                .first()
            )
            if existing:
                return

            # Reuse any row already occupying this deterministic slot. Like
            # _get_or_create_instance, the by-IP check filters is_active but
            # uq_app_component_instance does not — so an INACTIVE row squatting
            # (fdm-discovered, multi-protocol, hash(ip)) would collide on the
            # INSERT below. Reactivate it instead.
            slot = (
                self.db.query(PI)
                .filter(
                    PI.flux_app_name == "fdm-discovered",
                    PI.component_name == "multi-protocol",
                    PI.instance_number == inst_no,
                )
                .first()
            )
            if slot:
                slot.ip_address = ip
                slot.country_code = country_code
                slot.country_name = country_name
                slot.city = city
                slot.health_status = "healthy"
                slot.is_active = True
                self.db.flush()
                logger.info(
                    f"Reactivated fdm-discovered PI slot {inst_no} -> {ip} ({country_code})"
                )
                return

            new_instance = PI(
                protocol_id=0,  # multi-protocol sentinel
                flux_app_name="fdm-discovered",
                component_name="multi-protocol",
                instance_number=inst_no,
                ip_address=ip,
                country_code=country_code,
                country_name=country_name,
                city=city,
                health_status="healthy",
                is_active=True,
            )
            self.db.add(new_instance)
            self.db.flush()
            logger.info(f"Created PI row for {ip} via GeoIP ({country_code})")
        except Exception as e:
            savepoint.rollback()
            logger.warning(
                f"PI row creation failed for {ip}: {e}. "
                f"Will retry on next sync via _ensure_pi_for_fdm_domains phase."
            )
        finally:
            _release_savepoint(savepoint)

    async def _filter_ips_by_region(
        self, ips: List[str], region_code: str
    ) -> List[str]:
        """Filter IPs to only those in the specified region.

        Uses ProtocolInstance.country_code first, then falls back to
        ip-api.com GeoIP lookup for unknown IPs. Results are cached in
        ProtocolInstance for future syncs.

        Args:
            ips: List of IP addresses to filter
            region_code: ISO country code (e.g., 'CH', 'PL')

        Returns:
            IPs that are in the specified region
        """
        import aiohttp

        from app.models.ip_management import ProtocolInstance as PI

        matched = []
        unresolved = []

        for ip in ips:
            savepoint = self.db.begin_nested()
            try:
                instance = (
                    self.db.query(PI)
                    .filter(PI.ip_address == ip, PI.is_active == True)
                    .first()
                )
                if instance and instance.country_code:
                    if instance.country_code.upper() == region_code:
                        matched.append(ip)
                    elif instance.country_code.upper() == "XX":
                        unresolved.append(ip)
                else:
                    unresolved.append(ip)
            except Exception:
                savepoint.rollback()
                unresolved.append(ip)
            finally:
                _release_savepoint(savepoint)

        # Resolve unknown IPs via GeoIP. On match, create a PI row so future
        # syncs find it via the cached path (and connection-string JOIN works).
        if unresolved:
            async with aiohttp.ClientSession() as session:
                for ip in unresolved:
                    try:
                        result = await self._resolve_one_instance(session, _StubIP(ip))
                    except Exception as e:
                        logger.warning(f"GeoIP failed for {ip}: {e}")
                        continue
                    if result is None:
                        continue
                    code, country_name, city = result
                    if code == region_code:
                        matched.append(ip)
                        # Create PI row so future syncs find it cached.
                        self._create_pi_row_for_ip(ip, code, country_name, city)
                    logger.info(f"GeoIP: {ip} -> {code}")

        return matched

    async def _run_phase(self, name: str, coro_fn) -> None:
        """Run a sync phase in isolation. Logs outcome + swallows exceptions.

        A phase that throws is logged at ERROR level but does not propagate,
        so the main deployment sync loop still runs. This keeps the 10-min
        cycle productive even when one phase hits a transient failure.
        """
        try:
            await coro_fn()
        except Exception as e:
            # Roll back so a failed commit inside the phase can't leave the
            # session in a PendingRollbackError state that aborts the unguarded
            # `deployments = self.db.query(...)` following the pre-sync phases.
            self.db.rollback()
            logger.error(
                f"FDM sync phase '{name}' failed (continuing with rest of cycle): {e}",
                exc_info=True,
            )

    async def _sync_deployment_isolated(
        self,
        dep_id: int,
        dep_app: str,
        dep_region: str,
        semaphore: asyncio.Semaphore,
    ) -> Tuple[str, FdmSyncLog]:
        """Phase 4.6: sync ONE deployment on its own SessionLocal(), bounded
        by `semaphore`. Mirrors the SessionLocal()-per-task convention every
        Celery task in this codebase already uses (app/tasks/*.py) -- required
        because self.db is a synchronous SQLAlchemy Session, unsafe to share
        across concurrently-scheduled coroutines.

        `_discovery_cache`/`_spec_expected` are copied (not shared by
        reference) onto `scratch`, since sync_deployment() can write a
        cache-miss entry into either during the concurrent fan-out -- sharing
        the dict object would mean two concurrent tasks mutate the same dict.
        `_spec_gap_by_app` IS shared by reference: it is only ever written
        during the earlier sequential `_detect_spec_gap` phase and is
        read-only for the rest of the cycle.

        dep_app/dep_region are captured by the caller from the pre-fan-out
        query on self.db, so the results key is always available -- even on
        the missing-deployment path below, where the row can't be loaded to
        derive them from a fresh session.

        This method must NEVER raise: every failure -- from the deployment
        re-fetch, from sync_deployment() itself, or from this method's OWN
        failure-recovery code (rollback/commit/close each failing) -- is
        caught here and converted into a tagged failure FdmSyncLog. A raise
        from this method would propagate out of asyncio.gather() in
        sync_all_deployments() and abort the whole cycle's results for every
        OTHER concurrently-running deployment, defeating the entire point of
        per-deployment isolation.
        """
        key = f"{dep_app}:{dep_region}"

        def _failed_log(exc: Exception) -> FdmSyncLog:
            return FdmSyncLog(
                deployment_id=dep_id,
                sync_started_at=datetime.now(timezone.utc).replace(tzinfo=None),
                sync_completed_at=datetime.now(timezone.utc).replace(tzinfo=None),
                status="failed",
                errors=[{"error": str(exc), "type": type(exc).__name__}],
            )

        async with semaphore:
            db = None
            try:
                # expire_on_commit=False: this method returns sync_log (and
                # sync_all_deployments's caller reads .status off every
                # returned FdmSyncLog after this scratch session is closed
                # in the finally below). The default expire_on_commit=True
                # would mark every attribute for lazy-reload on the next
                # commit, which then raises DetachedInstanceError once the
                # session is closed -- confirmed live 2026-07-19: this
                # aborted every sync_all_deployments cycle via celery's
                # autoretry, growing backoff, though every individual
                # deployment's own sync work had already completed and
                # committed correctly (data was never at risk, only the
                # summary log line + the task-level retry loop).
                db = SessionLocal(expire_on_commit=False)
                scratch = FdmSyncService(db)
                scratch._discovery_cache = dict(self._discovery_cache)
                scratch._spec_expected = dict(self._spec_expected)
                scratch._spec_gap_by_app = self._spec_gap_by_app

                try:
                    deployment = (
                        db.query(FdmDeployment)
                        .filter(FdmDeployment.id == dep_id)
                        .first()
                    )
                    if deployment is None:
                        raise LookupError("deployment no longer exists")
                    sync_log = await scratch.sync_deployment(deployment)
                    return key, sync_log
                except Exception as e:
                    logger.exception(f"Failed to sync deployment {dep_app}: {e}")
                    try:
                        db.rollback()
                    except Exception:
                        logger.exception(
                            f"Failed to roll back scratch session for {dep_app}"
                        )
                    sync_log = _failed_log(e)
                    try:
                        db.add(sync_log)
                        db.commit()
                    except Exception:
                        logger.exception(f"Failed to persist failure log for {dep_app}")
                    return key, sync_log
            except Exception as e:
                # Backstop: something failed even in the failure-recovery path
                # above (e.g. scratch construction itself). Never let this
                # propagate -- always return a tagged failure.
                logger.exception(f"Unhandled error syncing deployment {dep_app}: {e}")
                return key, _failed_log(e)
            finally:
                if db is not None:
                    try:
                        db.close()
                    except Exception:
                        logger.exception(
                            f"Failed to close scratch session for {dep_app}"
                        )

    async def sync_all_deployments(self) -> Dict[str, FdmSyncLog]:
        """Sync all active FDM deployments.

        Queries all active FdmDeployment records and syncs each one.
        Before syncing, runs a region-splitting pass: for any app whose
        instances span multiple regions, automatically creates per-region
        deployments so the sync can filter IPs correctly.

        Note: Each deployment is synced independently with its own transaction.
        If one deployment fails, others may still succeed. Check individual
        FdmSyncLog.status for per-deployment results. This is intentional
        behavior as deployments are independent entities.

        Phase 4.3: guarded by a Redis overlap lock (see app.core.overlap_lock).
        If another sync is in progress, this cycle is skipped (returns {}).
        Fail-open if Redis is unavailable.

        Returns:
            Dictionary mapping 'flux_app_name:region' -> FdmSyncLog

        Raises:
            FdmSyncServiceError: If sync fails critically
        """
        async with overlap_lock("fdm:sync:lock") as acquired:
            if not acquired:
                logger.info(
                    "FDM sync_all_deployments skipped: another sync is in progress"
                )
                return {}
            # Phase 1-10: Pre-sync phases are individually wrapped so one phase
            # failure does not abort the cycle. Each phase logs its own outcome
            # or error. The main deployment sync loop runs regardless.
            await self._run_phase(
                "fetch_and_persist_app_specs", self._fetch_and_persist_app_specs
            )
            await self._run_phase("detect_spec_gap", self._detect_spec_gap)
            await self._run_phase("re_resolve_xx", self._re_resolve_xx_instances)
            await self._run_phase("auto_split_regions", self._auto_split_regions)
            await self._run_phase("detect_new_countries", self._detect_new_countries)
            await self._run_phase(
                "validate_domain_ips", self._validate_domain_ips_against_instances
            )
            await self._run_phase(
                "auto_deactivate_phantom", self._auto_deactivate_phantom_deployments
            )
            await self._run_phase(
                "reconcile_deployment_app_state", self._reconcile_deployment_app_state
            )
            await self._run_phase(
                "prune_inactive_deployment_domains",
                self._prune_inactive_deployment_domains,
            )
            await self._run_phase(
                "ensure_pi_for_fdm_domains", self._ensure_pi_for_fdm_domains
            )

            # Query all active deployments (now includes any newly split ones)
            deployments = (
                self.db.query(FdmDeployment)
                .filter(FdmDeployment.is_active == True)
                .all()
            )

            logger.info(f"Syncing {len(deployments)} active deployments")

            # Phase 4.6: pre-warm the discovery cache sequentially (no I/O race
            # possible) BEFORE any concurrent per-deployment task can start, so
            # the fan-out below is guaranteed 100% cache-hit for every
            # (app_name, port) pair it needs.
            await self._prewarm_discovery_cache(deployments)

            semaphore = asyncio.Semaphore(self.SYNC_CONCURRENCY)
            tasks = [
                self._sync_deployment_isolated(
                    d.id, d.flux_app_name, d.region, semaphore
                )
                for d in deployments
            ]
            pairs = await asyncio.gather(*tasks)
            results: Dict[str, FdmSyncLog] = dict(pairs)

            logger.info(
                f"Sync all deployments completed: "
                f"{len(results)} results, "
                f"{sum(1 for r in results.values() if r.status == 'success')} successful"
            )

            return results

    async def reconcile_app(self, app_name: str) -> dict:
        """Scoped, on-demand reconcile for ONE app (invoked by toggle/delete).

        Operator-driven, so NO 30-min grace (unlike the beat's prune phase):
        - app inactive / unregistered -> prune this app's domains + DNS NOW.
        - app active -> reactivate deployments, reset consecutive_failures,
          sync each deployment once.

        Idempotent: safe to call from both the beat-reaction and manually.
        """
        from app.models.flux_app_registration import FluxAppRegistration

        app = (
            self.db.query(FluxAppRegistration)
            .filter(FluxAppRegistration.app_name == app_name)
            .first()
        )
        app_active = bool(app and app.is_active)

        if not app_active:
            pruned = await self._prune_inactive_deployment_domains(
                grace_minutes=0,
                app_name=app_name,
            )
            return {"app_name": app_name, "active": False, "pruned": pruned}

        deployments = (
            self.db.query(FdmDeployment)
            .filter(FdmDeployment.flux_app_name == app_name)
            .all()
        )
        for dep in deployments:
            dep.is_active = True
            dep.consecutive_failures = 0
        self.db.commit()

        results: Dict[str, str] = {}
        for dep in deployments:
            key = f"{app_name}:{dep.region}"
            try:
                log = await self.sync_deployment(dep)
                # sync_deployment always sets sync_log.status (to "success",
                # "partial", or "failed") before returning -- every branch of
                # its try/except/finalize-tail assigns it; column is DB-nullable
                # but never actually None on a returned log.
                assert log.status is not None
                results[key] = log.status
            except Exception as e:
                self.db.rollback()
                logger.exception(f"reconcile_app sync failed for {key}: {e}")
                results[key] = "failed"
        return {"app_name": app_name, "active": True, "synced": results}

    async def _fetch_and_persist_app_specs(self) -> None:
        """Phase 3.3: refresh each active app's declared Flux spec and persist
        expected_instances + the snapshot, so downstream pool sizing (3.5) and
        gap detection (3.4) are spec-aware.

        One PUBLIC GET per app per cycle (cheap). On fetch failure, keep the
        last known expected_instances and mark last_spec_status='fetch_failed'
        so the gap phase knows the number may be stale. Populates the intra-cycle
        self._spec_expected cache consumed by pool sizing.
        """
        from datetime import datetime, timezone

        from app.models.flux_app_registration import FluxAppRegistration

        apps = (
            self.db.query(FluxAppRegistration)
            .filter(FluxAppRegistration.is_active == True)
            .all()
        )
        if not apps:
            return

        try:
            client = FluxCloudClient()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Spec fetch: FluxCloudClient unavailable: {e}")
            return

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            fetcher = FluxSpecFetcher(client)
            for app in apps:
                spec = await fetcher.fetch_spec(app.app_name)
                app.last_spec_fetched_at = now
                if spec is None:
                    app.last_spec_status = "fetch_failed"
                    logger.info(
                        f"Spec fetch failed for {app.app_name}; keeping last expected"
                    )
                    continue
                app.expected_instances = spec["instances"]
                app.spec_components = spec["components"]
                app.spec_geolocation = spec["geolocation"]
                app.last_spec_status = "ok"
                if spec["instances"] is not None:
                    self._spec_expected[app.app_name] = spec["instances"]
                else:
                    self._spec_expected.pop(app.app_name, None)
            self.db.commit()
        except Exception as e:  # noqa: BLE001
            self.db.rollback()
            logger.error(f"Spec fetch+persist phase failed: {e}", exc_info=True)
        finally:
            try:
                await client.close()
            except Exception:  # noqa: BLE001
                pass

    def _get_platform_setting(self, key: str) -> Optional[str]:
        from app.models.platform_settings import PlatformSetting

        row = self.db.query(PlatformSetting).filter(PlatformSetting.key == key).first()
        return row.value if row else None

    def _set_platform_setting(self, key: str, value: str) -> None:
        from app.models.platform_settings import PlatformSetting

        row = self.db.query(PlatformSetting).filter(PlatformSetting.key == key).first()
        if row is None:
            self.db.add(PlatformSetting(key=key, value=value))
        else:
            row.value = value
        self.db.flush()

    async def _get_cached_instances(
        self, app_name: str, port: int
    ) -> "_DiscoveryResult":
        """Phase 4.1: fetch + memoize app instances once per (app, port) per cycle.

        Returns a _DiscoveryResult distinguishing discovery-FAILURE (ok=False)
        from discovery-SUCCESS-with-zero-healthy (ok=True, healthy_ips=[]). The
        failure is cached too, so the N call sites per app per cycle (3.4-d) do
        not each re-fail during a Flux/provider outage.
        """
        key = (app_name, port)
        cached = self._discovery_cache.get(key)
        if cached is not None:
            return cached
        try:
            async with FluxDiscoveryService() as discovery:
                all_ips, healthy_ips = await discovery.get_app_instances(
                    app_name=app_name, port=port
                )
            result = _DiscoveryResult(
                all_ips=all_ips, healthy_ips=healthy_ips, ok=True, error=None
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Discovery failed for {app_name}:{port}: {e}")
            result = _DiscoveryResult(
                all_ips=[], healthy_ips=[], ok=False, error=str(e)
            )
        self._discovery_cache[key] = result
        return result

    async def _prewarm_discovery_cache(self, deployments: List[FdmDeployment]) -> None:
        """Phase 4.6: populate self._discovery_cache for every distinct
        (app_name, port) pair needed by `deployments`, sequentially, BEFORE
        any concurrent per-deployment sync starts.

        Guarantees the concurrent phase (added in Task 2) is 100% cache-hit:
        no two concurrent tasks can race to populate the same key, and Phase
        4.1's "once per (app,port) per cycle" guarantee holds regardless of
        concurrency.

        Phase 4.7c: sync_deployment's own discovery call (_discover_instances,
        called from this same class) passes deployment.health_check_port or
        443 as its protocol_port, matching this method's own key derivation
        exactly -- so every deployment prewarmed here is guaranteed a cache
        hit during the fan-out, regardless of its configured port.
        """
        pairs = {
            (dep.flux_app_name, dep.health_check_port or 443) for dep in deployments
        }
        for app_name, port in pairs:
            await self._get_cached_instances(app_name, port)

    async def _detect_spec_gap(self) -> None:
        """Phase 3.4: per active app with a known expected_instances, compare
        against discovered healthy IPs; record the gap and fire a de-duplicated
        superadmin alert after N consecutive short cycles.

        Option B (design literal) — the gap is queryable in TWO places:
          (1) PlatformSetting dedup state-machine:
                fdm:spec_gap:{app}:cycles        = consecutive short-cycle count (int str)
                fdm:spec_gap:{app}:last_alerted  = ISO timestamp (6h cooldown)
          (2) FdmSyncLog.errors: each active deployment of a gapped app gets a
                {"spec_gap": {"expected": E, "actual": A}} entry appended to its
                sync-log errors this cycle, via _inject_spec_gap_into_log in
                _sync_deployment (AFTER status computation, so a healthy sync of
                an under-provisioned app stays status="success").

        Mirrors the _alert_dns_dark_tlds cooldown pattern.
        """
        from datetime import datetime, timedelta, timezone

        from app.models.flux_app_registration import FluxAppRegistration
        from app.services.notifications.router import NotificationRouter

        self._spec_gap_by_app = {}  # fresh each cycle

        apps = (
            self.db.query(FluxAppRegistration)
            .filter(
                FluxAppRegistration.is_active == True,
                FluxAppRegistration.expected_instances.isnot(None),
            )
            .all()
        )
        if not apps:
            return

        router = NotificationRouter(self.db)
        now = datetime.now(timezone.utc)
        cooldown = timedelta(hours=self.SPEC_GAP_COOLDOWN_HOURS)

        for app in apps:
            expected = app.expected_instances or 0
            res = await self._get_cached_instances(app.app_name, 443)
            if not res.ok:
                # Discovery failed -> can't tell app-down from Flux-down. FREEZE
                # cycles (no increment, no reset) and skip. Kills 3.4-a false alerts.
                logger.info(
                    f"Spec gap: skipping {app.app_name} (discovery failed this cycle)"
                )
                continue
            actual = len(res.all_ips)
            key_cycles = f"fdm:spec_gap:{app.app_name}:cycles"
            key_alerted = f"fdm:spec_gap:{app.app_name}:last_alerted"

            if actual >= expected:
                self._set_platform_setting(key_cycles, "0")
                continue

            try:
                cycles = int(self._get_platform_setting(key_cycles) or 0) + 1
            except ValueError:
                logger.warning(
                    f"Spec gap: corrupt cycles value for {app.app_name}; resetting"
                )
                cycles = 1
            self._set_platform_setting(key_cycles, str(cycles))
            # Option B: record for per-deployment sync-log injection this cycle
            self._spec_gap_by_app[app.app_name] = {
                "expected": expected,
                "actual": actual,
            }

            if cycles < self.SPEC_GAP_THRESHOLD:
                continue
            last_alerted_raw = self._get_platform_setting(key_alerted)
            if last_alerted_raw:
                try:
                    if now - datetime.fromisoformat(last_alerted_raw) < cooldown:
                        continue  # cooled down
                except ValueError:
                    pass  # corrupt stamp -> fall through and re-alert
            msg = (
                f"FDM spec gap: app '{app.app_name}' has {actual}/{expected} "
                f"healthy instances for {cycles} consecutive cycles."
            )
            if router.send_to_super_admin(msg):
                self._set_platform_setting(key_alerted, now.isoformat())
        try:
            self.db.commit()
        except Exception as e:  # noqa: BLE001
            self.db.rollback()
            logger.warning(f"Spec gap phase commit failed: {e}")

    def _inject_spec_gap_into_log(self, deployment, sync_log) -> None:
        """Phase 3.4 Option B: append this deployment's owning-app spec gap to
        the sync-log errors array for DB-queryability (design §3.3). Called from
        _sync_deployment AFTER status is computed, so a healthy sync of an
        under-provisioned app stays status='success' — the gap is an app-level
        observation, not a per-deployment sync error. No-op when the app has no
        gap this cycle (e.g. the on-demand reconcile_app path)."""
        gap = self._spec_gap_by_app.get(
            getattr(deployment, "flux_app_name", None) or ""
        )
        if gap:
            sync_log.errors = list(sync_log.errors or []) + [{"spec_gap": gap}]

    async def _reconcile_deployment_app_state(self) -> None:
        """Deactivate active deployments whose FluxAppRegistration is missing or inactive.

        The beat syncs FdmDeployment rows filtered on is_active alone and never
        consults FluxAppRegistration.is_active, so a deployment under an app the
        operator toggled off (or that was deleted) would keep syncing + serving
        DNS until the 30-min prune grace caught it. This phase closes that gap
        each cycle: it marks such deployments inactive so (a) the main sync loop
        excludes them THIS cycle -- they stop refreshing their DNS A-records --
        and (b) the subsequent prune_inactive_deployment_domains phase reaps
        their DNS records within its grace window (~30 min on the beat path,
        where _run_phase invokes prune with the default grace_minutes=30;
        immediate on the operator-driven fdm.reconcile_app path, which calls
        prune with grace_minutes=0).
        (Operator toggle/delete ALSO trigger immediate scoped reconcile via
        fdm.reconcile_app; this is the belt-and-braces beat-side path.)
        """
        from app.models.flux_app_registration import FluxAppRegistration

        # Phase 4.7a: was 2 full-table loads (all active app names, all active
        # deployments) plus a Python-side list comprehension to find orphans.
        # active_app_names is still materialized as a real Python set (safe,
        # cheap -- just names, not full rows) so it can be passed directly to
        # a SQL NOT IN clause, letting the database do the orphan filtering
        # instead of iterating every active deployment in this process.
        active_app_names = {
            name
            for (name,) in (
                self.db.query(FluxAppRegistration.app_name)
                .filter(FluxAppRegistration.is_active == True)
                .all()
            )
        }

        orphaned = (
            self.db.query(FdmDeployment)
            .filter(
                FdmDeployment.is_active == True,
                FdmDeployment.flux_app_name.notin_(active_app_names),
            )
            .all()
        )
        for dep in orphaned:
            dep.is_active = False
            logger.info(
                f"Deactivating deployment {dep.flux_app_name}:{dep.region} "
                f"(app missing or inactive)"
            )
        if orphaned:
            self.db.commit()

    async def _auto_split_regions(self) -> None:
        """Detect multi-region apps and auto-create per-region deployments.

        For apps registered with region="XX" (placeholder), discovers their
        instances, determines each IP's region via GeoIP, and creates
        separate deployments per region with correct pool sizes. The original
        "XX" deployments are deactivated.
        """
        from app.models.flux_app_registration import FluxAppRegistration

        # Only enabled apps may acquire new serving regions.
        xx_deployments = (
            self.db.query(FdmDeployment)
            .join(
                FluxAppRegistration,
                FluxAppRegistration.app_name == FdmDeployment.flux_app_name,
            )
            .filter(
                FdmDeployment.region == "XX",
                FdmDeployment.is_active == True,
                FluxAppRegistration.is_active == True,
            )
            .all()
        )

        if not xx_deployments:
            return

        # Group by app name
        app_protocols: Dict[str, List[FdmDeployment]] = {}
        for dep in xx_deployments:
            app_protocols.setdefault(dep.flux_app_name, []).append(dep)

        for app_name, deployments in app_protocols.items():
            # Use the first deployment's port for discovery
            first_port = deployments[0].health_check_port or 443

            res = await self._get_cached_instances(app_name=app_name, port=first_port)
            if not res.ok:
                continue  # discovery failed this cycle; preserve skip semantics
            healthy_ips = await self._region_candidate_ips(app_name, res.all_ips)

            if not healthy_ips:
                continue

            # Determine region for each healthy IP
            ip_regions: Dict[str, List[str]] = {}  # region -> [ips]
            for ip in healthy_ips:
                region = await self._resolve_ip_region(ip)
                if region:
                    ip_regions.setdefault(region, []).append(ip)

            if len(ip_regions) <= 1:
                # Single region — rename the XX placeholder to that region,
                # UNLESS a per-region deployment already exists (e.g. one created
                # by _detect_new_countries). Renaming into an existing
                # (app, region) pair violates uq_deployment_app_region and aborts
                # the whole sync cycle, so on collision deactivate the XX
                # placeholder instead — exactly what the multi-region branch does.
                # Its dead domains get reaped by _prune_inactive_deployment_domains.
                single_region = list(ip_regions.keys())[0] if ip_regions else "XX"
                if single_region == "XX":
                    # Nothing resolved to a real region; leave placeholders as-is.
                    continue
                for dep in deployments:
                    existing = (
                        self.db.query(FdmDeployment)
                        .filter(
                            FdmDeployment.flux_app_name == app_name,
                            FdmDeployment.region == single_region,
                            FdmDeployment.id != dep.id,
                        )
                        .first()
                    )
                    if existing:
                        existing.domain_pool_size = len(healthy_ips)
                        existing.is_active = True
                        existing.consecutive_failures = 0
                        dep.is_active = False
                        logger.info(
                            f"Region split: {app_name} XX->{single_region} would "
                            f"collide with existing dep#{existing.id}; deactivated "
                            f"XX dep#{dep.id} instead"
                        )
                    else:
                        dep.region = single_region
                        dep.domain_pool_size = len(healthy_ips)
                self.db.commit()
                logger.info(
                    f"Region split: {app_name} is single-region ({single_region}), "
                    f"updated {len(deployments)} deployments"
                )
                continue

            # Multi-region: create per-region deployments, deactivate XX originals
            logger.info(
                f"Region split: {app_name} spans {len(ip_regions)} regions: "
                f"{list(ip_regions.keys())}"
            )

            for region, region_ips in ip_regions.items():
                # Check if per-region deployment already exists
                existing = (
                    self.db.query(FdmDeployment)
                    .filter(
                        FdmDeployment.flux_app_name == app_name,
                        FdmDeployment.region == region,
                    )
                    .first()
                )
                if existing:
                    existing.domain_pool_size = len(region_ips)
                    existing.is_active = True
                    existing.consecutive_failures = 0
                    continue

                # Create single protocol-agnostic deployment for this region
                base_domain = deployments[0].base_domain
                new_dep = FdmDeployment(
                    flux_app_name=app_name,
                    region=region,
                    base_domain=base_domain,
                    domain_pool_size=len(region_ips),
                    is_active=True,
                    last_sync_status="never",
                )
                self.db.add(new_dep)
                logger.info(
                    f"Region split: created {app_name}/{region} "
                    f"(pool={len(region_ips)})"
                )

            # Deactivate all original XX deployments
            for dep in deployments:
                dep.is_active = False

            self.db.commit()

    async def _resolve_ip_region(self, ip: str) -> Optional[str]:
        """Resolve an IP to its ISO country code (e.g., 'CH', 'PL')."""
        from app.models.ip_management import ProtocolInstance as PI

        # Try ProtocolInstance first
        savepoint = self.db.begin_nested()
        try:
            instance = (
                self.db.query(PI)
                .filter(PI.ip_address == ip, PI.is_active == True)
                .first()
            )
            if instance and instance.country_code:
                return instance.country_code.upper()
        except Exception:
            savepoint.rollback()
        finally:
            _release_savepoint(savepoint)

        # Fall back to GeoIP
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                url = f"http://ip-api.com/json/{ip}?fields=countryCode"
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=3)
                ) as resp:
                    data = await resp.json()
                    return data.get("countryCode", "").upper() or None
        except Exception as e:
            logger.warning(f"GeoIP lookup failed for {ip}: {e}")
            return None

    async def _re_resolve_xx_instances(self) -> int:
        """Re-resolve GeoIP for ProtocolInstances stuck with country_code='XX'.

        Queries all active instances with country_code='XX' and attempts
        ip-api.com lookup. Updates country_code, country_name, and city on success.

        Returns:
            Number of instances successfully resolved.
        """
        from app.models.ip_management import ProtocolInstance as PI

        xx_instances = (
            self.db.query(PI)
            .filter(PI.country_code == "XX", PI.is_active == True)
            .all()
        )

        if not xx_instances:
            return 0

        logger.info(f"Re-resolving GeoIP for {len(xx_instances)} XX instances")

        resolved_count = 0
        import aiohttp

        async with aiohttp.ClientSession() as session:
            for instance in xx_instances:
                result = await self._resolve_one_instance(session, instance)
                if result is None:
                    continue
                country_code, country_name, city = result
                savepoint = self.db.begin_nested()
                try:
                    instance.country_code = country_code
                    instance.country_name = country_name
                    if city:
                        instance.city = city
                    self.db.commit()
                    resolved_count += 1
                    logger.info(
                        f"Resolved XX instance: {instance.ip_address} -> "
                        f"{country_code} ({country_name})"
                    )
                except Exception as e:
                    savepoint.rollback()
                    logger.warning(
                        f"Failed to update instance {instance.ip_address}: {e}"
                    )

        logger.info(f"Re-resolved {resolved_count}/{len(xx_instances)} XX instances")
        return resolved_count

    async def _resolve_one_instance(
        self, session, instance
    ) -> Optional[Tuple[str, str, Optional[str]]]:
        """Resolve a single instance's GeoIP via ip-api.com.

        Returns:
            (country_code, country_name, city) tuple on success, None on failure.
        """
        import aiohttp

        url = (
            f"http://ip-api.com/json/{instance.ip_address}"
            f"?fields=countryCode,country,city"
        )
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 429:
                    logger.warning(f"ip-api.com rate limited for {instance.ip_address}")
                    return None
                data = await resp.json()
                code = data.get("countryCode", "").upper()
                if code:
                    return (
                        code,
                        data.get("country", "Unknown"),
                        data.get("city"),
                    )
        except Exception as e:
            logger.debug(f"GeoIP failed for {instance.ip_address}: {e}")
        return None

    async def _region_candidate_ips(
        self, app_name: str, all_ips: List[str]
    ) -> Optional[List[str]]:
        """Refresh endpoint evidence before creating/reactivating serving regions.

        Allocation alone cannot revive a region the liveness gate demoted.
        Refresh even when every deployment is inactive so recovery stays reachable.
        A gate failure freezes discovery's state changes; the serving sync retains
        its separate fail-open policy. A mass-outage fail-safe may preserve current
        serving, but is not evidence to restore previously demoted endpoints.
        """
        if not (settings.FDM_LIVENESS_ENABLED and all_ips):
            return all_ips

        from app.models.fdm_ip_liveness import FdmIpLiveness

        try:
            dead_ips = await LivenessGate(self.db).gate(app_name, all_ips)
            demoted_ips = {
                str(row[0])
                for row in self.db.query(FdmIpLiveness.ip_address)
                .filter(
                    FdmIpLiveness.flux_app_name == app_name,
                    FdmIpLiveness.ip_address.in_(all_ips),
                    FdmIpLiveness.demoted_at.isnot(None),
                )
                .all()
            }
            return [ip for ip in all_ips if ip not in dead_ips | demoted_ips]
        except Exception:
            self.db.rollback()
            logger.warning(
                "Region discovery: liveness unavailable for %s; preserving regions",
                app_name,
                exc_info=True,
            )
            return None

    async def _detect_new_countries(self) -> None:
        """Discover serving regions for enabled apps, including inactive deployments.

        Refresh app-scoped, any-port liveness before considering country changes.
        A recovered endpoint may reactivate its region and reset its failure streak;
        an allocated-but-demoted endpoint must not cause activation or pool churn.

        Uses all_ips as probe candidates, not discovery's single-port healthy_ips.
        Disabled/missing app registrations are excluded even if a deployment is
        still active. Inactive deployments remain discovery seeds so an app whose
        last region was deactivated can recover without operator intervention.
        """
        from app.models.flux_app_registration import FluxAppRegistration

        registered_deployments = (
            self.db.query(FdmDeployment)
            .join(
                FluxAppRegistration,
                FluxAppRegistration.app_name == FdmDeployment.flux_app_name,
            )
            .filter(FluxAppRegistration.is_active == True)
            .all()
        )

        app_protocols: Dict[str, List[FdmDeployment]] = {}
        for dep in registered_deployments:
            app_protocols.setdefault(dep.flux_app_name, []).append(dep)

        for app_name, deployments in app_protocols.items():
            ports = {d.health_check_port or 443 for d in deployments}
            first_port = min(ports) if ports else 443

            res = await self._get_cached_instances(app_name=app_name, port=first_port)
            if not res.ok:
                continue
            all_ips = await self._region_candidate_ips(app_name, res.all_ips)
            if not all_ips:
                continue

            ip_countries: Dict[str, str] = {}
            for ip in all_ips:
                region = await self._resolve_ip_region(ip)
                if region and region != "XX":
                    ip_countries[ip] = region

            countries_with_ips = set(ip_countries.values())
            if not countries_with_ips:
                continue

            existing_regions = {d.region.upper() for d in deployments}
            new_countries = countries_with_ips - existing_regions

            if new_countries:
                logger.info(
                    f"Country detection: {app_name} has new countries {new_countries} "
                    f"(existing: {existing_regions})"
                )

            for country in countries_with_ips:
                country_ips = [ip for ip, c in ip_countries.items() if c == country]
                pool_size = len(country_ips)

                existing = (
                    self.db.query(FdmDeployment)
                    .filter(
                        FdmDeployment.flux_app_name == app_name,
                        FdmDeployment.region == country,
                    )
                    .first()
                )
                if existing:
                    if existing.is_active and existing.consecutive_failures == 0:
                        continue
                    existing.domain_pool_size = max(
                        existing.domain_pool_size or 0, pool_size
                    )
                    existing.is_active = True
                    existing.consecutive_failures = 0
                    logger.info(
                        f"Country detection: updated existing {app_name}/{country} (pool={pool_size})"
                    )
                    continue

                base_domain = deployments[0].base_domain
                new_dep = FdmDeployment(
                    flux_app_name=app_name,
                    region=country,
                    base_domain=base_domain,
                    domain_pool_size=pool_size,
                    is_active=True,
                    last_sync_status="never",
                )
                self.db.add(new_dep)
                logger.info(
                    f"Country detection: created {app_name}/{country} "
                    f"(pool={pool_size}, IPs={country_ips})"
                )

            try:
                self.db.commit()
            except Exception as e:
                self.db.rollback()
                logger.warning(f"Country detection: commit failed for {app_name}: {e}")

    async def _auto_deactivate_phantom_deployments(self) -> int:
        """Deactivate deployments that have failed N consecutive syncs.

        A "phantom" deployment is one where Flux discovery consistently finds
        no instances in its region. Common cause: transient IPs from
        _detect_new_countries that later disappeared from Flux.

        Threshold: 3 consecutive failures (30 min at 10-min sync cadence).
        Safety: the consecutive_failures counter is only incremented when
        instances_found > 0 (guard in sync_deployment), so Flux API outages
        never reach the threshold.

        Deactivates (does NOT delete) so _detect_new_countries can reactivate
        if the region later gets instances again.

        Returns:
            Number of deployments deactivated.
        """
        PHANTOM_THRESHOLD = 3

        phantoms = (
            self.db.query(FdmDeployment)
            .filter(
                FdmDeployment.is_active == True,
                FdmDeployment.consecutive_failures >= PHANTOM_THRESHOLD,
            )
            .all()
        )

        if not phantoms:
            return 0

        for phantom in phantoms:
            phantom.is_active = False
            logger.warning(
                f"Auto-deactivated phantom deployment: "
                f"{phantom.flux_app_name}/{phantom.region} "
                f"(id={phantom.id}, consecutive_failures={phantom.consecutive_failures})"
            )

        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error(
                f"Auto-deactivation commit failed after deactivating "
                f"{len(phantoms)} deployments: {e}. "
                f"They will be re-attempted on the next sync cycle."
            )
            return 0
        return len(phantoms)

    async def _ensure_pi_for_fdm_domains(self) -> int:
        """Self-healing: backfill missing PI rows for healthy FDM domains.

        For each healthy FdmDomain with a current_ip, check whether an active
        ProtocolInstance row exists for that IP. If not, create one using
        _get_or_create_instance (which uses the multi-protocol sentinel for
        protocol-agnostic deployments).

        This phase runs every sync cycle so any PI gap self-corrects within
        10 minutes. Without it, a transient FK violation or DB outage would
        leave permanent gaps in the connection-string JOIN.

        Returns:
            Number of PI rows created.
        """
        from app.models.ip_management import ProtocolInstance as PI

        healthy_domains = (
            self.db.query(FdmDomain)
            .filter(
                FdmDomain.health_status == "healthy",
                FdmDomain.current_ip.isnot(None),
            )
            .all()
        )

        if not healthy_domains:
            return 0

        created_count = 0
        for domain in healthy_domains:
            ip_str = str(domain.current_ip)

            savepoint = self.db.begin_nested()
            try:
                existing = (
                    self.db.query(PI)
                    .filter(PI.ip_address == ip_str, PI.is_active == True)
                    .first()
                )
                if existing:
                    continue

                deployment = (
                    self.db.query(FdmDeployment)
                    .filter(FdmDeployment.id == domain.deployment_id)
                    .first()
                )
                if not deployment:
                    logger.warning(
                        f"PI backfill: domain {domain.domain_name} references "
                        f"missing deployment_id={domain.deployment_id}; skipping"
                    )
                    continue

                instance = self._get_or_create_instance(
                    deployment=deployment,
                    ip=ip_str,
                    instance_number=self._fdm_instance_number_for_ip(ip_str),
                )
                if instance:
                    created_count += 1
                    logger.info(
                        f"PI backfill: created instance for {domain.domain_name} "
                        f"-> {ip_str}"
                    )
            except Exception as e:
                savepoint.rollback()
                logger.warning(
                    f"PI backfill: failed for {domain.domain_name} "
                    f"(ip={ip_str}): {e}"
                )
                continue
            finally:
                _release_savepoint(savepoint)

        if created_count > 0:
            try:
                self.db.commit()
            except Exception as e:
                self.db.rollback()
                logger.error(
                    f"PI backfill commit failed after creating "
                    f"{created_count} rows: {e}"
                )
                return 0

        return created_count

    async def _validate_domain_ips_against_instances(self) -> int:
        """Mark unhealthy any healthy domain whose current_ip left Flux.

        For each healthy FdmDomain, retain its current_ip if its owning app
        has fresh, non-demoted FDM liveness evidence or an active row exists
        in protocol_instances. Otherwise mark it unhealthy so the next sync
        cycle rotates it to a fresh IP via _manage_domain_lifecycle.

        Skips:
        - Domains with NULL current_ip (nothing to validate)
        - Already-unhealthy domains (no double-processing)
        - App/IP pairs FDM's liveness gate probed within LIVENESS_FRESH_SECONDS
          and has not demoted. Apps on the same host have different ports, so
          another app's probe cannot vouch for this endpoint.
          flux.check_all_instances_health keeps
          deactivating live IPs' PI rows (FDM re-creates them seconds later),
          and trusting PI.is_active alone queued live domains for deletion
          (2026-10-24).

        Returns:
            Number of domains marked unhealthy.
        """
        from app.models.fdm_ip_liveness import FdmIpLiveness
        from app.models.ip_management import ProtocolInstance as PI

        healthy_domains = (
            self.db.query(FdmDomain)
            .filter(
                FdmDomain.health_status == "healthy",
                FdmDomain.current_ip.isnot(None),
            )
            .all()
        )

        if not healthy_domains:
            return 0

        fresh_since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            seconds=self.LIVENESS_FRESH_SECONDS
        )
        fdm_live_endpoints = {
            (row[0], str(row[1]))
            for row in self.db.query(
                FdmIpLiveness.flux_app_name, FdmIpLiveness.ip_address
            )
            .filter(
                FdmIpLiveness.last_checked_at >= fresh_since,
                FdmIpLiveness.demoted_at.is_(None),
            )
            .all()
        }

        marked_count = 0
        for domain in healthy_domains:
            ip_str = str(domain.current_ip)
            if (domain.deployment.flux_app_name, ip_str) in fdm_live_endpoints:
                continue

            savepoint = self.db.begin_nested()
            try:
                active_instance = (
                    self.db.query(PI)
                    .filter(
                        PI.ip_address == ip_str,
                        PI.is_active == True,
                    )
                    .first()
                )
            except Exception:
                savepoint.rollback()
                continue
            finally:
                _release_savepoint(savepoint)

            if not active_instance:
                domain.health_status = "unhealthy"
                logger.info(
                    f"Stale IP detected: {domain.domain_name} -> {ip_str} "
                    f"no longer in active protocol_instances; marking unhealthy"
                )
                marked_count += 1

        if marked_count > 0:
            try:
                self.db.commit()
            except Exception as e:
                self.db.rollback()
                logger.error(
                    f"Domain IP validation commit failed after marking "
                    f"{marked_count} domains unhealthy: {e}. "
                    f"They will be re-processed on the next sync cycle."
                )
                return 0

        return marked_count

    async def _rightsize_domain_pool(
        self, deployment: FdmDeployment, healthy_count: int
    ) -> int:
        """Shrink each active TLD's domain pool to _spec_pool_target(deployment, healthy_count),
        pruning the LEAST-loaded domains first within each TLD. Per-TLD
        (multi-active): a deployment's domains span N active fdm TLDs and each
        is sized independently. Legacy tld_id=NULL rows count toward an active
        TLD (mirrors _ensure_domains_exist's 4b.1 invariant).

        Growth is implicit via _ensure_domains_exist / _manage_domain_lifecycle
        top-ups. This method only shrinks.
        """
        target_size = self._spec_pool_target(deployment, healthy_count)
        total_pruned = 0
        # Bounded per cycle: a large shrink drains over several cycles instead
        # of bursting DNS deletes into the ArvanCloud rate limit.
        max_prune = settings.FDM_RIGHTSIZE_MAX_PRUNE_PER_CYCLE

        for tld in self._active_fdm_tlds():
            tld_domains = (
                self.db.query(FdmDomain)
                .filter(
                    FdmDomain.deployment_id == deployment.id,
                    (FdmDomain.tld_id == tld.id) | (FdmDomain.tld_id.is_(None)),
                )
                .all()
            )
            if len(tld_domains) <= target_size:
                continue
            tld_domains.sort(key=lambda d: getattr(d, "assigned_users_count", 0) or 0)
            excess = len(tld_domains) - target_size
            for domain in tld_domains[:excess]:
                if total_pruned >= max_prune:
                    break
                logger.info(
                    f"Pruning excess domain {domain.domain_name} "
                    f"(deployment {deployment.flux_app_name}/{deployment.region} "
                    f"tld={tld.domain}: {len(tld_domains)} -> {target_size})"
                )
                # Keep the row when the record may still exist (e.g. a
                # rate-limited ArvanCloud delete): deleting it anyway orphans
                # a record in a ~100-record zone. Retried next cycle.
                if not await self._delete_dns_record_for_domain(domain):
                    break
                self.db.delete(domain)
                total_pruned += 1

        if total_pruned:
            deployment.domain_pool_size = target_size
            try:
                self.db.commit()
            except Exception as e:
                self.db.rollback()
                logger.warning(f"Rightsize prune commit failed: {e}")
                return 0
        elif deployment.domain_pool_size != target_size:
            deployment.domain_pool_size = target_size
            try:
                self.db.commit()
            except Exception as e:
                self.db.rollback()
                logger.warning(f"Rightsize pool-size update commit failed: {e}")
                return 0
        return total_pruned

    async def _delete_dns_record_for_domain(self, domain: FdmDomain) -> bool:
        """Best-effort DNS A-record deletion for a domain about to be deleted.

        Resolves the DNS provider from the domain's OWN tld (domain.tld_id) —
        not whichever fdm TLD is currently active — so a record created under
        TLD-B is still deleted via TLD-B's provider after any single-active
        swap. Legacy rows with no tld_id fall back to the active fdm TLD.
        Swallows per-record errors with a warning so a single DNS API failure
        doesn't block DB cleanup.

        Returns True when the record is gone (deleted, already absent/404, or
        there was none), False when it may still exist. Callers that must not
        orphan records (_rightsize_domain_pool) keep the row on False.
        """
        if not domain.dns_record_id:
            return True  # No DNS record to clean up

        try:
            from app.models.registered_tld import RegisteredTld

            # Phase 4b.1: resolve the DNS provider from the domain's OWN tld
            # (domain.tld_id), NOT whichever fdm TLD is currently active.
            # A record created under TLD-B must be deleted via TLD-B's
            # provider; the old .first()-on-active picked the wrong provider
            # after any single-active swap (silent cross-provider no-op).
            tld = None
            if domain.tld_id:
                tld = self.db.get(RegisteredTld, domain.tld_id)
            if tld is None:
                # Legacy rows (tld_id NULL, pre-4a-backfill): fall back to the
                # active fdm TLD — preserves prior behavior for unmigrated rows.
                tld = (
                    self.db.query(RegisteredTld)
                    .filter(
                        RegisteredTld.purpose == "fdm",
                        RegisteredTld.is_active == True,
                    )
                    .first()
                )
            if not tld:
                logger.warning(
                    f"Cannot delete DNS record for {domain.domain_name}: "
                    f"no FDM TLD resolved (tld_id={domain.tld_id})"
                )
                return False

            client = create_dns_client(
                provider=tld.dns_provider,
                domain=tld.domain,
                zone_id=tld.zone_id,
            )
            async with client:
                await client.delete_dns_record(domain.dns_record_id)
            logger.info(
                f"Deleted DNS A-record {domain.dns_record_id} for {domain.domain_name}"
            )
            return True
        except Exception as e:
            if getattr(e, "status_code", None) == 404:
                return True  # already gone
            logger.warning(
                f"DNS A-record deletion failed for {domain.domain_name} "
                f"(record_id={domain.dns_record_id}): {e}."
            )
            return False

    def create_deployment(
        self,
        flux_app_name: str,
        region: Optional[str] = None,
        domain_pool_size: int = 5,
    ) -> FdmDeployment:
        """
        Create a new protocol-agnostic FDM deployment.

        Args:
            flux_app_name: Flux application name (e.g., 'fluxvpn-nl-01')
            region: Region code (auto-detected from app name if not provided)
            domain_pool_size: Number of domains to manage (default: 5)

        Returns:
            Created FdmDeployment

        Raises:
            FdmSyncServiceError: If creation fails
        """
        if region is None:
            region = self._detect_region_from_app_name(flux_app_name)

        existing = (
            self.db.query(FdmDeployment)
            .filter(
                FdmDeployment.flux_app_name == flux_app_name,
                FdmDeployment.region == region,
            )
            .first()
        )

        if existing:
            logger.warning(
                f"Deployment already exists for {flux_app_name}/{region}: {existing.id}"
            )
            return existing

        from app.models.registered_tld import RegisteredTld

        tld = (
            self.db.query(RegisteredTld)
            .filter(
                RegisteredTld.purpose == "fdm",
                RegisteredTld.is_active == True,
            )
            .first()
        )

        base_domain = (
            tld.domain
            if tld
            else getattr(settings, "CLOUDFLARE_DOMAIN", "operator3.example.invalid")
        )

        deployment = FdmDeployment(
            flux_app_name=flux_app_name,
            region=region,
            domain_pool_size=domain_pool_size,
            base_domain=base_domain,
            is_active=True,
            last_sync_status="never",
        )

        self.db.add(deployment)
        self.db.commit()
        self.db.refresh(deployment)

        logger.info(
            f"Created FDM deployment: {flux_app_name}"
            f" (id={deployment.id}, region={region}, pool_size={domain_pool_size})"
        )

        return deployment

    @staticmethod
    def _detect_region_from_app_name(flux_app_name: str) -> str:
        """
        Detect region code from Flux app name.

        Tries to parse region from naming patterns like 'fluxvpn-nl-01'.
        Falls back to 'XX' for arbitrary names (resolved on first sync).

        Args:
            flux_app_name: Flux app name (e.g., 'fluxvpn-nl-01')

        Returns:
            Region code (e.g., 'NL') or 'XX' if unknown

        Example:
            >>> FdmSyncService._detect_region_from_app_name('fluxvpn-nl-01')
            'NL'
        """
        from app.core.constants import COUNTRY_NAMES

        parts = flux_app_name.split("-")
        if len(parts) >= 3:
            candidate = parts[-2].upper()
            if candidate in COUNTRY_NAMES:
                return candidate
        if len(parts) == 2:
            candidate = parts[-1].upper()
            if candidate in COUNTRY_NAMES:
                return candidate
        return "XX"


def get_fdm_sync_service(db: Session) -> FdmSyncService:
    """
    Factory function for creating FdmSyncService instances.

    Args:
        db: SQLAlchemy database session

    Returns:
        FdmSyncService instance
    """
    return FdmSyncService(db)
