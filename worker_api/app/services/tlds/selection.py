"""TLD selection service — the single boundary for "which TLD does this admin use".

Least-active-user-count load balancing, sticky per admin until the pool changes,
self-healing on stale effective assignments. See spec §6.

Timestamps: ``assigned_at``/``updated_at`` are maintained by the model's
``onupdate=func.current_timestamp()`` (DB clock), so this service does NOT set
them manually — that keeps app/DB clocks from diverging and avoids the Py3.12
``datetime.utcnow()`` deprecation.
"""

import logging

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.admin_tld_state import AdminTldState
from app.models.admin_users import AdminUser
from app.models.registered_tld import RegisteredTld

logger = logging.getLogger(__name__)


class NoActiveTld(Exception):
    """Raised when no active (non-deleted) TLD exists for a purpose."""

    def __init__(self, purpose: str):
        super().__init__(f"No active TLD available for purpose={purpose}")
        self.purpose = purpose


class TldSelectionService:
    def __init__(self, db: Session):
        self.db = db

    def active_user_counts(self, purpose: str) -> dict[int, int]:
        """{tld_id: #active AdminUsers} whose admin's effective TLD (for this
        purpose) is that tld. The single query shared by LB and analytics."""
        rows = (
            self.db.query(
                AdminTldState.effective_tld_id,
                func.count(AdminUser.id),
            )
            .join(AdminUser, AdminUser.admin_id == AdminTldState.admin_id)
            .filter(
                AdminTldState.purpose == purpose,
                AdminUser.status == "active",
            )
            .group_by(AdminTldState.effective_tld_id)
            .all()
        )
        return {tld_id: count for tld_id, count in rows if tld_id is not None}

    def _healthy_fdm_tld_ids(self, tld_ids: list[int]) -> set[int]:
        """Subset of `tld_ids` having >=1 healthy FdmDomain. fdm-only concept.
        Single batched query (pool is tiny; tld_id is indexed)."""
        if not tld_ids:
            return set()
        from app.models.fdm import FdmDomain

        rows = (
            self.db.query(FdmDomain.tld_id)
            .filter(
                FdmDomain.tld_id.in_(tld_ids),
                FdmDomain.health_status == "healthy",
            )
            .distinct()
            .all()
        )
        return {r[0] for r in rows}

    def fdm_dns_health(self, tld_ids: list[int]) -> dict[int, dict]:
        """fdm-only per-TLD DNS health for the analytics snapshot (spec §4.3).
        Returns {tld_id: {healthy, total, all_dns_failed, last_error}}.
        Sources FdmDomain.health_status counts + the most recent dns error
        sample from fdm_sync_logs.errors (entries carry tld_id, set by the sync
        orchestrator in Task 3). Returns {} for an empty/None tld_ids list.

        NOTE: intentionally a separate, richer read from _healthy_fdm_tld_ids
        (the hot-path set query). This is the 60s-refresh analytics path."""
        if not tld_ids:
            return {}
        from app.models.fdm import FdmDomain, FdmSyncLog

        counts = (
            self.db.query(FdmDomain.tld_id, FdmDomain.health_status)
            .filter(FdmDomain.tld_id.in_(tld_ids))
            .all()
        )
        agg: dict[int, dict] = {tid: {"healthy": 0, "total": 0} for tid in tld_ids}
        for tid, hs in counts:
            agg.setdefault(tid, {"healthy": 0, "total": 0})
            agg[tid]["total"] += 1
            if hs == "healthy":
                agg[tid]["healthy"] += 1

        result: dict[int, dict] = {}
        for tid in tld_ids:
            a = agg.get(tid, {"healthy": 0, "total": 0})
            # most recent sync log whose errors JSONB contains this tld_id
            log = (
                self.db.query(FdmSyncLog)
                .filter(FdmSyncLog.errors.contains([{"tld_id": tid}]))
                .order_by(FdmSyncLog.created_at.desc())
                .first()
            )
            last_error = None
            if log and log.errors:
                for e in log.errors:
                    if (
                        isinstance(e, dict)
                        and e.get("tld_id") == tid
                        and e.get("sample")
                    ):
                        last_error = str(e["sample"])
                        break
            result[tid] = {
                "healthy_domains": a["healthy"],
                "total_domains": a["total"],
                "all_dns_failed": a["total"] > 0 and a["healthy"] == 0,
                "last_error": last_error,
            }
        return result

    def assign_via_lb(
        self, purpose: str, exclude_tld_id: int | None = None
    ) -> RegisteredTld:
        """Pick the least-loaded active TLD (tie-break by id). Raises NoActiveTld."""
        q = self.db.query(RegisteredTld).filter(
            RegisteredTld.purpose == purpose,
            RegisteredTld.is_active.is_(True),
            RegisteredTld.deleted_at.is_(None),
        )
        if exclude_tld_id is not None:
            q = q.filter(RegisteredTld.id != exclude_tld_id)
        pool = q.all()
        if not pool:
            raise NoActiveTld(purpose)
        # fdm-only health gate (spec §4.1): prefer TLDs with >=1 healthy
        # domain. If EVERY fdm TLD is dark, keep today's is_active pool
        # unchanged (do-no-harm floor). The all-dark alert is fired by the
        # sync orchestrator, not here, to avoid per-request spam.
        if purpose == "fdm":
            healthy_ids = self._healthy_fdm_tld_ids([t.id for t in pool])
            healthy_pool = [t for t in pool if t.id in healthy_ids]
            if healthy_pool:
                pool = healthy_pool
        counts = self.active_user_counts(purpose)
        return min(pool, key=lambda t: (counts.get(t.id, 0), t.id))

    def resolve_effective(self, admin_id: int, purpose: str) -> RegisteredTld:
        """Return the admin's current effective TLD. Lazy on first touch, sticky,
        and self-healing: a stale effective (deactivated/deleted TLD) re-LBs."""
        state = (
            self.db.query(AdminTldState)
            .filter(
                AdminTldState.admin_id == admin_id, AdminTldState.purpose == purpose
            )
            .first()
        )
        if state is None:
            return self._store_assignment(admin_id, purpose, pinned_tld_id=None)

        # Honor an active pin.
        if state.pinned_tld_id is not None:
            pinned = self.db.get(RegisteredTld, state.pinned_tld_id)
            if pinned and pinned.is_active and pinned.deleted_at is None:
                if state.effective_tld_id != pinned.id:
                    state.effective_tld_id = pinned.id
                    state.source = "pin"
                    self.db.flush()
                return pinned

        # Honor a still-valid stored effective (sticky).
        if state.effective_tld_id is not None:
            eff = self.db.get(RegisteredTld, state.effective_tld_id)
            if eff and eff.is_active and eff.deleted_at is None:
                return eff

        # Stale -> self-heal, preserving any pin.
        return self._store_assignment(
            admin_id,
            purpose,
            pinned_tld_id=state.pinned_tld_id,
            state=state,
        )

    def set_pin(self, admin_id: int, purpose: str, tld_id: int) -> AdminTldState:
        """Pin an admin to a specific TLD; effective becomes the pin."""
        tld = self.db.get(RegisteredTld, tld_id)
        if tld is None or tld.purpose != purpose or tld.deleted_at is not None:
            raise ValueError(f"TLD {tld_id} not valid for purpose={purpose}")
        # Never pin to an INACTIVE TLD. Provisioning (DNS A-record for
        # subscription/dashboard/admin_panel; FdmDomain rows + subdomain DNS for
        # fdm; and the Traefik router for HTTP purposes) happens only on
        # activate. Pinning to a registered-but-never-activated TLD routed
        # admins at a host with no DNS/route -> "reassignment sticks but the
        # domain doesn't work" (audit 2026-08-19). Reject for ALL purposes.
        if not tld.is_active:
            raise ValueError(
                f"TLD {tld.domain} is not active; activate it before pinning"
            )
        # fdm-only health guard (spec §4.1): never pin to a TLD with 0 healthy
        # domains — that routes users dark. Hard-reject (not warn) so a
        # superadmin must fix the DNS zone before pinning. Direct prevention of
        # the admin-9 -> #11 near-miss. Non-fdm purposes have no health concept.
        if purpose == "fdm" and tld_id not in self._healthy_fdm_tld_ids([tld_id]):
            raise ValueError(
                f"TLD {tld.domain} has 0 healthy domains; cannot pin — "
                f"fix its DNS zone first"
            )
        state = (
            self.db.query(AdminTldState)
            .filter(
                AdminTldState.admin_id == admin_id, AdminTldState.purpose == purpose
            )
            .first()
        )
        if state is None:
            state = AdminTldState(admin_id=admin_id, purpose=purpose)
            self.db.add(state)
        state.pinned_tld_id = tld_id
        state.effective_tld_id = tld_id
        state.source = "pin"
        self.db.flush()
        return state

    def clear_pin(self, admin_id: int, purpose: str) -> AdminTldState | None:
        """Remove the pin; effective recomputed via LB. No-op if no state row."""
        state = (
            self.db.query(AdminTldState)
            .filter(
                AdminTldState.admin_id == admin_id, AdminTldState.purpose == purpose
            )
            .first()
        )
        if state is None:
            return None
        state.pinned_tld_id = None
        chosen = self.assign_via_lb(purpose)
        state.effective_tld_id = chosen.id
        state.source = "lb"
        self.db.flush()
        return state

    def _store_assignment(
        self,
        admin_id: int,
        purpose: str,
        pinned_tld_id: int | None,
        state: AdminTldState | None = None,
    ) -> RegisteredTld:
        """Assign via LB and persist into AdminTldState (create or update).

        Race-safe on the create path: concurrent first-touch for the same
        (admin, purpose) hits ``uq_admin_tld_state_admin_purpose``. A loser
        insert is isolated by a SAVEPOINT (``begin_nested``) — the context
        manager rolls it back to the savepoint on ``IntegrityError``, leaving
        the outer transaction usable. We then re-query the winner's row and
        honor it. NOTE: do NOT call ``self.db.rollback()`` here — that rolls
        back the root transaction, not the savepoint, and would clobber rows
        the same transaction already wrote.
        """
        chosen = self.assign_via_lb(purpose)
        if state is None:
            state = AdminTldState(admin_id=admin_id, purpose=purpose)
            state.pinned_tld_id = pinned_tld_id
            state.effective_tld_id = chosen.id
            state.source = "pin" if pinned_tld_id == chosen.id else "lb"
            try:
                with self.db.begin_nested():  # SAVEPOINT isolates a loser insert
                    self.db.add(state)
                    self.db.flush()
            except IntegrityError:
                # Savepoint rolled back by the context manager; outer txn intact.
                existing = (
                    self.db.query(AdminTldState)
                    .filter(
                        AdminTldState.admin_id == admin_id,
                        AdminTldState.purpose == purpose,
                    )
                    .first()
                )
                if existing is not None:
                    # Winner's row is visible: honor its effective if still valid,
                    # else self-heal into the existing row via a fresh LB pick.
                    if existing.effective_tld_id is not None:
                        eff = self.db.get(RegisteredTld, existing.effective_tld_id)
                        if eff and eff.is_active and eff.deleted_at is None:
                            return eff
                    chosen = self.assign_via_lb(purpose)
                    existing.effective_tld_id = chosen.id
                    existing.source = "lb"
                    self.db.flush()
                    return chosen
                # Winner not visible yet (flush != commit): return a read-only
                # pick without persisting — stickiness is settled at commit time.
                return chosen
        else:
            state.pinned_tld_id = pinned_tld_id
            state.effective_tld_id = chosen.id
            state.source = "pin" if pinned_tld_id == chosen.id else "lb"
            self.db.flush()
        return chosen

    def migrate_off(
        self,
        tld_id: int,
        clear_pinned: bool = False,
    ) -> tuple[list[tuple[int, str, str | None, str]], list[tuple[int, str]]]:
        """Reassign every admin whose effective==tld_id to the least-loaded
        OTHER active TLD. Returns (affected, cleared_pins).

        clear_pinned=False (deactivate): pins preserved (spec D8).
        clear_pinned=True (delete): pins pointing at tld_id cleared + reported.

        Raises NoActiveTld if no other active TLD exists for an affected purpose;
        callers (the deactivate/delete endpoints, Phase 2) are expected to guard
        with a last-active check and to roll back the session on exception, since
        this method flushes once at the end and leaves no partial DB state.
        """
        old_tld = self.db.get(RegisteredTld, tld_id)
        old_domain = old_tld.domain if old_tld else None

        states = (
            self.db.query(AdminTldState)
            .filter(AdminTldState.effective_tld_id == tld_id)
            .all()
        )
        affected: list[tuple[int, str, str | None, str]] = []
        cleared_pins: list[tuple[int, str]] = []
        for state in states:
            if clear_pinned and state.pinned_tld_id == tld_id:
                state.pinned_tld_id = None
                cleared_pins.append((state.admin_id, state.purpose))
            chosen = self.assign_via_lb(state.purpose, exclude_tld_id=tld_id)
            state.effective_tld_id = chosen.id
            state.source = "lb"
            affected.append((state.admin_id, state.purpose, old_domain, chosen.domain))
        self.db.flush()
        return affected, cleared_pins
