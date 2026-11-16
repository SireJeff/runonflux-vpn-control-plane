"""Regression guard for the 2026-08-19 TLD-domain audit.

The subscription/dashboard/admin_panel TLD activation + delete paths call the
DNS clients with the FULL apex domain as ``name`` (``tld.domain``), whereas FDM
calls pass a bare subdomain label. Both clients previously assumed a bare label
and mangled the apex:

- Cloudflare's ``list_dns_records`` built the filter as ``f"{name}.{domain}"``,
  yielding ``"example.com.example.com"`` at the apex -> matches nothing ->
  ``find_a_record_by_name`` misses the record -> re-activate ("already exists"
  self-heal) and delete silently fail to update/remove the live A-record.
- ArvanCloud returns record names ZONE-STRIPPED ("@" for the apex), but
  ``find_a_record_by_name`` compared against the raw full domain -> never
  matched the apex -> same orphaned-record bug.

These tests pin the fixed name normalization. Pure unit — no DB, no network.
"""
import asyncio
from unittest.mock import AsyncMock

from app.services.fdm.arvancloud_client import ArvanCloudDnsClient
from app.services.fdm.cloudflare_client import CloudflareDnsClient


# --- Cloudflare _fqdn (list filter normalization) ---------------------------


def _cf():
    return CloudflareDnsClient(api_token="t", zone_id="z", domain="example.com")


def test_cf_fqdn_qualifies_bare_subdomain_label():
    # FDM path: bare label must be qualified with the zone.
    assert _cf()._fqdn("us-01-a1") == "us-01-a1.example.com"


def test_cf_fqdn_leaves_apex_domain_unchanged():
    # subscription/dashboard/admin_panel path: full apex must NOT double-append.
    assert _cf()._fqdn("example.com") == "example.com"


def test_cf_fqdn_leaves_existing_subdomain_fqdn_unchanged():
    assert _cf()._fqdn("cdn.example.com") == "cdn.example.com"


# --- ArvanCloud find_a_record_by_name (zone-stripped comparison) ------------


def _arvan():
    return ArvanCloudDnsClient(api_key="k", domain="example.com")


def test_arvan_finds_apex_record_by_full_domain():
    """Caller passes the full apex domain; Arvan returns it as "@". Must match."""
    client = _arvan()
    client.list_dns_records = AsyncMock(
        return_value={"result": [{"id": "apex-id", "name": "@", "content": "1.2.3.4"}]}
    )

    found = asyncio.run(client.find_a_record_by_name("example.com"))

    assert found is not None and found["id"] == "apex-id"
    # apex scan must NOT pass "@" as a substring search term
    client.list_dns_records.assert_awaited_once()
    assert client.list_dns_records.await_args.kwargs.get("name") is None


def test_arvan_finds_subdomain_record_by_full_fqdn():
    client = _arvan()
    client.list_dns_records = AsyncMock(
        return_value={"result": [{"id": "sub-id", "name": "cdn", "content": "1.2.3.4"}]}
    )

    found = asyncio.run(client.find_a_record_by_name("cdn.example.com"))

    assert found is not None and found["id"] == "sub-id"
    assert client.list_dns_records.await_args.kwargs.get("name") == "cdn"


def test_arvan_returns_none_when_apex_absent():
    client = _arvan()
    client.list_dns_records = AsyncMock(
        return_value={"result": [{"id": "other", "name": "www", "content": "1.2.3.4"}]}
    )
    assert asyncio.run(client.find_a_record_by_name("example.com")) is None
