"DNS sync regression: skip healthy, already-converged domains to preserve provider rate limits."
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import app.services.fdm.fdm_sync_service as _fdm

FdmSyncService = _fdm.FdmSyncService


def _run(coro):
    return asyncio.run(coro)


def _tld(id=10, domain="operator1.example.invalid", provider="arvancloud"):
    t = MagicMock()
    t.id = id
    t.domain = domain
    t.dns_provider = provider
    t.zone_id = domain
    return t


def _domain(
    tld_id=10, name="node-1.operator1.example.invalid", health="unknown", ip=None, rid=None
):
    d = MagicMock()
    d.tld_id = tld_id
    d.domain_name = name
    d.health_status = health
    d.current_ip = ip
    d.dns_record_id = rid
    return d


def _client():
    c = MagicMock()
    c.__aenter__ = AsyncMock(return_value=c)
    c.__aexit__ = AsyncMock(return_value=False)
    c.ensure_record_exists = AsyncMock(return_value={"id": "rec-new"})
    return c


def _service_with(client, tld):
    svc = FdmSyncService(MagicMock())
    svc._active_fdm_tlds = MagicMock(return_value=[tld])
    svc._get_or_create_instance = MagicMock(return_value=MagicMock(id=1))
    svc._extract_subdomain = MagicMock(side_effect=lambda n: n.split(".")[0])
    return svc


def test_converged_domain_is_not_rewritten():
    tld = _tld()
    converged = _domain(
        name="ok.operator1.example.invalid", health="healthy", ip="1.1.1.1", rid="rec-A"
    )
    stale = _domain(name="bad.operator1.example.invalid", health="unknown", ip=None, rid=None)
    client = _client()
    svc = _service_with(client, tld)

    with patch.object(_fdm, "create_dns_client", return_value=client):
        updated, errors = _run(
            svc._update_dns_records_v2(
                MagicMock(), [converged, stale], ["1.1.1.1", "2.2.2.2"]
            )
        )

    # Only the stale domain should hit the Arvan API; the converged one is skipped.
    assert client.ensure_record_exists.await_count == 1
    # Both still count toward "updated" so the deployment can reach success.
    assert updated == 2
    assert converged.health_status == "healthy"
    assert stale.health_status == "healthy"
    assert errors == []


def test_all_converged_makes_zero_api_calls():
    tld = _tld()
    domains = [
        _domain(
            name=f"n{i}.operator1.example.invalid", health="healthy", ip="1.1.1.1", rid=f"rec-{i}"
        )
        for i in range(5)
    ]
    client = _client()
    svc = _service_with(client, tld)

    with patch.object(_fdm, "create_dns_client", return_value=client):
        updated, errors = _run(
            svc._update_dns_records_v2(MagicMock(), domains, ["1.1.1.1"])
        )

    assert client.ensure_record_exists.await_count == 0
    assert updated == len(domains)  # steady state: all converged, zero budget spent
    assert errors == []


def test_healthy_but_pointing_at_dead_ip_is_rewritten():
    tld = _tld()
    # Healthy + has record id, but current_ip is no longer in the healthy set.
    moved = _domain(
        name="moved.operator1.example.invalid", health="healthy", ip="9.9.9.9", rid="rec-Z"
    )
    client = _client()
    svc = _service_with(client, tld)

    with patch.object(_fdm, "create_dns_client", return_value=client):
        updated, errors = _run(
            svc._update_dns_records_v2(MagicMock(), [moved], ["1.1.1.1"])
        )

    # Its IP dropped out of the healthy set -> must be re-pointed.
    assert client.ensure_record_exists.await_count == 1
    assert moved.current_ip == "1.1.1.1"
    assert updated == 1
